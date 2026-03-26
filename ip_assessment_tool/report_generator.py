"""Report generator for the IP Assessment Tool.

Writes assessment reports to disk in JSON and CSV formats.
"""

import csv
import logging
from pathlib import Path

from ip_assessment_tool.models import Report

logger = logging.getLogger(__name__)


def write_json_report(report: Report, output_path: Path) -> Path:
    """Serialize Report to JSON file. Returns the written file path."""
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / "ip_assessment_report.json"
    json_content = report.model_dump_json(indent=2)
    file_path.write_text(json_content, encoding="utf-8")
    logger.info("JSON report written to %s", file_path)
    return file_path


def write_csv_report(report: Report, output_path: Path) -> Path:
    """Serialize Report to CSV file with header row. Returns the written file path."""
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / "ip_assessment_report.csv"

    header = [
        "account_id",
        "account_name",
        "region",
        "active_ips",
        "inactive_ips",
        "eips_associated",
        "eips_unassociated",
        "unique_eips",
    ]

    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)

        for account in report.accounts:
            for region_result in account.regions:
                active_ips = 0
                inactive_ips = 0
                eips_associated = 0
                eips_unassociated = 0
                unique_eips = 0

                if region_result.eni_result:
                    active_ips = region_result.eni_result.active_ip_count
                    inactive_ips = region_result.eni_result.inactive_ip_count

                if region_result.eip_result:
                    eips_associated = region_result.eip_result.associated_count
                    eips_unassociated = region_result.eip_result.unassociated_count
                    unique_eips = region_result.eip_result.unique_eip_count

                writer.writerow([
                    account.account_id,
                    account.account_name,
                    region_result.region,
                    active_ips,
                    inactive_ips,
                    eips_associated,
                    eips_unassociated,
                    unique_eips,
                ])

    logger.info("CSV report written to %s", file_path)
    return file_path


def write_eip_detail_csv(report: Report, output_path: Path) -> Path:
    """Write a detailed EIP CSV with per-EIP rows including associated service."""
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / "ip_assessment_eip_details.csv"

    header = [
        "account_id",
        "account_name",
        "region",
        "allocation_id",
        "public_ip",
        "is_associated",
        "service_managed",
        "instance_id",
        "eni_id",
    ]

    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)

        for account in report.accounts:
            for region_result in account.regions:
                if region_result.eip_result:
                    for eip in region_result.eip_result.eips:
                        writer.writerow([
                            account.account_id,
                            account.account_name,
                            region_result.region,
                            eip.allocation_id,
                            eip.public_ip,
                            eip.is_associated,
                            eip.associated_service or "",
                            eip.instance_id or "",
                            eip.eni_id or "",
                        ])

    logger.info("EIP detail CSV written to %s", file_path)
    return file_path


def write_eni_detail_csv(report: Report, output_path: Path) -> Path:
    """Write a detailed ENI CSV with per-ENI rows including service managed."""
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / "ip_assessment_eni_details.csv"

    header = [
        "account_id",
        "account_name",
        "region",
        "eni_id",
        "status",
        "service_managed",
        "interface_type",
        "ipv4_count",
        "ipv6_count",
        "public_ip",
        "description",
    ]

    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)

        for account in report.accounts:
            for region_result in account.regions:
                if region_result.eni_result:
                    for eni in region_result.eni_result.enis:
                        writer.writerow([
                            account.account_id,
                            account.account_name,
                            region_result.region,
                            eni.eni_id,
                            eni.status,
                            eni.service_managed or "",
                            eni.interface_type or "",
                            len(eni.private_ipv4_addresses),
                            len(eni.ipv6_addresses),
                            eni.public_ip or "",
                            eni.description or "",
                        ])

    logger.info("ENI detail CSV written to %s", file_path)
    return file_path

def write_html_report(report: Report, output_path: Path) -> Path:
    """Write a single HTML report containing all three data sections with styling."""
    import html as html_mod

    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / "ip_assessment_report.html"

    timestamp = report.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    summary = report.summary

    # Build summary rows
    summary_rows = _build_summary_rows(report)
    eni_rows = _build_eni_rows(report)
    eip_rows = _build_eip_rows(report)
    error_rows = _build_error_rows(report)

    def _esc(val: object) -> str:
        return html_mod.escape(str(val))

    # Summary table body
    summary_tbody = ""
    for r in summary_rows:
        summary_tbody += "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in r) + "</tr>\n"

    # ENI table body
    eni_tbody = ""
    for r in eni_rows:
        status_class = ' class="status-active"' if r[4] == "in-use" else ' class="status-inactive"' if r[4] == "available" else ""
        cells = ""
        for i, c in enumerate(r):
            if i == 4:
                cells += f"<td{status_class}>{_esc(c)}</td>"
            else:
                cells += f"<td>{_esc(c)}</td>"
        eni_tbody += f"<tr>{cells}</tr>\n"

    # EIP table body
    eip_tbody = ""
    for r in eip_rows:
        assoc_class = ' class="status-active"' if r[5] == "True" else ' class="status-inactive"' if r[5] == "False" else ""
        cells = ""
        for i, c in enumerate(r):
            if i == 5:
                cells += f"<td{assoc_class}>{_esc(c)}</td>"
            else:
                cells += f"<td>{_esc(c)}</td>"
        eip_tbody += f"<tr>{cells}</tr>\n"

    # Error table body
    error_tbody = ""
    for r in error_rows:
        error_tbody += "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in r) + "</tr>\n"
    no_errors_msg = '<tr><td colspan="5" style="text-align:center;color:var(--green);padding:16px;">No errors recorded</td></tr>' if not error_rows else ""
    no_summary_msg = '<tr><td colspan="8" style="text-align:center;color:var(--text-secondary);padding:16px;">No IPs found across any account or region</td></tr>' if not summary_rows else ""
    no_eni_msg = '<tr><td colspan="11" style="text-align:center;color:var(--text-secondary);padding:16px;">No ENIs found across any account or region</td></tr>' if not eni_rows else ""
    no_eip_msg = '<tr><td colspan="9" style="text-align:center;color:var(--text-secondary);padding:16px;">No EIPs found across any account or region</td></tr>' if not eip_rows else ""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IP Assessment Report</title>
