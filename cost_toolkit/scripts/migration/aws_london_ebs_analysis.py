#!/usr/bin/env python3
"""Analyze EBS volumes in London region."""


import boto3
from botocore.exceptions import ClientError

from cost_toolkit.common.aws_common import get_resource_tags
from cost_toolkit.scripts import aws_utils


def _print_volume_details(ec2, vol):
    """Print detailed information for a single volume."""
    try:
        vol_response = ec2.describe_volumes(VolumeIds=[vol["id"]])
        volume = vol_response["Volumes"][0]

        device = None
        if "Attachments" in volume and volume["Attachments"]:
            device = volume["Attachments"][0].get("Device")
        device = device or "Unknown"
        create_time = volume["CreateTime"]
        tags = get_resource_tags(volume)
        name_tag = tags.get("Name") or "No name"

        print(f"  Volume: {vol['id']}")
        print(f"    Size: {vol['size']}")
        print(f"    Device: {device}")
        print(f"    Created: {create_time}")
        print(f"    Name: {name_tag}")
        print(f"    Tags: {tags}")
        print()

    except ClientError as e:
        print(f"    Error getting details for {vol['id']}: {e}")


def _check_unattached_volume(ec2, unattached_volume):
    """Check and print unattached volume details."""
    print("🔍 Unattached Volume Details:")
    try:
        vol_response = ec2.describe_volumes(VolumeIds=[unattached_volume["id"]])
        volume = vol_response["Volumes"][0]

        create_time = volume["CreateTime"]
        tags = get_resource_tags(volume)
        name_tag = tags.get("Name")

        print(f"  Volume: {unattached_volume['id']}")
        print(f"    Size: {unattached_volume['size']}")
        print(f"    Created: {create_time}")
        print(f"    Name: {name_tag}")
        print(f"    Tags: {tags}")
        print()

    except ClientError as e:
        print(f"    Error getting details for {unattached_volume['id']}: {e}")


def _start_stopped_instance(ec2, instance_id):
    """Start instance if it's stopped."""
    print("🚀 Starting instance for analysis...")
    try:
        ec2.start_instances(InstanceIds=[instance_id])
        print("  Instance start initiated. Waiting for running state...")
        aws_utils.wait_for_instance_running(ec2, instance_id, max_attempts=20)
        print("  ✅ Instance is now running!")

        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]
        public_ip = instance.get("PublicIpAddress") or "No public IP"
        private_ip = instance.get("PrivateIpAddress") or "No private IP"

        print(f"  Public IP: {public_ip}")
        print(f"  Private IP: {private_ip}")
        print()

    except ClientError as e:
        print(f"  ❌ Error starting instance: {e}")


def _is_related_snapshot(snap, instance_id, attached_volumes):
    """Check if snapshot is related to instance or attached volumes."""
    if "Description" not in snap:
        return False
    description = snap["Description"]
    if instance_id in description:
        return True
    return any(vol["id"] in description for vol in attached_volumes)


def _print_snapshot_info(snap):
    """Print snapshot details."""
    snap_id = snap["SnapshotId"]
    size = snap.get("VolumeSize")
    start_time = snap["StartTime"]
    description = snap.get("Description")
    print(f"    {snap_id}: {size} GB, created {start_time}")
    print(f"      Description: {description}")


def _analyze_snapshots(ec2, instance_id, attached_volumes):
    """Analyze snapshots related to the instance."""
    print("📸 Related Snapshots Analysis:")
    try:
        snapshots_response = ec2.describe_snapshots(OwnerIds=["sel"])
        snapshots = []
        if "Snapshots" in snapshots_response:
            snapshots = snapshots_response["Snapshots"]

        related_snapshots = [snap for snap in snapshots if _is_related_snapshot(snap, instance_id, attached_volumes)]

        if related_snapshots:
            print(f"  Found {len(related_snapshots)} snapshots related to this instance:")
            for snap in related_snapshots:
                _print_snapshot_info(snap)
            print()
        else:
            print("  No snapshots directly related to this instance found.")
            print()

    except ClientError as e:
        print(f"  Error analyzing snapshots: {e}")


