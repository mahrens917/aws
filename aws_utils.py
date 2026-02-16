"""
Shared S3 and IAM helpers.

This re-export module provides AWS utilities at the root level for scripts that import from here.
Functions defined here are generally also available in cost_toolkit modules:
- get_boto3_clients(): Core utilities for creating AWS service clients
- get_aws_identity(): Account identity information
- list_s3_buckets(): Wrapper around cost_toolkit.scripts.aws_s3_operations
- generate_restrictive_bucket_policy(): Policy generation utilities
- Policy file I/O and bucket policy application functions

Note: New code should prefer importing from cost_toolkit.common and cost_toolkit.scripts
modules directly.
"""

import json

import boto3

from cost_toolkit.scripts.aws_s3_operations import list_buckets as _list_buckets_raw


def get_boto3_clients():
    """
    Create and return boto3 clients for AWS services.

    Returns:
        tuple: (s3_client, sts_client, iam_client)
    """
    s3 = boto3.client("s3")
    sts = boto3.client("sts")
    iam = boto3.client("iam")
    return s3, sts, iam


def get_aws_identity():
    """
    Get AWS account and IAM user information.

    Returns:
        dict: Contains account_id, username, and user_arn
    """
    _, sts, iam = get_boto3_clients()

    account_id = sts.get_caller_identity()["Account"]
    user = iam.get_user()
    username = user["User"]["UserName"]
    user_arn = user["User"]["Arn"]

    return {"account_id": account_id, "username": username, "user_arn": user_arn}


def list_s3_buckets():
    """
    List all S3 buckets in the account.

    Delegates to canonical implementation in cost_toolkit.scripts.aws_s3_operations.

    Returns:
        list: List of bucket names
    """
    buckets = _list_buckets_raw()
    return [bucket["Name"] for bucket in buckets]


def generate_restrictive_bucket_policy(user_arn, bucket_name):
    """
    Generate an S3 bucket policy that allows full access only to a specific IAM user.

    Args:
        user_arn (str): IAM user ARN to grant access to
        bucket_name (str): S3 bucket name

    Returns:
        dict: S3 bucket policy document
    """
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowOnlyMeFullAccess",
                "Effect": "Allow",
                "Principal": {"AWS": user_arn},
                "Action": "s3:*",
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}",
                    f"arn:aws:s3:::{bucket_name}/*",
                ],
            }
        ],
    }


def save_policy_to_file(policy, filename):
    """
    Save a policy document to a JSON file.

    Args:
        policy (dict): Policy document
        filename (str): Output filename
    """
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(policy, f, indent=2)


def load_policy_from_file(filename):
    """
    Load a policy document from a JSON file.

    Args:
        filename (str): Input filename

    Returns:
        str: Policy document as JSON string
    """
    with open(filename, encoding="utf-8") as f:
        return f.read()


def apply_bucket_policy(bucket_name, policy_json):
    """
    Apply a bucket policy to an S3 bucket.

    Args:
        bucket_name (str): S3 bucket name
        policy_json (str): Policy document as JSON string
    """
    s3, _, _ = get_boto3_clients()
    s3.put_bucket_policy(Bucket=bucket_name, Policy=policy_json)


def print_interactive_help(script_name: str, available_items: list, item_type: str = "buckets"):
    """
    Print interactive help message showing available options.

    Args:
        script_name (str): Name of the script (e.g., "block_s3.py")
        available_items (list): List of available items to show
        item_type (str): Type of items being shown (default: "buckets")
    """
    print("No buckets specified. Available options:")
    print(f"  - Run with bucket names: python {script_name} bucket1 bucket2")
    print(f"  - Run with --all flag: python {script_name} --all")
    print(f"\nAvailable {item_type}:")
    if available_items:
        for item in available_items:
            print(f"  - {item}")
    else:
        print("  (none found)")
