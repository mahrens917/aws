#!/usr/bin/env python3
"""
AWS EBS Snapshot to S3 Semi-Manual Export Script
This script automates the reliable parts and provides manual commands for the rest:

AUTOMATED:
- Creates AMIs from snapshots (this works reliably)
- Sets up S3 buckets with proper configuration
- Validates prerequisites

MANUAL (with exact commands provided):
- Export AMI to S3 (you run the AWS CLI commands)
- Monitor export progress
- Clean up temporary AMIs after success

This approach gives you control over the problematic AWS export service.
"""

from datetime import datetime

from botocore.exceptions import BotoCoreError, ClientError

from cost_toolkit.common.aws_client_factory import load_credentials_from_env
from cost_toolkit.common.aws_common import create_ec2_and_s3_clients
from cost_toolkit.common.cost_utils import calculate_snapshot_cost
from cost_toolkit.scripts.optimization.snapshot_export_common import (
    create_ami_from_snapshot,
    create_s3_bucket_if_not_exists,
)
from cost_toolkit.scripts.snapshot_export_common import SAMPLE_SNAPSHOTS


def prepare_snapshot_for_export(snapshot_info, aws_access_key_id, aws_secret_access_key):
    """Prepare a snapshot for manual export by creating AMI and S3 bucket"""
    snapshot_id = snapshot_info["snapshot_id"]
    region = snapshot_info["region"]
    size_gb = snapshot_info["size_gb"]
    description = snapshot_info["description"]

    print(f"\n🔍 Preparing {snapshot_id} ({size_gb} GB) in {region}...")

    # Create clients
    ec2_client, s3_client = create_ec2_and_s3_clients(region, aws_access_key_id, aws_secret_access_key)

    # Create S3 bucket
    bucket_name = f"ebs-snapshot-archive-{region}-{datetime.now().strftime('%Y%m%d')}"
    create_s3_bucket_if_not_exists(s3_client, bucket_name, region)

    # Create AMI - use gp2 for better compatibility with manual workflow
    ami_id = create_ami_from_snapshot(
        ec2_client,
        snapshot_id,
        description,
        volume_type="gp2",
        boot_mode="legacy-bios",
        ena_support=False,
    )

    # Calculate potential savings
    ebs_monthly_cost = calculate_snapshot_cost(size_gb)
    s3_monthly_cost = size_gb * 0.023
    monthly_savings = ebs_monthly_cost - s3_monthly_cost

    return {
        "snapshot_id": snapshot_id,
        "ami_id": ami_id,
        "bucket_name": bucket_name,
        "region": region,
        "size_gb": size_gb,
        "monthly_savings": monthly_savings,
        "description": description,
    }


def _build_export_command(_ami_id, _bucket_name, _region, _snapshot_id):
    """Build AWS CLI export command"""
    return """aws ec2 export-image \\
    --image-id {ami_id} \\
    --disk-image-format VMDK \\
    --s3-export-location S3Bucket={bucket_name},S3Prefix=ebs-snapshots/{ami_id}/ \\
    --description "Manual export of {snapshot_id}" \\
    --region {region}"""


def _build_monitor_command(_region, _ami_id):
    """Build monitoring command"""
    return """# Monitor export progress:
aws ec2 describe-export-image-tasks \\
    --region {region} \\
    --query 'ExportImageTasks[?ImageId==`{ami_id}`].[ExportImageTaskId,Status,Progress,StatusMessage]' \\
    --output table"""


def _build_s3_check_command(_bucket_name, _ami_id):
    """Build S3 verification command"""
    return """# Check S3 file directly:
aws s3 ls s3://{bucket_name}/ebs-snapshots/{ami_id}/ --recursive --human-readable

# Check S3 file size (most reliable completion check):
aws s3api head-object --bucket {bucket_name} --key ebs-snapshots/{ami_id}/{ami_id}.vmdk"""


def _build_cleanup_command(_ami_id, _region):
    """Build cleanup command"""
    return """# CLEANUP (run only after successful export):
aws ec2 deregister-image --image-id {ami_id} --region {region}"""


def _print_workflow_and_troubleshooting():
    """Print workflow instructions and troubleshooting tips"""
    print("📊 EXPORT WORKFLOW:")
    print("1. Run each export command above")
    print("2. Monitor progress with the monitor commands")
    print("3. If export gets stuck at 80%, wait 2-3 hours and check S3 directly")
    print("4. Once S3 file appears and is stable, run cleanup commands")
    print("5. Verify S3 files exist before deleting original snapshots")
    print()

    print("🔧 TROUBLESHOOTING:")
    print("- If export fails immediately: Try again in 10-15 minutes")
    print("- If stuck at 80%: Check S3 directly - file might be complete")
    print("- If export gets deleted: Try in a different region (eu-west-2 works better)")
    print()


def _print_monitoring_commands(prepared_snapshots):
    """Print S3 monitoring commands"""
    print("📊 S3 FILE SIZE MONITORING COMMANDS:")
    for prep in prepared_snapshots:
        bucket_name = prep["bucket_name"]
        ami_id = prep["ami_id"]
        print(f"aws s3api head-object --bucket {bucket_name} " f"--key ebs-snapshots/{ami_id}/{ami_id}.vmdk")
    print()


