#!/usr/bin/env python3
"""
AWS Elastic IP Audit Script
Audits all Elastic IP addresses across all AWS regions to identify:
- Allocated but unassociated Elastic IPs (these incur charges)
- Associated Elastic IPs and their attachments
- Cost implications and recommendations

Unassociated Elastic IPs cost $0.005 per hour ($3.65/month each)
"""

import sys

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_ec2_client, load_credentials_from_env
from cost_toolkit.scripts.aws_ec2_operations import (
    describe_addresses,
    get_all_regions,
    get_instance_name,
)


def audit_elastic_ips_in_region(region, aws_access_key_id, aws_secret_access_key):
    """Audit Elastic IPs in a specific region"""
    try:
        addresses = describe_addresses(
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        if not addresses:
            return None

        region_data = {
            "region": region,
            "total_eips": len(addresses),
            "associated_eips": [],
            "unassociated_eips": [],
            "total_monthly_cost": 0,
        }

        for address in addresses:
            eip_data = {
                "allocation_id": address.get("AllocationId"),
                "public_ip": address.get("PublicIp"),
                "domain": address.get("Domain"),
                "instance_id": address.get("InstanceId"),
                "association_id": address.get("AssociationId"),
                "network_interface_id": address.get("NetworkInterfaceId"),
                "private_ip": address.get("PrivateIpAddress"),
                "tags": address.get("Tags") or [],
            }

            # Check if EIP is associated
            if eip_data["instance_id"] or eip_data["network_interface_id"]:
                region_data["associated_eips"].append(eip_data)
            else:
                # Unassociated EIPs cost $0.005/hour = $3.65/month
                eip_data["monthly_cost"] = 3.65
                region_data["unassociated_eips"].append(eip_data)
                region_data["total_monthly_cost"] += 3.65

    except ClientError as e:
        print(f"   ❌ Error auditing region {region}: {e}")
        return None

    return region_data


def _scan_all_regions(regions, aws_access_key_id, aws_secret_access_key):
    """Scan all regions for Elastic IPs."""
    total_eips = 0
    total_unassociated = 0
    total_monthly_cost = 0
    regions_with_eips = []

    for region in regions:
        print(f"🔍 Auditing region: {region}")

        region_data = audit_elastic_ips_in_region(region, aws_access_key_id, aws_secret_access_key)

        if region_data:
            regions_with_eips.append(region_data)
            total_eips += region_data["total_eips"]
            total_unassociated += len(region_data["unassociated_eips"])
            total_monthly_cost += region_data["total_monthly_cost"]

            print(f"   📍 Found {region_data['total_eips']} Elastic IP(s)")
            if region_data["unassociated_eips"]:
                print(
                    f"   ⚠️  {len(region_data['unassociated_eips'])} unassociated "
                    f"(costing ${region_data['total_monthly_cost']:.2f}/month)"
                )
        else:
            print("   ✅ No Elastic IPs found")

    return regions_with_eips, total_eips, total_unassociated, total_monthly_cost


def _print_associated_eips(region_data, aws_access_key_id, aws_secret_access_key):
    """Print associated EIPs for a region."""
    if not region_data["associated_eips"]:
        return

    print(f"✅ Associated Elastic IPs ({len(region_data['associated_eips'])}):")

    ec2_client = create_ec2_client(
        region=region_data["region"],
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    for eip in region_data["associated_eips"]:
        attachment = "Unknown"
        if eip["instance_id"]:
            instance_name = get_instance_name(ec2_client, eip["instance_id"])
            attachment = f"Instance: {eip['instance_id']} ({instance_name})"
        elif eip["network_interface_id"]:
            attachment = f"Network Interface: {eip['network_interface_id']}"

        print(f"   • {eip['public_ip']} → {attachment}")


def _print_unassociated_eips(region_data):
    """Print unassociated EIPs for a region."""
    if not region_data["unassociated_eips"]:
        return

    eip_count = len(region_data["unassociated_eips"])
    print(f"⚠️  Unassociated Elastic IPs ({eip_count}) - COSTING MONEY:")
    for eip in region_data["unassociated_eips"]:
        tags_str = ""
        if eip["tags"]:
            tag_names = [f"{tag['Key']}:{tag['Value']}" for tag in eip["tags"]]
            tags_str = f" (Tags: {', '.join(tag_names)})"

        print(f"   • {eip['public_ip']} (ID: {eip['allocation_id']}) - " f"${eip['monthly_cost']:.2f}/month{tags_str}")


def _print_cleanup_recommendations(regions_with_eips, total_monthly_cost):
    """Print cleanup recommendations and commands."""
    print("💡 RECOMMENDATIONS:")
    print("=" * 80)
    print("1. Release unused Elastic IPs to eliminate charges")
    print("2. Associate Elastic IPs with running instances if needed")
    print("3. Consider using dynamic public IPs for non-production workloads")
    print()
    print("🔧 Commands to release unassociated Elastic IPs:")
    for region_data in regions_with_eips:
        if region_data["unassociated_eips"]:
            for eip in region_data["unassociated_eips"]:
                print(f"   aws ec2 release-address --allocation-id {eip['allocation_id']} " f"--region {region_data['region']}")
    print()
    print(f"💰 Total potential monthly savings: ${total_monthly_cost:.2f}")
    print(f"💰 Total potential annual savings: ${total_monthly_cost * 12:.2f}")


def audit_all_elastic_ips():
    """Audit Elastic IPs across all AWS regions"""
    aws_access_key_id, aws_secret_access_key = load_credentials_from_env()

    print("AWS Elastic IP Audit")
    print("=" * 80)
    print("Scanning all regions for Elastic IP addresses...")
    print("⚠️  Note: Unassociated Elastic IPs cost $0.005/hour ($3.65/month each)")
    print()

    regions = get_all_regions(aws_access_key_id, aws_secret_access_key)
    regions_with_eips, total_eips, total_unassociated, total_monthly_cost = _scan_all_regions(
        regions, aws_access_key_id, aws_secret_access_key
    )

    print()
    print("=" * 80)
    print("🎯 ELASTIC IP AUDIT RESULTS")
    print("=" * 80)

    if not regions_with_eips:
        print("✅ No Elastic IPs found in any region")
        print("💰 No Elastic IP costs detected")
        return

    print(f"📊 Total Elastic IPs found: {total_eips}")
    print(f"⚠️  Unassociated Elastic IPs: {total_unassociated}")
    print(f"💰 Monthly cost from unassociated EIPs: ${total_monthly_cost:.2f}")
    print(f"💰 Annual cost from unassociated EIPs: ${total_monthly_cost * 12:.2f}")
    print()

    for region_data in regions_with_eips:
        print(f"📍 Region: {region_data['region']}")
        print("-" * 40)

        _print_associated_eips(region_data, aws_access_key_id, aws_secret_access_key)
        _print_unassociated_eips(region_data)

        print()

    if total_unassociated > 0:
        _print_cleanup_recommendations(regions_with_eips, total_monthly_cost)


def main():
    """Main function."""
    try:
        audit_all_elastic_ips()
    except ClientError as e:
        print(f"❌ Script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
