"""Low-idle-cost hosted dashboard, intentionally separate from CoreStack."""

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_authorizers as authorizers
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct


class DashboardHostedStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, project_prefix: str, core, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        for key, value in {"Project": project_prefix, "Environment": "portfolio", "Lifecycle": "dashboard", "CostCenter": "demo"}.items():
            Tags.of(self).add(key, value)

        site_bucket = s3.Bucket(
            self, "SiteBucket", block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=True,
        )
        user_pool = cognito.UserPool(
            self, "UserPool", self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            password_policy=cognito.PasswordPolicy(min_length=14, require_digits=True, require_lowercase=True, require_uppercase=True, require_symbols=True, temp_password_validity=Duration.days(3)),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(otp=True, sms=False),
            removal_policy=RemovalPolicy.DESTROY,
        )
        user_pool_client = user_pool.add_client(
            "BrowserClient", generate_secret=False,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL],
                callback_urls=["https://example.invalid/dashboard-login-unconfigured"],
                logout_urls=["https://example.invalid/dashboard-logout-unconfigured"],
            ),
            prevent_user_existence_errors=True,
            auth_session_validity=Duration.minutes(3),
            refresh_token_validity=Duration.hours(8),
        )
        domain = user_pool.add_domain("ManagedLogin", cognito_domain=cognito.CognitoDomainOptions(domain_prefix=f"{project_prefix}-dashboard-{self.account}"))
        issuer = f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}"
        api_handler = lambda_.Function(
            self, "ReadApi", runtime=lambda_.Runtime.PYTHON_3_12, handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("src/dashboard_api"), timeout=Duration.seconds(10), memory_size=256,
            tracing=lambda_.Tracing.PASS_THROUGH, log_retention=logs.RetentionDays.THREE_DAYS,
            environment={"STATE_TABLE": core.state_table.table_name, "DATA_BUCKET": core.data_bucket.bucket_name, "CACHE_TTL_SECONDS": "15", "COGNITO_ISSUER": issuer, "COGNITO_CLIENT_ID": user_pool_client.user_pool_client_id, "COGNITO_DOMAIN": f"https://{domain.domain_name}"},
        )
        api_handler.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:BatchGetItem"], resources=[core.state_table.table_arn]))
        api_handler.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[
            core.data_bucket.arn_for_objects("curated/publication/current.json"),
            core.data_bucket.arn_for_objects("curated/publication/runs/*/kpi-summary.json"),
            core.data_bucket.arn_for_objects("staging/m3/*/quality-report.json"),
        ]))
        api = apigwv2.HttpApi(self, "HttpApi", create_default_stage=True)
        jwt = authorizers.HttpJwtAuthorizer("DashboardJwt", jwt_issuer=issuer, jwt_audience=[user_pool_client.user_pool_client_id])
        integration = integrations.HttpLambdaIntegration("ReadIntegration", api_handler)
        api.add_routes(path="/api/v1/config", methods=[apigwv2.HttpMethod.GET], integration=integration)
        for path in ["/api/v1/pumps", "/api/v1/pumps/{esp_id}", "/api/v1/kpis/latest", "/api/v1/health"]:
            api.add_routes(path=path, methods=[apigwv2.HttpMethod.GET], integration=integration, authorizer=jwt)
        api_domain = f"{api.api_id}.execute-api.{self.region}.amazonaws.com"
        distribution = cloudfront.Distribution(
            self, "Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
            ),
            additional_behaviors={"/api/*": cloudfront.BehaviorOptions(
                origin=origins.HttpOrigin(api_domain), viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL, cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
            )},
            default_root_object="index.html", minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            enable_logging=False,
        )
        s3deploy.BucketDeployment(self, "DeploySite", sources=[s3deploy.Source.asset("dashboard/static")], destination_bucket=site_bucket, distribution=distribution, distribution_paths=["/*"], prune=True)
        # GitHub has no long-lived AWS credential. The trust is pinned to one
        # repository *and* to its protected GitHub Environment. CDK bootstrap
        # roles perform asset publishing/deployment after this narrow entry role
        # is assumed; see docs for the required environment protection rule.
        github_provider = iam.OpenIdConnectProvider(
            self, "GitHubActionsOidc", url="https://token.actions.githubusercontent.com",
            client_ids=["sts.amazonaws.com"],
        )
        github_deploy_role = iam.Role(
            self, "GitHubDeployRole",
            assumed_by=iam.WebIdentityPrincipal(
                github_provider.open_id_connect_provider_arn,
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                        # GitHub's current OIDC subject includes immutable
                        # owner/repository IDs as well as their readable names.
                        "token.actions.githubusercontent.com:sub": "repo:xuanquangIT@80450825/aws-oilfield-esp@1358796241:environment:dashboard-production",
                    }
                },
            ),
            max_session_duration=Duration.hours(1),
            description="GitHub Actions OIDC entry role for the protected dashboard deployment environment.",
        )
        bootstrap_roles = [
            f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-deploy-role-{self.account}-{self.region}",
            f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-file-publishing-role-{self.account}-{self.region}",
            f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-image-publishing-role-{self.account}-{self.region}",
            f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-lookup-role-{self.account}-{self.region}",
        ]
        github_deploy_role.add_to_policy(iam.PolicyStatement(actions=["sts:AssumeRole"], resources=bootstrap_roles))
        # Post-deploy OAuth redirect reconciliation needs only these two
        # reads/writes; CDK deployment itself still flows through bootstrap.
        github_deploy_role.add_to_policy(iam.PolicyStatement(
            actions=["cloudformation:DescribeStacks"],
            resources=[f"arn:aws:cloudformation:{self.region}:{self.account}:stack/{construct_id}/*"],
        ))
        github_deploy_role.add_to_policy(iam.PolicyStatement(
            actions=["cognito-idp:DescribeUserPoolClient", "cognito-idp:UpdateUserPoolClient"],
            resources=[user_pool.user_pool_arn],
        ))
        CfnOutput(self, "DashboardUrl", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "CloudFrontDistributionId", value=distribution.distribution_id)
        CfnOutput(self, "CognitoUserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "CognitoUserPoolClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, "CognitoDomain", value=f"https://{domain.domain_name}")
        CfnOutput(self, "DashboardApiUrl", value=api.api_endpoint)
        CfnOutput(self, "GitHubDashboardDeployRoleArn", value=github_deploy_role.role_arn)
