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


class ENIResult(BaseModel):
    account_id: str
    region: str
    enis: list[ENIRecord]
    active_ip_count: int
    inactive_ip_count: int


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


class ReportSummary(BaseModel):
    total_accounts_scanned: int
    total_accounts_with_errors: int
    total_regions_scanned: int
    total_active_ips: int
    total_inactive_ips: int
    total_eips_associated: int
    total_eips_unassociated: int


class Report(BaseModel):
    timestamp: datetime
    organization_id: str | None = None
    accounts: list[AccountResult]
    summary: ReportSummary
    errors: list[ErrorRecord] = []


class ReportParseError(Exception):
    """Raised when a report file cannot be parsed."""

    pass
