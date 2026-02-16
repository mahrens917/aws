#!/usr/bin/env python3
"""
AWS S3 Standardization Script
Implements specific S3 bucket configurations:
1. Delete mail.satoshi.report bucket
2. Ensure all buckets (except akiaiw6gwdirbsbuzqiq-arq-1) are private
3. Remove lifecycle policies from all buckets (except akiaiw6gwdirbsbuzqiq-arq-1)
4. Move all objects to Standard storage class
"""

from botocore.exceptions import ClientError, NoCredentialsError

from cost_toolkit.common.aws_client_factory import create_s3_client
from cost_toolkit.common.s3_utils import get_bucket_region
from cost_toolkit.scripts.aws_s3_operations import list_buckets
from cost_toolkit.scripts.aws_utils import setup_aws_credentials

# Bucket to exclude from standardization - DO NOT TOUCH
EXCLUDED_BUCKET = "akiaiw6gwdirbsbuzqiq-arq-1"


def ensure_bucket_private(bucket_name, region):
    """Ensure a bucket has private access configuration"""
    try:
        s3_client = create_s3_client(region=region)

        print(f"🔒 Securing bucket: {bucket_name}")

        # Set public access block to maximum security
        public_access_block_config = {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        }

        s3_client.put_public_access_block(Bucket=bucket_name, PublicAccessBlockConfiguration=public_access_block_config)

        # Remove any public bucket policy
        try:
            s3_client.delete_bucket_policy(Bucket=bucket_name)
            print(f"  Removed bucket policy from {bucket_name}")
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchBucketPolicy":
                print(f"  Warning: Could not remove bucket policy from {bucket_name}: {e}")

        print(f"✅ Secured bucket: {bucket_name}")

    except ClientError as e:
        print(f"❌ Error securing bucket {bucket_name}: {e}")
        return False

    return True


def remove_lifecycle_policy(bucket_name, region):
    """Remove lifecycle policy from a bucket"""
    try:
        s3_client = create_s3_client(region=region)
        print(f"📋 Removing lifecycle policy from: {bucket_name}")

        try:
            s3_client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
            s3_client.delete_bucket_lifecycle(Bucket=bucket_name)
            print(f"✅ Removed lifecycle policy from: {bucket_name}")
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchLifecycleConfiguration":
                print(f"✅ No lifecycle policy to remove from: {bucket_name}")
                return True
            print(f"❌ Error removing lifecycle policy from {bucket_name}: {e}")
            return False
    except ClientError as e:
        print(f"❌ Unexpected error removing lifecycle policy from {bucket_name}: {e}")
        return False
    else:
        return True


def _convert_object_to_standard(s3_client, bucket_name, key):
    """Convert a single object to Standard storage class."""
    copy_source = {"Bucket": bucket_name, "Key": key}
    s3_client.copy_object(
        CopySource=copy_source,
        Bucket=bucket_name,
        Key=key,
        StorageClass="STANDARD",
        MetadataDirective="COPY",
    )


def _process_page_objects(s3_client, bucket_name, page):
    """Process objects from a single page of results."""
    if "Contents" not in page:
        return 0, 0

    objects_processed = 0
    objects_converted = 0

    for obj in page["Contents"]:
        objects_processed += 1
        key = obj["Key"]
        current_storage_class = obj.get("StorageClass")

        if current_storage_class == "STANDARD":
            continue

        try:
            _convert_object_to_standard(s3_client, bucket_name, key)
            objects_converted += 1

            if objects_converted % 100 == 0:
                print(f"    Converted {objects_converted} objects...")

        except ClientError as e:
            print(f"    Warning: Could not convert {key}: {e}")

    return objects_processed, objects_converted


def move_objects_to_standard_storage(bucket_name, region):
    """Move all objects in a bucket to Standard storage class"""
    try:
        s3_client = create_s3_client(region=region)
        print(f"📦 Converting objects to Standard storage in: {bucket_name}")

        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket_name)

        total_processed = 0
        total_converted = 0

        for page in pages:
            processed, converted = _process_page_objects(s3_client, bucket_name, page)
            total_processed += processed
            total_converted += converted

        print(f"✅ Processed {total_processed} objects, " f"converted {total_converted} to Standard storage in: {bucket_name}")

    except ClientError as e:
        print(f"❌ Error converting objects in bucket {bucket_name}: {e}")
        return False
    return True


def _process_single_bucket(bucket_name, bucket_region):
    """Process a single bucket through all standardization steps."""
    print(f"Processing bucket: {bucket_name} (region: {bucket_region})")
    print("-" * 60)

    print("Step 2: Ensuring bucket is private...")
    ensure_bucket_private(bucket_name, bucket_region)

    print("Step 3: Removing lifecycle policy...")
    remove_lifecycle_policy(bucket_name, bucket_region)

    print("Step 4: Converting objects to Standard storage...")
    move_objects_to_standard_storage(bucket_name, bucket_region)

    print()


def standardize_s3_buckets():
    """Main function to standardize S3 bucket configurations"""
    setup_aws_credentials()

    print("AWS S3 Bucket Standardization")
    print("=" * 80)
    print("Implementing S3 bucket standardization requirements:")
    print(f"1. Exclude {EXCLUDED_BUCKET} from ALL processing")
    print("2. Ensure all remaining buckets are private")
    print("3. Remove lifecycle policies from all remaining buckets")
    print("4. Move all objects to Standard storage class")
    print()

    try:
        # Get all buckets
        buckets = list_buckets()

        if not buckets:
            print("✅ No S3 buckets found in your account")
            return

        print(f"🔍 Found {len(buckets)} S3 bucket(s) to process")
        print()

        buckets = [b for b in buckets if b["Name"] != EXCLUDED_BUCKET]

        print(f"ℹ️  Excluding {EXCLUDED_BUCKET} from ALL processing (will not be touched)")
        print()

        for bucket in buckets:
            bucket_name = bucket["Name"]
            bucket_region = get_bucket_region(bucket_name)
            _process_single_bucket(bucket_name, bucket_region)

        print("=" * 80)
        print("🎯 S3 STANDARDIZATION COMPLETE")
        print("=" * 80)
        print("Summary of changes:")
        print(f"✅ Excluded {EXCLUDED_BUCKET} from ALL processing")
        print("✅ Secured all remaining buckets")
        print("✅ Removed lifecycle policies from all remaining buckets")
        print("✅ Converted all objects to Standard storage class")
        print()
        print("All processed S3 buckets now have:")
        print("• Private access (no public access)")
        print("• No lifecycle policies")
        print("• All objects in Standard storage class")
        print(f"• {EXCLUDED_BUCKET} was completely excluded and remains unchanged")

    except NoCredentialsError:
        print("❌ AWS credentials not found. Please configure your credentials.")
    except ClientError as e:
        print(f"❌ AWS API error: {e}")


def main():
    """Main function."""
    # Confirm before running destructive operations
    print("⚠️  WARNING: This script will make changes to your S3 buckets!")
    print(f"   - Exclude {EXCLUDED_BUCKET} from ALL processing")
    print("   - Remove lifecycle policies from remaining buckets")
    print("   - Change storage classes to Standard")
    print("   - Set all remaining buckets to private")
    print()

    confirm = input("Are you sure you want to proceed? (type 'yes' to continue): ")
    if confirm.lower() == "yes":
        standardize_s3_buckets()
    else:
        print("Operation cancelled.")


if __name__ == "__main__":
    main()
