#!/usr/bin/env python3
"""Security group usage analysis and cleanup."""

import boto3
from botocore.exceptions import ClientError


def _collect_used_sgs_from_instances(ec2):
    """Collect security group IDs from EC2 instances."""
    instances_response = ec2.describe_instances()
    used_sgs = set()

    for reservation in instances_response["Reservations"]:
        for instance in reservation["Instances"]:
            if instance["State"]["Name"] != "terminated":
                if "SecurityGroups" in instance:
                    for sg in instance["SecurityGroups"]:
                        used_sgs.add(sg["GroupId"])

    return used_sgs


def _collect_used_sgs_from_enis(ec2):
    """Collect security group IDs from network interfaces."""
    eni_response = ec2.describe_network_interfaces()
    used_sgs = set()

    if "NetworkInterfaces" in eni_response:
        for eni in eni_response["NetworkInterfaces"]:
            if "Groups" in eni:
                for sg in eni["Groups"]:
                    used_sgs.add(sg["GroupId"])

    return used_sgs


def _collect_used_sgs_from_rds(region_name):
    """Collect security group IDs from RDS instances."""
    used_sgs = set()
    try:
        rds = boto3.client("rds", region_name=region_name)
        db_response = rds.describe_db_instances()
        if "DBInstances" in db_response:
            for db in db_response["DBInstances"]:
                if "VpcSecurityGroups" in db:
                    for sg in db["VpcSecurityGroups"]:
                        used_sgs.add(sg["VpcSecurityGroupId"])
    except ClientError as e:
        print(f"  Warning: Could not check RDS security groups: {e}")

    return used_sgs


def _collect_used_sgs_from_elb(region_name):
    """Collect security group IDs from load balancers."""
    used_sgs = set()
    try:
        elbv2 = boto3.client("elbv2", region_name=region_name)
        lb_response = elbv2.describe_load_balancers()
        if "LoadBalancers" in lb_response:
            for lb in lb_response["LoadBalancers"]:
                if "SecurityGroups" in lb:
                    for sg_id in lb["SecurityGroups"]:
                        used_sgs.add(sg_id)
    except ClientError as e:
        print(f"  Warning: Could not check ELB security groups: {e}")

    return used_sgs


def _categorize_security_groups(all_sgs, used_sgs):
    """Categorize security groups into used, unused, and default."""
    unused_sgs = []
    used_sg_details = []
    default_sgs = []

    for sg in all_sgs:
        sg_id = sg["GroupId"]
        sg_name = sg["GroupName"]

        if sg_name == "default":
            default_sgs.append(sg)
        elif sg_id in used_sgs:
            used_sg_details.append(sg)
        else:
            unused_sgs.append(sg)

    return unused_sgs, used_sg_details, default_sgs


def analyze_security_groups_usage(region_name):
    """Analyze which security groups are actually in use."""
    print(f"\n🔍 Analyzing Security Group usage in {region_name}")
    print("=" * 80)

    try:
        ec2 = boto3.client("ec2", region_name=region_name)

        sg_response = ec2.describe_security_groups()
        all_sgs = []
        if "SecurityGroups" in sg_response:
            all_sgs = sg_response["SecurityGroups"]

        used_sgs = set()
        used_sgs.update(_collect_used_sgs_from_instances(ec2))
        used_sgs.update(_collect_used_sgs_from_enis(ec2))
        used_sgs.update(_collect_used_sgs_from_rds(region_name))
        used_sgs.update(_collect_used_sgs_from_elb(region_name))

        unused_sgs, used_sg_details, default_sgs = _categorize_security_groups(all_sgs, used_sgs)

        print(f"Total Security Groups: {len(all_sgs)}")
        print(f"  ✅ In use: {len(used_sg_details)}")
        print(f"  🔒 Default (keep): {len(default_sgs)}")
        print(f"  🗑️  Unused (can delete): {len(unused_sgs)}")

        if unused_sgs:
            print("\nUnused Security Groups:")
            for sg in unused_sgs:
                vpc_id = sg.get("VpcId")
                print(f"  {sg['GroupId']} - {sg['GroupName']} (VPC: {vpc_id})")

    except ClientError as e:
        print(f"❌ Error analyzing security groups: {e}")
        return {"unused": [], "used": [], "default": []}
    return {"unused": unused_sgs, "used": used_sg_details, "default": default_sgs}


def delete_unused_security_groups(unused_sgs, region_name):
    """Delete unused security groups."""
    print(f"\n🗑️  Deleting unused security groups in {region_name}")
    print("=" * 80)

    if not unused_sgs:
        print("No unused security groups to delete")
        return True

    try:
        ec2 = boto3.client("ec2", region_name=region_name)

        deleted_count = 0
        failed_count = 0

        for sg in unused_sgs:
            sg_id = sg["GroupId"]
            sg_name = sg["GroupName"]

            try:
                ec2.delete_security_group(GroupId=sg_id)
                print(f"  ✅ Deleted {sg_id} ({sg_name})")
                deleted_count += 1
            except ClientError as e:
                print(f"  ❌ Failed to delete {sg_id} ({sg_name}): {e}")
                failed_count += 1

        print("\nSecurity Group deletion summary:")
        print(f"  ✅ Deleted: {deleted_count}")
        print(f"  ❌ Failed: {failed_count}")

    except ClientError as e:
        print(f"❌ Error deleting security groups: {e}")
        return False

    return failed_count == 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    pass
