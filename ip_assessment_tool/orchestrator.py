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
        current_account: bool = False,
    ):
        self.role_name = role_name
        self.output_dir = Path(output_dir)
        self.output_format = output_format
        self.account_filter = account_filter
        self.current_account = current_account

    def run(self) -> Report:
        """Execute full assessment pipeline. Returns the consolidated Report."""
        # Current-account mode: skip Organizations discovery + role assumption
        # and scan only the account for the current credentials.
        if self.current_account:
            return self._run_current_account()

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

        # Determine the caller's own account so we can scan it with the current
        # session directly instead of assuming a role into it (assuming a role
        # into the account you are already in typically fails with AccessDenied).
        caller_account_id = self._get_caller_account_id()

        # Step 3: Process each account with fail-forward
        role_assumer = RoleAssumer(role_name=self.role_name)
        account_results: list[AccountResult] = []
        all_errors: list[ErrorRecord] = []

        for idx, account in enumerate(accounts, start=1):
            try:
                result, errors = self._process_account(
                    role_assumer,
                    account.account_id,
                    account.account_name,
                    caller_account_id=caller_account_id,
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
        self._write_reports(report)

        return report

    def _run_current_account(self) -> Report:
        """Scan only the account for the current credentials.

        Uses the default boto3 session directly: no Organizations discovery and
        no cross-account role assumption. The current identity's own permissions
        are used to call the EC2 describe APIs.
        """
        session = boto3.Session()

        # Resolve the current account ID via STS for labeling the report.
        try:
            account_id = session.client("sts").get_caller_identity()["Account"]
        except Exception as exc:
            logger.error("Could not determine current account via STS: %s", exc)
            account_id = "current"

        account_name = "current-account"
        print(
            f"Scanning current account {account_id} using existing credentials "
            f"(Organizations discovery and role assumption skipped).",
            file=sys.stderr,
        )
        logger.info("Current-account mode: scanning %s", account_id)

        errors: list[ErrorRecord] = []
        # The initial describe_regions call needs a region. Use the session's
        # configured region if present, otherwise fall back to us-east-1 (which
        # can enumerate all enabled regions for the account).
        bootstrap_region = session.region_name or "us-east-1"
        ec2_client = session.client("ec2", region_name=bootstrap_region)
        regions = get_enabled_regions(ec2_client)
        logger.info("Account %s: found %d enabled region(s)", account_id, len(regions))

        region_results = scan_regions(session, account_id, regions)

        total_active_ips = sum(
            rr.eni_result.active_ip_count
            for rr in region_results
            if rr.eni_result is not None
        )
        total_active_ips += sum(
            rr.eip_result.unique_active_eip_count
            for rr in region_results
            if rr.eip_result is not None
        )
        total_eips = sum(
            rr.eip_result.associated_count + rr.eip_result.unassociated_count
            for rr in region_results
            if rr.eip_result is not None
        )

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

        account_result = AccountResult(
            account_id=account_id,
            account_name=account_name,
            regions=region_results,
            total_active_ips=total_active_ips,
            total_eips=total_eips,
            errors=account_error_strings,
        )

        timestamp = datetime.now(timezone.utc)
        report = aggregate_results([account_result], errors, timestamp)
        self._write_reports(report)
        return report

    def _write_reports(self, report: Report) -> None:
        """Write the report to disk in the configured formats (plus always HTML)."""
        if self.output_format in ("json", "both"):
            write_json_report(report, self.output_dir)
        if self.output_format in ("csv", "both"):
            write_csv_report(report, self.output_dir)
            write_eip_detail_csv(report, self.output_dir)
            write_eni_detail_csv(report, self.output_dir)

        # Always generate the HTML report
        write_html_report(report, self.output_dir)

    def _get_caller_account_id(self) -> str | None:
        """Return the account ID of the current credentials, or None if unavailable."""
        try:
            return boto3.client("sts").get_caller_identity()["Account"]
        except Exception as exc:
            logger.warning("Could not determine caller account via STS: %s", exc)
            return None

    def _process_account(
        self,
        role_assumer: RoleAssumer,
        account_id: str,
        account_name: str,
        caller_account_id: str | None = None,
    ) -> tuple[AccountResult, list[ErrorRecord]]:
        """Process a single account: assume role (or use the current session for
        the caller's own account), discover regions, and scan.

        Returns:
            A tuple of (AccountResult, list of ErrorRecords for this account).
        """
        errors: list[ErrorRecord] = []

        if caller_account_id is not None and account_id == caller_account_id:
            # Scanning the account we are already authenticated to: use the
            # current session directly rather than assuming a role into it.
            logger.info(
                "Account %s is the caller's own account; scanning with current "
                "session (no role assumption).",
                account_id,
            )
            session = boto3.Session()
        else:
            # Assume role into the (member) account
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

        # Discover enabled regions. A session with no configured region needs an
        # explicit one for the initial describe_regions call; fall back to us-east-1.
        bootstrap_region = session.region_name or "us-east-1"
        ec2_client = session.client("ec2", region_name=bootstrap_region)
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

        # Add associated EIPs without ENI (e.g., NAT Gateway) to active count
        total_active_ips += sum(
            rr.eip_result.unique_active_eip_count
            for rr in region_results
            if rr.eip_result is not None
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
