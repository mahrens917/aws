#!/usr/bin/env python3
"""
AWS AMI and Snapshot Analysis Script
Analyzes AMIs that are preventing snapshot deletion and provides detailed information
about what each AMI is used for and whether it can be safely deregistered.
"""

import sys

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import extract_tag_value
from cost_toolkit.common.cost_utils import calculate_snapshot_cost
from cost_toolkit.common.credential_utils import setup_aws_credentials


def get_ami_details(ec2_client, ami_id):
    """Get detailed information about an AMI"""
    try:
        response = ec2_client.describe_images(ImageIds=[ami_id])
        if response["Images"]:
            ami = response["Images"][0]
            return {
                "ami_id": ami_id,
                "name": ami.get("Name"),
                "description": ami.get("Description"),
                "state": ami.get("State"),
                "creation_date": ami.get("CreationDate"),
                "owner_id": ami.get("OwnerId"),
                "public": ami.get("Public"),
                "platform": ami.get("Platform"),
                "architecture": ami.get("Architecture"),
                "virtualization_type": ami.get("VirtualizationType"),
                "root_device_type": ami.get("RootDeviceType"),
                "block_device_mappings": (ami.get("BlockDeviceMappings") or []),
                "tags": ami.get("Tags") or [],
            }
    except ClientError as e:
        return {"ami_id": ami_id, "error": str(e), "accessible": False}
    return None


def check_ami_usage(ec2_client, ami_id):
    """Check if AMI is currently being used by any instances"""
    try:
        # Check for running instances using this AMI
        response = ec2_client.describe_instances(
            Filters=[
                {"Name": "image-id", "Values": [ami_id]},
                {
                    "Name": "instance-state-name",
                    "Values": ["pending", "running", "shutting-down", "stopping", "stopped"],
                },
            ]
        )

        instances = []
        for reservation in response["Reservations"]:
            for instance in reservation["Instances"]:
                instance_tags = []
                if "Tags" in instance:
                    instance_tags = instance["Tags"]
                instances.append(
                    {
                        "instance_id": instance["InstanceId"],
                        "state": instance["State"]["Name"],
                        "launch_time": instance.get("LaunchTime"),
                        "instance_type": instance.get("InstanceType"),
                        "tags": instance_tags,
                    }
                )

    except ClientError as e:
        print(f"   ❌ Error checking AMI usage: {e}")
        return []

    return instances


def _print_ami_details(ami_details):
    """Print AMI details."""
    print(f"   📋 AMI Name: {ami_details['name']}")
    print(f"   📝 Description: {ami_details['description']}")
    print(f"   📅 Created: {ami_details['creation_date']}")
    print(f"   🏗️  Architecture: {ami_details['architecture']}")
    print(f"   💻 Platform: {ami_details['platform']}")
    print(f"   🔧 State: {ami_details['state']}")
    print(f"   🔒 Public: {ami_details['public']}")


def _print_ami_tags(ami_details):
    """Print AMI tags."""
    if ami_details["tags"]:
        print("   🏷️  Tags:")
        for tag in ami_details["tags"]:
            print(f"      {tag['Key']}: {tag['Value']}")
    else:
        print("   🏷️  Tags: None")


def _print_ami_usage(instances):
    """Print instances using the AMI."""
    if instances:
        print(f"   ⚠️  Currently used by {len(instances)} instance(s):")
        for instance in instances:
            # Create resource dict with uppercase Tags key for extract_tag_value
            resource_dict = {"Tags": instance["tags"]}
            instance_name = extract_tag_value(resource_dict, "Name")
            print(f"      - {instance['instance_id']} ({instance_name}) - {instance['state']}")
    else:
        print("   ✅ Not currently used by any instances")