def _print_recommendations(attached_volumes, unattached_volume, current_state):
    """Print analysis and recommendations."""
    print("💡 ANALYSIS & RECOMMENDATIONS:")
    print("=" * 80)

    sizes = [vol["size"] for vol in attached_volumes]
    duplicate_sizes = [size for size in set(sizes) if sizes.count(size) > 1]

    if duplicate_sizes:
        print(f"⚠️  Found volumes with duplicate sizes: {duplicate_sizes}")
        print("   These may be duplicates - manual inspection needed after instance starts")

    print(f"🗑️  Unattached volume {unattached_volume['id']} (32 GB) can likely be deleted")
    print("   This volume is not attached to any instance and costs $2.56/month")
    print()

    print("📋 NEXT STEPS:")
    print("1. SSH into the running instance to examine volume contents")
    print("2. Check mount points: df -h")
    print("3. Examine each volume's contents to identify duplicates")
    print("4. Identify the most recent/important data")
    print("5. Plan cleanup of duplicate volumes")
    print()

    if current_state == "stopped":
        print("⚠️  IMPORTANT: Instance was started for analysis.")
        print("   Remember to stop it after analysis to avoid ongoing compute charges!")


def analyze_london_ebs():
    """Analyze London EBS volumes and start instance for inspection"""
    aws_utils.setup_aws_credentials()

    print("AWS London EBS Analysis")
    print("=" * 80)

    ec2 = boto3.client("ec2", region_name="eu-west-2")

    # Instance and volume details from audit
    instance_id = "i-05ad29f28fc8a8fdc"
    attached_volumes = [
        {"id": "vol-0e148f66bcb4f7a0b", "size": "1024 GB", "type": "gp3"},
        {"id": "vol-089b9ed38099c68f3", "size": "384 GB", "type": "gp3"},
        {"id": "vol-0e07da8b7b7dafa17", "size": "1024 GB", "type": "gp3"},
        {"id": "vol-0249308257e5fa64d", "size": "64 GB", "type": "gp3"},
    ]
    unattached_volume = {"id": "vol-08f9abc839d13db62", "size": "32 GB", "type": "gp3"}

    print("📋 London EBS Summary:")
    print(f"Instance: {instance_id}")
    print(f"Attached volumes: {len(attached_volumes)}")
    print(f"Unattached volumes: 1 ({unattached_volume['id']})")
    print()

    # Check current instance state
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]
        current_state = instance["State"]["Name"]
        instance_type = instance["InstanceType"]

        print("🖥️  Instance Details:")
        print(f"  Instance ID: {instance_id}")
        print(f"  Instance Type: {instance_type}")
        print(f"  Current State: {current_state}")
        print()

        print("📦 Attached Volume Details:")
        for i, vol in enumerate(attached_volumes, 1):
            print(f"  Volume {i}: {vol['id']}")
            _print_volume_details(ec2, vol)

        _check_unattached_volume(ec2, unattached_volume)

        if current_state == "stopped":
            _start_stopped_instance(ec2, instance_id)
        elif current_state == "running":
            print("✅ Instance is already running!")
            public_ip = instance.get("PublicIpAddress") or "No public IP"
            private_ip = instance.get("PrivateIpAddress") or "No private IP"
            print(f"  Public IP: {public_ip}")
            print(f"  Private IP: {private_ip}")
            print()
        else:
            print(f"⚠️  Instance is in '{current_state}' state")
            print()

        _analyze_snapshots(ec2, instance_id, attached_volumes)
        _print_recommendations(attached_volumes, unattached_volume, current_state)

    except ClientError as e:
        print(f"❌ Error analyzing instance: {e}")


def main():
    """Main function."""
    analyze_london_ebs()


if __name__ == "__main__":
    main()
