#!/usr/bin/env python3
"""
AWS Stopped Instance Cleanup Script
Terminates stopped EC2 instances and cleans up associated resources.
"""

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import load_credentials_from_env
from cost_toolkit.common.aws_common import (
    extract_tag_value,
    extract_volumes_from_instance,
    get_resource_tags,
)
from cost_toolkit.scripts.aws_ec2_operations import describe_instance, terminate_instance


def get_instance_cleanup_details(region_name, instance_id, aws_access_key_id, aws_secret_access_key):
    """
    Get detailed information about an EC2 instance for cleanup operations.

    Uses canonical implementations from aws_common for tag and volume extraction.

    Args:
        region_name: AWS region name
        instance_id: EC2 instance ID
        aws_access_key_id: AWS access key ID
        aws_secret_access_key: AWS secret access key

    Returns:
        dict: Instance details for cleanup operations

    Raises:
        ClientError: If API call fails
    """
    instance = describe_instance(
        region=region_name,
        instance_id=instance_id,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    # Use canonical tag and volume extraction functions
    tags = get_resource_tags(instance)
    volumes_raw = extract_volumes_from_instance(instance)

    # Convert volumes to the format expected by this script (device vs device_name)
    volumes = [
        {
            "volume_id": vol["volume_id"],
            "device_name": vol["device"],
            "delete_on_termination": vol["delete_on_termination"],
        }
        for vol in volumes_raw
    ]

    name = extract_tag_value(instance, "Name") or "No Name"

    security_groups = []
    if "SecurityGroups" in instance:
        security_groups = instance["SecurityGroups"]
    network_interfaces = []
    if "NetworkInterfaces" in instance:
        network_interfaces = instance["NetworkInterfaces"]
    instance_info = {
        "instance_id": instance_id,
        "name": name,
        "instance_type": instance["InstanceType"],
        "state": instance["State"]["Name"],
        "vpc_id": instance.get("VpcId"),
        "subnet_id": instance.get("SubnetId"),
        "private_ip": instance.get("PrivateIpAddress"),
        "public_ip": instance.get("PublicIpAddress"),
        "launch_time": instance.get("LaunchTime"),
        "volumes": volumes,
        "tags": tags,
        "security_groups": [sg["GroupId"] for sg in security_groups],
        "network_interfaces": [eni["NetworkInterfaceId"] for eni in network_interfaces],
    }

    return instance_info


def _get_stopped_instances():
    """Return list of stopped instances to terminate."""
    return [
        {"region": "eu-west-2", "instance_id": "i-09ff569745467b037", "type": "r7i.2xlarge"},
        {"region": "eu-west-2", "instance_id": "i-0635f4a0de21cbc37", "type": "r7i.2xlarge"},
    ]


def _print_instance_details(details):
    """Print detailed information about an instance."""
    print(f"   Name: {details['name']}")
    print(f"   Type: {details['instance_type']}")
    print(f"   State: {details['state']}")
    print(f"   VPC: {details['vpc_id']}")
    print(f"   Launch Time: {details['launch_time']}")
    print(f"   Volumes: {len(details['volumes'])} attached")
    print(f"   Network Interfaces: {len(details['network_interfaces'])} attached")

    for volume in details["volumes"]:
        delete_behavior = "will be deleted" if volume["delete_on_termination"] else "will be preserved"
        print(f"      📀 {volume['volume_id']} ({volume['device_name']}) - {delete_behavior}")


def _analyze_instances(stopped_instances, aws_access_key_id, aws_secret_access_key):
    """Analyze and gather details for all stopped instances."""
    instance_details = []
    for instance in stopped_instances:
        region = instance["region"]
        instance_id = instance["instance_id"]

        print(f"🔍 Analyzing instance: {instance_id} ({region})")
        details = get_instance_cleanup_details(region, instance_id, aws_access_key_id, aws_secret_access_key)

        if details:
            instance_details.append({"region": region, "details": details})
            _print_instance_details(details)
        print()

    return instance_details


def _terminate_all_instances(instance_details, aws_access_key_id, aws_secret_access_key):
    """Terminate all instances and return results."""
    terminated_instances = []
    failed_terminations = []

    for instance_data in instance_details:
        region = instance_data["region"]
        details = instance_data["details"]
        instance_id = details["instance_id"]

        success = terminate_instance(region, instance_id, aws_access_key_id, aws_secret_access_key)

        if success:
            terminated_instances.append(instance_data)
        else:
            failed_terminations.append(instance_data)

    return terminated_instances, failed_terminations


def _print_termination_summary(terminated_instances, failed_terminations):
    """Print summary of termination results."""
    print("\n" + "=" * 50)
    print("🎯 INSTANCE TERMINATION SUMMARY")
    print("=" * 50)
    print(f"✅ Successfully terminated: {len(terminated_instances)} instances")
    print(f"❌ Failed terminations: {len(failed_terminations)} instances")
    print()

    if terminated_instances:
        print("✅ Successfully terminated instances:")
        for instance_data in terminated_instances:
            details = instance_data["details"]
            region = instance_data["region"]
            print(f"   🗑️  {details['instance_id']} ({region}) - " f"{details['name']} ({details['instance_type']})")

    if failed_terminations:
        print("\n❌ Failed terminations:")
        for instance_data in failed_terminations:
            details = instance_data["details"]
            region = instance_data["region"]
            print(f"   ❌ {details['instance_id']} ({region}) - {details['name']}")


def main():
    """Main execution function"""
    print("AWS Stopped Instance Cleanup")
    print("=" * 50)
    print("Terminating stopped EC2 instances and cleaning up resources...")
    print()

    try:
        aws_access_key_id, aws_secret_access_key = load_credentials_from_env()
        stopped_instances = _get_stopped_instances()

        print(f"🎯 Target: {len(stopped_instances)} stopped instances")
        print()

        instance_details = _analyze_instances(stopped_instances, aws_access_key_id, aws_secret_access_key)

        if not instance_details:
            print("❌ No valid instances found to terminate")
            return

        print("⚠️  TERMINATION IMPACT:")
        print("   • Instances will be permanently deleted")
        print("   • Some EBS volumes may be deleted (check delete_on_termination)")
        print("   • Network interfaces will be detached")
        print("   • This action cannot be undone")
        print("   • Significant cost savings from stopping r7i.2xlarge instances")
        print()

        confirmation = input("Type 'TERMINATE STOPPED INSTANCES' to proceed: ")

        if confirmation != "TERMINATE STOPPED INSTANCES":
            print("❌ Operation cancelled - confirmation text did not match")
            return

        print("\n🚨 Proceeding with instance termination...")
        print("=" * 50)

        terminated_instances, failed_terminations = _terminate_all_instances(instance_details, aws_access_key_id, aws_secret_access_key)

        _print_termination_summary(terminated_instances, failed_terminations)

        if len(terminated_instances) > 0:
            print("\n🎉 Instance termination completed!")
            print("   • Stopped instances have been terminated")
            print("   • Network interfaces will be automatically detached")
            print("   • EBS volumes handled according to delete_on_termination setting")
            print("   • Significant cost savings achieved")
            print("\n💡 Next steps:")
            print("   • Wait for termination to complete (5-10 minutes)")
            print("   • Run VPC cleanup to remove empty VPCs if desired")
            print("   • Verify no orphaned resources remain")

    except ClientError as e:
        print(f"❌ Critical error during instance cleanup: {str(e)}")
        raise


if __name__ == "__main__":
    main()
