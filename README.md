# IP Assessment Tool

CLI tool that scans an entire AWS Organization to produce a consolidated inventory of active IP addresses, Elastic IPs, and VPC/Subnet CIDR allocations across all member accounts and regions. Designed to support IPAM Advanced Tier adoption decisions.

## Quick Start

```bash

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the assessment
python -m ip_assessment_tool --role-name OrganizationAccountAccessRole --output-dir ./reports --format both

# Parse an existing report
python -m ip_assessment_tool --parse ./reports/ip_assessment_report.json
```

## CLI Options

| Option | Default | Description |
|---|---|---|
| `--role-name` | `OrganizationAccountAccessRole` | IAM role to assume in each member account |
| `--output-dir` | `.` | Directory for report output |
| `--format` | `both` | Output format: `json`, `csv`, or `both` |
| `--account-filter` | all | Comma-separated account IDs to scan |
| `--parse FILE` | — | Parse and pretty-print an existing JSON report |

## Prerequisites

- Python 3.11+
- AWS CLI installed and configured
- A cross-account IAM role deployed to all member accounts (default: `OrganizationAccountAccessRole`)

### AWS Configuration

If you haven't configured AWS credentials on your machine yet:

1. Install the AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

2. Configure your credentials:
```bash
aws configure
```
You'll be prompted for:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g. `us-east-1`)
- Default output format (e.g. `json`)

3. Verify your setup:
```bash
aws sts get-caller-identity
```

If you use SSO or named profiles:
```bash
# Configure SSO
aws configure sso

# Run the tool with a specific profile
AWS_PROFILE=your-profile python -m ip_assessment_tool
```

### Required IAM Permissions

The credentials you configure need the following permissions in the management account:

- `organizations:ListAccounts`
- `organizations:DescribeOrganization`
- `sts:AssumeRole` (to assume into member accounts)

The cross-account role in each member account needs:

- `ec2:DescribeNetworkInterfaces`
- `ec2:DescribeAddresses`
- `ec2:DescribeVpcs`
- `ec2:DescribeSubnets`
- `ec2:DescribeRegions`

## What It Collects

- **ENIs**: All Elastic Network Interfaces with private IPv4 and IPv6 addresses, classified as active (in-use) or inactive (available), with the managing AWS service identified (EC2, ELB, Lambda, RDS, NAT Gateway, ECS, VPC Endpoint, etc.)
- **EIPs**: All Elastic IPs, classified as associated or unassociated, with the associated service identified and double-count prevention against ENI data
- **VPC CIDRs**: All VPC primary and secondary CIDR blocks (IPv4 and IPv6), subnet CIDRs, and available IP counts

## Report Output

When using `--format both` or `--format csv`, the tool generates three CSV files:

| File | Description |
|---|---|
| `ip_assessment_report.csv` | Summary per account/region with aggregated IP counts |
| `ip_assessment_eni_details.csv` | Per-ENI detail with service managed, interface type, IP counts |
| `ip_assessment_eip_details.csv` | Per-EIP detail with associated service, instance ID, ENI ID |

When using `--format json`, a single `ip_assessment_report.json` is generated containing all data.

An `ip_assessment_report.html` file is always generated regardless of format choice. It contains all three data sections (summary, ENI details, EIP details) in a single styled page with summary cards, navigation links, and color-coded status indicators. Open it in any browser for a quick visual overview.

### Summary CSV columns

`account_id`, `account_name`, `region`, `active_ips`, `inactive_ips`, `eips_associated`, `eips_unassociated`, `unique_eips`

### ENI Detail CSV columns

`account_id`, `account_name`, `region`, `eni_id`, `status`, `service_managed`, `interface_type`, `ipv4_count`, `ipv6_count`, `public_ip`, `description`

### EIP Detail CSV columns

`account_id`, `account_name`, `region`, `allocation_id`, `public_ip`, `is_associated`, `service_managed`, `instance_id`, `eni_id`

### Service Detection

The tool automatically identifies which AWS service manages each ENI and EIP:

| Service | Detection Method |
|---|---|
| EC2 | Instance attachment |
| ALB / NLB / ELB | Description prefix or requester ID |
| Lambda | Interface type or description |
| NAT Gateway | Interface type or description |
| RDS | Description or requester ID |
| ECS / Fargate | Interface type or description |
| VPC Endpoint | Interface type |
| ElastiCache, EFS, Redshift, DAX | Description patterns |

## Project Structure

```
ip_assessment_tool/
├── __init__.py
├── __main__.py          # Entry point (python -m ip_assessment_tool)
├── cli.py               # CLI argument parsing
├── orchestrator.py      # Pipeline coordinator
├── discovery.py         # AWS Organizations account discovery
├── role_assumer.py      # Cross-account STS role assumption
├── region_scanner.py    # Region discovery and concurrent scanning
├── eni_collector.py     # ENI and active IP enumeration
├── eip_collector.py     # Elastic IP enumeration
├── cidr_collector.py    # VPC/Subnet CIDR inventory
├── aggregator.py        # Result aggregation
├── report_generator.py  # JSON and CSV report output
├── report_parser.py     # Report parsing and pretty printing
├── retry.py             # Exponential backoff for throttling
└── models.py            # Pydantic data models
```

## Testing

```bash
python -m pytest tests/test_retry.py tests/test_discovery.py tests/test_role_assumer.py tests/test_region_scanner.py tests/test_eni_collector.py tests/test_eip_collector.py tests/test_cidr_collector.py tests/test_aggregator.py tests/test_report_generator.py tests/test_report_parser.py -v
```

## Error Handling

The tool uses fail-forward processing. If a single account or region fails, it logs the error and continues with the rest. The final report includes a summary of all errors and skipped resources.
