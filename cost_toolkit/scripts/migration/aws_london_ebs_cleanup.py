#!/usr/bin/env python3
"""Clean up EBS volumes in London region."""

import boto3
from botocore.exceptions import ClientError

from cost_toolkit.common.cost_utils import calculate_ebs_volume_cost
from cost_toolkit.scripts import aws_utils


def _print_volumes_to_delete(volumes_to_delete):
    """Print list of volumes scheduled for deletion."""
    print("🗑️  Volumes scheduled for deletion:")
    total_savings = 0
    for vol in volumes_to_delete:
        print(f"   • {vol['id']} ({vol['name']}) - {vol['size']}")
        print(f"     Reason: {vol['reason']}")
        print(f"     Savings: {vol['savings']}")
        savings_amount = int(vol["savings"].replace("$", "").replace("/month", ""))
        total_savings += savings_amount
        print()
    return total_savings


def _detach_volume(ec2, volume_id):
    """Detach a volume if it's attached."""
    response = ec2.describe_volumes(VolumeIds=[volume_id])
    volume = response["Volumes"][0]

    if volume["Attachments"]:
        attachment = volume["Attachments"][0]
        instance_id = attachment["InstanceId"]
        device = attachment["Device"]

        print(f"   Volume is attached to {instance_id} as {device}")
        print("   Detaching volume...")

        ec2.detach_volume(VolumeId=volume_id, InstanceId=instance_id, Device=device, Force=True)

        print("   ✅ Volume detachment initiated")
        print("   Waiting for volume to detach...")
        waiter = ec2.get_waiter("volume_available")
        waiter.wait(VolumeIds=[volume_id])
        print("   ✅ Volume successfully detached")
    else:
        print("   Volume is already detached")


def _delete_volumes(ec2, volumes_to_delete):
    """Delete volumes and return lists of deleted and failed volumes."""
    deleted_volumes = []
    failed_deletions = []

    for vol in volumes_to_delete:
        try:
            print(f"   Deleting {vol['id']} ({vol['name']})...")
            ec2.delete_volume(VolumeId=vol["id"])
            print(f"   ✅ Successfully deleted {vol['id']}")
            deleted_volumes.append(vol)
        except ClientError as e:
            print(f"   ❌ Failed to delete {vol['id']}: {str(e)}")
            failed_deletions.append({"volume": vol, "error": str(e)})

    return deleted_volumes, failed_deletions


def _print_cleanup_summary(deleted_volumes, failed_deletions):
    """Print cleanup summary."""
    print()
    print("📊 CLEANUP SUMMARY:")
    print("=" * 80)

    if deleted_volumes:
        print("✅ Successfully deleted volumes:")
        total_deleted_savings = 0
        for vol in deleted_volumes:
            print(f"   • {vol['id']} ({vol['name']}) - {vol['size']}")
            savings_amount = int(vol["savings"].replace("$", "").replace("/month", ""))
            total_deleted_savings += savings_amount
        print(f"   💰 Monthly savings achieved: ${total_deleted_savings}")
        print()
        return total_deleted_savings

    if failed_deletions:
        print("❌ Failed deletions:")
        for failure in failed_deletions:
            vol = failure["volume"]
            error = failure["error"]
            print(f"   • {vol['id']} ({vol['name']}): {error}")
        print()

    return 0


def _show_remaining_volumes(ec2):
    """Show remaining volumes after cleanup."""
    print("📦 Remaining London EBS volumes:")
    try:
        response = ec2.describe_volumes(
            Filters=[
                {"Name": "state", "Values": ["available", "in-use"]},
                {"Name": "availability-zone", "Values": ["eu-west-2a", "eu-west-2b", "eu-west-2c"]},
            ]
        )

        remaining_cost = 0
        for volume in response["Volumes"]:
            size = volume["Size"]
            vol_id = volume["VolumeId"]
            state = volume["State"]

            name = "No name"
            if "Tags" in volume:
                for tag in volume["Tags"]:
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                        break

            monthly_cost = calculate_ebs_volume_cost(size, "gp3")
            remaining_cost += monthly_cost

            print(f"   • {vol_id} ({name}) - {size} GB - {state} - ${monthly_cost:.2f}/month")

        print(f"   💰 Total remaining monthly cost: ${remaining_cost:.2f}")

    except ClientError as e:
        print(f"   ❌ Error listing remaining volumes: {str(e)}")


def cleanup_london_ebs_volumes():
    """Clean up duplicate and unattached EBS volumes in London"""
    aws_utils.setup_aws_credentials()

    print("AWS London EBS Volume Cleanup")
    print("=" * 80)

    ec2 = boto3.client("ec2", region_name="eu-west-2")

    # Volumes to delete
    volumes_to_delete = [
        {
            "id": "vol-0e148f66bcb4f7a0b",
            "name": "Tars (OLD)",
            "size": "1024 GB",
            "reason": "Duplicate - older version of Tars 2",
            "savings": "$82/month",
        },
        {
            "id": "vol-08f9abc839d13db62",
            "name": "Unattached",
            "size": "32 GB",
            "reason": "Unattached volume - not in use",
            "savings": "$3/month",
        },
    ]

    total_savings = _print_volumes_to_delete(volumes_to_delete)
    print(f"💰 Total estimated monthly savings: ${total_savings}")
    print()

    print("🔧 Step 1: Detaching old Tars volume if attached...")
    try:
        _detach_volume(ec2, "vol-0e148f66bcb4f7a0b")
    except ClientError as e:
        print(f"   ❌ Error detaching volume: {str(e)}")
        return

    print()
    print("🗑️  Step 2: Deleting volumes...")

    deleted_volumes, failed_deletions = _delete_volumes(ec2, volumes_to_delete)

    total_deleted_savings = _print_cleanup_summary(deleted_volumes, failed_deletions)
    _show_remaining_volumes(ec2)

    print()
    print("🎯 OPTIMIZATION COMPLETE!")
    print(f"   Estimated monthly savings: ${total_deleted_savings if deleted_volumes else 0}")
    print("   Duplicate 'Tars' volume removed, keeping newer 'Tars 2'")
    print("   Unattached volume removed")


def main():
    """Main function."""
    cleanup_london_ebs_volumes()


if __name__ == "__main__":
    main()
