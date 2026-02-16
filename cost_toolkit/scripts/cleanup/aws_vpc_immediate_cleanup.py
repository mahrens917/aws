#!/usr/bin/env python3
"""Immediately clean up unused VPC and networking resources."""

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import get_all_aws_regions
from cost_toolkit.scripts.aws_utils import get_instance_info


def release_public_ip_from_instance(instance_id, region_name):
    """Release public IP address from an EC2 instance"""
    print(f"\n🔧 Releasing public IP from instance {instance_id} in {region_name}")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)
        instance = get_instance_info(instance_id, region_name)

        current_public_ip = instance.get("PublicIpAddress")
        if not current_public_ip:
            print(f"✅ Instance {instance_id} has no public IP address")
            return True

        print(f"Current public IP: {current_public_ip}")

        # Check if it's an Elastic IP or auto-assigned
        network_interfaces = []
        if "NetworkInterfaces" in instance:
            network_interfaces = instance["NetworkInterfaces"]
        first_interface = network_interfaces[0] if network_interfaces else {}
        association = {}
        if "Association" in first_interface:
            association = first_interface["Association"]
        association_id = association.get("AssociationId")
        allocation_id = association.get("AllocationId")

        if allocation_id:
            print(f"This is an Elastic IP (allocation: {allocation_id})")
            if association_id:
                print(f"Disassociating Elastic IP (association: {association_id})")
                ec2.disassociate_address(AssociationId=association_id)
                print("✅ Elastic IP disassociated from instance")

                # Ask if we should also release the Elastic IP
                print(f"⚠️  Elastic IP {current_public_ip} is now idle and will cost $3.60/month")
                print(f"To release it completely, run: aws ec2 release-address " f"--allocation-id {allocation_id} --region {region_name}")
                return True
            print("✅ Elastic IP is already disassociated")
            return True

        print("This is an auto-assigned public IP")
        print("To remove it, we need to modify the instance's network interface")

        # For auto-assigned IPs, we need to modify the instance
        # This requires stopping and starting the instance
        print("⚠️  To remove auto-assigned public IP, the instance needs to be stopped and reconfigured")
        print("This will cause downtime. Proceed? (This script will not auto-proceed)")
    except ClientError as e:
        print(f"❌ Error releasing public IP: {e}")
    return False


def remove_detached_internet_gateway(igw_id, region_name):
    """Remove a detached Internet Gateway"""
    print(f"\n🔧 Removing detached Internet Gateway {igw_id} in {region_name}")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)

        # First verify it's detached
        response = ec2.describe_internet_gateways(InternetGatewayIds=[igw_id])
        igw = response["InternetGateways"][0]

        attachments = []
        if "Attachments" in igw:
            attachments = igw["Attachments"]
        if attachments:
            attached_vpcs = [att["VpcId"] for att in attachments if att["State"] == "available"]
            if attached_vpcs:
                print(f"❌ Cannot delete IGW {igw_id} - still attached to VPCs: {attached_vpcs}")
                return False

        print(f"Confirmed IGW {igw_id} is detached")

        # Delete the Internet Gateway
        ec2.delete_internet_gateway(InternetGatewayId=igw_id)
        print(f"✅ Internet Gateway {igw_id} deleted successfully")

    except ClientError as e:
        print(f"❌ Error deleting Internet Gateway: {e}")
        return False

    return True


def _check_vpc_ec2_instances(ec2, vpc_id, analysis):
    """Check for EC2 instances in a VPC"""
    instances_response = ec2.describe_instances(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {
                "Name": "instance-state-name",
                "Values": ["running", "stopped", "stopping", "pending"],
            },
        ]
    )

    instances = []
    for reservation in instances_response["Reservations"]:
        instances.extend(reservation["Instances"])

    if instances:
        analysis["blocking_resources"].append(f"{len(instances)} EC2 instances")
        analysis["can_delete"] = False


def _check_vpc_igws(ec2, vpc_id, analysis):
    """Check for attached Internet Gateways in a VPC"""
    igw_response = ec2.describe_internet_gateways(Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}])
    igws = []
    if "InternetGateways" in igw_response:
        igws = igw_response["InternetGateways"]
    if igws:
        analysis["dependencies"].append(f"{len(igws)} Internet Gateways")


