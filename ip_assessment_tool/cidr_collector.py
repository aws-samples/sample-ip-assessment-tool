"""VPC/CIDR collector - inventories VPC and Subnet CIDR blocks."""

import ipaddress
import logging

from ip_assessment_tool.models import CIDRRecord, CIDRResult, SubnetRecord, VPCRecord

logger = logging.getLogger(__name__)


def _cidr_ip_count(cidr_block: str) -> int:
    """Calculate the number of IP addresses in a CIDR block.

    Handles both IPv4 and IPv6 CIDR notation.
    """
    try:
        network = ipaddress.ip_network(cidr_block, strict=False)
        return network.num_addresses
    except ValueError:
        logger.warning("Invalid CIDR block: %s", cidr_block)
        return 0


def collect_cidr_data(ec2_client, account_id: str, region: str) -> CIDRResult:
    """Query all VPCs (with primary + secondary CIDRs) and all Subnets.
    Calculate total allocated IP space.

    Args:
        ec2_client: A boto3 EC2 client.
        account_id: The AWS account ID being scanned.
        region: The AWS region being scanned.

    Returns:
        A CIDRResult with all VPC/subnet records and total allocated IP count.
    """
    vpcs = _collect_vpcs(ec2_client)
    subnets = _collect_subnets(ec2_client)

    total_allocated_ips = 0
    for vpc in vpcs:
        total_allocated_ips += vpc.primary_cidr.ip_count
        for secondary in vpc.secondary_cidrs:
            total_allocated_ips += secondary.ip_count

    logger.info(
        "Account %s, region %s: found %d VPC(s), %d subnet(s), %d total allocated IP(s)",
        account_id,
        region,
        len(vpcs),
        len(subnets),
        total_allocated_ips,
    )

    return CIDRResult(
        account_id=account_id,
        region=region,
        vpcs=vpcs,
        subnets=subnets,
        total_allocated_ips=total_allocated_ips,
    )


def _collect_vpcs(ec2_client) -> list[VPCRecord]:
    """Paginate through all VPCs and extract primary + secondary CIDR blocks."""
    paginator = ec2_client.get_paginator("describe_vpcs")
    vpcs: list[VPCRecord] = []

    for page in paginator.paginate():
        for vpc in page.get("Vpcs", []):
            vpc_id = vpc["VpcId"]
            primary_cidr_block = vpc["CidrBlock"]
            primary_cidr = CIDRRecord(
                cidr_block=primary_cidr_block,
                ip_count=_cidr_ip_count(primary_cidr_block),
            )

            # Secondary IPv4 CIDRs from CidrBlockAssociationSet
            secondary_cidrs: list[CIDRRecord] = []
            for assoc in vpc.get("CidrBlockAssociationSet", []):
                cidr = assoc.get("CidrBlock", "")
                if cidr and cidr != primary_cidr_block:
                    secondary_cidrs.append(
                        CIDRRecord(
                            cidr_block=cidr,
                            ip_count=_cidr_ip_count(cidr),
                        )
                    )

            # IPv6 CIDRs from Ipv6CidrBlockAssociationSet
            for assoc in vpc.get("Ipv6CidrBlockAssociationSet", []):
                cidr = assoc.get("Ipv6CidrBlock", "")
                if cidr:
                    secondary_cidrs.append(
                        CIDRRecord(
                            cidr_block=cidr,
                            ip_count=_cidr_ip_count(cidr),
                        )
                    )

            vpcs.append(
                VPCRecord(
                    vpc_id=vpc_id,
                    primary_cidr=primary_cidr,
                    secondary_cidrs=secondary_cidrs,
                )
            )

    return vpcs


def _collect_subnets(ec2_client) -> list[SubnetRecord]:
    """Paginate through all subnets and extract CIDR and available IP count."""
    paginator = ec2_client.get_paginator("describe_subnets")
    subnets: list[SubnetRecord] = []

    for page in paginator.paginate():
        for subnet in page.get("Subnets", []):
            subnet_id = subnet["SubnetId"]
            vpc_id = subnet["VpcId"]
            cidr_block = subnet["CidrBlock"]
            available_ip_count = subnet.get("AvailableIpAddressCount", 0)

            subnets.append(
                SubnetRecord(
                    subnet_id=subnet_id,
                    vpc_id=vpc_id,
                    cidr=CIDRRecord(
                        cidr_block=cidr_block,
                        ip_count=_cidr_ip_count(cidr_block),
                    ),
                    available_ip_count=available_ip_count,
                )
            )

    return subnets
