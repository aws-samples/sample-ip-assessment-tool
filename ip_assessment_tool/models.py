"""Pydantic data models for the IP Assessment Tool."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class AccountInfo(BaseModel):
    account_id: str
    account_name: str
    status: AccountStatus
    is_management: bool = False


class IPAddress(BaseModel):
    address: str
    version: int  # 4 or 6
    is_active: bool


class ENIRecord(BaseModel):
    eni_id: str
    status: str  # "in-use" or "available"
    private_ipv4_addresses: list[str]
    ipv6_addresses: list[str]
    public_ip: str | None = None
    interface_type: str | None = None
    service_managed: str | None = None  # e.g. "EC2", "ELB", "Lambda", "RDS", "NAT Gateway"
    description: str | None = None
    # Delegated prefixes attached to the ENI (free; inventory only, not billed)
    ipv4_prefixes: list[str] = []  # e.g. ["10.0.1.0/28"]
    ipv6_prefixes: list[str] = []  # e.g. ["2600:1f18:...::/80"]


class ENIResult(BaseModel):
    account_id: str
    region: str
    enis: list[ENIRecord]
    active_ip_count: int  # Combined IPv4 + IPv6 on in-use ENIs (kept for backward compatibility)
    inactive_ip_count: int  # Combined IPv4 + IPv6 on available ENIs
    # Address-family breakdown of the active (in-use ENI) counts
    active_ipv4_count: int = 0  # Private IPv4 addresses on in-use ENIs
    active_ipv6_count: int = 0  # IPv6 addresses on in-use ENIs
    # Billable public IPv4 addresses auto-assigned to in-use ENIs ($0.005/hr each)
    active_public_ipv4_count: int = 0
    # Address-family breakdown of the inactive (available ENI) counts
    inactive_ipv4_count: int = 0
    inactive_ipv6_count: int = 0
    # Distinct public IPv4 address strings seen on in-use ENIs. Used to dedupe
    # against Elastic IPs (an EIP attached to an ENI appears in both collectors)
    # so each billable address is counted exactly once.
    active_public_ipv4_addresses: list[str] = []
    # Delegated prefixes on in-use ENIs (free; inventory only, excluded from billing)
    active_ipv4_prefix_count: int = 0
    active_ipv6_prefix_count: int = 0


class EIPRecord(BaseModel):
    allocation_id: str
    public_ip: str
    is_associated: bool
    association_id: str | None = None
    eni_id: str | None = None  # For double-count detection
    instance_id: str | None = None
    associated_service: str | None = None  # e.g. "EC2", "NAT Gateway", "ELB"


class EIPResult(BaseModel):
    account_id: str
    region: str
    eips: list[EIPRecord]
    associated_count: int
    unassociated_count: int
    unique_eip_count: int  # EIPs not already counted via ENI
    unique_active_eip_count: int = 0  # Associated EIPs without eni_id (e.g., NAT Gateway)
    # All EIP public IPv4 address strings (associated + unassociated). Used to
    # dedupe against ENI public IPs when computing the billable total.
    public_ipv4_addresses: list[str] = []


class CIDRRecord(BaseModel):
    cidr_block: str
    ip_count: int


class VPCRecord(BaseModel):
    vpc_id: str
    primary_cidr: CIDRRecord
    secondary_cidrs: list[CIDRRecord] = []


class SubnetRecord(BaseModel):
    subnet_id: str
    vpc_id: str
    cidr: CIDRRecord
    available_ip_count: int


class CIDRResult(BaseModel):
    account_id: str
    region: str
    vpcs: list[VPCRecord]
    subnets: list[SubnetRecord]
    total_allocated_ips: int


class RegionResult(BaseModel):
    region: str
    eni_result: ENIResult | None = None
    eip_result: EIPResult | None = None
    cidr_result: CIDRResult | None = None
    errors: list[str] = []


class AccountResult(BaseModel):
    account_id: str
    account_name: str
    regions: list[RegionResult] = []
    total_active_ips: int = 0
    total_eips: int = 0
    errors: list[str] = []


class ErrorRecord(BaseModel):
    account_id: str
    region: str | None = None
    api_call: str | None = None
    error_message: str


# Hourly price (USD) AWS charges per public IPv4 address since 2024-02-01.
PUBLIC_IPV4_HOURLY_USD = 0.005
# Approximate hours per month used to project the monthly public IPv4 cost.
HOURS_PER_MONTH = 730


class ReportSummary(BaseModel):
    total_accounts_scanned: int
    total_accounts_with_errors: int
    total_regions_scanned: int
    total_active_ips: int
    total_inactive_ips: int
    total_eips_associated: int
    total_eips_unassociated: int
    # Address-family breakdown of active IPs (IPv6 adoption / billing view)
    total_active_ipv4: int = 0
    total_active_ipv6: int = 0
    # Billable public IPv4 addresses: the DISTINCT union of ENI public IPs and
    # EIP public IPs (an EIP attached to an ENI is the same address in both, so
    # it is counted once). Both associated and unassociated EIPs are billed at
    # $0.005/hr since 2024-02-01. IPv6 is never billed.
    total_billable_public_ipv4: int = 0
    # Projected monthly cost of the billable public IPv4 addresses, in USD.
    estimated_monthly_public_ipv4_cost_usd: float = 0.0
    # Delegated prefixes on in-use ENIs (free; inventory only, not billed).
    total_active_ipv4_prefixes: int = 0
    total_active_ipv6_prefixes: int = 0


class Report(BaseModel):
    timestamp: datetime
    organization_id: str | None = None
    accounts: list[AccountResult]
    summary: ReportSummary
    errors: list[ErrorRecord] = []


class ReportParseError(Exception):
    """Raised when a report file cannot be parsed."""

    pass
