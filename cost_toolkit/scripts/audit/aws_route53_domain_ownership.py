#!/usr/bin/env python3
"""Verify Route53 domain ownership."""


import boto3
from botocore.exceptions import ClientError


def _get_domain_annual_cost(domain_name):
    """Get estimated annual cost for a domain based on TLD."""
    if domain_name.endswith(".com"):
        return 12.00
    if domain_name.endswith(".org"):
        return 12.00
    if domain_name.endswith(".net"):
        return 12.00
    if domain_name.endswith(".report"):
        return 25.00
    return 15.00


def _process_single_domain(route53domains, domain):
    """Process a single domain and return its details."""
    domain_name = domain.get("DomainName")
    expiry = domain.get("Expiry")
    auto_renew = domain.get("AutoRenew")

    print(f"Domain: {domain_name}")
    print(f"  Expiry: {expiry}")
    print(f"  Auto-renew: {auto_renew}")

    try:
        domain_detail = route53domains.get_domain_detail(DomainName=domain_name)
        registrar = domain_detail.get("RegistrarName")
        status = []
        if "StatusList" in domain_detail:
            status = domain_detail["StatusList"]
        nameservers = []
        if "Nameservers" in domain_detail:
            nameservers = domain_detail["Nameservers"]

        print(f"  Registrar: {registrar}")
        print(f"  Status: {', '.join(status) if status else 'Unknown'}")
        print("  Nameservers:")
        for ns in nameservers:
            ns_name = ns.get("Name")
            print(f"    {ns_name}")

        annual_cost = _get_domain_annual_cost(domain_name)
        print(f"  Estimated annual cost: ${annual_cost:.2f}")
        print()

    except ClientError as e:
        print(f"  ❌ Error getting domain details: {e}")
        print()
        return None
    return {
        "domain_name": domain_name,
        "expiry": expiry,
        "auto_renew": auto_renew,
        "registrar": registrar,
        "status": status,
        "nameservers": nameservers,
        "annual_cost": annual_cost,
    }


def check_route53_registered_domains():
    """Check domains registered through Route 53"""
    print("\n🏠 Checking Route 53 Registered Domains")
    print("=" * 80)

    try:
        route53domains = boto3.client("route53domains", region_name="us-east-1")
        domains_response = route53domains.list_domains()
        domains = []
        if "Domains" in domains_response:
            domains = domains_response["Domains"]

        if not domains:
            print("✅ No domains registered through Route 53")
            return []

        domain_details = [detail for domain in domains if (detail := _process_single_domain(route53domains, domain)) is not None]
        total_annual_cost = sum(d["annual_cost"] for d in domain_details)

        print("📊 Domain Registration Summary:")
        print(f"  Total registered domains: {len(domains)}")
        print(f"  Estimated total annual cost: ${total_annual_cost:.2f}")

    except ClientError as e:
        print(f"❌ Error checking registered domains: {e}")
        return []

    return domain_details


def check_current_hosted_zones():
    """Check current hosted zones (after cleanup)"""
    print("\n🌐 Current Route 53 Hosted Zones")
    print("=" * 80)

    try:
        route53 = boto3.client("route53")

        # Get all hosted zones
        response = route53.list_hosted_zones()
        hosted_zones = []
        if "HostedZones" in response:
            hosted_zones = response["HostedZones"]

        if not hosted_zones:
            print("✅ No hosted zones found")
            return []

        zone_details = []

        for zone in hosted_zones:
            zone_id = zone["Id"].split("/")[-1]  # Remove /hostedzone/ prefix
            zone_name = zone["Name"]
            config = {}
            if "Config" in zone:
                config = zone["Config"]
            is_private = config.get("PrivateZone")
            record_count = zone.get("ResourceRecordSetCount")

            print(f"Hosted Zone: {zone_name}")
            print(f"  Zone ID: {zone_id}")
            print(f"  Type: {'Private' if is_private else 'Public'}")
            print(f"  Record Count: {record_count}")
            print("  Monthly Cost: $0.50")

            zone_details.append(
                {
                    "zone_name": zone_name,
                    "zone_id": zone_id,
                    "is_private": is_private,
                    "record_count": record_count,
                }
            )
            print()

        print("📊 Hosted Zones Summary:")
        print(f"  Total zones: {len(hosted_zones)}")
        print(f"  Monthly cost: ${len(hosted_zones) * 0.50:.2f}")

    except ClientError as e:
        print(f"❌ Error checking hosted zones: {e}")
        return []

    return zone_details


def _print_ownership_analysis(registered_domains, hosted_zones):
    """Print domain ownership analysis."""
    print("\n" + "=" * 80)
    print("🎯 DOMAIN OWNERSHIP ANALYSIS")
    print("=" * 80)

    if registered_domains:
        print("✅ You OWN these domains through Route 53:")
        for domain in registered_domains:
            print(f"  {domain['domain_name']} (expires: {domain['expiry']})")
    else:
        print("❌ No domains registered through Route 53")
        print("   Your domains may be registered elsewhere (GoDaddy, Namecheap, etc.)")

    if hosted_zones:
        print("\n🌐 You have DNS hosting for:")
        for zone in hosted_zones:
            print(f"  {zone['zone_name']} (Route 53 hosted zone)")


def _print_cost_breakdown(registered_domains, hosted_zones):
    """Print cost breakdown."""
    print("\n💰 COST BREAKDOWN:")

    if registered_domains:
        total_registration_cost = sum(d["annual_cost"] for d in registered_domains)
        print(f"  Domain registration: ${total_registration_cost:.2f}/year")
    else:
        print("  Domain registration: $0/year (registered elsewhere)")

    if hosted_zones:
        monthly_hosting_cost = len(hosted_zones) * 0.50
        annual_hosting_cost = monthly_hosting_cost * 12
        print(f"  DNS hosting: ${monthly_hosting_cost:.2f}/month (${annual_hosting_cost:.2f}/year)")
    else:
        print("  DNS hosting: $0/month")


def _print_recommendations(registered_domains, hosted_zones):
    """Print recommendations."""
    print("\n📋 RECOMMENDATIONS:")

    if not registered_domains and hosted_zones:
        print("  🔍 Your domains are likely registered elsewhere")
        print("  💡 You can keep using Route 53 for DNS even if domains are registered elsewhere")
        print("  💰 Consider moving DNS to free providers like Cloudflare to save money")

    if registered_domains:
        print(f"  ✅ You own {len(registered_domains)} domain(s) through Route 53")
        print("  🔄 These will auto-renew unless you disable it")
        print("  💡 You can transfer DNS hosting elsewhere while keeping registration here")


def main():
    """Analyze Route53 domain ownership."""
    print("AWS Route 53 Domain Ownership Analysis")
    print("=" * 80)
    print("Checking domain registration vs DNS hosting...")

    registered_domains = check_route53_registered_domains()
    hosted_zones = check_current_hosted_zones()

    _print_ownership_analysis(registered_domains, hosted_zones)
    _print_cost_breakdown(registered_domains, hosted_zones)
    _print_recommendations(registered_domains, hosted_zones)


if __name__ == "__main__":
    main()
