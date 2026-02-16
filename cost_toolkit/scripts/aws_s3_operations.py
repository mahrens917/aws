#!/usr/bin/env python3
"""
AWS S3 Operations Module
Common S3 API operations extracted to reduce code duplication.
"""

from typing import Optional

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_s3_client


def get_bucket_location(
    bucket_name: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> str:
    """
    Get the region where an S3 bucket is located.

    Args:
        bucket_name: Name of the S3 bucket
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        str: AWS region name (defaults to 'us-east-1' if LocationConstraint is None)

    Raises:
        ClientError: If bucket not found or API call fails
    """
    s3_client = create_s3_client(
        region="us-east-1",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    response = s3_client.get_bucket_location(Bucket=bucket_name)
    location = response.get("LocationConstraint")

    # S3 API returns None for us-east-1 buckets - this is documented AWS behavior
    # See: https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetBucketLocation.html
    if location is None:
        return "us-east-1"
    return location


def create_bucket(
    bucket_name: str,
    region: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> bool:
    """
    Create an S3 bucket in a specific region.

    Args:
        bucket_name: Name of the S3 bucket to create
        region: AWS region name
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        s3_client = create_s3_client(
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        # us-east-1 doesn't need LocationConstraint
        if region == "us-east-1":
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )

        print(f"✅ Created S3 bucket: {bucket_name} in {region}")

    except ClientError as e:
        print(f"❌ Failed to create bucket {bucket_name}: {str(e)}")
        return False
    return True


def list_buckets(
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> list[dict]:
    """
    List all S3 buckets in the account.

    Args:
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        list: List of bucket dictionaries

    Raises:
        ClientError: If API call fails
        KeyError: If response is missing expected 'Buckets' key
    """
    s3_client = create_s3_client(
        region="us-east-1",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    response = s3_client.list_buckets()
    return response["Buckets"]


def head_object(
    bucket_name: str,
    key: str,
    region: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> dict:
    """
    Get metadata about an S3 object without downloading it.

    Args:
        bucket_name: Name of the S3 bucket
        key: Object key
        region: AWS region name
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        dict: Object metadata including ContentLength, LastModified, etc.

    Raises:
        ClientError: If object not found or API call fails
    """
    s3_client = create_s3_client(
        region=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    return s3_client.head_object(Bucket=bucket_name, Key=key)


def delete_object(
    bucket_name: str,
    key: str,
    region: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> bool:
    """
    Delete an object from an S3 bucket.

    Args:
        bucket_name: Name of the S3 bucket
        key: Object key to delete
        region: AWS region name
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        s3_client = create_s3_client(
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        s3_client.delete_object(Bucket=bucket_name, Key=key)
        print(f"✅ Deleted object: s3://{bucket_name}/{key}")

    except ClientError as e:
        print(f"❌ Failed to delete object {key}: {str(e)}")
        return False
    return True


def delete_bucket(
    bucket_name: str,
    region: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> bool:
    """
    Delete an empty S3 bucket.

    Args:
        bucket_name: Name of the S3 bucket to delete
        region: AWS region name
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        s3_client = create_s3_client(
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        s3_client.delete_bucket(Bucket=bucket_name)
        print(f"✅ Deleted bucket: {bucket_name}")

    except ClientError as e:
        print(f"❌ Failed to delete bucket {bucket_name}: {str(e)}")
        return False
    return True


def get_bucket_versioning(
    bucket_name: str,
    region: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> dict:
    """
    Get the versioning configuration of an S3 bucket.

    Args:
        bucket_name: Name of the S3 bucket
        region: AWS region name
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        dict: Versioning configuration

    Raises:
        ClientError: If API call fails
    """
    s3_client = create_s3_client(
        region=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    return s3_client.get_bucket_versioning(Bucket=bucket_name)


def get_bucket_tagging(
    bucket_name: str,
    region: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> list[dict]:
    """
    Get tags for an S3 bucket.

    Args:
        bucket_name: Name of the S3 bucket
        region: AWS region name
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        list: List of tag dictionaries, or empty list if no tags

    Raises:
        ClientError: If API call fails (except NoSuchTagSet)
    """
    try:
        s3_client = create_s3_client(
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        response = s3_client.get_bucket_tagging(Bucket=bucket_name)
        return response["TagSet"]

    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchTagSet":
            return []
        raise


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit("This module exposes helpers; run cost_toolkit scripts that import it instead.")
