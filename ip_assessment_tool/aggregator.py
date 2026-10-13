"""Aggregator module that merges per-account, per-region results into a consolidated Report."""

from datetime import datetime

from ip_assessment_tool.models import (
    HOURS_PER_MONTH,
    PUBLIC_IPV4_HOURLY_USD,
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
    total_active_ipv4 = 0
    total_active_ipv6 = 0
    total_active_ipv4_prefixes = 0
    total_active_ipv6_prefixes = 0
    # Count billable public IPv4 by DISTINCT address, deduped per region across
    # ENI public IPs and EIP public IPs (an EIP on an ENI appears in both).
    total_billable_public_ipv4 = 0

    for account in account_results:
        total_active_ips += account.total_active_ips
        total_regions_scanned += len(account.regions)

        if len(account.errors) > 0:
            total_accounts_with_errors += 1

        for region in account.regions:
            billable_in_region: set[str] = set()

            if region.eni_result is not None:
                total_inactive_ips += region.eni_result.inactive_ip_count
                total_active_ipv4 += region.eni_result.active_ipv4_count
                total_active_ipv6 += region.eni_result.active_ipv6_count
                total_active_ipv4_prefixes += region.eni_result.active_ipv4_prefix_count
                total_active_ipv6_prefixes += region.eni_result.active_ipv6_prefix_count
                billable_in_region.update(region.eni_result.active_public_ipv4_addresses)

            if region.eip_result is not None:
                total_inactive_ips += region.eip_result.unassociated_count
                total_eips_associated += region.eip_result.associated_count
                total_eips_unassociated += region.eip_result.unassociated_count
                # All EIPs (associated + unassociated) are billable. Union by
                # address string dedupes any EIP already seen as an ENI public IP.
                billable_in_region.update(region.eip_result.public_ipv4_addresses)

            total_billable_public_ipv4 += len(billable_in_region)

    estimated_monthly_public_ipv4_cost_usd = round(
        total_billable_public_ipv4 * PUBLIC_IPV4_HOURLY_USD * HOURS_PER_MONTH, 2
    )

    summary = ReportSummary(
        total_accounts_scanned=len(account_results),
        total_accounts_with_errors=total_accounts_with_errors,
        total_regions_scanned=total_regions_scanned,
        total_active_ips=total_active_ips,
        total_inactive_ips=total_inactive_ips,
        total_eips_associated=total_eips_associated,
        total_eips_unassociated=total_eips_unassociated,
        total_active_ipv4=total_active_ipv4,
        total_active_ipv6=total_active_ipv6,
        total_billable_public_ipv4=total_billable_public_ipv4,
        estimated_monthly_public_ipv4_cost_usd=estimated_monthly_public_ipv4_cost_usd,
        total_active_ipv4_prefixes=total_active_ipv4_prefixes,
        total_active_ipv6_prefixes=total_active_ipv6_prefixes,
    )

    return Report(
        timestamp=timestamp,
        organization_id=organization_id,
        accounts=account_results,
        summary=summary,
        errors=errors,
    )
