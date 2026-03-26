"""Orchestrator module coordinating the full IP assessment pipeline.

Discovers accounts, assumes roles, scans regions, collects data,
aggregates results, and generates reports.
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3

from ip_assessment_tool.aggregator import aggregate_results
from ip_assessment_tool.discovery import discover_accounts
from ip_assessment_tool.models import AccountResult, ErrorRecord, Report
from ip_assessment_tool.region_scanner import get_enabled_regions, scan_regions
from ip_assessment_tool.report_generator import write_csv_report, write_eip_detail_csv, write_eni_detail_csv, write_html_report, write_json_report
from ip_assessment_tool.role_assumer import RoleAssumer

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates the end-to-end IP assessment pipeline."""

    def __init__(
        self,
        role_name: str,
        output_dir: str,
        output_format: str,
        account_filter: list[str] | None = None,
    ):
        self.role_name = role_name
        self.output_dir = Path(output_dir)
        self.output_format = output_format
        self.account_filter = account_filter

    def run(self) -> Report:
        """Execute full assessment pipeline. Returns the consolidated Report."""
        # Step 1: Discover accounts via Organizations API
        org_client = boto3.client("organizations")
        accounts = discover_accounts(org_client)

        # Step 2: Apply account filter if provided
        if self.account_filter:
            accounts = [a for a in accounts if a.account_id in self.account_filter]

        total_accounts = len(accounts)
        print(
            f"Discovered {total_accounts} account(s) to scan.",
            file=sys.stderr,
        )
        logger.info("Discovered %d account(s) to scan", total_accounts)

        # Step 3: Process each account with fail-forward
        role_assumer = RoleAssumer(role_name=self.role_name)
        account_results: list[AccountResult] = []
        all_errors: list[ErrorRecord] = []

        for idx, account in enumerate(accounts, start=1):
            try:
                result, errors = self._process_account(
                    role_assumer, account.account_id, account.account_name
                )
                account_results.append(result)
                all_errors.extend(errors)
            except Exception as exc:
                logger.error(
                    "Unrecoverable error processing account %s: %s",
                    account.account_id,
                    exc,
                )
                error = ErrorRecord(
                    account_id=account.account_id,
                    error_message=f"Unrecoverable error: {exc}",
                )
                all_errors.append(error)
                account_results.append(
                    AccountResult(
                        account_id=account.account_id,
                        account_name=account.account_name,
                        errors=[str(exc)],
                    )
                )

            print(
                f"Processed {idx} of {total_accounts} accounts.",
                file=sys.stderr,
            )
            logger.info("Processed %d of %d accounts", idx, total_accounts)

        # Step 4: Aggregate results into a Report
        timestamp = datetime.now(timezone.utc)
        report = aggregate_results(account_results, all_errors, timestamp)

        # Step 5: Write reports based on output_format
        if self.output_format in ("json", "both"):
            write_json_report(report, self.output_dir)
        if self.output_format in ("csv", "both"):
            write_csv_report(report, self.output_dir)
            write_eip_detail_csv(report, self.output_dir)
            write_eni_detail_csv(report, self.output_dir)

        # Always generate the HTML report
        write_html_report(report, self.output_dir)

        return report

    def _process_account(
        self,
        role_assumer: RoleAssumer,
        account_id: str,
        account_name: str,
    ) -> tuple[AccountResult, list[ErrorRecord]]:
        """Process a single account: assume role, discover regions, scan.

        Returns:
            A tuple of (AccountResult, list of ErrorRecords for this account).
        """
        errors: list[ErrorRecord] = []

        # Assume role into the account
        session = role_assumer.assume_role(account_id)
        if session is None:
            error_msg = f"Failed to assume role in account {account_id}"
            logger.error(error_msg)
            error = ErrorRecord(
                account_id=account_id,
                api_call="sts:AssumeRole",
                error_message=error_msg,
            )
            errors.append(error)
            return (
                AccountResult(
                    account_id=account_id,
                    account_name=account_name,
                    errors=[error_msg],
                ),
                errors,
            )

        # Discover enabled regions
        ec2_client = session.client("ec2")
        regions = get_enabled_regions(ec2_client)
        logger.info(
            "Account %s: found %d enabled region(s)", account_id, len(regions)
        )

        # Scan all regions concurrently
        region_results = scan_regions(session, account_id, regions)

        # Compute per-account totals
        total_active_ips = sum(
            rr.eni_result.active_ip_count
            for rr in region_results
            if rr.eni_result is not None
        )
        total_eips = sum(
            rr.eip_result.associated_count + rr.eip_result.unassociated_count
            for rr in region_results
            if rr.eip_result is not None
        )

        # Collect region-level errors into ErrorRecords
        account_error_strings: list[str] = []
        for rr in region_results:
            for err_msg in rr.errors:
                account_error_strings.append(err_msg)
                errors.append(
                    ErrorRecord(
                        account_id=account_id,
                        region=rr.region,
                        error_message=err_msg,
                    )
                )

        return (
            AccountResult(
                account_id=account_id,
                account_name=account_name,
                regions=region_results,
                total_active_ips=total_active_ips,
                total_eips=total_eips,
                errors=account_error_strings,
            ),
            errors,
        )