def _print_cost_summary(prepared_snapshots):
    """Print cost savings summary"""
    total_savings = sum(prep["monthly_savings"] for prep in prepared_snapshots)
    print("💰 POTENTIAL SAVINGS:")
    print(f"   Monthly: ${total_savings:.2f}")
    print(f"   Annual: ${total_savings * 12:.2f}")


def generate_manual_commands(prepared_snapshots):
    """Generate the manual AWS CLI commands for exports"""
    print("\n" + "=" * 80)
    print("📋 MANUAL EXPORT COMMANDS")
    print("=" * 80)
    print("The AMIs are ready! Now run these commands manually to export them:")
    print()

    export_commands = []
    monitor_commands = []
    cleanup_commands = []

    for i, prep in enumerate(prepared_snapshots, 1):
        ami_id = prep["ami_id"]
        bucket_name = prep["bucket_name"]
        region = prep["region"]
        snapshot_id = prep["snapshot_id"]

        export_cmd = _build_export_command(ami_id, bucket_name, region, snapshot_id)
        monitor_cmd = _build_monitor_command(region, ami_id)
        s3_check_cmd = _build_s3_check_command(bucket_name, ami_id)
        cleanup_cmd = _build_cleanup_command(ami_id, region)

        print(f"## Step {i}: Export {snapshot_id} ({prep['size_gb']} GB)")
        print("### Export Command:")
        print(export_cmd)
        print()
        print("### Monitor Progress:")
        print(monitor_cmd)
        print()
        print(s3_check_cmd)
        print()
        print("### Cleanup (ONLY after success):")
        print(cleanup_cmd)
        print()
        print("-" * 60)
        print()

        export_commands.append(export_cmd)
        monitor_commands.append(monitor_cmd)
        cleanup_commands.append(cleanup_cmd)

    _print_workflow_and_troubleshooting()
    _print_monitoring_commands(prepared_snapshots)
    _print_cost_summary(prepared_snapshots)

    return export_commands, monitor_commands, cleanup_commands


def _get_target_snapshots():
    """Get list of snapshots to process"""
    return SAMPLE_SNAPSHOTS


def _prepare_all_snapshots(snapshots, aws_access_key_id, aws_secret_access_key):
    """Prepare all snapshots for export"""
    prepared_snapshots = []
    for snapshot in snapshots:
        try:
            prepared = prepare_snapshot_for_export(snapshot, aws_access_key_id, aws_secret_access_key)
            prepared_snapshots.append(prepared)
        except (BotoCoreError, ClientError) as exc:
            print(f"   ❌ Failed to prepare {snapshot['snapshot_id']}: {exc}")
        except RuntimeError as exc:
            print(f"   ❌ Failed to prepare {snapshot['snapshot_id']}: {exc}")
    return prepared_snapshots


def _save_commands_to_file(prepared_snapshots, export_commands, monitor_commands, cleanup_commands):
    """Save generated commands to a file"""
    commands_file = f"manual_export_commands_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(commands_file, "w", encoding="utf-8") as f:
        f.write("AWS EBS Snapshot to S3 Manual Export Commands\n")
        f.write("=" * 50 + "\n\n")

        for i, prep in enumerate(prepared_snapshots, 1):
            f.write(f"Step {i}: Export {prep['snapshot_id']} ({prep['size_gb']} GB)\n")
            f.write("-" * 40 + "\n")
            f.write("Export Command:\n")
            f.write(export_commands[i - 1] + "\n\n")
            f.write("Monitor Command:\n")
            f.write(monitor_commands[i - 1] + "\n\n")
            f.write("Cleanup Command:\n")
            f.write(cleanup_commands[i - 1] + "\n\n")

    print(f"\n📄 Commands saved to: {commands_file}")


def main():
    """Main function"""
    print("AWS EBS Snapshot to S3 Semi-Manual Export Script")
    print("=" * 80)
    print("This script will:")
    print("✅ Create AMIs from your snapshots (automated)")
    print("✅ Set up S3 buckets (automated)")
    print("📋 Provide exact manual commands for exports")
    print("📋 Provide monitoring and cleanup commands")
    print()

    aws_access_key_id, aws_secret_access_key = load_credentials_from_env()
    snapshots = _get_target_snapshots()

    total_size_gb = sum(snap["size_gb"] for snap in snapshots)
    total_monthly_savings = total_size_gb * (0.05 - 0.023)

    print(f"🎯 Target: {len(snapshots)} snapshots ({total_size_gb} GB total)")
    print(f"💰 Potential monthly savings: ${total_monthly_savings:.2f}")
    print(f"💰 Potential annual savings: ${total_monthly_savings * 12:.2f}")
    print()

    print("\n🚀 Starting automated preparation...")

    prepared_snapshots = _prepare_all_snapshots(snapshots, aws_access_key_id, aws_secret_access_key)

    export_commands, monitor_commands, cleanup_commands = generate_manual_commands(prepared_snapshots)

    _save_commands_to_file(prepared_snapshots, export_commands, monitor_commands, cleanup_commands)

    print("\n✅ PREPARATION COMPLETE!")
    print("🎯 Next: Run the manual export commands shown above")


if __name__ == "__main__":
    main()
