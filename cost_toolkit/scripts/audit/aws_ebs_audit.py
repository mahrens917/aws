#!/usr/bin/env python3
"""Audit EBS volumes and storage costs."""

from collections import defaultdict
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.cost_utils import calculate_ebs_volume_cost, calculate_snapshot_cost
from cost_toolkit.common.credential_utils import setup_aws_credentials
from cost_toolkit.scripts.aws_ec2_operations import get_all_regions

# Constants
OLD_SNAPSHOT_AGE_DAYS = 30


def _get_attachment_info(volume):
    """Extract attachment information from volume"""
    attachments = []
    if "Attachments" in volume:
        attachments = volume["Attachments"]
    if not attachments:
        return "Not attached"
    instance_id = attachments[0].get("InstanceId")
    return f"Instance: {instance_id}"


def _process_volume(volume, region):
    """Process a single volume and return its details"""
    volume_id = volume["VolumeId"]
    size_gb = volume["Size"]
    volume_type = volume["VolumeType"]
    state = volume["State"]
    attached_to = _get_attachment_info(volume)
    monthly_cost = calculate_ebs_volume_cost(size_gb, volume_type)

    print(f"  Volume ID: {volume_id}")
    print(f"    Size: {size_gb} GB")
    print(f"    Type: {volume_type}")
    print(f"    State: {state}")
    print(f"    Attached to: {attached_to}")
    print(f"    Est. monthly cost: ${monthly_cost:.2f}")
    print()

    return {
        "region": region,
        "volume_id": volume_id,
        "size_gb": size_gb,
        "volume_type": volume_type,
        "state": state,
        "attached_to": attached_to,
        "monthly_cost": monthly_cost,
    }


def _process_snapshot(snapshot, region):
    """Process a single snapshot and return its details"""
    snapshot_id = snapshot["SnapshotId"]
    if "VolumeSize" not in snapshot:
        raise KeyError(f"Snapshot {snapshot_id} missing VolumeSize")
    size_gb = snapshot["VolumeSize"]
    state = snapshot["State"]
    start_time = snapshot["StartTime"]
    description = snapshot.get("Description")
    monthly_cost = calculate_snapshot_cost(size_gb)

    print(f"  Snapshot ID: {snapshot_id}")
    print(f"    Size: {size_gb} GB")
    print(f"    State: {state}")
    print(f"    Created: {start_time}")
    print(f"    Description: {description}")
    print(f"    Est. monthly cost: ${monthly_cost:.2f}")
    print()

    return {
        "region": region,
        "snapshot_id": snapshot_id,
        "size_gb": size_gb,
        "state": state,
        "start_time": start_time,
        "description": description,
        "monthly_cost": monthly_cost,
    }


def _audit_region(region):
    """Audit EBS resources in a single region"""
    ec2 = create_client("ec2", region=region)
    volumes_response = ec2.describe_volumes()
    volumes = []
    if "Volumes" in volumes_response:
        volumes = volumes_response["Volumes"]
    snapshots_response = ec2.describe_snapshots(OwnerIds=["self"])
    snapshots = []
    if "Snapshots" in snapshots_response:
        snapshots = snapshots_response["Snapshots"]

    if not volumes and not snapshots:
        return [], []

    print(f"🔍 Auditing EBS resources in {region}")
    print("=" * 80)

    volume_details = []
    if volumes:
        print(f"📦 EBS Volumes ({len(volumes)} found):")
        for volume in volumes:
            volume_details.append(_process_volume(volume, region))

    snapshot_details = []
    if snapshots:
        print(f"📸 EBS Snapshots ({len(snapshots)} found):")
        for snapshot in snapshots:
            snapshot_details.append(_process_snapshot(snapshot, region))

    print()
    return volume_details, snapshot_details


def _print_volume_breakdown(volume_details):
    """Print breakdown of volumes by type"""
    print("📊 Volume Breakdown by Type:")
    volume_types = defaultdict(lambda: {"count": 0, "size": 0, "cost": 0})
    for vol in volume_details:
        volume_types[vol["volume_type"]]["count"] += 1
        volume_types[vol["volume_type"]]["size"] += vol["size_gb"]
        volume_types[vol["volume_type"]]["cost"] += vol["monthly_cost"]

    for vol_type, stats in volume_types.items():
        count = stats["count"]
        size = stats["size"]
        cost = stats["cost"]
        print(f"  {vol_type}: {count} volumes, {size} GB total, ${cost:.2f}/month")
    print()


