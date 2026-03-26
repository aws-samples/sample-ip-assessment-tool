"""Account discovery module for the IP Assessment Tool.

Queries AWS Organizations to discover all active accounts, including the
management account, and excludes suspended accounts with warnings.
"""

import logging

from ip_assessment_tool.models import AccountInfo, AccountStatus

logger = logging.getLogger(__name__)


def discover_accounts(org_client) -> list[AccountInfo]:
    """Return all active accounts in the Organization, including the management account.

    Suspended accounts are excluded and logged as warnings.

    Args:
        org_client: A boto3 Organizations client.

    Returns:
        A list of AccountInfo for all active accounts.
    """
    # Get the management account ID
    org_response = org_client.describe_organization()
    management_account_id = org_response["Organization"]["MasterAccountId"]

    # Paginate through all accounts
    paginator = org_client.get_paginator("list_accounts")
    accounts: list[AccountInfo] = []

    for page in paginator.paginate():
        for account in page["Accounts"]:
            status = AccountStatus(account["Status"])

            if status == AccountStatus.SUSPENDED:
                logger.warning(
                    "Excluding suspended account: %s (%s)",
                    account["Id"],
                    account.get("Name", "Unknown"),
                )
                continue

            accounts.append(
                AccountInfo(
                    account_id=account["Id"],
                    account_name=account.get("Name", ""),
                    status=status,
                    is_management=(account["Id"] == management_account_id),
                )
            )

    logger.info("Discovered %d active account(s)", len(accounts))
    return accounts
