"""CLI interface for fixed snapshot export"""

import argparse
from datetime import datetime

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_common import create_ec2_and_s3_clients
from cost_toolkit.common.credential_utils import setup_aws_credentials
from cost_toolkit.scripts.optimization.snapshot_export_common import (
    create_ami_from_snapshot,
    create_s3_bucket_if_not_exists,
    setup_s3_bucket_versioning,
)
from cost_toolkit.scripts.snapshot_export_common import (
    print_export_results,
    print_export_summary,
)

from .constants import (
    ExportTaskDeletedException,
    ExportTaskFailedException,
    ExportTaskStuckException,
)
from .export_helpers import export_ami_to_s3_with_recovery
from .export_ops import create_s3_bucket_new
from .monitoring import calculate_cost_savings, verify_s3_export_final
from .recovery import (
    check_existing_completed_exports,
    cleanup_temporary_ami,
    get_snapshots_to_export,
)


def _setup_aws_clients(region, aws_access_key_id, aws_secret_access_key):
    """Create and return EC2 and S3 clients for the given region."""
    return create_ec2_and_s3_clients(region, aws_access_key_id, aws_secret_access_key)


def _setup_s3_bucket_for_export(s3_client, region):
    """Create and configure S3 bucket for snapshot export."""
    bucket_name = f"ebs-snapshot-archive-{region}-{datetime.now().strftime('%Y%m%d')}"

    print(f"   🔍 Checking for existing completed exports in {region}...")
    check_existing_completed_exports(s3_client, region)

    try:
        create_s3_bucket_if_not_exists(s3_client, bucket_name, region)
    except s3_client.exceptions.NoSuchBucket:
        create_s3_bucket_new(s3_client, bucket_name, region)

    setup_s3_bucket_versioning(s3_client, bucket_name)

    return bucket_name


def _build_export_result(snapshot_id, ami_id, bucket_name, *, s3_key, export_task_id, size_gb, savings):
    """Build export result dictionary."""
    return {
        "snapshot_id": snapshot_id,
        "ami_id": ami_id,
        "bucket_name": bucket_name,
        "s3_key": s3_key,
        "export_task_id": export_task_id,
        "size_gb": size_gb,
        "monthly_savings": savings["monthly_savings"],
        "success": True,
    }


def export_single_snapshot_to_s3(snapshot_info, aws_access_key_id, aws_secret_access_key):
    """Export a single snapshot to S3 with comprehensive error handling"""
    snapshot_id = snapshot_info["snapshot_id"]
    region = snapshot_info["region"]
    size_gb = snapshot_info["size_gb"]
    description = snapshot_info["description"]

    print(f"🔍 Processing {snapshot_id} ({size_gb} GB) in {region}...")

    ec2_client, s3_client = _setup_aws_clients(region, aws_access_key_id, aws_secret_access_key)
    bucket_name = _setup_s3_bucket_for_export(s3_client, region)

    ami_id = create_ami_from_snapshot(ec2_client, snapshot_id, description)

    try:
        export_task_id, s3_key = export_ami_to_s3_with_recovery(ec2_client, s3_client, ami_id, bucket_name, region, size_gb)

        verify_s3_export_final(s3_client, bucket_name, s3_key, size_gb)

        savings = calculate_cost_savings(size_gb)

        cleanup_temporary_ami(ec2_client, ami_id, region)

        print(f"   ✅ Successfully exported {snapshot_id}")
        print(f"   📍 S3 location: s3://{bucket_name}/{s3_key}")
        print(f"   💰 Monthly savings: ${savings['monthly_savings']:.2f}")

        return _build_export_result(
            snapshot_id,
            ami_id,
            bucket_name,
            s3_key=s3_key,
            export_task_id=export_task_id,
            size_gb=size_gb,
            savings=savings,
        )

    except (ExportTaskDeletedException, ExportTaskStuckException):
        try:
            cleanup_temporary_ami(ec2_client, ami_id, region)
        except ClientError as cleanup_error:
            print(f"   ⚠️  Warning: Could not clean up AMI {ami_id}: {cleanup_error}")

        raise

    except ClientError:
        try:
            cleanup_temporary_ami(ec2_client, ami_id, region)
        except ClientError as cleanup_error:
            print(f"   ⚠️  Warning: Could not clean up AMI {ami_id}: {cleanup_error}")

        raise


