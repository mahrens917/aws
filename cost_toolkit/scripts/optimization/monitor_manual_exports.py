#!/usr/bin/env python3
"""
Monitor Manual AWS Export Tasks
This script helps you monitor the progress of manual export tasks and check S3 files.
"""

import argparse
from datetime import datetime
from threading import Event

import boto3
from botocore.exceptions import ClientError

_WAIT_EVENT = Event()


def check_export_status(region, ami_id=None):
    """Check status of export tasks in a region"""
    ec2_client = boto3.client("ec2", region_name=region)

    try:
        response = ec2_client.describe_export_image_tasks()
        if ami_id:
            # Check specific AMI
            tasks = [task for task in response["ExportImageTasks"] if task["ImageId"] == ami_id]
        else:
            # Check all export tasks
            tasks = response["ExportImageTasks"]

        if not tasks:
            print(f"   📭 No export tasks found in {region}" + (f" for AMI {ami_id}" if ami_id else ""))
            return []

        print(f"   📊 Export tasks in {region}:")
        for task in tasks:
            task_id = task["ExportImageTaskId"]
            status = task["Status"]
            progress = task.get("Progress")
            message = task.get("StatusMessage")
            ami = task["ImageId"]

            status_emoji_map = {"active": "🔄", "completed": "✅", "failed": "❌", "deleted": "🗑️"}
            status_emoji = status_emoji_map[status] if status in status_emoji_map else "❓"

            print(f"      {status_emoji} {task_id}")
            print(f"         AMI: {ami}")
            print(f"         Status: {status} | Progress: {progress}%")
            if message:
                print(f"         Message: {message}")
            print()

    except ClientError as e:
        print(f"   ❌ Error checking exports in {region}: {e}")
        return []

    return tasks


def check_s3_files(region, bucket_name=None):
    """Check S3 files in export buckets"""
    s3_client = boto3.client("s3", region_name=region)

    if not bucket_name:
        bucket_name = f"ebs-snapshot-archive-{region}-{datetime.now().strftime('%Y%m%d')}"

    try:
        print(f"   🔍 Checking S3 bucket: {bucket_name}")

        # List objects in the ebs-snapshots prefix
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix="ebs-snapshots/")

        if "Contents" not in response:
            print(f"      📭 No files found in s3://{bucket_name}/ebs-snapshots/")
            return []

        files = []
        for obj in response["Contents"]:
            if obj["Key"].endswith(".vmdk"):
                size_gb = obj["Size"] / (1024**3)
                files.append(
                    {
                        "key": obj["Key"],
                        "size_gb": size_gb,
                        "last_modified": obj["LastModified"],
                        "size_bytes": obj["Size"],
                    }
                )

        if files:
            print(f"      ✅ Found {len(files)} VMDK files:")
            for file in files:
                print(f"         📄 {file['key']}")
                print(f"            Size: {file['size_gb']:.2f} GB ({file['size_bytes']:,} bytes)")
                print(f"            Modified: {file['last_modified']}")
                print()
        else:
            print("      📭 No VMDK files found in bucket")

    except s3_client.exceptions.NoSuchBucket:
        print(f"      ❌ Bucket {bucket_name} does not exist")
        return []
    except ClientError as e:
        print(f"      ❌ Error checking S3: {e}")
        return []

    return files


def _print_task_summary(all_tasks):
    """Print summary of export tasks."""
    if not all_tasks:
        print("📭 No export tasks found")
        return

    active_tasks = [t for t in all_tasks if t["Status"] == "active"]
    completed_tasks = [t for t in all_tasks if t["Status"] == "completed"]
    failed_tasks = [t for t in all_tasks if t["Status"] == "failed"]
    deleted_tasks = [t for t in all_tasks if t["Status"] == "deleted"]

    print(f"🔄 Active exports: {len(active_tasks)}")
    print(f"✅ Completed exports: {len(completed_tasks)}")
    print(f"❌ Failed exports: {len(failed_tasks)}")
    print(f"🗑️  Deleted exports: {len(deleted_tasks)}")


def _print_file_summary(all_files):
    """Print summary of S3 files and savings."""
    if not all_files:
        print("📭 No S3 VMDK files found")
        return

    total_size_gb = sum(f["size_gb"] for f in all_files)
    print(f"📄 S3 VMDK files: {len(all_files)} ({total_size_gb:.2f} GB total)")

    monthly_savings = total_size_gb * (0.05 - 0.023)
    print(f"💰 Current monthly savings: ${monthly_savings:.2f}")
    print(f"💰 Current annual savings: ${monthly_savings * 12:.2f}")


def monitor_all_regions():
    """Monitor exports across all relevant regions"""
    regions = ["us-east-2", "eu-west-2"]

    print("AWS Export Monitor")
    print("=" * 50)
    print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    all_tasks = []
    all_files = []

    for region in regions:
        print(f"🌍 Region: {region}")
        print("-" * 30)

        tasks = check_export_status(region)
        all_tasks.extend(tasks)

        files = check_s3_files(region)
        all_files.extend(files)

        print()

    print("📊 SUMMARY")
    print("=" * 50)

    _print_task_summary(all_tasks)
    _print_file_summary(all_files)


def check_specific_ami(region, ami_id):
    """Check status of a specific AMI export"""
    print(f"Checking AMI {ami_id} in {region}")
    print("=" * 50)

    # Check export task
    check_export_status(region, ami_id)

    # Check S3 files for this AMI
    s3_client = boto3.client("s3", region_name=region)

    bucket_name = f"ebs-snapshot-archive-{region}-{datetime.now().strftime('%Y%m%d')}"

    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=f"ebs-snapshots/{ami_id}/")

        if "Contents" in response:
            print(f"   📄 S3 files for AMI {ami_id}:")
            for obj in response["Contents"]:
                size_gb = obj["Size"] / (1024**3)
                print(f"      {obj['Key']} - {size_gb:.2f} GB")
        else:
            print(f"   📭 No S3 files found for AMI {ami_id}")

    except ClientError as e:
        print(f"   ❌ Error checking S3 for AMI {ami_id}: {e}")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Monitor manual AWS export tasks")
    parser.add_argument("--region", help="Specific region to check")
    parser.add_argument("--ami", help="Specific AMI ID to check")
    parser.add_argument("--watch", action="store_true", help="Continuously monitor (refresh every 2 minutes)")

    args = parser.parse_args()

    try:
        if args.ami and args.region:
            check_specific_ami(args.region, args.ami)
        elif args.watch:
            print("🔄 Continuous monitoring mode (Ctrl+C to stop)")
            print("Refreshing every 2 minutes...")
            print()

            while True:
                monitor_all_regions()
                print("\n⏳ Waiting 2 minutes for next check...")
                _WAIT_EVENT.wait(120)
        else:
            monitor_all_regions()

    except KeyboardInterrupt:
        print("\n👋 Monitoring stopped")
    except ClientError as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
