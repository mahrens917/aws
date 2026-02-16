#!/usr/bin/env python3
"""Setup Route53 domain records for DNS configuration."""

import socket
import sys
from threading import Event

import boto3
from botocore.exceptions import ClientError

from cost_toolkit.scripts.setup.exceptions import (
    AWSAPIError,
    DNSRecordCreationError,
    DNSSetupError,
)
from cost_toolkit.scripts.setup.route53_helpers import (
    _apply_dns_changes,
    _build_existing_records_map,
    _check_dns_records,
    _create_root_domain_change,
    _create_www_subdomain_change,
    _find_hosted_zone,
    _get_nameserver_records,
    _print_dns_status,
)

_WAIT_EVENT = Event()


def get_current_hosted_zone_nameservers(domain_name):
    """Get the nameservers for the current hosted zone"""
    print(f"🔍 Getting nameservers for {domain_name}")

    try:
        route53 = boto3.client("route53")

        target_zone = _find_hosted_zone(route53, domain_name)
        zone_id = target_zone["Id"].split("/")[-1]
        print(f"  Found hosted zone: {zone_id}")

        nameservers = _get_nameserver_records(route53, target_zone["Id"], domain_name)

        print("  Current nameservers:")
        for ns in nameservers:
            print(f"    - {ns}")

    except ClientError as e:
        raise AWSAPIError(e) from e
    return nameservers, zone_id


def update_domain_nameservers_at_registrar(domain_name, nameservers):
    """Update nameservers at the domain registrar"""
    print(f"\n🔧 Updating nameservers at registrar for {domain_name}")

    try:
        route53domains = boto3.client("route53domains", region_name="us-east-1")

        # Check if domain is registered through Route53
        try:
            _ = route53domains.get_domain_detail(DomainName=domain_name)
            print("  Domain is registered through Route53")

            # Update nameservers
            nameserver_list = [{"Name": ns.rstrip(".")} for ns in nameservers]

            print("  Updating to nameservers:")
            for ns in nameserver_list:
                print(f"    - {ns['Name']}")

            response = route53domains.update_domain_nameservers(DomainName=domain_name, Nameservers=nameserver_list)

            operation_id = response.get("OperationId")
            print(f"  ✅ Nameserver update initiated (Operation ID: {operation_id})")
            print("  ⏳ Changes may take up to 48 hours to propagate globally")
        except ClientError as e:
            if "DomainNotFound" in str(e):
                print("  ❌ Domain is NOT registered through Route53")
                print("  📋 You need to manually update nameservers at your registrar:")
                print(f"     Domain: {domain_name}")
                print("     New nameservers:")
                for ns in nameservers:
                    print(f"       - {ns}")
                print("  💡 Log into your domain registrar (GoDaddy, Namecheap, etc.) and update the nameservers")
                return False
            raise
    except ClientError as e:
        print(f"❌ Route53 Domains API error: {e}")
        return False
    else:
        return True


def verify_canva_dns_setup(domain_name, zone_id):
    """Verify the DNS records are properly set up for Canva"""
    print(f"\n🔍 Verifying Canva DNS setup for {domain_name}")

    try:
        route53 = boto3.client("route53")

        records_response = route53.list_resource_record_sets(HostedZoneId=f"/hostedzone/{zone_id}")
        records = []
        if "ResourceRecordSets" in records_response:
            records = records_response["ResourceRecordSets"]

        has_root_a, has_www_a, has_canva_txt, canva_ip = _check_dns_records(records, domain_name)
        all_present = _print_dns_status(has_root_a, has_www_a, has_canva_txt)
    except ClientError as e:
        raise DNSSetupError(e) from e
    return all_present, canva_ip