<style>
  :root {{
    --primary: #232f3e;
    --accent: #ff9900;
    --bg: #f5f7fa;
    --card-bg: #ffffff;
    --border: #e1e4e8;
    --text: #24292e;
    --text-secondary: #586069;
    --green: #28a745;
    --red: #d73a49;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
  }}
  header {{
    background: var(--primary);
    color: #fff;
    padding: 24px 32px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  header h1 {{ font-size: 1.5rem; font-weight: 600; }}
  header .meta {{ font-size: 0.85rem; color: #adb5bd; }}
  .summary-cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    padding: 24px 32px;
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    text-align: center;
  }}
  .card .value {{
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--primary);
  }}
  .card .label {{
    font-size: 0.8rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 4px;
  }}
  .section {{
    padding: 0 32px 32px;
  }}
  .section h2 {{
    font-size: 1.15rem;
    font-weight: 600;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--accent);
    display: inline-block;
  }}
  .table-wrap {{
    overflow-x: auto;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }}
  th {{
    background: var(--primary);
    color: #fff;
    padding: 10px 12px;
    text-align: left;
    font-weight: 500;
    white-space: nowrap;
  }}
  td {{
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #f0f4f8; }}
  .status-active {{ color: var(--green); font-weight: 600; }}
  .status-inactive {{ color: var(--red); font-weight: 600; }}
  .nav {{
    display: flex;
    gap: 12px;
    padding: 16px 32px 0;
  }}
  .nav a {{
    padding: 8px 16px;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    text-decoration: none;
    color: var(--primary);
    font-size: 0.85rem;
    font-weight: 500;
    transition: background 0.15s;
  }}
  .nav a:hover {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  footer {{
    text-align: center;
    padding: 24px;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }}
</style>
</head>
<body>
<header>
  <h1>IP Assessment Report</h1>
  <div class="meta">Generated: {_esc(timestamp)}</div>
</header>

<div class="summary-cards">
  <div class="card"><div class="value">{summary.total_accounts_scanned}</div><div class="label">Accounts Scanned</div></div>
  <div class="card"><div class="value">{summary.total_regions_scanned}</div><div class="label">Regions Scanned</div></div>
  <div class="card"><div class="value">{summary.total_active_ips:,}</div><div class="label">Active IPs</div></div>
  <div class="card"><div class="value">{summary.total_inactive_ips:,}</div><div class="label">Inactive IPs</div></div>
  <div class="card"><div class="value">{summary.total_eips_associated:,}</div><div class="label">EIPs Associated</div></div>
  <div class="card"><div class="value">{summary.total_eips_unassociated:,}</div><div class="label">EIPs Unassociated</div></div>
  <div class="card"><div class="value">{summary.total_accounts_with_errors}</div><div class="label">Accounts with Errors</div></div>
</div>

<div class="nav">
  <a href="#summary">IP Inventory</a>
  <a href="#eni-details">ENI Details</a>
  <a href="#eip-details">EIP Details</a>
  <a href="#errors">Errors</a>
</div>

<div class="section" id="summary">
  <h2>IP Inventory Overview</h2>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>Account ID</th><th>Account Name</th><th>Region</th>
        <th>Active IPs</th><th>Inactive IPs</th><th>EIPs Assoc.</th>
        <th>EIPs Unassoc.</th><th>Unique EIPs</th>
      </tr></thead>
      <tbody>{summary_tbody}{no_summary_msg}</tbody>
    </table>
  </div>
</div>

<div class="section" id="eni-details">
  <h2>ENI Details</h2>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>Account ID</th><th>Account Name</th><th>Region</th><th>ENI ID</th>
        <th>Status</th><th>Service Managed</th><th>Interface Type</th>
        <th>IPv4 Count</th><th>IPv6 Count</th><th>Public IP</th><th>Description</th>
      </tr></thead>
      <tbody>{eni_tbody}{no_eni_msg}</tbody>
    </table>
  </div>
</div>

<div class="section" id="eip-details">
  <h2>EIP Details</h2>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>Account ID</th><th>Account Name</th><th>Region</th><th>Allocation ID</th>
        <th>Public IP</th><th>Associated</th><th>Service Managed</th>
        <th>Instance ID</th><th>ENI ID</th>
      </tr></thead>
      <tbody>{eip_tbody}{no_eip_msg}</tbody>
    </table>
  </div>
</div>

<div class="section" id="errors">
  <h2>Errors</h2>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>Account ID</th><th>Region</th><th>API Call</th><th>Error Message</th><th>Suggested Fix</th>
      </tr></thead>
      <tbody>{error_tbody}{no_errors_msg}</tbody>
    </table>
  </div>
</div>

<footer>IP Assessment Tool &mdash; Generated {_esc(timestamp)}</footer>
</body>
</html>"""

    file_path.write_text(html_content, encoding="utf-8")
    logger.info("HTML report written to %s", file_path)
    return file_path


def _build_summary_rows(report: Report) -> list[list[str]]:
    """Build row data for the summary table. Only includes rows where at least one count is non-zero."""
    rows: list[list[str]] = []
    for account in report.accounts:
        for rr in account.regions:
            active = rr.eni_result.active_ip_count if rr.eni_result else 0
            inactive = rr.eni_result.inactive_ip_count if rr.eni_result else 0
            ea = rr.eip_result.associated_count if rr.eip_result else 0
            eu = rr.eip_result.unassociated_count if rr.eip_result else 0
            ue = rr.eip_result.unique_eip_count if rr.eip_result else 0
            if active or inactive or ea or eu or ue:
                rows.append([
                    account.account_id, account.account_name, rr.region,
                    str(active), str(inactive), str(ea), str(eu), str(ue),
                ])
    return rows


def _build_eni_rows(report: Report) -> list[list[str]]:
    """Build row data for the ENI detail table."""
    rows: list[list[str]] = []
    for account in report.accounts:
        for rr in account.regions:
            if rr.eni_result:
                for eni in rr.eni_result.enis:
                    rows.append([
                        account.account_id, account.account_name, rr.region,
                        eni.eni_id, eni.status, eni.service_managed or "",
                        eni.interface_type or "",
                        str(len(eni.private_ipv4_addresses)),
                        str(len(eni.ipv6_addresses)),
                        eni.public_ip or "", eni.description or "",
                    ])
    return rows


def _build_eip_rows(report: Report) -> list[list[str]]:
    """Build row data for the EIP detail table."""
    rows: list[list[str]] = []
    for account in report.accounts:
        for rr in account.regions:
            if rr.eip_result:
                for eip in rr.eip_result.eips:
                    rows.append([
                        account.account_id, account.account_name, rr.region,
                        eip.allocation_id, eip.public_ip, str(eip.is_associated),
                        eip.associated_service or "", eip.instance_id or "",
                        eip.eni_id or "",
                    ])
    return rows


def _suggest_fix(error_message: str, api_call: str | None) -> str:
    """Suggest a fix based on common AWS error patterns."""
    msg = error_message.lower()
    api = (api_call or "").lower()

    if "accessdenied" in msg or "access denied" in msg or "not authorized" in msg:
        if "assumerole" in api or "assumerole" in msg:
            return "Ensure the cross-account role exists and the trust policy allows sts:AssumeRole from the management account"
        return "Check IAM permissions — the role is missing the required policy for this API call"

    if "throttl" in msg or "rate exceeded" in msg or "requestlimitexceeded" in msg:
        return "API rate limit hit — try again later or reduce concurrency"

    if "failed to assume role" in msg:
        return "Verify the role name is correct and deployed to the target account with a valid trust policy"

    if "invalidclienttokenid" in msg or "security token" in msg or "expired" in msg:
        return "AWS credentials are invalid or expired — run 'aws sts get-caller-identity' to verify, then refresh credentials"

    if "unrecoverable error" in msg:
        return "An unexpected error occurred processing this account — check CloudTrail logs for details"

    if "eni collection failed" in msg:
        return "Ensure the role has ec2:DescribeNetworkInterfaces permission in this region"

    if "eip collection failed" in msg:
        return "Ensure the role has ec2:DescribeAddresses permission in this region"

    if "cidr collection failed" in msg:
        return "Ensure the role has ec2:DescribeVpcs and ec2:DescribeSubnets permissions in this region"

    if "region scan failed" in msg:
        return "Region may be disabled or inaccessible — verify the region is opted-in for this account"

    if "endpoint" in msg or "could not connect" in msg or "connection" in msg:
        return "Network connectivity issue — check VPC endpoints, proxy settings, or internet access"

    return "Review the error message and check IAM permissions, network connectivity, and service availability"


def _build_error_rows(report: Report) -> list[list[str]]:
    """Build row data for the errors table including suggested fixes."""
    rows: list[list[str]] = []
    for err in report.errors:
        rows.append([
            err.account_id,
            err.region or "",
            err.api_call or "",
            err.error_message,
            _suggest_fix(err.error_message, err.api_call),
        ])
    return rows

