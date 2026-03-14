#!/usr/bin/env python3
"""Migrate EBS data to S3 storage."""

import os

import boto3
from botocore.exceptions import ClientError

from cost_toolkit.common.s3_utils import create_s3_bucket_with_region
from cost_toolkit.scripts import aws_utils

# Volume IDs for migration
REMAINING_VOLUMES = [
    "vol-089b9ed38099c68f3",  # 384 GB
    "vol-0249308257e5fa64d",  # Tars 3 - 64 GB
]


def _print_setup_header():
    """Print the setup header."""
    print("AWS EBS to S3 Migration Setup")
    print("=" * 80)
    print("🪣 Creating S3 bucket for user file storage")
    print("📁 Setting up migration from EBS volumes to S3 Standard")
    print()


def _create_s3_bucket(s3, bucket_name):
    """Create the S3 bucket for migration."""
    print("🪣 CREATING S3 BUCKET:")
    print("=" * 80)
    print(f"Bucket name: {bucket_name}")
    print("Region: eu-west-2 (London)")
    print("Storage class: S3 Standard")
    print()

    try:
        create_s3_bucket_with_region(s3, bucket_name, "eu-west-2")
    except ClientError as e:
        if "BucketAlreadyExists" in str(e):
            print("✅ S3 bucket already exists")
        else:
            print(f"❌ Error creating bucket: {str(e)}")
            raise

    print(f"✅ Created S3 bucket: {bucket_name}")
    print()


def _display_volume_info(ec2):
    """Display information about the volumes to be migrated."""
    print("📊 CURRENT EBS VOLUMES:")
    print("=" * 80)

    volumes_response = ec2.describe_volumes(VolumeIds=REMAINING_VOLUMES)
    volumes = volumes_response["Volumes"]

    for volume in volumes:
        vol_id = volume["VolumeId"]
        size = volume["Size"]

        name = "No name"
        if "Tags" in volume:
            for tag in volume["Tags"]:
                if tag["Key"] == "Name":
                    name = tag["Value"]
                    break

        print(f"📦 {name} ({vol_id}): {size} GB")

    print()


def _generate_migration_script(bucket_name):
    """Generate the bash migration script."""
    return f"""#!/bin/bash

# AWS EBS to S3 Migration Script
# This script transfers user files from EBS volumes to S3 Standard storage

echo "Starting EBS to S3 migration..."
echo "Target bucket: {bucket_name}"
echo "Region: eu-west-2"
echo ""

# Ensure volumes are mounted
echo "📦 Checking volume mounts..."
sudo mkdir -p /mnt/vol384
sudo mkdir -p /mnt/vol64

# Mount volumes (adjust device names as needed)
sudo mount /dev/nvme1n1 /mnt/vol384 2>/dev/null || echo "Volume 384GB already mounted or not available"
sudo mount /dev/nvme2n1 /mnt/vol64 2>/dev/null || echo "Volume 64GB already mounted or not available"

echo ""
echo "📁 Identifying user directories to migrate..."

# Function to sync directory to S3
sync_to_s3() {{
    local source_path="$1"
    local s3_prefix="$2"

    if [ -d "$source_path" ]; then
        echo "🔄 Syncing $source_path to s3://{bucket_name}/$s3_prefix/"
        aws s3 sync "$source_path" "s3://{bucket_name}/$s3_prefix/" \\
            --region eu-west-2 \\
            --storage-class STANDARD \\
            --exclude "*.tmp" \\
            --exclude "*.log" \\
            --exclude ".cache/*" \\
            --exclude "lost+found/*"
        echo "✅ Completed: $source_path"
        echo ""
    else
        echo "⚠️  Directory not found: $source_path"
    fi
}}

# Migrate from 384GB volume
echo "📦 Processing 384GB volume (/mnt/vol384)..."
sync_to_s3 "/mnt/vol384/home" "384gb-volume/home"
sync_to_s3 "/mnt/vol384/opt" "384gb-volume/opt"
sync_to_s3 "/mnt/vol384/var/www" "384gb-volume/var-www"
sync_to_s3 "/mnt/vol384/data" "384gb-volume/data"

# Migrate from 64GB volume (Tars 3)
echo "📦 Processing 64GB volume (/mnt/vol64)..."
sync_to_s3 "/mnt/vol64/home" "64gb-volume/home"
sync_to_s3 "/mnt/vol64/opt" "64gb-volume/opt"
sync_to_s3 "/mnt/vol64/var/www" "64gb-volume/var-www"
sync_to_s3 "/mnt/vol64/data" "64gb-volume/data"

echo ""
echo "📊 Migration summary:"
aws s3 ls s3://{bucket_name}/ --recursive --human-readable --summarize

echo ""
echo "💰 Cost comparison:"
echo "EBS (current): $35.84/month for 448GB"
echo "S3 Standard: ~$10.30/month for 448GB"
echo "Potential savings: ~$25.54/month"

echo ""
echo "✅ Migration complete!"
echo "Files are now stored in S3 bucket: {bucket_name}"
"""


def _write_migration_script(migration_script):
    """Write and make executable the migration script."""
    print("📝 MIGRATION SCRIPT:")
    print("=" * 80)

    with open("ebs_to_s3_migration.sh", "w", encoding="utf-8") as f:
        f.write(migration_script)

    os.chmod("ebs_to_s3_migration.sh", 0o700)

    print("✅ Migration script created: ebs_to_s3_migration.sh")
    print()


def _print_next_steps(bucket_name):
    """Print next steps and cost savings information."""
    print("📋 NEXT STEPS:")
    print("=" * 80)
    print("1. ✅ S3 bucket created: " + bucket_name)
    print("2. ✅ Migration script ready: ebs_to_s3_migration.sh")
    print("3. 🔄 Run the script on your EC2 instance:")
    print("   ./ebs_to_s3_migration.sh")
    print()
    print("💰 EXPECTED COST SAVINGS:")
    print("   Current EBS: $35.84/month (448GB)")
    print("   S3 Standard: ~$10.30/month (448GB)")
    print("   Monthly savings: ~$25.54")
    print()
    print("🎯 TOTAL OPTIMIZATION IMPACT:")
    print("   EBS cleanup savings: $166.92/month")
    print("   S3 migration savings: ~$25.54/month")
    print("   Combined savings: ~$192.46/month")


def create_s3_bucket_and_migrate():
    """Create S3 bucket and set up migration from EBS to S3"""
    aws_utils.setup_aws_credentials()
    _print_setup_header()

    s3 = boto3.client("s3", region_name="eu-west-2")
    ec2 = boto3.client("ec2", region_name="eu-west-2")

    bucket_name = "aws-user-files-backup-london"

    try:
        _create_s3_bucket(s3, bucket_name)
        _display_volume_info(ec2)

        migration_script = _generate_migration_script(bucket_name)
        _write_migration_script(migration_script)
        _print_next_steps(bucket_name)

    except ClientError as e:
        print(f"❌ Error during setup: {str(e)}")


def main():
    """Main function."""
    create_s3_bucket_and_migrate()


if __name__ == "__main__":
    main()
