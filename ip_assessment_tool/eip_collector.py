"""EIP collector - enumerates Elastic IPs."""

import logging

from ip_assessment_tool.models import EIPRecord, EIPResult, ENIResult

logger = logging.getLogger(__name__)


def _infer_service(
    addr: dict,
    instance_id: str | None,
    eni_id: str | None,
    eni_service_map: dict[str, str] | None = None,
    nat_gw_alloc_ids: set[str] | None = None,
    allocation_id: str | None = None,
) -> str | None:
    """Infer the associated AWS service from EIP address metadata.

    Uses the ENI service map (from ENI collector) and NAT Gateway allocation
    IDs to resolve the actual managing service.
    """
    if not addr.get("AssociationId"):
        return None
    if instance_id:
        return "EC2"
    # Check if this EIP belongs to a NAT Gateway
    if allocation_id and nat_gw_alloc_ids and allocation_id in nat_gw_alloc_ids:
        return "NAT Gateway"
    # Look up the ENI's service_managed from ENI collector data
    if eni_id and eni_service_map:
        service = eni_service_map.get(eni_id)
        if service and service != "Unknown":
            return service
    # Fallback: check tags for NAT hints
    if "nat-" in addr.get("Tags", [{}]).__repr__().lower():
        return "NAT Gateway"
    if eni_id and not instance_id:
        return "Unknown"
    return "Unknown"


def collect_eip_data(
    ec2_client,
    account_id: str,
    region: str,
    eni_result: ENIResult | None = None,
) -> EIPResult:
    """Query all EIPs. Classify as associated or unassociated.
    Track which EIPs overlap with ENI-counted IPs to avoid double-counting.

    Args:
        ec2_client: A boto3 EC2 client.
        account_id: The AWS account ID being scanned.
        region: The AWS region being scanned.
        eni_result: Optional ENI collection result used to resolve service names.

    Returns:
        An EIPResult with all EIP records and classification counts.
    """
    # Build ENI ID → service_managed lookup from ENI data
    eni_service_map: dict[str, str] | None = None
    if eni_result:
        eni_service_map = {
            eni.eni_id: eni.service_managed
            for eni in eni_result.enis
            if eni.service_managed
        }

    # Build a set of EIP allocation IDs used by NAT Gateways
    nat_gw_alloc_ids: set[str] = set()
    try:
        nat_paginator = ec2_client.get_paginator("describe_nat_gateways")
        for page in nat_paginator.paginate():
            for ngw in page.get("NatGateways", []):
                for addr in ngw.get("NatGatewayAddresses", []):
                    alloc_id = addr.get("AllocationId")
                    if alloc_id:
                        nat_gw_alloc_ids.add(alloc_id)
    except Exception as exc:
        logger.warning("Could not enumerate NAT Gateways for EIP service detection: %s", exc)

    response = ec2_client.describe_addresses()
    addresses = response.get("Addresses", [])

    eips: list[EIPRecord] = []
    associated_count = 0
    unassociated_count = 0
    unique_eip_count = 0

    for addr in addresses:
        allocation_id = addr.get("AllocationId", "")
        public_ip = addr.get("PublicIp", "")
        association_id = addr.get("AssociationId") or None
        eni_id = addr.get("NetworkInterfaceId") or None
        instance_id = addr.get("InstanceId") or None
        is_associated = bool(association_id)

        # Infer associated service from available fields
        associated_service = _infer_service(addr, instance_id, eni_id, eni_service_map, nat_gw_alloc_ids, allocation_id)

        eips.append(
            EIPRecord(
                allocation_id=allocation_id,
                public_ip=public_ip,
                is_associated=is_associated,
                association_id=association_id,
                eni_id=eni_id,
                instance_id=instance_id,
                associated_service=associated_service,
            )
        )

        if is_associated:
            associated_count += 1
        else:
            unassociated_count += 1

        # EIPs without an eni_id are not already counted via ENI enumeration
        if not eni_id:
            unique_eip_count += 1

    logger.info(
        "Account %s, region %s: found %d EIP(s), %d associated, %d unassociated, %d unique (not ENI-counted)",
        account_id,
        region,
        len(eips),
        associated_count,
        unassociated_count,
        unique_eip_count,
    )

    return EIPResult(
        account_id=account_id,
        region=region,
        eips=eips,
        associated_count=associated_count,
        unassociated_count=unassociated_count,
        unique_eip_count=unique_eip_count,
    )
