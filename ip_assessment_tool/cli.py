"""CLI interface for the IP Assessment Tool.

Parses command-line arguments and invokes the orchestrator to run
the full IP assessment pipeline across an AWS Organization.
"""

import argparse
import logging
import sys
from pathlib import Path

from ip_assessment_tool.models import ReportParseError


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser with role-name, output-dir, format, and account-filter options."""
    parser = argparse.ArgumentParser(
        prog="ip-assessment-tool",
        description="IP Assessment Tool - AWS Organization IP address inventory",
    )
    parser.add_argument(
        "--role-name",
        type=str,
        default="OrganizationAccountAccessRole",
        help="IAM role name to assume in each member account (default: OrganizationAccountAccessRole)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Directory to write report files to (default: current directory)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "csv", "both"],
        default="both",
        help="Output format for the report (default: both)",
    )
    parser.add_argument(
        "--account-filter",
        type=str,
        default=None,
        help="Comma-separated list of account IDs to scan (default: all accounts)",
    )
    parser.add_argument(
        "--parse",
        type=str,
        default=None,
        metavar="FILE",
        help="Parse an existing JSON report file and pretty-print it instead of running assessment",
    )
    return parser


def main(args: list[str] | None = None) -> int:
    """Entry point. Returns exit code 0 on success, non-zero on failure."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    # Set up logging to stderr
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    # Handle --parse mode: parse and pretty-print an existing report
    if parsed.parse is not None:
        return _handle_parse(parsed.parse)

    # Parse account filter
    account_filter: list[str] | None = None
    if parsed.account_filter:
        account_filter = [
            acct.strip() for acct in parsed.account_filter.split(",") if acct.strip()
        ]

    # Run the full assessment
    print("Starting IP assessment...", file=sys.stderr)
    try:
        from ip_assessment_tool.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            role_name=parsed.role_name,
            output_dir=parsed.output_dir,
            output_format=parsed.format,
            account_filter=account_filter,
        )
        report = orchestrator.run()
        print(
            f"Assessment complete. Scanned {report.summary.total_accounts_scanned} accounts "
            f"across {report.summary.total_regions_scanned} regions.",
            file=sys.stderr,
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_parse(file_path_str: str) -> int:
    """Parse an existing JSON report and pretty-print it to stdout."""
    try:
        from ip_assessment_tool.report_parser import (
            parse_json_report,
            pretty_print_report,
        )

        file_path = Path(file_path_str)
        report = parse_json_report(file_path)
        print(pretty_print_report(report))
        return 0
    except ReportParseError as e:
        print(f"Error parsing report: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
