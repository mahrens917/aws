"""
AWS EBS Volume Utility Functions Module
Contains helper functions for region discovery and tag management.
"""

from typing import Optional

import boto3

from cost_toolkit.common.aws_client_factory import create_ec2_client
from cost_toolkit.common.aws_common import (
    find_resource_region,
    get_all_aws_regions,
)
from cost_toolkit.common.aws_common import get_instance_name as _aws_common_get_instance_name
from cost_toolkit.common.aws_common import (
    get_resource_tags,
)

__all__ = ["get_all_aws_regions", "find_volume_region", "get_volume_tags", "get_instance_name"]


def find_volume_region(volume_id: str) -> Optional[str]:
    """
    Find which region contains the specified volume.

    Delegates to canonical find_resource_region in aws_common.

    Args:
        volume_id: The EBS volume ID to locate

    Returns:
        Region name if found, None otherwise
    """
    return find_resource_region("volume", volume_id)


def get_instance_name_by_region(instance_id: str, region: str) -> Optional[str]:
    """
    Get the Name tag value for an EC2 instance in a specific region.

    Args:
        instance_id: The EC2 instance ID
        region: AWS region where the instance is located

    Returns:
        Instance name from Name tag, or None if not found
    """
    ec2_client = create_ec2_client(region)
    return get_instance_name(ec2_client, instance_id)


def _get_instance_name_with_client(ec2_client, instance_id: str) -> Optional[str]:
    """Internal helper to allow mocking the underlying name lookup."""
    name = _aws_common_get_instance_name(ec2_client, instance_id)
    return name


def get_instance_name(instance_id: str, region: str) -> Optional[str]:
    """Create a regional EC2 client and return the instance Name tag if present."""
    ec2_client = boto3.client("ec2", region_name=region)
    return _get_instance_name_with_client(ec2_client, instance_id)


get_volume_tags = get_resource_tags