def _check_vpc_nat_gateways(ec2, vpc_id, analysis):
    """Check for NAT Gateways in a VPC"""
    nat_response = ec2.describe_nat_gateways(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    nat_gateways = []
    if "NatGateways" in nat_response:
        nat_gateways = nat_response["NatGateways"]
    nats = [nat for nat in nat_gateways if nat["State"] != "deleted"]
    if nats:
        analysis["blocking_resources"].append(f"{len(nats)} NAT Gateways")
        analysis["can_delete"] = False


def _check_vpc_endpoints(ec2, vpc_id, analysis):
    """Check for VPC Endpoints in a VPC"""
    endpoints_response = ec2.describe_vpc_endpoints(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    vpc_endpoints = []
    if "VpcEndpoints" in endpoints_response:
        vpc_endpoints = endpoints_response["VpcEndpoints"]
    endpoints = [ep for ep in vpc_endpoints if ep["State"] != "deleted"]
    if endpoints:
        analysis["blocking_resources"].append(f"{len(endpoints)} VPC Endpoints")
        analysis["can_delete"] = False


def _check_vpc_network_resources(ec2, vpc_id, analysis):
    """Check for network resources (IGW, NAT, Endpoints) in a VPC"""
    _check_vpc_igws(ec2, vpc_id, analysis)
    _check_vpc_nat_gateways(ec2, vpc_id, analysis)
    _check_vpc_endpoints(ec2, vpc_id, analysis)


def _check_vpc_load_balancers(region_name, vpc_id, analysis):
    """Check for load balancers in a VPC"""
    try:
        elbv2 = create_client("elbv2", region=region_name)
        lb_response = elbv2.describe_load_balancers()
        load_balancers = []
        if "LoadBalancers" in lb_response:
            load_balancers = lb_response["LoadBalancers"]
        vpc_lbs = [lb for lb in load_balancers if "VpcId" in lb and lb["VpcId"] == vpc_id]
        if vpc_lbs:
            analysis["blocking_resources"].append(f"{len(vpc_lbs)} Load Balancers")
            analysis["can_delete"] = False
    except ClientError as e:
        print(f"  Warning: Could not check load balancers: {e}")


def _check_vpc_rds_instances(region_name, vpc_id, analysis):
    """Check for RDS instances in a VPC"""
    try:
        rds = create_client("rds", region=region_name)
        db_response = rds.describe_db_instances()
        db_instances = []
        if "DBInstances" in db_response:
            db_instances = db_response["DBInstances"]
        vpc_dbs = []
        for db in db_instances:
            db_subnet_group = db.get("DBSubnetGroup")
            if db_subnet_group and "VpcId" in db_subnet_group and db_subnet_group["VpcId"] == vpc_id:
                vpc_dbs.append(db)
        if vpc_dbs:
            analysis["blocking_resources"].append(f"{len(vpc_dbs)} RDS instances")
            analysis["can_delete"] = False
    except ClientError as e:
        print(f"  Warning: Could not check RDS instances: {e}")


def _print_vpc_analysis(vpc_id, is_default, analysis):
    """Print analysis results for a VPC"""
    print(f"\nVPC: {vpc_id} ({'Default' if is_default else 'Custom'})")
    print(f"  Can delete: {'✅ Yes' if analysis['can_delete'] else '❌ No'}")
    if analysis["dependencies"]:
        print(f"  Dependencies: {', '.join(analysis['dependencies'])}")
    if analysis["blocking_resources"]:
        print(f"  Blocking resources: {', '.join(analysis['blocking_resources'])}")


def analyze_vpc_dependencies(region_name):
    """Analyze VPC dependencies to determine safe removal order"""
    print(f"\n🔍 Analyzing VPC dependencies in {region_name}")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)

        # Get all VPCs
        vpcs_response = ec2.describe_vpcs()
        vpcs = []
        if "Vpcs" in vpcs_response:
            vpcs = vpcs_response["Vpcs"]

        vpc_analysis = {}

        for vpc in vpcs:
            vpc_id = vpc["VpcId"]
            is_default = vpc["IsDefault"]

            analysis = {
                "vpc_id": vpc_id,
                "is_default": is_default,
                "can_delete": not is_default,  # Default VPCs should generally be kept
                "dependencies": [],
                "blocking_resources": [],
            }

            _check_vpc_ec2_instances(ec2, vpc_id, analysis)
            _check_vpc_network_resources(ec2, vpc_id, analysis)
            _check_vpc_load_balancers(region_name, vpc_id, analysis)
            _check_vpc_rds_instances(region_name, vpc_id, analysis)

            vpc_analysis[vpc_id] = analysis
            _print_vpc_analysis(vpc_id, is_default, analysis)

    except ClientError as e:
        print(f"❌ Error analyzing VPC dependencies: {e}")
        return {}

    return vpc_analysis


def _categorize_vpcs(all_vpc_analysis):
    """Categorize VPCs into deletable and non-deletable"""
    deletable_vpcs = []
    non_deletable_vpcs = []

    for region, vpcs in all_vpc_analysis.items():
        for vpc_id, analysis in vpcs.items():
            if analysis["can_delete"]:
                deletable_vpcs.append((region, vpc_id, analysis))
            else:
                non_deletable_vpcs.append((region, vpc_id, analysis))

    return deletable_vpcs, non_deletable_vpcs


def _print_vpc_recommendations(deletable_vpcs, non_deletable_vpcs):
    """Print VPC deletion recommendations"""
    print("\n📋 VPC DELETION ANALYSIS:")

    if deletable_vpcs:
        print(f"\n✅ VPCs that CAN be safely deleted ({len(deletable_vpcs)}):")
        for region, vpc_id, analysis in deletable_vpcs:
            deps = ", ".join(analysis["dependencies"]) if analysis["dependencies"] else "No dependencies"
            print(f"  {vpc_id} ({region}) - {deps}")

    if non_deletable_vpcs:
        print(f"\n❌ VPCs that CANNOT be deleted ({len(non_deletable_vpcs)}):")
        for region, vpc_id, analysis in non_deletable_vpcs:
            reasons = analysis["blocking_resources"] + (["Default VPC"] if analysis["is_default"] else [])
            print(f"  {vpc_id} ({region}) - Blocked by: {', '.join(reasons)}")

    print("\n💡 NEXT STEPS:")
    if deletable_vpcs:
        print(f"  1. You can safely delete {len(deletable_vpcs)} VPCs")
        print("  2. This will also remove their associated subnets, route tables, and security groups")
        print("  3. Internet Gateways will be detached and can then be deleted")


def main():
    """Scan and report VPC deletion possibilities."""
    print("AWS VPC Immediate Cleanup")
    print("=" * 80)
    print("Performing immediate cleanup tasks...")

    # Task 1: Release public IP from instance
    print("\n" + "=" * 80)
    print("TASK 1: Release Public IP Address")
    print("=" * 80)

    success1 = release_public_ip_from_instance("i-00c39b1ba0eba3e2d", "us-east-2")

    # Task 2: Remove detached IGW
    print("\n" + "=" * 80)
    print("TASK 2: Remove Detached Internet Gateway")
    print("=" * 80)

    success2 = remove_detached_internet_gateway("igw-0dba67db64171222c", "us-west-2")

    # Task 3: Analyze VPC dependencies
    print("\n" + "=" * 80)
    print("TASK 3: Analyze VPC Dependencies")
    print("=" * 80)

    all_vpc_analysis = {}
    target_regions = get_all_aws_regions()

    for region in target_regions:
        region_analysis = analyze_vpc_dependencies(region)
        all_vpc_analysis[region] = region_analysis

    # Summary
    print("\n" + "=" * 80)
    print("🎯 CLEANUP SUMMARY")
    print("=" * 80)

    print(f"Public IP release: {'✅ Success' if success1 else '❌ Failed/Manual action required'}")
    print(f"IGW removal: {'✅ Success' if success2 else '❌ Failed'}")

    # VPC deletion recommendations
    deletable_vpcs, non_deletable_vpcs = _categorize_vpcs(all_vpc_analysis)
    _print_vpc_recommendations(deletable_vpcs, non_deletable_vpcs)

    if non_deletable_vpcs:
        print(f"  4. {len(non_deletable_vpcs)} VPCs have blocking resources " "that must be removed first")
        print("  5. Consider if the blocking resources are still needed")


if __name__ == "__main__":
    main()
