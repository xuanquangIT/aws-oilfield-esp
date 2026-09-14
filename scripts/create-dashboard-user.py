"""Create one invite-only dashboard account; email delivery is opt-in."""

from __future__ import annotations

import argparse
import os

import boto3


def pool_id(cfn, stack: str) -> str:
    for item in cfn.describe_stacks(StackName=stack)["Stacks"][0].get("Outputs", []):
        if item["OutputKey"] == "CognitoUserPoolId":
            return item["OutputValue"]
    raise RuntimeError("CognitoUserPoolId output not found")


def main() -> None:
    parser = argparse.ArgumentParser(description="Invite an administrator-approved email address to the dashboard.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--send-invite", action="store_true", help="Send Cognito's temporary-password email. Without this flag no external email is sent.")
    parser.add_argument("--stack", default="oilfield-esp-dashboard-hosted")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1")
    args = parser.parse_args()
    session = boto3.Session(region_name=args.region)
    cfn, cognito = session.client("cloudformation"), session.client("cognito-idp")
    request = {
        "UserPoolId": pool_id(cfn, args.stack), "Username": args.email,
        "UserAttributes": [{"Name": "email", "Value": args.email}, {"Name": "email_verified", "Value": "true"}],
    }
    if args.send_invite:
        request["DesiredDeliveryMediums"] = ["EMAIL"]
    else:
        request["MessageAction"] = "SUPPRESS"
    response = cognito.admin_create_user(**request)
    print(f"Created dashboard user {response['User']['Username']}. Invite email sent: {args.send_invite}")


if __name__ == "__main__":
    main()
