#!/usr/bin/env python3
"""Audit VPC configuration and resources."""

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import get_all_aws_regions, list_elastic_ip_addresses


def _process_elastic_ip_address(addr, region_name):
    """Process a single elastic IP address and return its info."""
    addr_tags = []
    if "Tags" in addr:
        addr_tags = addr["Tags"]
    ip_info = {
        "region": region_name,
        "public_ip": addr.get("PublicIp"),
        "allocation_id": addr.get("AllocationId"),
        "association_id": addr.get("AssociationId"),
        "instance_id": addr.get("InstanceId"),
        "network_interface_id": addr.get("NetworkInterfaceId"),
        "domain": addr.get("Domain"),
        "tags": addr_tags,
    }

    if "AssociationId" in addr:
        status = "🟢 IN USE"
        cost_per_hour = 0.005
    else:
        status = "🔴 IDLE (COSTING MONEY)"
        cost_per_hour = 0.005

    monthly_cost = cost_per_hour * 24 * 30
    ip_info["status"] = status
    ip_info["monthly_cost_estimate"] = monthly_cost

    return ip_info, monthly_cost


def _print_elastic_ip_details(ip_info):
    """Print details for a single elastic IP."""
    print(f"Public IP: {ip_info['public_ip']}")
    print(f"  Status: {ip_info['status']}")
    print(f"  Allocation ID: {ip_info['allocation_id']}")
    if ip_info["instance_id"]:
        associated_with = ip_info["instance_id"]
    elif ip_info["network_interface_id"]:
        associated_with = ip_info["network_interface_id"]
    else:
        associated_with = "Nothing"
    print(f"  Associated with: {associated_with}")
    print(f"  Domain: {ip_info['domain']}")
    print(f"  Estimated monthly cost: ${ip_info['monthly_cost_estimate']:.2f}")

    if ip_info["tags"]:
        print("  Tags:")
        for tag in ip_info["tags"]:
            print(f"    {tag['Key']}: {tag['Value']}")
    print()


def audit_elastic_ips_in_region(region_name):
    """Audit Elastic IP addresses in a specific region"""
    print(f"\n🔍 Auditing Elastic IPs in {region_name}")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)

        addresses = list_elastic_ip_addresses(ec2)

        if not addresses:
            print(f"✅ No Elastic IP addresses found in {region_name}")
            return []

        region_summary = []
        total_cost_estimate = 0

        for addr in addresses:
            ip_info, monthly_cost = _process_elastic_ip_address(addr, region_name)
            total_cost_estimate += monthly_cost
            _print_elastic_ip_details(ip_info)
            region_summary.append(ip_info)

        print(f"📊 Region Summary for {region_name}:")
        print(f"  Total Elastic IPs: {len(addresses)}")
        print(f"  Estimated monthly cost: ${total_cost_estimate:.2f}")

    except ClientError as e:
        if e.response["Error"]["Code"] == "UnauthorizedOperation":
            print(f"❌ No permission to access {region_name}")
        else:
            print(f"❌ Error auditing {region_name}: {e}")
        return []

    return region_summary


def audit_nat_gateways_in_region(region_name):
    """Audit NAT Gateways in a specific region"""
    print(f"\n🔍 Auditing NAT Gateways in {region_name}")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)

        response = ec2.describe_nat_gateways()
        nat_gateways = []
        if "NatGateways" in response:
            nat_gateways = response["NatGateways"]

        if not nat_gateways:
            print(f"✅ No NAT Gateways found in {region_name}")
            return []

        region_summary = []

        for nat in nat_gateways:
            nat_tags = []
            if "Tags" in nat:
                nat_tags = nat["Tags"]
            nat_info = {
                "region": region_name,
                "nat_gateway_id": nat.get("NatGatewayId"),
                "state": nat.get("State"),
                "vpc_id": nat.get("VpcId"),
                "subnet_id": nat.get("SubnetId"),
                "create_time": nat.get("CreateTime"),
                "tags": nat_tags,
            }

            # NAT Gateway costs approximately $0.045/hour + data processing
            monthly_cost_estimate = 0.045 * 24 * 30  # ~$32.40/month base cost

            print(f"NAT Gateway: {nat_info['nat_gateway_id']}")
            print(f"  State: {nat_info['state']}")
            print(f"  VPC: {nat_info['vpc_id']}")
            print(f"  Subnet: {nat_info['subnet_id']}")
            print(f"  Created: {nat_info['create_time']}")
            print(f"  Estimated monthly cost: ${monthly_cost_estimate:.2f} (base + data processing)")

            if nat_info["tags"]:
                print("  Tags:")
                for tag in nat_info["tags"]:
                    print(f"    {tag['Key']}: {tag['Value']}")

            print()
            region_summary.append(nat_info)

    except ClientError as e:
        print(f"❌ Error auditing NAT Gateways in {region_name}: {e}")
        return []

    return region_summary


def main():
    """Audit VPC resources and costs."""
    print("AWS VPC Cost Audit")
    print("=" * 80)
    print("Analyzing Public IPv4 addresses and other VPC resources that incur costs...")

    # Focus on regions where we saw VPC costs
    regions = get_all_aws_regions()

    all_elastic_ips = []
    all_nat_gateways = []
    total_estimated_cost = 0

    for region in regions:
        elastic_ips = audit_elastic_ips_in_region(region)
        nat_gateways = audit_nat_gateways_in_region(region)

        all_elastic_ips.extend(elastic_ips)
        all_nat_gateways.extend(nat_gateways)

        region_cost = sum(ip["monthly_cost_estimate"] for ip in elastic_ips)
        total_estimated_cost += region_cost

    # Summary
    print("\n" + "=" * 80)
    print("🎯 OVERALL SUMMARY")
    print("=" * 80)

    print(f"Total Elastic IP addresses found: {len(all_elastic_ips)}")
    print(f"Total NAT Gateways found: {len(all_nat_gateways)}")
    print(f"Estimated monthly cost for Elastic IPs: ${total_estimated_cost:.2f}")

    # Categorize IPs
    idle_ips = [ip for ip in all_elastic_ips if "IDLE" in ip["status"]]
    in_use_ips = [ip for ip in all_elastic_ips if "IN USE" in ip["status"]]

    print("\n📊 Elastic IP Breakdown:")
    print(f"  🔴 Idle (costing money): {len(idle_ips)} IPs")
    print(f"  🟢 In use: {len(in_use_ips)} IPs")

    if idle_ips:
        print("\n💰 COST OPTIMIZATION OPPORTUNITY:")
        total_savings = sum(ip["monthly_cost_estimate"] for ip in idle_ips)
        print(f"  Releasing {len(idle_ips)} idle Elastic IPs " f"could save ~${total_savings:.2f}/month")
        print("  These IPs are not associated with any resources and are just costing money.")

    print("\n📋 RECOMMENDATIONS:")
    print("  1. Review idle Elastic IPs - can they be released?")
    print("  2. Consider if all in-use IPs are actually needed")
    print("  3. Note: Released IPs cannot be recovered (you get a new IP if you allocate again)")
    print("  4. Alternative: Keep critical IPs, release unused ones")


if __name__ == "__main__":
    main()
