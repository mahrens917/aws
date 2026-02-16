#!/usr/bin/env python3
"""Audit Route53 DNS records and costs."""


from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import (
    create_route53_client,
    create_route53resolver_client,
)
from cost_toolkit.common.route53_utils import parse_hosted_zone
from cost_toolkit.scripts.aws_route53_operations import (
    list_hosted_zones,
    list_resource_record_sets,
)

# Route 53 constants
COST_VARIANCE_THRESHOLD = 0.50  # Acceptable cost difference in dollars
DEFAULT_DNS_RECORD_COUNT = 2  # NS and SOA records
EXPECTED_HOSTED_ZONE_COUNT_1 = 3  # Common configuration
EXPECTED_HOSTED_ZONE_COUNT_2 = 2  # Alternative configuration
EXPECTED_HEALTH_CHECK_COUNT = 2  # Common health check count


def _print_zone_records(_route53, zone_id):
    """Print DNS records for a zone."""
    try:
        records = list_resource_record_sets(hosted_zone_id=zone_id)

        print("  Records:")
        for record in records:
            record_name = record.get("Name")
            record_type = record.get("Type")
            ttl = record.get("TTL")

            if record_type in ["NS", "SOA"]:
                continue

            print(f"    {record_name} ({record_type}) TTL: {ttl}")

            resource_records = []
            if "ResourceRecords" in record:
                resource_records = record["ResourceRecords"]
            for rr in resource_records:
                rr_value = rr.get("Value")
                print(f"      -> {rr_value}")

            alias_target = record.get("AliasTarget")
            if alias_target:
                dns_name = alias_target.get("DNSName")
                print(f"      -> ALIAS: {dns_name}")

    except ClientError as e:
        print(f"  ❌ Error getting records: {e}")


def audit_route53_hosted_zones():
    """Audit Route 53 hosted zones and their costs"""
    print("\n🔍 Auditing Route 53 Hosted Zones")
    print("=" * 80)

    try:
        route53 = create_route53_client()

        hosted_zones = list_hosted_zones()

        if not hosted_zones:
            print("✅ No hosted zones found")
            return []

        zone_details = []
        total_monthly_cost = 0

        for zone in hosted_zones:
            zone_info = parse_hosted_zone(zone)
            zone_id = zone_info["zone_id"]
            zone_name = zone_info["zone_name"]
            is_private = zone_info["is_private"]
            record_count = zone_info["record_count"]

            monthly_cost = 0.50
            total_monthly_cost += monthly_cost

            zone_info = {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "is_private": is_private,
                "record_count": record_count,
                "monthly_cost": monthly_cost,
            }

            print(f"Hosted Zone: {zone_name}")
            print(f"  Zone ID: {zone_id}")
            print(f"  Type: {'Private' if is_private else 'Public'}")
            print(f"  Record Count: {record_count}")
            print(f"  Monthly Cost: ${monthly_cost:.2f}")

            _print_zone_records(route53, zone["Id"])

            print()
            zone_details.append(zone_info)

        print("📊 Hosted Zones Summary:")
        print(f"  Total zones: {len(hosted_zones)}")
        print(f"  Estimated monthly cost: ${total_monthly_cost:.2f}")

    except ClientError as e:
        print(f"❌ Error auditing Route 53: {e}")
        return []

    return zone_details


def audit_route53_health_checks():
    """Audit Route 53 health checks"""
    print("\n🔍 Auditing Route 53 Health Checks")
    print("=" * 80)

    try:
        route53 = create_route53_client()

        response = route53.list_health_checks()
        health_checks = []
        if "HealthChecks" in response:
            health_checks = response["HealthChecks"]

        if not health_checks:
            print("✅ No health checks found")
            return []

        health_check_details = []
        total_monthly_cost = 0

        for hc in health_checks:
            hc_id = hc["Id"]
            hc_config = {}
            if "HealthCheckConfig" in hc:
                hc_config = hc["HealthCheckConfig"]
            hc_type = hc_config.get("Type")

            # Health checks cost $0.50/month each
            monthly_cost = 0.50
            total_monthly_cost += monthly_cost

            print(f"Health Check: {hc_id}")
            print(f"  Type: {hc_type}")
            print(f"  Monthly Cost: ${monthly_cost:.2f}")

            if hc_type in {"HTTP", "HTTPS"}:
                fqdn = hc_config.get("FullyQualifiedDomainName")
                port = hc_config.get("Port")
                path = hc_config.get("ResourcePath")
                print(f"  Target: {hc_type.lower()}://{fqdn}:{port}{path}")

            health_check_details.append({"id": hc_id, "type": hc_type, "monthly_cost": monthly_cost})
            print()

        print("📊 Health Checks Summary:")
        print(f"  Total health checks: {len(health_checks)}")
        print(f"  Estimated monthly cost: ${total_monthly_cost:.2f}")

    except ClientError as e:
        print(f"❌ Error auditing health checks: {e}")
        return []

    return health_check_details


