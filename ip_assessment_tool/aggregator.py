"""Aggregator module that merges per-account, per-region results into a consolidated Report."""

from datetime import datetime

from ip_assessment_tool.models import (
    AccountResult,
    ErrorRecord,
    Report,
    ReportSummary,
)


def aggregate_results(
    account_results: list[AccountResult],
    errors: list[ErrorRecord],
    timestamp: datetime,
    organization_id: str | None = None,
) -> Report:
    """Combine all account/region results into a single Report with summary totals."""
    total_active_ips = 0
    total_inactive_ips = 0
    total_eips_associated = 0
    total_eips_unassociated = 0
    total_regions_scanned = 0
    total_accounts_with_errors = 0

    for account in account_results:
        total_active_ips += account.total_active_ips
        total_regions_scanned += len(account.regions)

        if len(account.errors) > 0:
            total_accounts_with_errors += 1

        for region in account.regions:
            if region.eni_result is not None:
                total_inactive_ips += region.eni_result.inactive_ip_count

            if region.eip_result is not None:
                total_eips_associated += region.eip_result.associated_count
                total_eips_unassociated += region.eip_result.unassociated_count

    summary = ReportSummary(
        total_accounts_scanned=len(account_results),
        total_accounts_with_errors=total_accounts_with_errors,
        total_regions_scanned=total_regions_scanned,
        total_active_ips=total_active_ips,
        total_inactive_ips=total_inactive_ips,
        total_eips_associated=total_eips_associated,
        total_eips_unassociated=total_eips_unassociated,
    )

    return Report(
        timestamp=timestamp,
        organization_id=organization_id,
        accounts=account_results,
        summary=summary,
        errors=errors,
    )
