#!/usr/bin/env python3
"""
AWS Snapshot Bulk Deletion Script
Deletes multiple EBS snapshots across regions.
"""


from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import get_common_regions_extended
from cost_toolkit.common.confirmation_prompts import confirm_bulk_deletion
from cost_toolkit.common.cost_utils import calculate_snapshot_cost
from cost_toolkit.scripts.aws_ec2_operations import delete_snapshot, find_resource_region

from ..aws_utils import setup_aws_credentials

COMMON_REGIONS = get_common_regions_extended()


def get_snapshot_details(snapshot_id, region):
    """
    Get detailed information about a snapshot.

    Args:
        snapshot_id: The EBS snapshot ID
        region: AWS region where the snapshot is located

    Returns:
        Dictionary containing snapshot information
    """
    ec2_client = create_client("ec2", region=region)
    response = ec2_client.describe_snapshots(SnapshotIds=[snapshot_id])
    if "Snapshots" not in response or not response["Snapshots"]:
        raise ValueError(f"Snapshot {snapshot_id} not found in {region}")
    snapshots = response["Snapshots"]
    if not snapshots:
        raise ValueError(f"Snapshot {snapshot_id} not found in {region}")

    snapshot = snapshots[0]
    required_fields = ["VolumeSize", "State", "StartTime", "Encrypted"]
    missing_fields = [field for field in required_fields if field not in snapshot]
    if missing_fields:
        raise KeyError(f"Snapshot {snapshot_id} missing required fields: {', '.join(missing_fields)}")

    return {
        "snapshot_id": snapshot.get("SnapshotId"),
        "region": region,
        "size_gb": snapshot["VolumeSize"],
        "state": snapshot["State"],
        "start_time": snapshot["StartTime"],
        "description": snapshot.get("Description"),
        "encrypted": snapshot["Encrypted"],
    }


def delete_snapshot_safely(snapshot_id, region, *, snapshot_info=None):
    """
    Safely delete an EBS snapshot with proper checks.

    Args:
        snapshot_id: The EBS snapshot ID to delete
        region: AWS region where the snapshot is located

    Returns:
        True if successful, False otherwise
    """
    try:
        ec2_client = create_client("ec2", region=region)

        # Get snapshot details first
        if snapshot_info is None:
            snapshot_info = get_snapshot_details(snapshot_id, region)

        print(f"🗑️  Deleting snapshot: {snapshot_id}")
        print(f"   Region: {region}")
        print(f"   Size: {snapshot_info['size_gb']} GB")
        print(f"   Created: {snapshot_info['start_time']}")
        description = snapshot_info["description"]
        if description:
            description_preview = description[:80]
        else:
            description_preview = "<missing description>"
        print(f"   Description: {description_preview}")

        # Calculate cost savings
        monthly_savings = calculate_snapshot_cost(snapshot_info["size_gb"])

        # Delete the snapshot using canonical helper
        deletion_success = delete_snapshot(
            snapshot_id,
            region,
            ec2_client=ec2_client,
        )
        if not deletion_success:
            print()
            return False

        print(f"   💰 Monthly savings: ${monthly_savings:.2f}")
        print()

    except ClientError as e:
        print(f"   ❌ Error deleting snapshot {snapshot_id}: {str(e)}")
        print()
        return False

    return True


def get_bulk_deletion_snapshots():
    """Get list of snapshot IDs to delete"""
    return [
        "snap-03490193a42293c87",  # 1024 GB - snapshot 2
        "snap-09e90c64db692f884",  # 1024 GB - CreateImage
        "snap-0e4a9793f5a9ac3fb",  # 1024 GB - Final Large Sized Snapshot
        "snap-07c0d4017e24b3240",  # 32 GB - SadTalker
        "snap-0fbb003580d3dc8ba",  # 64 GB - SadTalker
        "snap-04ced16a925e3f820",  # 8 GB - mufasa snapshot
        "snap-024d718f6d670bff2",  # 8 GB - CreateImage
        "snap-0ac8b88270ff68d4d",  # 8 GB - CreateImage
        "snap-036eee4a7c291fd26",  # 8 GB - Copied
        "snap-0700cdc4cdfaaf8fd",  # 8 GB - Copied
        "snap-05a42843f18ba1c5e",  # 8 GB - Copied mufasa snapshot
        "snap-0c81e260dcafb8968",  # 8 GB - Snapshot of Unnamed (mufasa backup)
    ]


def print_bulk_deletion_warning(snapshots_to_delete):
    """Print warning message about bulk deletion"""
    print("AWS Snapshot Bulk Deletion Script")
    print("=" * 80)
    print("Deleting specified EBS snapshots...")
    print()
    print(f"🎯 Target: {len(snapshots_to_delete)} snapshots for deletion")
    print()
    print("⚠️  FINAL WARNING: This will permanently delete these snapshots!")
    print("   - All snapshot data will be lost")
    print("   - This action cannot be undone")
    print("   - You will lose the ability to restore from these snapshots")
    print()


def process_bulk_deletions(snapshots_to_delete):
    """Process deletion for all snapshots"""
    successful_deletions = 0
    failed_deletions = 0
    total_savings = 0

    for snapshot_id in snapshots_to_delete:
        print(f"🔍 Processing {snapshot_id}...")

        region = find_resource_region("snapshot", snapshot_id, regions=COMMON_REGIONS)
        if region is None:
            region = find_resource_region("snapshot", snapshot_id)

        if not region:
            print(f"   ❌ Snapshot {snapshot_id} not found in any region")
            failed_deletions += 1
            print()
            continue

        try:
            snapshot_info = get_snapshot_details(snapshot_id, region)
        except (ClientError, ValueError) as exc:
            print(f"   ❌ Unable to retrieve details for {snapshot_id}: {exc}")
            failed_deletions += 1
            print()
            continue

        monthly_savings = calculate_snapshot_cost(snapshot_info["size_gb"])
        total_savings += monthly_savings

        if delete_snapshot_safely(snapshot_id, region, snapshot_info=snapshot_info):
            successful_deletions += 1
        else:
            failed_deletions += 1

    return successful_deletions, failed_deletions, total_savings


def print_bulk_deletion_summary(successful_deletions, failed_deletions, total_savings):
    """Print summary of bulk deletion results"""
    print("=" * 80)
    print("🎯 BULK DELETION SUMMARY")
    print("=" * 80)

    print(f"✅ Successfully deleted: {successful_deletions} snapshots")
    if failed_deletions > 0:
        print(f"❌ Failed to delete: {failed_deletions} snapshots")

    print(f"💰 Total monthly savings: ${total_savings:.2f}")
    print(f"💰 Annual savings: ${total_savings * 12:.2f}")

    if successful_deletions > 0:
        print()
        print("🎉 Snapshot cleanup completed successfully!")
        print("   Your AWS storage costs have been significantly reduced.")

    print()
    print("📝 Remaining snapshots can be verified with:")
    print("   python3 scripts/audit/aws_ebs_audit.py")


def main():
    """Main function to delete specified snapshots."""
    setup_aws_credentials()

    snapshots_to_delete = get_bulk_deletion_snapshots()
    print_bulk_deletion_warning(snapshots_to_delete)

    if not confirm_bulk_deletion():
        print("❌ Deletion cancelled")
        return

    print()
    print("🚨 Proceeding with bulk snapshot deletion...")
    print("=" * 80)

    successful, failed, savings = process_bulk_deletions(snapshots_to_delete)
    print_bulk_deletion_summary(successful, failed, savings)


if __name__ == "__main__":
    main()