def _print_unattached_volumes(volume_details):
    """Print information about unattached volumes"""
    unattached_volumes = [vol for vol in volume_details if "Not attached" in vol["attached_to"]]
    if not unattached_volumes:
        return []

    print("⚠️  UNATTACHED VOLUMES (Potential cleanup candidates):")
    unattached_cost = sum(vol["monthly_cost"] for vol in unattached_volumes)
    count = len(unattached_volumes)
    print(f"Found {count} unattached volumes costing ${unattached_cost:.2f}/month")
    for vol in unattached_volumes:
        region = vol["region"]
        volume_id = vol["volume_id"]
        size = vol["size_gb"]
        vol_type = vol["volume_type"]
        cost = vol["monthly_cost"]
        print(f"  {region}: {volume_id} ({size} GB {vol_type}) - ${cost:.2f}/month")
    print()
    return unattached_volumes


def _print_old_snapshots(snapshot_details):
    """Print information about old snapshots"""
    print("📅 SNAPSHOT AGE ANALYSIS:")
    now = datetime.now(timezone.utc)
    old_snapshots = []
    for snap in snapshot_details:
        age_days = (now - snap["start_time"]).days
        if age_days > OLD_SNAPSHOT_AGE_DAYS:
            old_snapshots.append({**snap, "age_days": age_days})

    if old_snapshots:
        old_snapshot_cost = sum(snap["monthly_cost"] for snap in old_snapshots)
        count = len(old_snapshots)
        days = OLD_SNAPSHOT_AGE_DAYS
        print(f"Found {count} snapshots older than {days} days " f"costing ${old_snapshot_cost:.2f}/month")
        old_snapshots.sort(key=lambda x: x["monthly_cost"], reverse=True)
        for snap in old_snapshots[:10]:
            region = snap["region"]
            snapshot_id = snap["snapshot_id"]
            size = snap["size_gb"]
            age = snap["age_days"]
            cost = snap["monthly_cost"]
            print(f"  {region}: {snapshot_id} ({size} GB, {age} days old) - ${cost:.2f}/month")
    else:
        print(f"All snapshots are less than {OLD_SNAPSHOT_AGE_DAYS} days old")
    print()
    return old_snapshots


def _print_recommendations(unattached_volumes, old_snapshots):
    """Print recommendations for cost optimization"""
    print("💡 RECOMMENDATIONS:")
    if unattached_volumes:
        cost_savings = sum(vol["monthly_cost"] for vol in unattached_volumes)
        count = len(unattached_volumes)
        print(f"  1. Consider deleting {count} unattached volumes " f"to save ${cost_savings:.2f}/month")
    if old_snapshots:
        cost_savings = sum(snap["monthly_cost"] for snap in old_snapshots)
        count = len(old_snapshots)
        print(f"  2. Review {count} old snapshots - delete unnecessary ones " f"to save up to ${cost_savings:.2f}/month")
    if not unattached_volumes and not old_snapshots:
        print("  All EBS resources appear to be in active use")


def audit_ebs_volumes():
    """Audit all EBS volumes across all regions"""
    setup_aws_credentials()

    print("AWS EBS Volume & Snapshot Audit")
    print("=" * 80)
    print("Analyzing all EBS volumes and snapshots across all regions...")
    print()

    regions = get_all_regions()
    all_volume_details = []
    all_snapshot_details = []

    for region in regions:
        try:
            volume_details, snapshot_details = _audit_region(region)
            all_volume_details.extend(volume_details)
            all_snapshot_details.extend(snapshot_details)
        except ClientError as e:
            print(f"⚠️  Error auditing {region}: {e}")
            continue

    total_volume_cost = sum(vol["monthly_cost"] for vol in all_volume_details)
    total_snapshot_cost = sum(snap["monthly_cost"] for snap in all_snapshot_details)

    print("=" * 80)
    print("🎯 OVERALL EBS SUMMARY")
    print("=" * 80)
    print(f"Total EBS Volumes found: {len(all_volume_details)}")
    print(f"Total EBS Snapshots found: {len(all_snapshot_details)}")
    print(f"Estimated monthly cost for volumes: ${total_volume_cost:.2f}")
    print(f"Estimated monthly cost for snapshots: ${total_snapshot_cost:.2f}")
    print(f"Total estimated monthly EBS cost: ${total_volume_cost + total_snapshot_cost:.2f}")
    print()

    if all_volume_details:
        _print_volume_breakdown(all_volume_details)

    unattached_volumes = _print_unattached_volumes(all_volume_details)

    old_snapshots = []
    if all_snapshot_details:
        old_snapshots = _print_old_snapshots(all_snapshot_details)

    _print_recommendations(unattached_volumes, old_snapshots)


def main():
    """Main function."""
    audit_ebs_volumes()


if __name__ == "__main__":
    main()