def audit_route53_resolver_endpoints():
    """Audit Route 53 Resolver endpoints"""
    print("\n🔍 Auditing Route 53 Resolver Endpoints")
    print("=" * 80)

    try:
        route53resolver = create_route53resolver_client()

        # Get resolver endpoints
        response = route53resolver.list_resolver_endpoints()
        endpoints = []
        if "ResolverEndpoints" in response:
            endpoints = response["ResolverEndpoints"]

        if not endpoints:
            print("✅ No resolver endpoints found")
            return []

        endpoint_details = []
        total_monthly_cost = 0

        for endpoint in endpoints:
            endpoint_id = endpoint["Id"]
            endpoint_name = endpoint.get("Name")
            direction = endpoint.get("Direction")
            status = endpoint.get("Status")

            # Resolver endpoints cost ~$0.125/hour = ~$90/month
            monthly_cost = 90.0
            total_monthly_cost += monthly_cost

            print(f"Resolver Endpoint: {endpoint_name}")
            print(f"  ID: {endpoint_id}")
            print(f"  Direction: {direction}")
            print(f"  Status: {status}")
            print(f"  Monthly Cost: ${monthly_cost:.2f}")

            endpoint_details.append(
                {
                    "id": endpoint_id,
                    "name": endpoint_name,
                    "direction": direction,
                    "status": status,
                    "monthly_cost": monthly_cost,
                }
            )
            print()

        print("📊 Resolver Endpoints Summary:")
        print(f"  Total endpoints: {len(endpoints)}")
        print(f"  Estimated monthly cost: ${total_monthly_cost:.2f}")

    except ClientError as e:
        print(f"❌ Error auditing resolver endpoints: {e}")
        return []

    return endpoint_details


def _print_cost_breakdown(
    hosted_zones,
    health_checks,
    resolver_endpoints,
    *,
    total_hosted_zone_cost,
    total_health_check_cost,
    total_resolver_cost,
    total_estimated_cost,
):
    """Print Route 53 cost breakdown."""
    print("\n" + "=" * 80)
    print("🎯 ROUTE 53 COST BREAKDOWN")
    print("=" * 80)

    print(f"Hosted Zones: ${total_hosted_zone_cost:.2f}/month ({len(hosted_zones)} zones)")
    print(f"Health Checks: ${total_health_check_cost:.2f}/month ({len(health_checks)} checks)")
    print(f"Resolver Endpoints: ${total_resolver_cost:.2f}/month " f"({len(resolver_endpoints)} endpoints)")
    print(f"Total Estimated: ${total_estimated_cost:.2f}/month")
    print("Your Reported Cost: $1.57")

    print("\n💡 COST ANALYSIS:")
    if abs(total_estimated_cost - 1.57) < COST_VARIANCE_THRESHOLD:
        print("  ✅ Estimated cost closely matches reported cost")
    else:
        print("  ⚠️  Estimated cost differs from reported cost")


def _print_optimization_opportunities(hosted_zones, health_checks, resolver_endpoints):
    """Print optimization opportunities."""
    print("\n📋 OPTIMIZATION OPPORTUNITIES:")

    if hosted_zones:
        print(f"  Hosted Zones ({len(hosted_zones)} zones):")
        for zone in hosted_zones:
            if zone["record_count"] <= DEFAULT_DNS_RECORD_COUNT:
                print(f"    🗑️  {zone['zone_name']} - appears unused (only default records)")
            else:
                print(f"    ✅ {zone['zone_name']} - has {zone['record_count']} records " "(likely in use)")

    if health_checks:
        print(f"  Health Checks ({len(health_checks)} checks):")
        print("    💡 Review if all health checks are necessary")
        print("    💰 Each health check costs $0.50/month")

    if resolver_endpoints:
        print(f"  Resolver Endpoints ({len(resolver_endpoints)} endpoints):")
        print("    ⚠️  Very expensive! Each endpoint costs ~$90/month")
        print("    🔍 Review if resolver endpoints are actually needed")


def _print_cost_explanation(hosted_zones, health_checks):
    """Print likely explanation for cost."""
    print("\n🎯 LIKELY EXPLANATION FOR $1.57:")
    if len(hosted_zones) == EXPECTED_HOSTED_ZONE_COUNT_1:
        print("  3 hosted zones × $0.50 = $1.50/month")
        print("  Plus DNS queries and other small charges = ~$1.57")
    elif len(hosted_zones) == EXPECTED_HOSTED_ZONE_COUNT_2 and len(health_checks) == EXPECTED_HEALTH_CHECK_COUNT:
        print("  2 hosted zones × $0.50 + 2 health checks × $0.50 = $2.00/month")
        print("  Partial month billing could explain $1.57")
    else:
        print("  Route 53 charges include:")
        print("    - Hosted zones: $0.50/month each")
        print("    - DNS queries: $0.40 per million queries")
        print("    - Health checks: $0.50/month each")


def main():
    """Audit Route53 DNS costs."""
    print("AWS Route 53 Cost Audit")
    print("=" * 80)
    print("Analyzing Route 53 resources that could be costing $1.57...")

    hosted_zones = audit_route53_hosted_zones()
    health_checks = audit_route53_health_checks()
    resolver_endpoints = audit_route53_resolver_endpoints()

    total_hosted_zone_cost = sum(zone["monthly_cost"] for zone in hosted_zones)
    total_health_check_cost = sum(hc["monthly_cost"] for hc in health_checks)
    total_resolver_cost = sum(ep["monthly_cost"] for ep in resolver_endpoints)

    total_estimated_cost = total_hosted_zone_cost + total_health_check_cost + total_resolver_cost

    _print_cost_breakdown(
        hosted_zones,
        health_checks,
        resolver_endpoints,
        total_hosted_zone_cost=total_hosted_zone_cost,
        total_health_check_cost=total_health_check_cost,
        total_resolver_cost=total_resolver_cost,
        total_estimated_cost=total_estimated_cost,
    )
    _print_optimization_opportunities(hosted_zones, health_checks, resolver_endpoints)
    _print_cost_explanation(hosted_zones, health_checks)


if __name__ == "__main__":
    main()