def _print_export_intro_fixed(snapshots_to_export, total_savings):
    """Print introduction and summary for export."""
    print("AWS EBS Snapshot to S3 Export Script - FIXED VERSION")
    print("=" * 80)
    print("Exporting EBS snapshots to S3 with fail-fast error handling...")

    print_export_summary(snapshots_to_export, total_savings)

    print("⚠️  IMPORTANT NOTES:")
    print("   - Export process can take several hours per snapshot")
    print("   - AMIs will be created temporarily and automatically cleaned up after export")
    print("   - Data will be stored in S3 Standard for immediate access")
    print("   - All errors will fail fast - no hidden failures")
    print()


def _print_final_summary_fixed(successful_exports, export_results, snapshots_to_export):
    """Print final summary of export operation."""
    print("=" * 80)
    print("🎯 S3 EXPORT SUMMARY")
    print("=" * 80)
    print(f"✅ Successfully exported: {successful_exports} snapshots")

    if not export_results:
        return

    print_export_results(export_results)
    print("3. Delete original EBS snapshots to realize savings")
    print()
    print("🔧 Delete Original Snapshots (after verifying S3 exports):")
    for result in export_results:
        region = next(snap["region"] for snap in snapshots_to_export if snap["snapshot_id"] == result["snapshot_id"])
        print(f"   aws ec2 delete-snapshot --snapshot-id {result['snapshot_id']} --region {region}")


def export_snapshots_to_s3_fixed():
    """Main function to export EBS snapshots to S3 with fail-fast error handling"""
    aws_access_key_id, aws_secret_access_key = setup_aws_credentials()
    snapshots_to_export = get_snapshots_to_export(aws_access_key_id, aws_secret_access_key)

    total_size_gb = sum(snap["size_gb"] for snap in snapshots_to_export)
    total_savings = calculate_cost_savings(total_size_gb)

    _print_export_intro_fixed(snapshots_to_export, total_savings)

    confirmation = input("Type 'EXPORT TO S3' to proceed with snapshot export: ")
    if confirmation != "EXPORT TO S3":
        msg = "Operation cancelled by user"
        raise ValueError(msg)

    print()
    print("🚨 Proceeding with snapshot export to S3...")
    print("=" * 80)

    export_results = []
    snapshots_to_export = sorted(snapshots_to_export, key=lambda x: x["size_gb"])

    print("📋 Processing snapshots in order of size (smallest first):")
    for snap in snapshots_to_export:
        print(f"   - {snap['snapshot_id']}: {snap['size_gb']} GB")
    print()

    for snap_info in snapshots_to_export:
        try:
            result = export_single_snapshot_to_s3(snap_info, aws_access_key_id, aws_secret_access_key)
            export_results.append(result)

        except (ExportTaskDeletedException, ExportTaskStuckException) as e:
            print(f"   ❌ Failed to export {snap_info['snapshot_id']}: {e}")
            print("   💡 This is a known AWS export service issue - continuing with next snapshot...")
            print("   🔄 Continuing with next snapshot...")
            continue

        except ClientError as e:
            print(f"   ❌ Failed to export {snap_info['snapshot_id']}: {e}")
            msg = f"Export failed for {snap_info['snapshot_id']}: {e}"
            raise ExportTaskFailedException(msg) from e
        print()

    _print_final_summary_fixed(len(export_results), export_results, snapshots_to_export)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Export EBS snapshots to S3 for cost optimization - FIXED VERSION",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 aws_snapshot_to_s3_export_fixed.py    # Export with fail-fast error handling
        """,
    )

    parser.parse_args()

    export_snapshots_to_s3_fixed()


if __name__ == "__main__":
    main()