def _analyze_snapshot_cost(ec2_client, snapshot_id, instances):
    """Analyze snapshot cost and return monthly cost."""
    try:
        snapshots = ec2_client.describe_snapshots(SnapshotIds=[snapshot_id])
        if snapshots["Snapshots"]:
            snapshot = snapshots["Snapshots"][0]
            size_gb = snapshot["VolumeSize"]
            monthly_cost = calculate_snapshot_cost(size_gb)
            print(f"   💰 Snapshot size: {size_gb} GB")
            print(f"   💰 Monthly cost: ${monthly_cost:.2f}")

            if not instances:
                print(f"   💡 RECOMMENDATION: This AMI appears unused - " f"consider deregistering to save ${monthly_cost:.2f}/month")
            else:
                print("   ⚠️  CAUTION: AMI is in use - verify instances before deregistering")
            return monthly_cost
    except ClientError as e:
        print(f"   ❌ Error getting snapshot details: {e}")
    return 0


def _analyze_single_snapshot(ec2_client, snapshot_id, ami_id, region):
    """Analyze a single snapshot-AMI relationship. Returns monthly cost."""
    print(f"🔍 Analyzing {snapshot_id} -> {ami_id} in {region}")
    print("-" * 60)

    ami_details = get_ami_details(ec2_client, ami_id)

    if ami_details and "error" not in ami_details:
        _print_ami_details(ami_details)
        _print_ami_tags(ami_details)
        instances = check_ami_usage(ec2_client, ami_id)
        _print_ami_usage(instances)
        monthly_cost = _analyze_snapshot_cost(ec2_client, snapshot_id, instances)
    elif ami_details and "error" in ami_details:
        print(f"   ❌ Error accessing AMI: {ami_details['error']}")
        print("   💡 This AMI may be owned by another account or may not exist")
        monthly_cost = 0
    else:
        print("   ❌ AMI not found or inaccessible")
        monthly_cost = 0

    print()
    return monthly_cost


def analyze_snapshot_ami_relationships():
    """Analyze the relationship between snapshots and AMIs"""
    aws_access_key_id, aws_secret_access_key = setup_aws_credentials()

    snapshot_ami_mapping = {
        "snap-09e90c64db692f884": {"ami": "ami-0cb04cf30dc50a00e", "region": "eu-west-2"},
        "snap-07c0d4017e24b3240": {"ami": "ami-0abc073133c9d3e18", "region": "us-east-1"},
        "snap-0fbb003580d3dc8ba": {"ami": "ami-0b340e8c04ad01f48", "region": "us-east-1"},
        "snap-024d718f6d670bff2": {"ami": "ami-0833a92e637927528", "region": "us-east-1"},
        "snap-0ac8b88270ff68d4d": {"ami": "ami-0cb41e78dab346fb3", "region": "us-east-1"},
        "snap-036eee4a7c291fd26": {"ami": "ami-05d0a30507ebee9d6", "region": "us-east-2"},
        "snap-0700cdc4cdfaaf8fd": {"ami": "ami-07b9b9991f7466e6d", "region": "us-east-2"},
        "snap-05a42843f18ba1c5e": {"ami": "ami-0966e8f6fa677382b", "region": "us-east-2"},
    }

    print("AWS AMI and Snapshot Analysis")
    print("=" * 80)
    print("Analyzing AMIs that are preventing snapshot deletion...\n")

    total_potential_savings = 0

    for snapshot_id, info in snapshot_ami_mapping.items():
        ec2_client = create_client(
            "ec2",
            region=info["region"],
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        monthly_cost = _analyze_single_snapshot(ec2_client, snapshot_id, info["ami"], info["region"])
        total_potential_savings += monthly_cost

    print("=" * 80)
    print("🎯 SUMMARY")
    print("=" * 80)
    print(f"Total snapshots analyzed: {len(snapshot_ami_mapping)}")
    print(f"Total potential monthly savings if all AMIs were deregistered: " f"${total_potential_savings:.2f}")
    print(f"Total potential annual savings: ${total_potential_savings * 12:.2f}")
    print()
    print("💡 NEXT STEPS:")
    print("1. Review each AMI to determine if it's still needed")
    print("2. For unused AMIs, deregister them using: aws ec2 deregister-image --image-id <ami-id>")
    print("3. After deregistering AMIs, the associated snapshots can be deleted")
    print("4. Always verify that no critical systems depend on these AMIs before deregistering")


def main():
    """Main function."""
    try:
        analyze_snapshot_ami_relationships()
    except ClientError as e:
        print(f"❌ Script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
