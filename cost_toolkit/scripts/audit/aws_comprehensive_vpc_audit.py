#!/usr/bin/env python3
"""
AWS Comprehensive VPC Audit Script
Audits all VPC resources across regions to identify unused components that can be cleaned up:
- VPCs and their usage
- Subnets and their attachments
- Security Groups and their usage
- Network ACLs
- Internet Gateways
- Route Tables
- Network Interfaces
- VPC Endpoints

Identifies orphaned resources that may be left over from terminated instances.
"""

import sys

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import extract_tag_value, get_all_aws_regions
from cost_toolkit.common.credential_utils import setup_aws_credentials
from cost_toolkit.scripts.audit.vpc_audit_helpers import (
    _collect_unused_network_interfaces,
    _collect_unused_security_groups,
    _collect_vpc_endpoints,
    _collect_vpc_internet_gateways,
    _collect_vpc_nat_gateways,
    _collect_vpc_route_tables,
    _collect_vpc_security_groups,
    _collect_vpc_subnets,
    _get_active_instances,
)


def get_resource_name(tags):
    """Extract Name tag from resource tags. Delegates to canonical implementation."""
    resource_dict = {"Tags": tags} if tags else {}
    return extract_tag_value(resource_dict, "Name")


def audit_vpc_resources_in_region(region, aws_access_key_id, aws_secret_access_key):
    """Audit VPC resources in a specific region"""
    try:
        ec2_client = create_client(
            "ec2",
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        region_data = {
            "region": region,
            "vpcs": [],
            "unused_security_groups": [],
            "unused_network_interfaces": [],
            "vpc_endpoints": [],
            "internet_gateways": [],
            "nat_gateways": [],
            "route_tables": [],
            "network_acls": [],
        }

        vpcs = []
        vpcs_response = ec2_client.describe_vpcs()
        if "Vpcs" in vpcs_response:
            vpcs = vpcs_response["Vpcs"]

        if not vpcs:
            return None

        active_instances = _get_active_instances(ec2_client)

        for vpc in vpcs:
            vpc_id = vpc["VpcId"]
            vpc_instances = [inst for inst in active_instances if inst["vpc_id"] == vpc_id]

            vpc_data = {
                "vpc_id": vpc_id,
                "name": get_resource_name(vpc.get("Tags")),
                "cidr": vpc["CidrBlock"],
                "is_default": vpc.get("IsDefault"),
                "state": vpc["State"],
                "instances": vpc_instances,
                "instance_count": len(vpc_instances),
                "subnets": _collect_vpc_subnets(ec2_client, vpc_id),
                "security_groups": _collect_vpc_security_groups(ec2_client, vpc_id),
                "route_tables": _collect_vpc_route_tables(ec2_client, vpc_id),
                "internet_gateways": _collect_vpc_internet_gateways(ec2_client, vpc_id),
                "nat_gateways": _collect_vpc_nat_gateways(ec2_client, vpc_id),
            }

            region_data["vpcs"].append(vpc_data)

        region_data["unused_security_groups"] = _collect_unused_security_groups(ec2_client)
        region_data["unused_network_interfaces"] = _collect_unused_network_interfaces(ec2_client)
        region_data["vpc_endpoints"] = _collect_vpc_endpoints(ec2_client)

    except ClientError as e:
        print(f"   ❌ Error auditing region {region}: {e}")
        return None

    return region_data


def _print_vpc_details(vpc):
    """Print details for a single VPC."""
    print(f"🏠 VPC: {vpc['vpc_id']} ({vpc['name']})")
    print(f"   CIDR: {vpc['cidr']}")
    print(f"   Default VPC: {vpc['is_default']}")
    print(f"   Active instances: {vpc['instance_count']}")

    if vpc["instances"]:
        for instance in vpc["instances"]:
            print(f"     • {instance['instance_id']} ({instance['name']}) - {instance['state']}")

    print(f"   Subnets: {len(vpc['subnets'])}")
    print(f"   Security Groups: {len(vpc['security_groups'])}")
    print(f"   Route Tables: {len(vpc['route_tables'])}")
    print(f"   Internet Gateways: {len(vpc['internet_gateways'])}")
    print(f"   NAT Gateways: {len(vpc['nat_gateways'])}")
    print()


def _print_unused_resources(region_data):
    """Print unused resources for a region."""
    if region_data["unused_security_groups"]:
        print("🔶 Unused Security Groups (can be deleted):")
        for sg in region_data["unused_security_groups"]:
            print(f"   • {sg['group_id']} ({sg['name']}) in VPC {sg['vpc_id']}")

    if region_data["unused_network_interfaces"]:
        print("🔶 Unused Network Interfaces (can be deleted):")
        for eni in region_data["unused_network_interfaces"]:
            print(f"   • {eni['interface_id']} ({eni['name']}) - {eni['private_ip']}")

    if region_data["vpc_endpoints"]:
        print("🔗 VPC Endpoints (review if needed):")
        for vpce in region_data["vpc_endpoints"]:
            print(f"   • {vpce['endpoint_id']} - {vpce['service_name']} ({vpce['state']})")

    print()


def _print_cleanup_recommendations(total_unused_resources):
    """Print cleanup recommendations."""
    if total_unused_resources > 0:
        print("💡 CLEANUP RECOMMENDATIONS:")
        print("=" * 80)
        print("1. Delete unused security groups (no cost but good hygiene)")
        print("2. Delete unused network interfaces (no cost but good hygiene)")
        print("3. Review VPC endpoints - some may have hourly charges")
        print("4. Consider consolidating VPCs if you have multiple unused ones")
        print()
        print("🔧 Cleanup commands will be provided after confirmation")


def _has_region_resources(region_data):
    """Check if region has any resources worth reporting."""
    if not region_data:
        return False
    return bool(
        region_data["vpcs"]
        or region_data["unused_security_groups"]
        or region_data["unused_network_interfaces"]
        or region_data["vpc_endpoints"]
    )


def _print_region_summary(region_data):
    """Print summary for a single region."""
    print(f"   📍 Found {len(region_data['vpcs'])} VPC(s)")
    if region_data["unused_security_groups"]:
        print(f"   🔶 {len(region_data['unused_security_groups'])} unused security groups")
    if region_data["unused_network_interfaces"]:
        print(f"   🔶 {len(region_data['unused_network_interfaces'])} unused network interfaces")
    if region_data["vpc_endpoints"]:
        print(f"   🔗 {len(region_data['vpc_endpoints'])} VPC endpoints")


def _print_detailed_results(regions_with_resources):
    """Print detailed results for all regions with resources."""
    for region_data in regions_with_resources:
        region = region_data["region"]
        print(f"📍 Region: {region}")
        print("-" * 50)

        for vpc in region_data["vpcs"]:
            _print_vpc_details(vpc)

        _print_unused_resources(region_data)


def audit_comprehensive_vpc():
    """Audit VPC resources across key AWS regions"""
    aws_access_key_id, aws_secret_access_key = setup_aws_credentials()

    print("AWS Comprehensive VPC Audit")
    print("=" * 80)
    print("Analyzing VPC resources and identifying cleanup opportunities...")
    print()

    regions = get_all_aws_regions()

    total_vpcs = 0
    total_unused_resources = 0
    regions_with_resources = []

    for region in regions:
        print(f"🔍 Auditing region: {region}")

        region_data = audit_vpc_resources_in_region(region, aws_access_key_id, aws_secret_access_key)

        if _has_region_resources(region_data):
            regions_with_resources.append(region_data)
            total_vpcs += len(region_data["vpcs"])
            total_unused_resources += len(region_data["unused_security_groups"]) + len(region_data["unused_network_interfaces"])
            _print_region_summary(region_data)
        else:
            print("   ✅ No VPC resources found")

    print()
    print("=" * 80)
    print("🎯 COMPREHENSIVE VPC AUDIT RESULTS")
    print("=" * 80)

    if not regions_with_resources:
        print("✅ No VPC resources found in audited regions")
        return

    print(f"📊 Total VPCs found: {total_vpcs}")
    print(f"🔶 Total unused resources: {total_unused_resources}")
    print()

    _print_detailed_results(regions_with_resources)
    _print_cleanup_recommendations(total_unused_resources)


def main():
    """Main function."""
    try:
        audit_comprehensive_vpc()
    except ClientError as e:
        print(f"❌ Script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
