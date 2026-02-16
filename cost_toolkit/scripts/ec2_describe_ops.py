#!/usr/bin/env python3
"""
EC2 Describe Operations Module
Query-only EC2 API operations for describing resources.
"""

from typing import Optional

from cost_toolkit.common.aws_client_factory import create_ec2_client


def describe_addresses(
    region: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> list[dict]:
    """
    Get all Elastic IP addresses in a region.

    Args:
        region: AWS region name
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        list: List of Elastic IP address dictionaries

    Raises:
        ClientError: If API call fails
    """
    ec2_client = create_ec2_client(
        region=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    response = ec2_client.describe_addresses()
    return response["Addresses"]


def describe_network_interfaces(
    region: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    filters: Optional[list[dict]] = None,
) -> list[dict]:
    """
    Get network interfaces in a region with optional filters.

    Args:
        region: AWS region name
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key
        filters: Optional list of filter dictionaries

    Returns:
        list: List of network interface dictionaries

    Raises:
        ClientError: If API call fails
    """
    ec2_client = create_ec2_client(
        region=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    params = {}
    if filters:
        params["Filters"] = filters

    response = ec2_client.describe_network_interfaces(**params)
    return response["NetworkInterfaces"]


def describe_security_groups(
    region: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    group_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Get security groups in a region.

    Args:
        region: AWS region name
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key
        group_ids: Optional list of security group IDs to filter

    Returns:
        list: List of security group dictionaries

    Raises:
        ClientError: If API call fails
    """
    ec2_client = create_ec2_client(
        region=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    params = {}
    if group_ids:
        params["GroupIds"] = group_ids

    response = ec2_client.describe_security_groups(**params)
    security_groups = []
    if "SecurityGroups" in response:
        security_groups = response["SecurityGroups"]
    return security_groups


def describe_snapshots(
    region: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    owner_ids: Optional[list[str]] = None,
    snapshot_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Get EBS snapshots in a region.

    Args:
        region: AWS region name
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key
        owner_ids: Optional list of owner IDs to filter (e.g., ['self'])
        snapshot_ids: Optional list of snapshot IDs to filter

    Returns:
        list: List of snapshot dictionaries

    Raises:
        ClientError: If API call fails
    """
    ec2_client = create_ec2_client(
        region=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    params = {}
    if owner_ids:
        params["OwnerIds"] = owner_ids
    if snapshot_ids:
        params["SnapshotIds"] = snapshot_ids

    response = ec2_client.describe_snapshots(**params)
    snapshots = []
    if "Snapshots" in response:
        snapshots = response["Snapshots"]
    return snapshots


def describe_volumes(
    region: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    filters: Optional[list[dict]] = None,
) -> list[dict]:
    """
    Get EBS volumes in a region.

    Args:
        region: AWS region name
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key
        filters: Optional list of filter dictionaries

    Returns:
        list: List of volume dictionaries

    Raises:
        ClientError: If API call fails
    """
    ec2_client = create_ec2_client(
        region=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    params = {}
    if filters:
        params["Filters"] = filters

    response = ec2_client.describe_volumes(**params)
    volumes = []
    if "Volumes" in response:
        volumes = response["Volumes"]
    return volumes
