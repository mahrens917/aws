#!/usr/bin/env python3
"""
AWS Security Group Dependencies Audit Script
Investigates why security groups cannot be deleted by finding their dependencies:
- Network interfaces using the security groups
- Other security groups referencing them
- Load balancers or other services using them
- RDS instances or other database services

This helps understand what's preventing cleanup and provides targeted solutions.
"""

import sys

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import extract_tag_value
from cost_toolkit.common.credential_utils import setup_aws_credentials
from cost_toolkit.common.security_group_constants import ALL_CIRCULAR_SECURITY_GROUPS


def _collect_network_interface_deps(ec2_client, group_id):
    """Collect network interfaces using the security group."""
    eni_response = ec2_client.describe_network_interfaces(Filters=[{"Name": "group-id", "Values": [group_id]}])
    network_interfaces = []
    eni_list = []
    if "NetworkInterfaces" in eni_response:
        eni_list = eni_response["NetworkInterfaces"]
    for eni in eni_list:
        network_interfaces.append(
            {
                "interface_id": eni["NetworkInterfaceId"],
                "status": eni["Status"],
                "description": eni.get("Description"),
                "attachment": eni.get("Attachment"),
                "vpc_id": eni["VpcId"],
                "subnet_id": eni["SubnetId"],
            }
        )
    return network_interfaces


def _collect_instance_deps(ec2_client, group_id):
    """Collect instances using the security group."""
    instances_response = ec2_client.describe_instances(Filters=[{"Name": "instance.group-id", "Values": [group_id]}])
    instances = []
    for reservation in instances_response["Reservations"]:
        for instance in reservation["Instances"]:
            instances.append(
                {
                    "instance_id": instance["InstanceId"],
                    "state": instance["State"]["Name"],
                    "instance_type": instance["InstanceType"],
                    "vpc_id": instance.get("VpcId"),
                    "name": extract_tag_value(instance, "Name"),
                }
            )
    return instances


def _check_inbound_rules(sg, group_id):
    """Check inbound rules for references to target group."""
    rules = []
    ip_permissions = []
    if "IpPermissions" in sg:
        ip_permissions = sg["IpPermissions"]
    for rule in ip_permissions:
        group_pairs = []
        if "UserIdGroupPairs" in rule:
            group_pairs = rule["UserIdGroupPairs"]
        for group_pair in group_pairs:
            pair_group_id = group_pair.get("GroupId")
            if pair_group_id == group_id:
                from_port = rule.get("FromPort")
                to_port = rule.get("ToPort")
                rules.append(
                    {
                        "referencing_sg": sg["GroupId"],
                        "referencing_sg_name": sg["GroupName"],
                        "rule_type": "inbound",
                        "protocol": rule.get("IpProtocol"),
                        "port_range": f"{from_port}-{to_port}",
                    }
                )
    return rules


def _check_outbound_rules(sg, group_id):
    """Check outbound rules for references to target group."""
    rules = []
    ip_permissions_egress = []
    if "IpPermissionsEgress" in sg:
        ip_permissions_egress = sg["IpPermissionsEgress"]
    for rule in ip_permissions_egress:
        group_pairs = []
        if "UserIdGroupPairs" in rule:
            group_pairs = rule["UserIdGroupPairs"]
        for group_pair in group_pairs:
            pair_group_id = group_pair.get("GroupId")
            if pair_group_id == group_id:
                from_port = rule.get("FromPort")
                to_port = rule.get("ToPort")
                rules.append(
                    {
                        "referencing_sg": sg["GroupId"],
                        "referencing_sg_name": sg["GroupName"],
                        "rule_type": "outbound",
                        "protocol": rule.get("IpProtocol"),
                        "port_range": f"{from_port}-{to_port}",
                    }
                )
    return rules


def _collect_sg_rule_refs(ec2_client, group_id):
    """Collect security group rules referencing this group."""
    all_sgs_response = ec2_client.describe_security_groups()
    rules = []
    security_groups = []
    if "SecurityGroups" in all_sgs_response:
        security_groups = all_sgs_response["SecurityGroups"]
    for sg in security_groups:
        if sg["GroupId"] == group_id:
            continue

        rules.extend(_check_inbound_rules(sg, group_id))
        rules.extend(_check_outbound_rules(sg, group_id))
    return rules


