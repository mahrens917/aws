#!/usr/bin/env python3
"""
AWS Network Interface Audit Script
Identifies unused network interfaces across all regions for cleanup.
"""

import boto3
from botocore.exceptions import ClientError

from cost_toolkit.common.aws_common import get_resource_tags
from cost_toolkit.common.credential_utils import setup_aws_credentials
from cost_toolkit.scripts.aws_ec2_operations import get_all_regions

# boto3 used for per-region clients in audit_network_interfaces_in_region


def _build_interface_info(eni):
    """Build interface information dictionary from network interface data."""
    interface_id = eni["NetworkInterfaceId"]
    status = eni["Status"]
    interface_type = eni.get("InterfaceType")
    attachment = {}
    if "Attachment" in eni:
        attachment = eni["Attachment"]

    tags = get_resource_tags(eni)
    name = tags.get("Name")

    association = {}
    if "Association" in eni:
        association = eni["Association"]
    return {
        "interface_id": interface_id,
        "name": name,
        "status": status,
        "type": interface_type,
        "vpc_id": eni.get("VpcId"),
        "subnet_id": eni.get("SubnetId"),
        "private_ip": eni.get("PrivateIpAddress"),
        "public_ip": association.get("PublicIp"),
        "attached_to": attachment.get("InstanceId"),
        "attachment_status": attachment.get("Status"),
        "description": eni.get("Description"),
        "tags": tags,
    }


def _categorize_interface(status, attachment):
    """Determine if interface is unused or attached."""
    if status == "available" and not attachment:
        return "unused"
    return "attached"


def audit_network_interfaces_in_region(region_name, aws_access_key_id, aws_secret_access_key):
    """Audit network interfaces in a specific region"""
    try:
        ec2 = boto3.client(
            "ec2",
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        # Get all network interfaces
        response = ec2.describe_network_interfaces()
        network_interfaces = response["NetworkInterfaces"]

        if not network_interfaces:
            return None

        region_data = {
            "region": region_name,
            "total_interfaces": len(network_interfaces),
            "unused_interfaces": [],
            "attached_interfaces": [],
            "interface_details": [],
        }

        for eni in network_interfaces:
            interface_info = _build_interface_info(eni)
            region_data["interface_details"].append(interface_info)

            # Categorize interfaces
            attachment = {}
            if "Attachment" in eni:
                attachment = eni["Attachment"]
            category = _categorize_interface(eni["Status"], attachment)
            if category == "unused":
                region_data["unused_interfaces"].append(interface_info)
            else:
                region_data["attached_interfaces"].append(interface_info)

    except ClientError as e:
        print(f"❌ Error auditing network interfaces in {region_name}: {str(e)}")
        return None

    return region_data


def _print_unused_interfaces(regions_with_interfaces):
    """Print unused network interfaces details."""
    print("⚠️  UNUSED NETWORK INTERFACES FOUND")
    print("=" * 40)

    for region_data in regions_with_interfaces:
        if region_data["unused_interfaces"]:
            print(f"\n📍 Region: {region_data['region']}")
            print("-" * 30)

            for interface in region_data["unused_interfaces"]:
                print(f"   🔓 Interface: {interface['interface_id']}")
                print(f"      Name: {interface['name']}")
                print(f"      Type: {interface['type']}")
                print(f"      VPC: {interface['vpc_id']}")
                print(f"      Subnet: {interface['subnet_id']}")
                print(f"      Private IP: {interface['private_ip']}")
                print(f"      Description: {interface['description']}")
                print(f"      Status: {interface['status']}")
                print()

    print("💡 CLEANUP RECOMMENDATIONS:")
    print("   • Unused network interfaces can be safely deleted")
    print("   • No cost impact but improves account hygiene")
    print("   • Consider creating cleanup script for bulk deletion")


def _print_attached_interfaces(regions_with_interfaces):
    """Print attached network interfaces details."""
    print("\n" + "=" * 60)
    print("🔗 ATTACHED NETWORK INTERFACES DETAILS")
    print("=" * 60)

    for region_data in regions_with_interfaces:
        if region_data["attached_interfaces"]:
            print(f"\n📍 Region: {region_data['region']}")
            print("-" * 30)

            for interface in region_data["attached_interfaces"]:
                print(f"   🔗 Interface: {interface['interface_id']}")
                print(f"      Name: {interface['name']}")
                print(f"      Type: {interface['type']}")
                print(f"      Attached to: {interface['attached_to']}")
                print(f"      Status: {interface['status']}")
                print(f"      VPC: {interface['vpc_id']}")
                print(f"      Private IP: {interface['private_ip']}")
                print(f"      Public IP: {interface['public_ip']}")
                print()


def main():
    """Main execution function"""
    print("AWS Network Interface Audit")
    print("=" * 60)

    try:
        aws_access_key_id, aws_secret_access_key = setup_aws_credentials()

        regions = get_all_regions()
        print(f"🌍 Scanning {len(regions)} AWS regions for network interfaces...")
        print()

        total_interfaces = 0
        total_unused = 0
        regions_with_interfaces = []

        for region in regions:
            print(f"🔍 Checking region: {region}")
            region_data = audit_network_interfaces_in_region(region, aws_access_key_id, aws_secret_access_key)

            if region_data:
                regions_with_interfaces.append(region_data)
                total_interfaces += region_data["total_interfaces"]
                total_unused += len(region_data["unused_interfaces"])

                print(f"   📊 Found {region_data['total_interfaces']} network interfaces")
                print(f"   🔓 Unused: {len(region_data['unused_interfaces'])}")
                print(f"   🔗 Attached: {len(region_data['attached_interfaces'])}")
            else:
                print("   ✅ No network interfaces found")
            print()

        print("=" * 60)
        print("📋 NETWORK INTERFACE AUDIT SUMMARY")
        print("=" * 60)
        print(f"🌍 Regions scanned: {len(regions)}")
        print(f"📊 Total network interfaces: {total_interfaces}")
        print(f"🔓 Unused interfaces: {total_unused}")
        print(f"🔗 Attached interfaces: {total_interfaces - total_unused}")
        print()

        if total_unused > 0:
            _print_unused_interfaces(regions_with_interfaces)
        else:
            print("🎉 No unused network interfaces found!")
            print("   Your AWS account has clean network interface configuration.")

        if total_interfaces > total_unused:
            _print_attached_interfaces(regions_with_interfaces)

    except ClientError as e:
        print(f"❌ Critical error during network interface audit: {str(e)}")
        raise


if __name__ == "__main__":
    main()
