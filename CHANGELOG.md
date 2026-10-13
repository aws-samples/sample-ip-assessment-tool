# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **IPv4 vs IPv6 breakdown of active IPs.** The ENI collector now counts
  private IPv4 and IPv6 addresses separately on in-use and available ENIs,
  exposed on `ENIResult` as `active_ipv4_count`, `active_ipv6_count`,
  `inactive_ipv4_count`, and `inactive_ipv6_count`.
- **Billable public IPv4 tracking.** The ENI collector counts in-use ENIs that
  carry an auto-assigned public IPv4 address (`ENIResult.active_public_ipv4_count`).
  The aggregator combines these with Elastic IPs (both associated and
  unassociated, which AWS bills at `$0.005/hr` since 2024-02-01) into
  `ReportSummary.total_billable_public_ipv4`.
- **Estimated monthly public IPv4 cost.** `ReportSummary.estimated_monthly_public_ipv4_cost_usd`
  projects the public IPv4 charge at `$0.005/hr * 730 hrs/mo`. New
  `PUBLIC_IPV4_HOURLY_USD` and `HOURS_PER_MONTH` constants in `models.py`.
- **Report surfacing.** The HTML report adds summary cards for Active IPv4,
  Active IPv6, Billable Public IPv4, and Estimated Monthly IPv4 Cost. The
  console pretty-printer adds the matching IPv4/IPv6 breakdown and billing
  lines to its summary section.
- **`--current-account` mode.** New CLI flag to scan only the account for the
  current credentials using the default AWS session, skipping Organizations
  discovery and cross-account role assumption. Useful when you lack Organizations
  access or an assumable role (e.g. running against the management account).
- **Delegated prefix inventory.** The ENI collector now captures `Ipv4Prefixes`
  and `Ipv6Prefixes` per ENI (`ENIRecord.ipv4_prefixes` / `ipv6_prefixes`) and
  totals them on `ENIResult` and `ReportSummary`. Prefixes are free, so they are
  reported as inventory but excluded from the billable total. New
  `ipv4_prefix_count` / `ipv6_prefix_count` columns in the ENI detail CSV and HTML.

### Changed

- **Billable public IPv4 is now deduplicated by address.** The aggregator counts
  the **distinct union** of ENI public IPs and EIP public IPs per region, so an
  Elastic IP attached to an ENI (which appears in both collectors) is counted
  once instead of twice. The ENI and EIP collectors now expose the actual public
  IPv4 address strings (`active_public_ipv4_addresses`, `public_ipv4_addresses`)
  to support this.
- **All public IPs on an ENI are counted, not just the primary.** The ENI
  collector now inspects every per-private-IP association
  (`PrivateIpAddresses[].Association.PublicIp`) in addition to the ENI-level
  `Association.PublicIp`, fixing an undercount for ENIs with multiple associated
  EIPs (one per secondary private IP).

### Fixed

- **Org-wide scan no longer fails on the caller's own account.** During an
  Organization-wide scan, the account belonging to the current credentials is now
  scanned directly with the current session instead of attempting to assume a role
  into it (which fails with `AccessDenied`). Member accounts still use role
  assumption. A missing default region on that session falls back to `us-east-1`.

### Notes

- The existing combined `ENIResult.active_ip_count` / `inactive_ip_count`
  (IPv4 + IPv6 summed) are retained unchanged for backward compatibility; the
  new fields are additive and all default to `0`, so previously generated JSON
  reports still parse.
- IPv6 addresses carry no per-address AWS charge, so they are excluded from the
  billing estimate.
- The cost estimate is a flat-rate projection. It does not model the EC2 Free
  Tier (750 public IPv4 hours/month for the first 12 months) or BYOIP addresses
  (not charged), so it may slightly overstate cost for new accounts.
