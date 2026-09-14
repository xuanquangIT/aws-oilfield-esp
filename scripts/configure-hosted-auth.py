"""Set the deployed CloudFront URL as Cognito OAuth callback/logout URL.

This runs after each CDK deploy because CloudFront and Cognito have an
intentional dependency cycle. It preserves all generated user-pool-client
settings and changes only callback/logout URIs.
"""

from __future__ import annotations

import argparse
import os

import boto3


def output(cfn, stack: str, key: str) -> str:
    values = {item["OutputKey"]: item["OutputValue"] for item in cfn.describe_stacks(StackName=stack)["Stacks"][0].get("Outputs", [])}
    value = values.get(key)
    if not value:
        raise RuntimeError(f"Missing CloudFormation output {key}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure Cognito managed-login redirects for the hosted dashboard.")
    parser.add_argument("--stack", default="oilfield-esp-dashboard-hosted")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1")
    args = parser.parse_args()
    session = boto3.Session(region_name=args.region)
    cfn, cognito = session.client("cloudformation"), session.client("cognito-idp")
    pool_id, client_id = output(cfn, args.stack, "CognitoUserPoolId"), output(cfn, args.stack, "CognitoUserPoolClientId")
    dashboard_url = output(cfn, args.stack, "DashboardUrl").rstrip("/")
    client = cognito.describe_user_pool_client(UserPoolId=pool_id, ClientId=client_id)["UserPoolClient"]
    update = {
        "UserPoolId": pool_id, "ClientId": client_id,
        "CallbackURLs": [dashboard_url + "/"], "LogoutURLs": [dashboard_url + "/"],
        "AllowedOAuthFlows": client.get("AllowedOAuthFlows", []),
        "AllowedOAuthScopes": client.get("AllowedOAuthScopes", []),
        "AllowedOAuthFlowsUserPoolClient": client.get("AllowedOAuthFlowsUserPoolClient", False),
        "SupportedIdentityProviders": client.get("SupportedIdentityProviders", ["COGNITO"]),
        "PreventUserExistenceErrors": client.get("PreventUserExistenceErrors", "ENABLED"),
        "EnableTokenRevocation": client.get("EnableTokenRevocation", True),
        "EnablePropagateAdditionalUserContextData": client.get("EnablePropagateAdditionalUserContextData", False),
        "RefreshTokenValidity": client.get("RefreshTokenValidity", 1),
        "AccessTokenValidity": client.get("AccessTokenValidity", 1),
        "IdTokenValidity": client.get("IdTokenValidity", 1),
        "TokenValidityUnits": client.get("TokenValidityUnits", {}),
        "AuthSessionValidity": client.get("AuthSessionValidity", 3),
    }
    cognito.update_user_pool_client(**update)
    print(f"Configured Cognito redirects for {dashboard_url}")


if __name__ == "__main__":
    main()
