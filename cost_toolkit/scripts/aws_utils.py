#!/usr/bin/env python3
"""
AWS Utilities Module
Shared utilities for AWS credential management and common functions.
"""

from typing import Optional

import boto3
from botocore.exceptions import ClientError

from cost_toolkit.common import credential_utils
from cost_toolkit.common.aws_client_factory import (
    _resolve_env_path,
)
from cost_toolkit.common.aws_client_factory import (
    load_credentials_from_env as load_aws_credentials_from_env,
)
from cost_toolkit.common.aws_common import describe_instance_raw, get_all_aws_regions


class CredentialLoadError(Exception):
    """Raised when AWS credentials cannot be loaded."""


def load_aws_credentials(env_path: Optional[str] = None) -> None:
    """
    Load AWS credentials from a .env file.

    Args:
        env_path: Optional override path (used mainly for tests)

    Raises:
        CredentialLoadError: If credentials cannot be loaded
    """
    try:
        load_aws_credentials_from_env(env_path)
    except ValueError as exc:
        resolved_path = _resolve_env_path(env_path)
        msg = f"AWS credentials not found in {resolved_path}. " "Set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION."
        raise CredentialLoadError(msg) from exc


def setup_aws_credentials(env_path: Optional[str] = None):
    """
    Load AWS credentials and exit if not found.

    Args:
        env_path: Optional path to .env file containing credentials

    Note:
        This function exits the process if credentials are not found.
        For non-exit behavior, use credential_utils.setup_aws_credentials directly.
    """
    try:
        result = credential_utils.setup_aws_credentials(env_path=env_path)
    except ValueError as exc:
        raise CredentialLoadError(f"Failed to setup AWS credentials: {exc}") from exc
    if not result:
        raise CredentialLoadError("Failed to setup AWS credentials")


def get_aws_regions():
    """Get list of all AWS regions."""
    regions = get_all_aws_regions()
    return regions


def get_instance_info(instance_id: str, region_name: str) -> dict:
    """
    Get EC2 instance information for a given instance ID.

    Args:
        instance_id: EC2 instance ID
        region_name: AWS region name

    Returns:
        dict: Instance data from describe_instances API call

        Raises:
        ClientError: If instance not found or API call fails
    """
    ec2 = boto3.client("ec2", region_name=region_name)
    instance = describe_instance_raw(ec2, instance_id)
    if instance is None:
        raise ClientError(
            {"Error": {"Code": "InvalidInstanceID.NotFound", "Message": "Instance not found"}},
            "describe_instances",
        )
    return instance


def wait_for_instance_state(
    ec2_client,
    instance_id: str,
    waiter_name: str,
    delay: int = 15,
    max_attempts: int = 40,
):
    """
    Wait for an EC2 instance waiter state with consistent configuration.

    Args:
        ec2_client: Boto3 EC2 client
        instance_id: EC2 instance ID
        waiter_name: Waiter name, e.g., "instance_stopped" or "instance_running"
        delay: Waiter poll delay seconds
        max_attempts: Maximum waiter attempts

    Raises:
        botocore.exceptions.WaiterError: If the waiter times out or errors
    """
    waiter = ec2_client.get_waiter(waiter_name)
    waiter.wait(
        InstanceIds=[instance_id],
        WaiterConfig={"Delay": delay, "MaxAttempts": max_attempts},
    )


def wait_for_instance_running(
    ec2_client,
    instance_id: str,
    delay: int = 15,
    max_attempts: int = 40,
):
    """Wait for an EC2 instance to reach the running state using shared defaults."""
    wait_for_instance_state(ec2_client, instance_id, "instance_running", delay, max_attempts)


def wait_for_db_snapshot_completion(
    rds_client,
    snapshot_identifier: str,
    delay: int = 30,
    max_attempts: int = 120,
):
    """
    Wait for an RDS snapshot to complete with consistent waiter settings.

    Args:
        rds_client: Boto3 RDS client
        snapshot_identifier: Snapshot identifier to monitor
        delay: Waiter poll delay seconds
        max_attempts: Maximum waiter attempts
    """
    waiter = rds_client.get_waiter("db_snapshot_completed")
    waiter.wait(
        DBSnapshotIdentifier=snapshot_identifier,
        WaiterConfig={"Delay": delay, "MaxAttempts": max_attempts},
    )


def wait_for_db_instance_deleted(
    rds_client,
    instance_id: str,
    delay: int = 30,
    max_attempts: int = 20,
):
    """Wait for an RDS instance to reach the deleted state."""
    waiter = rds_client.get_waiter("db_instance_deleted")
    waiter.wait(
        DBInstanceIdentifier=instance_id,
        WaiterConfig={"Delay": delay, "MaxAttempts": max_attempts},
    )


def wait_for_db_instance_available(
    rds_client,
    instance_id: str,
    delay: int = 30,
    max_attempts: int = 20,
):
    """Wait for an RDS instance to reach the available state."""
    waiter = rds_client.get_waiter("db_instance_available")
    waiter.wait(
        DBInstanceIdentifier=instance_id,
        WaiterConfig={"Delay": delay, "MaxAttempts": max_attempts},
    )


def wait_for_db_cluster_available(
    rds_client,
    cluster_identifier: str,
    delay: int = 30,
    max_attempts: int = 120,
):
    """
    Wait for an RDS/Aurora cluster to reach available state using shared config.

    Args:
        rds_client: Boto3 RDS client
        cluster_identifier: Cluster identifier to monitor
        delay: Waiter poll delay seconds
        max_attempts: Maximum waiter attempts
    """
    waiter = rds_client.get_waiter("db_cluster_available")
    waiter.wait(
        DBClusterIdentifier=cluster_identifier,
        WaiterConfig={"Delay": delay, "MaxAttempts": max_attempts},
    )


def wait_for_route53_change(
    route53_client,
    change_id: str,
    delay: int = 10,
    max_attempts: int = 30,
):
    """
    Wait for a Route53 change to propagate using consistent waiter settings.

    Args:
        route53_client: Boto3 Route53 client
        change_id: Change ID returned from change_resource_record_sets
        delay: Waiter poll delay seconds
        max_attempts: Maximum waiter attempts
    """
    waiter = route53_client.get_waiter("resource_record_sets_changed")
    waiter.wait(
        Id=change_id,
        WaiterConfig={"Delay": delay, "MaxAttempts": max_attempts},
    )


if __name__ == "__main__":  # pragma: no cover - script entry point
    load_aws_credentials()
    print("AWS credentials loaded successfully")
