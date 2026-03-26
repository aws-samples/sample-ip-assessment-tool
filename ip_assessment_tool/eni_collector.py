"""ENI collector - enumerates ENIs and counts active/inactive IPs."""

import logging

from ip_assessment_tool.models import ENIRecord, ENIResult

logger = logging.getLogger(__name__)

# Mapping of ENI description patterns to AWS service names
_SERVICE_PATTERNS: list[tuple[str, str]] = [
    ("ELB app/", "ALB"),
    ("ELB net/", "NLB"),
    ("ELB ", "ELB"),
    ("ElastiCache", "ElastiCache"),
    ("RDSNetworkInterface", "RDS"),
    ("arn:aws:ecs:", "ECS"),
    ("AWS Lambda VPC ENI", "Lambda"),
    ("Interface for NAT Gateway", "NAT Gateway"),
    ("VPC Endpoint Interface", "VPC Endpoint"),
    ("AWS CodeStar Connections", "CodeStar"),
    ("DAX", "DAX"),
    ("Redshift", "Redshift"),
    ("EFS mount target", "EFS"),
    ("CloudHSM", "CloudHSM"),
    ("Managed by Fargate", "Fargate"),
]


def _infer_service_managed(eni: dict) -> str:
    """Infer the AWS service managing an ENI from its metadata."""
    interface_type = eni.get("InterfaceType", "")
    description = eni.get("Description", "")
    requester_id = eni.get("RequesterId", "")

    # Interface type gives strong signals
    if interface_type == "nat_gateway":
        return "NAT Gateway"
    if interface_type == "gateway_load_balancer_endpoint":
        return "GWLB Endpoint"
    if interface_type == "vpc_endpoint":
        return "VPC Endpoint"
    if interface_type == "lambda":
        return "Lambda"
    if interface_type == "efa":
        return "EFA"
    if interface_type == "trunk":
        return "ECS"

    # Check description patterns
    for pattern, service in _SERVICE_PATTERNS:
        if pattern in description:
            return service

    # Check requester for AWS-managed ENIs
    if requester_id.startswith("amazon-elb"):
        return "ELB"
    if requester_id.startswith("amazon-rds"):
        return "RDS"

    # If attached to an instance, it's EC2
    if eni.get("Attachment", {}).get("InstanceId"):
        return "EC2"

    return "Unknown"


def collect_eni_data(ec2_client, account_id: str, region: str) -> ENIResult:
    """Query all ENIs via paginator. Classify IPs as active (in-use) or inactive (available).
    Count both IPv4 and IPv6 addresses.

    Args:
        ec2_client: A boto3 EC2 client.
        account_id: The AWS account ID being scanned.
        region: The AWS region being scanned.

    Returns:
        An ENIResult with all ENI records and active/inactive IP counts.
    """
    paginator = ec2_client.get_paginator("describe_network_interfaces")
    enis: list[ENIRecord] = []
    active_ip_count = 0
    inactive_ip_count = 0

    for page in paginator.paginate():
        for eni in page.get("NetworkInterfaces", []):
            eni_id = eni["NetworkInterfaceId"]
            status = eni["Status"]

            private_ipv4_addresses = [
                addr["PrivateIpAddress"]
                for addr in eni.get("PrivateIpAddresses", [])
            ]

            ipv6_addresses = [
                addr["Ipv6Address"]
                for addr in eni.get("Ipv6Addresses", [])
            ]

            public_ip = eni.get("Association", {}).get("PublicIp")
            interface_type = eni.get("InterfaceType", "")
            description = eni.get("Description", "")
            service_managed = _infer_service_managed(eni)

            enis.append(
                ENIRecord(
                    eni_id=eni_id,
                    status=status,
                    private_ipv4_addresses=private_ipv4_addresses,
                    ipv6_addresses=ipv6_addresses,
                    public_ip=public_ip,
                    interface_type=interface_type or None,
                    service_managed=service_managed,
                    description=description or None,
                )
            )

            ip_count = len(private_ipv4_addresses) + len(ipv6_addresses)

            if status == "in-use":
                active_ip_count += ip_count
            elif status == "available":
                inactive_ip_count += ip_count

    logger.info(
        "Account %s, region %s: found %d ENI(s), %d active IP(s), %d inactive IP(s)",
        account_id,
        region,
        len(enis),
        active_ip_count,
        inactive_ip_count,
    )

    return ENIResult(
        account_id=account_id,
        region=region,
        enis=enis,
        active_ip_count=active_ip_count,
        inactive_ip_count=inactive_ip_count,
    )