def _collect_rds_deps(group_id, region, aws_access_key_id, aws_secret_access_key):
    """Collect RDS instances using the security group."""
    try:
        rds_client = create_client(
            "rds",
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        rds_response = rds_client.describe_db_instances()
        rds_instances = []
        db_instances = []
        if "DBInstances" in rds_response:
            db_instances = rds_response["DBInstances"]
        for db in db_instances:
            vpc_security_groups = []
            if "VpcSecurityGroups" in db:
                vpc_security_groups = db["VpcSecurityGroups"]
            for sg in vpc_security_groups:
                if sg["VpcSecurityGroupId"] == group_id:
                    db_subnet_group = {}
                    if "DbSubnetGroup" in db:
                        db_subnet_group = db["DbSubnetGroup"]
                    rds_instances.append(
                        {
                            "db_instance_id": db["DBInstanceIdentifier"],
                            "db_instance_status": db["DBInstanceStatus"],
                            "engine": db["Engine"],
                            "vpc_id": db_subnet_group.get("VpcId"),
                        }
                    )
    except ClientError as e:
        print(f"   ⚠️  Could not check RDS dependencies: {e}")
        return []
    return rds_instances


def check_security_group_dependencies(ec2_client, group_id, region, aws_access_key_id, aws_secret_access_key):
    """Check what's preventing a security group from being deleted"""
    dependencies = {
        "network_interfaces": [],
        "instances": [],
        "load_balancers": [],
        "rds_instances": [],
        "security_group_rules": [],
        "other_dependencies": [],
    }

    try:
        dependencies["network_interfaces"] = _collect_network_interface_deps(ec2_client, group_id)
        dependencies["instances"] = _collect_instance_deps(ec2_client, group_id)
        dependencies["security_group_rules"] = _collect_sg_rule_refs(ec2_client, group_id)
        dependencies["rds_instances"] = _collect_rds_deps(group_id, region, aws_access_key_id, aws_secret_access_key)

    except ClientError as e:
        print(f"   ❌ Error checking dependencies for {group_id}: {e}")
        return dependencies

    return dependencies


def _print_network_interfaces(network_interfaces):
    """Print network interface dependencies."""
    print(f"🔗 Network Interfaces ({len(network_interfaces)}):")
    for eni in network_interfaces:
        attachment_info = "Unattached"
        if eni["attachment"]:
            instance_id = eni["attachment"].get("InstanceId") if eni["attachment"] else None
            attachment_info = f"Attached to {instance_id}"
        print(f"   • {eni['interface_id']} - {eni['status']} - {attachment_info}")
        print(f"     Description: {eni['description']}")


def _print_instances(instances):
    """Print EC2 instance dependencies."""
    print(f"🖥️  Instances ({len(instances)}):")
    for instance in instances:
        print(f"   • {instance['instance_id']} ({instance['name']}) - {instance['state']}")


def _print_rds_instances(rds_instances):
    """Print RDS instance dependencies."""
    print(f"🗄️  RDS Instances ({len(rds_instances)}):")
    for rds in rds_instances:
        print(f"   • {rds['db_instance_id']} - {rds['engine']} - {rds['db_instance_status']}")


def _print_security_group_rules(security_group_rules):
    """Print security group rule dependencies."""
    print(f"🔒 Referenced by Security Group Rules ({len(security_group_rules)}):")
    for rule in security_group_rules:
        print(f"   • {rule['referencing_sg']} ({rule['referencing_sg_name']}) - " f"{rule['rule_type']} rule")
        print(f"     Protocol: {rule['protocol']}, Ports: {rule['port_range']}")


def _print_dependency_details(dependencies):
    """Print detailed dependency information."""
    has_dependencies = False

    if dependencies["network_interfaces"]:
        has_dependencies = True
        _print_network_interfaces(dependencies["network_interfaces"])

    if dependencies["instances"]:
        has_dependencies = True
        _print_instances(dependencies["instances"])

    if dependencies["rds_instances"]:
        has_dependencies = True
        _print_rds_instances(dependencies["rds_instances"])

    if dependencies["security_group_rules"]:
        has_dependencies = True
        _print_security_group_rules(dependencies["security_group_rules"])

    if not has_dependencies:
        print("❓ No obvious dependencies found - may be a transient issue")


def audit_security_group_dependencies():
    """Audit dependencies for security groups that couldn't be deleted"""
    aws_access_key_id, aws_secret_access_key = setup_aws_credentials()

    # Security groups that failed to delete - loaded from shared constants
    failed_security_groups = ALL_CIRCULAR_SECURITY_GROUPS

    print("AWS Security Group Dependencies Audit")
    print("=" * 60)
    print("Investigating why security groups cannot be deleted...")
    print()

    for sg_info in failed_security_groups:
        group_id = sg_info["group_id"]
        group_name = sg_info["name"]
        region = sg_info["region"]

        print(f"🔍 Analyzing {group_id} ({group_name}) in {region}")
        print("-" * 50)

        # Create EC2 client for the specific region
        ec2_client = create_client(
            "ec2",
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        dependencies = check_security_group_dependencies(ec2_client, group_id, region, aws_access_key_id, aws_secret_access_key)

        _print_dependency_details(dependencies)

        print()

    print("=" * 60)
    print("💡 CLEANUP RECOMMENDATIONS")
    print("=" * 60)
    print("1. Remove security group references from other security groups")
    print("2. Detach or delete unused network interfaces")
    print("3. Remove security groups from RDS instances if no longer needed")
    print("4. Terminate or modify instances using these security groups")
    print()
    print("🔧 After resolving dependencies, retry security group deletion")


def main():
    """Main function."""
    try:
        audit_security_group_dependencies()
    except ClientError as e:
        print(f"❌ Script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
