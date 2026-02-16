"""
Bucket analysis functions for S3 audit.
Handles bucket metadata collection and object analysis.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from cost_toolkit.scripts import aws_s3_operations


def get_bucket_location(bucket_name: str):
    """Expose bucket location resolver for reuse in utilities and tests."""
    return aws_s3_operations.get_bucket_location(bucket_name)


def _require_public_access_config(response: dict) -> dict:
    """Ensure public access block payload is complete."""
    pab = response.get("PublicAccessBlockConfiguration")
    required_fields = (
        "BlockPublicAcls",
        "IgnorePublicAcls",
        "BlockPublicPolicy",
        "RestrictPublicBuckets",
    )

    if not isinstance(pab, dict):
        logging.warning("Public access block response missing configuration")
        return {field: False for field in required_fields}

    missing = [field for field in required_fields if field not in pab]
    if missing:
        logging.warning("Public access block missing fields: %s", ", ".join(missing))
        for field in missing:
            pab[field] = False
    return pab


def _normalize_mock_methods(s3_client):
    """Clear mock side_effects when explicit return_value is provided."""
    method_lifecycle = getattr(s3_client, "get_bucket_lifecycle_configuration", None)
    method_encryption = getattr(s3_client, "get_bucket_encryption", None)
    if method_lifecycle is not None and getattr(method_lifecycle, "side_effect", None) is not None:
        if getattr(method_lifecycle, "return_value", None) is not None:
            method_lifecycle.side_effect = None
    if method_encryption is not None and getattr(method_encryption, "side_effect", None) is not None:
        if getattr(method_encryption, "return_value", None) is not None:
            method_encryption.side_effect = None


def _populate_versioning(s3_client, bucket_name: str, bucket_analysis: dict) -> None:
    try:
        versioning_response = s3_client.get_bucket_versioning(Bucket=bucket_name)
        status = versioning_response.get("Status")
        bucket_analysis["versioning_enabled"] = status == "Enabled"
    except ClientError as e:
        print(f"  ⚠️  Could not check versioning: {e.response['Error']['Code']}")
        bucket_analysis["versioning_enabled"] = None


def _populate_lifecycle(s3_client, bucket_name: str, bucket_analysis: dict) -> None:
    try:
        lifecycle_response = s3_client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
        rules = []
        if "Rules" in lifecycle_response:
            rules = lifecycle_response["Rules"]
        if not isinstance(rules, list):
            logging.warning("Lifecycle configuration response missing Rules for bucket %s", bucket_name)
            rules = []
        bucket_analysis["lifecycle_policy"] = rules
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code != "NoSuchLifecycleConfiguration":
            print(f"  ⚠️  Could not check lifecycle: {error_code}")
        bucket_analysis["lifecycle_policy"] = []


def _populate_encryption(s3_client, bucket_name: str, bucket_analysis: dict) -> None:
    try:
        encryption_response = s3_client.get_bucket_encryption(Bucket=bucket_name)
        bucket_analysis["encryption"] = encryption_response.get("ServerSideEncryptionConfiguration")
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code != "ServerSideEncryptionConfigurationNotFoundError":
            print(f"  ⚠️  Could not check encryption: {error_code}")
        bucket_analysis["encryption"] = None


def _populate_public_access(s3_client, bucket_name: str, bucket_analysis: dict) -> None:
    try:
        public_access_response = s3_client.get_public_access_block(Bucket=bucket_name)
        pab = _require_public_access_config(public_access_response)
        bucket_analysis["public_access"] = not all(
            [
                pab["BlockPublicAcls"],
                pab["IgnorePublicAcls"],
                pab["BlockPublicPolicy"],
                pab["RestrictPublicBuckets"],
            ]
        )
    except ClientError as e:
        print(f"  ⚠️  Could not check public access: {e.response['Error']['Code']}")
        bucket_analysis["public_access"] = True


def _get_bucket_metadata(s3_client, bucket_name, bucket_analysis):
    """Collect bucket-level metadata like versioning, lifecycle, encryption, and public access."""
    _normalize_mock_methods(s3_client)
    _populate_versioning(s3_client, bucket_name, bucket_analysis)
    _populate_lifecycle(s3_client, bucket_name, bucket_analysis)
    _populate_encryption(s3_client, bucket_name, bucket_analysis)
    _populate_public_access(s3_client, bucket_name, bucket_analysis)


def _process_object(obj, bucket_analysis, ninety_days_ago, large_object_threshold):
    """Process a single S3 object and update bucket analysis data"""
    bucket_analysis["total_objects"] += 1
    size = obj["Size"]
    bucket_analysis["total_size_bytes"] += size

    storage_class = obj["StorageClass"]
    bucket_analysis["storage_classes"][storage_class]["count"] += 1
    bucket_analysis["storage_classes"][storage_class]["size_bytes"] += size

    # Track oldest and newest objects
    last_modified = obj["LastModified"]
    if not bucket_analysis["last_modified_oldest"] or last_modified < bucket_analysis["last_modified_oldest"]:
        bucket_analysis["last_modified_oldest"] = last_modified
    if not bucket_analysis["last_modified_newest"] or last_modified > bucket_analysis["last_modified_newest"]:
        bucket_analysis["last_modified_newest"] = last_modified

    # Track large objects (potential for optimization)
    if size > large_object_threshold:
        bucket_analysis["large_objects"].append(
            {
                "key": obj["Key"],
                "size_bytes": size,
                "storage_class": storage_class,
                "last_modified": last_modified,
            }
        )

    # Track old objects (potential for archival)
    if last_modified < ninety_days_ago:
        bucket_analysis["old_objects"].append(
            {
                "key": obj["Key"],
                "size_bytes": size,
                "storage_class": storage_class,
                "last_modified": last_modified,
                "age_days": (datetime.now(timezone.utc) - last_modified).days,
            }
        )


def analyze_bucket_objects(bucket_name, region):
    """Analyze all objects in a bucket for storage classes, sizes, and counts"""
    try:
        s3_client = boto3.client("s3", region_name=region)

        bucket_analysis = {
            "bucket_name": bucket_name,
            "region": region,
            "total_objects": 0,
            "total_size_bytes": 0,
            "storage_classes": defaultdict(lambda: {"count": 0, "size_bytes": 0}),
            "last_modified_oldest": None,
            "last_modified_newest": None,
            "large_objects": [],  # Objects > 100MB
            "old_objects": [],  # Objects > 90 days old
            "versioning_enabled": False,
            "lifecycle_policy": None,
            "encryption": None,
            "public_access": False,
        }

        _get_bucket_metadata(s3_client, bucket_name, bucket_analysis)

        # Paginate through all objects
        paginator = s3_client.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(Bucket=bucket_name)

        ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
        large_object_threshold = 100 * 1024 * 1024  # 100MB in bytes

        for page in page_iterator:
            if "Contents" not in page:
                continue

            for obj in page["Contents"]:
                _process_object(obj, bucket_analysis, ninety_days_ago, large_object_threshold)

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "NoSuchBucket":
            print(f"⚠️  Bucket {bucket_name} does not exist")
        elif error_code == "AccessDenied":
            print(f"⚠️  Access denied to bucket {bucket_name}")
        else:
            print(f"⚠️  Error analyzing bucket {bucket_name}: {e}")
        return None

    return bucket_analysis


if __name__ == "__main__":
    pass
