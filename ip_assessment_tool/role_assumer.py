"""Role assumer module for the IP Assessment Tool.

Assumes cross-account IAM roles via AWS STS to obtain temporary credentials
for querying resources in member accounts.

Security considerations:
- Uses only temporary STS credentials (max 1-hour session) for cross-account access.
- Never logs or exposes credential values (AccessKeyId, SecretAccessKey, SessionToken).
- Relies on the default AWS credential chain for the initial STS client.
- No credentials are hardcoded in source code.
"""

import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

SESSION_NAME = "IPAssessmentTool"
MAX_SESSION_DURATION = 3600


class RoleAssumer:
    """Assumes cross-account roles via STS and returns boto3 Sessions."""

    def __init__(self, role_name: str, session_duration: int = 3600):
        self.role_name = role_name
        self.session_duration = min(session_duration, MAX_SESSION_DURATION)
        self._sts_client = boto3.client("sts")

    def assume_role(self, account_id: str) -> boto3.Session | None:
        """Assume role into account.

        Returns a boto3 Session with temporary credentials, or None on failure.

        Args:
            account_id: The AWS account ID to assume into.

        Returns:
            A boto3.Session configured with temporary credentials, or None.
        """
        role_arn = f"arn:aws:iam::{account_id}:role/{self.role_name}"

        try:
            response = self._sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=SESSION_NAME,
                DurationSeconds=self.session_duration,
            )
            credentials = response["Credentials"]
            return boto3.Session(
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            )
        except (ClientError, Exception) as exc:
            logger.error(
                "Failed to assume role %s in account %s: %s",
                role_arn,
                account_id,
                exc,
            )
            return None

    def refresh_credentials(self, account_id: str) -> boto3.Session | None:
        """Re-assume role to get fresh credentials if current ones are expired.

        Args:
            account_id: The AWS account ID to re-assume into.

        Returns:
            A boto3.Session configured with fresh temporary credentials, or None.
        """
        return self.assume_role(account_id)
