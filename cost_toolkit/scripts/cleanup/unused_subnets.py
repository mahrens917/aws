#!/usr/bin/env python3
"""Subnet usage analysis and cleanup."""

import boto3
from botocore.exceptions import ClientError


def _collect_used_subnets_from_instances(ec2):
    """Collect subnet IDs from EC2 instances."""
    instances_response = ec2.describe_instances()
    used_subnets = set()

    for reservation in instances_response["Reservations"]:
        for instance in reservation["Instances"]:
            if instance["State"]["Name"] != "terminated":
                if "SubnetId" in instance:
                    used_subnets.add(instance["SubnetId"])

    return used_subnets


def _collect_used_subnets_from_enis(ec2):
    """Collect subnet IDs from network interfaces."""
    eni_response = ec2.describe_network_interfaces()
    used_subnets = set()

    if "NetworkInterfaces" in eni_response:
        for eni in eni_response["NetworkInterfaces"]:
            if "SubnetId" in eni:
                used_subnets.add(eni["SubnetId"])

    return used_subnets


def _collect_used_subnets_from_nat_gateways(ec2):
    """Collect subnet IDs from NAT Gateways."""
    nat_response = ec2.describe_nat_gateways()
    used_subnets = set()

    if "NatGateways" in nat_response:
        for nat in nat_response["NatGateways"]:
            if nat["State"] != "deleted":
                if "SubnetId" in nat:
                    used_subnets.add(nat["SubnetId"])

    return used_subnets


def _collect_used_subnets_from_rds(region_name):
    """Collect subnet IDs from RDS subnet groups."""
    used_subnets = set()
    try:
        rds = boto3.client("rds", region_name=region_name)
        subnet_groups_response = rds.describe_db_subnet_groups()
        if "DBSubnetGroups" in subnet_groups_response:
            for sg in subnet_groups_response["DBSubnetGroups"]:
                if "Subnets" in sg:
                    for subnet in sg["Subnets"]:
                        used_subnets.add(subnet["SubnetIdentifier"])
    except ClientError as e:
        print(f"  Warning: Could not check RDS subnets: {e}")

    return used_subnets


def _extract_subnet_from_az(az):
    """Extract subnet ID from availability zone."""
    return az.get("SubnetId")


def _collect_subnets_from_load_balancers(lb_response):
    """Extract subnet IDs from load balancer response."""
    used_subnets = set()
    load_balancers = lb_response.get("LoadBalancers")
    if not load_balancers:
        return used_subnets
    for lb in load_balancers:
        if "AvailabilityZones" not in lb:
            continue
        for az in lb["AvailabilityZones"]:
            subnet_id = _extract_subnet_from_az(az)
            if subnet_id:
                used_subnets.add(subnet_id)
    return used_subnets


def _collect_used_subnets_from_elb(region_name):
    """Collect subnet IDs from load balancers."""
    try:
        elbv2 = boto3.client("elbv2", region_name=region_name)
        lb_response = elbv2.describe_load_balancers()
    except ClientError as e:
        print(f"  Warning: Could not check ELB subnets: {e}")
        return set()
    else:
        return _collect_subnets_from_load_balancers(lb_response)


def _categorize_subnets(all_subnets, used_subnets):
    """Categorize subnets into used and unused."""
    unused_subnets = []
    used_subnet_details = []

    for subnet in all_subnets:
        subnet_id = subnet["SubnetId"]
        if subnet_id in used_subnets:
            used_subnet_details.append(subnet)
        else:
            unused_subnets.append(subnet)

    return unused_subnets, used_subnet_details


def analyze_subnet_usage(region_name):
    """Analyze which subnets are actually in use."""
    print(f"\n🔍 Analyzing Subnet usage in {region_name}")
    print("=" * 80)

    try:
        ec2 = boto3.client("ec2", region_name=region_name)

        subnet_response = ec2.describe_subnets()
        all_subnets = []
        if "Subnets" in subnet_response:
            all_subnets = subnet_response["Subnets"]

        used_subnets = set()
        used_subnets.update(_collect_used_subnets_from_instances(ec2))
        used_subnets.update(_collect_used_subnets_from_enis(ec2))
        used_subnets.update(_collect_used_subnets_from_nat_gateways(ec2))
        used_subnets.update(_collect_used_subnets_from_rds(region_name))
        used_subnets.update(_collect_used_subnets_from_elb(region_name))

        unused_subnets, used_subnet_details = _categorize_subnets(all_subnets, used_subnets)

        print(f"Total Subnets: {len(all_subnets)}")
        print(f"  ✅ In use: {len(used_subnet_details)}")
        print(f"  🗑️  Unused (can delete): {len(unused_subnets)}")

        if unused_subnets:
            print("\nUnused Subnets:")
            for subnet in unused_subnets:
                subnet_id = subnet["SubnetId"]
                vpc_id = subnet.get("VpcId")
                az = subnet.get("AvailabilityZone")
                cidr = subnet.get("CidrBlock")
                print(f"  {subnet_id} - {cidr} (VPC: {vpc_id}, AZ: {az})")

    except ClientError as e:
        print(f"❌ Error analyzing subnets: {e}")
        return {"unused": [], "used": []}
    return {"unused": unused_subnets, "used": used_subnet_details}


def delete_unused_subnets(unused_subnets, region_name):
    """Delete unused subnets."""
    print(f"\n🗑️  Deleting unused subnets in {region_name}")
    print("=" * 80)

    if not unused_subnets:
        print("No unused subnets to delete")
        return True

    try:
        ec2 = boto3.client("ec2", region_name=region_name)

        deleted_count = 0
        failed_count = 0

        for subnet in unused_subnets:
            subnet_id = subnet["SubnetId"]
            cidr = subnet.get("CidrBlock")

            try:
                ec2.delete_subnet(SubnetId=subnet_id)
                print(f"  ✅ Deleted {subnet_id} ({cidr})")
                deleted_count += 1
            except ClientError as e:
                print(f"  ❌ Failed to delete {subnet_id} ({cidr}): {e}")
                failed_count += 1

        print("\nSubnet deletion summary:")
        print(f"  ✅ Deleted: {deleted_count}")
        print(f"  ❌ Failed: {failed_count}")

    except ClientError as e:
        print(f"❌ Error deleting subnets: {e}")
        return False

    return failed_count == 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    pass
