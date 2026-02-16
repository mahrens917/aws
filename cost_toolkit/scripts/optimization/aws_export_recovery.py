#!/usr/bin/env python3
"""
AWS Export Recovery Script
Checks if stuck exports have actually completed in S3 despite AWS showing 'active' status.
This addresses the known AWS issue where exports get stuck at 80% progress with 'converting' status.
"""

from datetime import datetime

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_common import create_ec2_and_s3_clients
from cost_toolkit.common.cost_utils import calculate_snapshot_cost
from cost_toolkit.common.credential_utils import setup_aws_credentials

EXPORT_STABILITY_MINUTES = 10


def _check_s3_file_exists(s3_client, bucket_name, s3_key):
    """Check if S3 file exists and get its metadata"""
    try:
        response = s3_client.head_object(Bucket=bucket_name, Key=s3_key)
        file_size_bytes = response["ContentLength"]
        file_size_gb = file_size_bytes / (1024**3)
        last_modified = response["LastModified"]
    except s3_client.exceptions.NoSuchKey:
        return {"exists": False}
    except ClientError as e:
        return {"exists": False, "error": str(e)}
    return {
        "exists": True,
        "size_bytes": file_size_bytes,
        "size_gb": file_size_gb,
        "last_modified": last_modified,
    }


def _is_file_stable(last_modified):
    """Check if file has been stable for required minutes"""
    time_since_modified = datetime.now(last_modified.tzinfo) - last_modified
    minutes_since_modified = time_since_modified.total_seconds() / 60
    return minutes_since_modified > EXPORT_STABILITY_MINUTES, minutes_since_modified


def _process_stuck_export(task, s3_client):
    """Process a potentially stuck export task"""
    export_task_id = task["ExportImageTaskId"]
    ami_id = task.get("ImageId") or "unknown"

    print("      ⚠️  Classic 80% stuck scenario detected!")

    s3_location = task.get("S3ExportLocation")
    if not s3_location:
        print("      ❌ No S3 bucket information found in export task")
        return None
    bucket_name = s3_location.get("S3Bucket")
    s3_prefix = s3_location.get("S3Prefix")

    if not bucket_name:
        print("      ❌ No S3 bucket information found in export task")
        return None

    s3_key = f"{s3_prefix}{export_task_id}.vmdk"
    print(f"      🔍 Checking S3: s3://{bucket_name}/{s3_key}")

    file_info = _check_s3_file_exists(s3_client, bucket_name, s3_key)

    if not file_info["exists"]:
        if "error" in file_info:
            print(f"      ❌ Error checking S3: {file_info['error']}")
        else:
            print("      ❌ S3 file not found - export may have genuinely failed")
        return None

    print("      ✅ S3 file exists!")
    print(f"      📏 Size: {file_info['size_gb']:.2f} GB ({file_info['size_bytes']:,} bytes)")
    print(f"      📅 Last modified: {file_info['last_modified']}")

    is_stable, minutes = _is_file_stable(file_info["last_modified"])

    if is_stable:
        print(f"      ✅ File appears stable (last modified {minutes:.1f} minutes ago)")
        print("      🎉 EXPORT LIKELY COMPLETED SUCCESSFULLY!")
        return {
            "export_task_id": export_task_id,
            "ami_id": ami_id,
            "bucket_name": bucket_name,
            "s3_key": s3_key,
            "size_gb": file_info["size_gb"],
            "status": "recovered",
        }
    print(f"      ⏳ File still being written (modified {minutes:.1f} minutes ago)")
    return None


def check_active_exports(region, aws_access_key_id, aws_secret_access_key):
    """Check all active export tasks in a region"""
    ec2_client, s3_client = create_ec2_and_s3_clients(region, aws_access_key_id, aws_secret_access_key)

    print(f"\n🔍 Checking active exports in {region}...")

    response = ec2_client.describe_export_image_tasks()
    active_exports = [task for task in response["ExportImageTasks"] if task["Status"] == "active"]

    if not active_exports:
        print(f"   ✅ No active exports found in {region}")
        return []

    print(f"   📊 Found {len(active_exports)} active export(s)")

    recovered_exports = []

    for task in active_exports:
        export_task_id = task["ExportImageTaskId"]
        ami_id = task.get("ImageId") or "unknown"
        progress = task.get("Progress") or "N/A"
        status_msg = task.get("StatusMessage")

        print(f"\n   🔍 Checking export {export_task_id}:")
        print(f"      AMI: {ami_id}")
        print(f"      Progress: {progress}%")
        print(f"      Status Message: {status_msg}")

        if progress == "80" and status_msg == "converting":
            recovered = _process_stuck_export(task, s3_client)
            if recovered:
                recovered_exports.append(recovered)
        else:
            print("      ℹ️  Not the classic stuck scenario - continuing to monitor")

    return recovered_exports


def main():
    """Main recovery function"""
    print("AWS Export Recovery Script")
    print("=" * 50)
    print("Checking for stuck exports that may have actually completed...")

    aws_access_key_id, aws_secret_access_key = setup_aws_credentials()

    # Check common regions where exports might be running
    regions_to_check = ["us-east-2", "eu-west-2", "us-east-1", "us-west-2"]

    all_recovered = []

    for region in regions_to_check:
        try:
            recovered = check_active_exports(region, aws_access_key_id, aws_secret_access_key)
            all_recovered.extend(recovered)
        except ClientError as e:
            print(f"\n❌ Error checking {region}: {e}")

    print("\n" + "=" * 50)
    print("🎯 RECOVERY SUMMARY")
    print("=" * 50)

    if all_recovered:
        print(f"✅ Found {len(all_recovered)} likely completed export(s):")

        total_size_gb = 0
        for export in all_recovered:
            print(f"\n   📦 Export: {export['export_task_id']}")
            print(f"      AMI: {export['ami_id']}")
            print(f"      S3: s3://{export['bucket_name']}/{export['s3_key']}")
            print(f"      Size: {export['size_gb']:.2f} GB")
            total_size_gb += export["size_gb"]

        print(f"\n💾 Total recovered data: {total_size_gb:.2f} GB")

        # Calculate cost savings
        ebs_monthly_cost = calculate_snapshot_cost(total_size_gb)
        s3_monthly_cost = total_size_gb * 0.023
        monthly_savings = ebs_monthly_cost - s3_monthly_cost

        print(f"💰 Monthly savings: ${monthly_savings:.2f}")
        print(f"💰 Annual savings: ${monthly_savings * 12:.2f}")

        print("\n📝 Next Steps:")
        print("1. Verify files in S3 console")
        print("2. Test restore process if needed")
        print("3. Clean up temporary AMIs")
        print("4. Delete original EBS snapshots")

    else:
        print("❌ No completed exports found")
        print("   All active exports are still genuinely in progress")


if __name__ == "__main__":
    main()
