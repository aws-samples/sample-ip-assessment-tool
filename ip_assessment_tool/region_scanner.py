"""Region scanner for discovering enabled regions and collecting IP data concurrently."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3

from ip_assessment_tool.cidr_collector import collect_cidr_data
from ip_assessment_tool.eip_collector import collect_eip_data
from ip_assessment_tool.eni_collector import collect_eni_data
from ip_assessment_tool.models import ErrorRecord, RegionResult

logger = logging.getLogger(__name__)


def get_enabled_regions(ec2_client) -> list[str]:
    """Return list of enabled region names for the account."""
    response = ec2_client.describe_regions(AllRegions=False)
    return [r["RegionName"] for r in response.get("Regions", [])]


def _scan_single_region(
    session: boto3.Session, account_id: str, region: str
) -> RegionResult:
    """Scan a single region, collecting ENI, EIP, and CIDR data."""
    errors: list[str] = []
    eni_result = None
    eip_result = None
    cidr_result = None

    ec2_client = session.client("ec2", region_name=region)

    try:
        eni_result = collect_eni_data(ec2_client, account_id, region)
    except Exception as exc:
        msg = f"ENI collection failed in {account_id}/{region}: {exc}"
        logger.error(msg)
        errors.append(msg)

    try:
        eip_result = collect_eip_data(ec2_client, account_id, region, eni_result)
    except Exception as exc:
        msg = f"EIP collection failed in {account_id}/{region}: {exc}"
        logger.error(msg)
        errors.append(msg)

    try:
        cidr_result = collect_cidr_data(ec2_client, account_id, region)
    except Exception as exc:
        msg = f"CIDR collection failed in {account_id}/{region}: {exc}"
        logger.error(msg)
        errors.append(msg)

    return RegionResult(
        region=region,
        eni_result=eni_result,
        eip_result=eip_result,
        cidr_result=cidr_result,
        errors=errors,
    )


def scan_regions(
    session: boto3.Session, account_id: str, regions: list[str]
) -> list[RegionResult]:
    """Scan all regions concurrently. Returns results per region, including errors."""
    results: list[RegionResult] = []

    with ThreadPoolExecutor() as executor:
        future_to_region = {
            executor.submit(_scan_single_region, session, account_id, region): region
            for region in regions
        }

        for future in as_completed(future_to_region):
            region = future_to_region[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                msg = f"Region scan failed for {account_id}/{region}: {exc}"
                logger.error(msg)
                results.append(RegionResult(region=region, errors=[msg]))

    return results