def create_missing_dns_records(domain_name, zone_id, canva_ip):
    """Create any missing DNS records for Canva"""
    print("\n🔧 Checking and creating missing DNS records")

    try:
        route53 = boto3.client("route53")

        # Get current records
        records_response = route53.list_resource_record_sets(HostedZoneId=f"/hostedzone/{zone_id}")
        records = []
        if "ResourceRecordSets" in records_response:
            records = records_response["ResourceRecordSets"]

        existing_records = _build_existing_records_map(records)

        changes = []

        # Check for root domain A record
        root_change = _create_root_domain_change(domain_name, existing_records, canva_ip)
        if root_change is False:
            return False
        if root_change:
            changes.append(root_change)

        # Check for www subdomain A record
        www_change = _create_www_subdomain_change(domain_name, existing_records, canva_ip)
        if www_change is False:
            return False
        if www_change:
            changes.append(www_change)

        # Apply changes if any
        if changes:
            _apply_dns_changes(route53, zone_id, changes)
        else:
            print("  ✅ All required DNS records already exist")

    except ClientError as e:
        raise DNSRecordCreationError(e) from e
    return True


def verify_dns_resolution(domain_name):
    """Verify DNS resolution for the domain"""
    print(f"\n🧪 Testing DNS resolution for {domain_name}")

    def _resolve(host: str):
        try:
            results = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
            addresses = [info[4][0] for info in results if info[4]]
            return addresses[0] if addresses else None
        except (socket.gaierror, OSError) as exc:
            print(f"  ❌ DNS lookup failed for {host}: {exc}")
            return None

    root_ip = _resolve(domain_name)
    if root_ip:
        print(f"  ✅ {domain_name} resolves to: {root_ip}")
    else:
        print(f"  ❌ {domain_name} does not resolve")

    www_ip = _resolve(f"www.{domain_name}")
    if www_ip:
        print(f"  ✅ www.{domain_name} resolves to: {www_ip}")
    else:
        print(f"  ❌ www.{domain_name} does not resolve")


def main():
    """Configure Route53 DNS records for iwannabenewyork.com domain."""
    domain_name = "iwannabenewyork.com"

    print("AWS Route53 Domain Setup for Canva")
    print("=" * 80)
    print(f"Setting up DNS for: {domain_name}")
    print("Target: Canva website")
    print("=" * 80)

    try:
        # Step 1: Get current hosted zone nameservers
        nameservers, zone_id = get_current_hosted_zone_nameservers(domain_name)

        # Step 2: Verify current DNS setup
        dns_ok, canva_ip = verify_canva_dns_setup(domain_name, zone_id)

        # Step 3: Create missing DNS records if needed
        if not dns_ok:
            if canva_ip:
                create_missing_dns_records(domain_name, zone_id, canva_ip)
            else:
                print("\n❌ Cannot create missing records without Canva IP address")
                print("   Please provide the correct IP address for your Canva site")

        # Step 4: Update nameservers at registrar
        print("\n" + "=" * 80)
        print("NAMESERVER UPDATE")
        print("=" * 80)

        ns_updated = update_domain_nameservers_at_registrar(domain_name, nameservers)

        # Step 5: Test DNS resolution
        if ns_updated:
            print("\n⏳ Waiting 30 seconds for initial DNS propagation...")
            _WAIT_EVENT.wait(30)

        verify_dns_resolution(domain_name)

        # Summary
        print("\n" + "=" * 80)
        print("🎯 SETUP SUMMARY")
        print("=" * 80)

        print(f"✅ Route53 hosted zone configured: {zone_id}")
        print("✅ DNS records verified for Canva")

        if ns_updated:
            print("✅ Nameservers updated at registrar")
            print("⏳ DNS propagation may take up to 48 hours")
        else:
            print("⚠️  Manual nameserver update required at registrar")
            print("   Update these nameservers at your domain registrar:")
            for ns in nameservers:
                print(f"     - {ns}")

        print("\n🌐 Your domain should resolve to your Canva site once DNS propagates")
        print(f"🔗 Test your site: https://{domain_name}")

    except ClientError as e:
        print(f"\n❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
