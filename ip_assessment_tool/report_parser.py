"""Report parser and pretty printer for the IP Assessment Tool.

Parses JSON report files into Report data structures and formats
them as human-readable tables for console output.
"""

import logging
from pathlib import Path

from ip_assessment_tool.models import Report, ReportParseError

logger = logging.getLogger(__name__)


def parse_json_report(file_path: Path) -> Report:
    """Parse a JSON report file into a Report data structure.

    Raises ReportParseError on invalid/corrupted files.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        report = Report.model_validate_json(content)
        logger.info("Successfully parsed report from %s", file_path)
        return report
    except FileNotFoundError:
        raise ReportParseError(f"Report file not found: {file_path}")
    except Exception as e:
        raise ReportParseError(
            f"Failed to parse report file '{file_path}': {e}"
        )


def pretty_print_report(report: Report) -> str:
    """Format Report as a human-readable table string for console output."""
    lines: list[str] = []

    # Header section
    lines.append("=" * 100)
    lines.append("IP Assessment Report")
    lines.append("=" * 100)
    lines.append(f"Timestamp:       {report.timestamp.isoformat()}")
    lines.append(f"Organization ID: {report.organization_id or 'N/A'}")
    lines.append("")

    # Per-account, per-region table
    col_headers = (
        f"{'Account ID':<16} {'Account Name':<20} {'Region':<16} "
        f"{'Active IPs':>10} {'Inactive IPs':>12} "
        f"{'EIPs Assoc':>10} {'EIPs Unassoc':>12}"
    )
    lines.append(col_headers)
    lines.append("-" * 100)

    for account in report.accounts:
        for region_result in account.regions:
            active_ips = 0
            inactive_ips = 0
            eips_assoc = 0
            eips_unassoc = 0

            if region_result.eni_result:
                active_ips = region_result.eni_result.active_ip_count
                inactive_ips = region_result.eni_result.inactive_ip_count

            if region_result.eip_result:
                eips_assoc = region_result.eip_result.associated_count
                eips_unassoc = region_result.eip_result.unassociated_count

            lines.append(
                f"{account.account_id:<16} {account.account_name:<20} "
                f"{region_result.region:<16} "
                f"{active_ips:>10} {inactive_ips:>12} "
                f"{eips_assoc:>10} {eips_unassoc:>12}"
            )

    # Summary section
    s = report.summary
    lines.append("")
    lines.append("=" * 100)
    lines.append("Summary")
    lines.append("=" * 100)
    lines.append(f"Total Accounts Scanned:      {s.total_accounts_scanned}")
    lines.append(f"Total Accounts with Errors:  {s.total_accounts_with_errors}")
    lines.append(f"Total Regions Scanned:       {s.total_regions_scanned}")
    lines.append(f"Total Active IPs:            {s.total_active_ips}")
    lines.append(f"Total Inactive IPs:          {s.total_inactive_ips}")
    lines.append(f"Total EIPs Associated:       {s.total_eips_associated}")
    lines.append(f"Total EIPs Unassociated:     {s.total_eips_unassociated}")
    lines.append("=" * 100)

    return "\n".join(lines)
