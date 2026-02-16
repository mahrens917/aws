"""Shared AWS client creation utilities."""

from __future__ import annotations

import logging
import os
from typing import Optional

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_ec2_client, create_s3_client

_STATIC_REGIONS_ENV = "COST_TOOLKIT_STATIC_AWS_REGIONS"

# Map resource types to their describe methods and response keys
_RESOURCE_CONFIG = {
    "volume": ("describe_volumes", "VolumeIds", "Volumes", "InvalidVolume.NotFound"),
    "snapshot": (
        "describe_snapshots",
        "SnapshotIds",
        "Snapshots",
        "InvalidSnapshot.NotFound",
    ),
    "ami": ("describe_images", "ImageIds", "Images", "InvalidAMIID.NotFound"),
    "instance": (
        "describe_instances",
        "InstanceIds",
        "Reservations",
        "InvalidInstanceID.NotFound",
    ),
}


def _parse_static_regions_env() -> list[str]:
    """Return configured AWS regions when tests set the override env var."""
    raw = os.getenv(_STATIC_REGIONS_ENV)
    if not raw:
        return []
    regions = [region.strip() for region in raw.split(",") if region.strip()]
    if not regions:
        logging.warning("%s is set but no valid region values were provided", _STATIC_REGIONS_ENV)
        return []
    logging.debug("Using static AWS regions override: %s", ", ".join(regions))
    return regions


def create_ec2_and_s3_clients(region, aws_access_key_id, aws_secret_access_key):
    """
    Create both EC2 and S3 boto3 clients with the provided credentials.

    Args:
        region: AWS region name
        aws_access_key_id: AWS access key ID
        aws_secret_access_key: AWS secret access key

    Returns:
        tuple: (ec2_client, s3_client)
    """
    ec2_client = create_ec2_client(
        region=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )
    s3_client = create_s3_client(
        region=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )
    return ec2_client, s3_client


def list_elastic_ip_addresses(ec2_client) -> list[dict]:
    """Return Elastic IP address metadata for a given EC2 client."""
    response = ec2_client.describe_addresses()
    if "Addresses" in response:
        return response["Addresses"]
    return []


def get_instance_name(ec2_client, instance_id: str) -> Optional[str]:
    """
    Get the Name tag of an EC2 instance.

    Args:
        ec2_client: Boto3 EC2 client instance
        instance_id: EC2 instance ID

    Returns:
        str: Instance name from Name tag, or None if not found

    Raises:
        ClientError: If API call fails
    """
    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            if "Tags" not in instance:
                continue
            for tag in instance["Tags"]:
                if tag["Key"] == "Name":
                    return tag["Value"]
    return None


def get_all_aws_regions(
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> list[str]:
    """
    Get all available AWS regions by querying the EC2 service.

    Args:
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        list: List of all AWS region names

    Raises:
        ClientError: If API call fails

    Note:
        This makes an API call to AWS. For a static list of common regions,
        use get_default_regions() instead or set the static override env var.
    """

    static_regions = _parse_static_regions_env()
    if static_regions:
        return static_regions

    ec2_client = create_ec2_client(
        region="us-east-1",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    response = ec2_client.describe_regions()
    return [region["RegionName"] for region in response["Regions"]]


def get_default_regions():
    """
    Get the default list of AWS regions commonly used for operations.

    Returns:
        list: List of AWS region names

    Note:
        This returns a static list. For all regions via API call,
        use get_all_aws_regions() instead.
    """
    return [
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "eu-west-1",
        "eu-west-2",
        "eu-central-1",
        "ap-southeast-1",
        "ap-southeast-2",
    ]


def get_common_regions_extended():
    """
    Return the canonical list of commonly used AWS regions (extended set).

    Adds a couple of high-usage regions on top of the default list.
    """
    regions = get_default_regions()
    extras = ["eu-west-3", "ap-northeast-1"]
    regions.extend([region for region in extras if region not in regions])
    return regions


def extract_tag_value(resource, key):
    """
    Extract a specific tag value from an AWS resource.

    Args:
        resource: AWS resource dict containing 'Tags' key
        key: Tag key to search for

    Returns:
        str: Tag value if found, None otherwise
    """
    if "Tags" not in resource:
        return None
    for tag in resource["Tags"]:
        if tag["Key"] == key:
            return tag["Value"]
    return None


def get_resource_tags(resource):
    """
    Extract all tags from an AWS resource as a dictionary.

    Args:
        resource: AWS resource dict containing 'Tags' key

    Returns:
        dict: Dictionary of tag key-value pairs
    """
    if "Tags" not in resource:
        return {}
    return {tag["Key"]: tag["Value"] for tag in resource["Tags"]}


def extract_volumes_from_instance(instance):
    """
    Extract volume information from an EC2 instance.

    Args:
        instance: EC2 instance dict from describe_instances

    Returns:
        list: List of dicts with volume_id, device, and delete_on_termination
    """
    volumes = []
    if "BlockDeviceMappings" not in instance:
        return volumes
    for bdm in instance["BlockDeviceMappings"]:
        if "Ebs" in bdm:
            volumes.append(
                {
                    "volume_id": bdm["Ebs"]["VolumeId"],
                    "device": bdm["DeviceName"],
                    "delete_on_termination": bdm["Ebs"]["DeleteOnTermination"],
                }
            )
    return volumes


def describe_instance_raw(ec2_client, instance_id: str):
    """Return the raw describe_instances payload for a single instance."""
    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            return instance
    return None


def get_instance_details(ec2_client, instance_id):
    """
    Get detailed information about an EC2 instance.

    Args:
        ec2_client: Boto3 EC2 client
        instance_id: The EC2 instance ID

    Returns:
        dict: Instance details or None if instance not found. Contains keys:
            - instance_id: Instance ID
            - name: Instance name from Name tag (None if not set)
            - state: Current instance state
            - instance_type: Instance type
            - launch_time: Launch timestamp
            - availability_zone: AZ where instance is running
            - volumes: List of attached volumes
            - tags: Dict of all instance tags

    Raises:
        ClientError: If API call fails
    """
    instance = describe_instance_raw(ec2_client, instance_id)
    if instance is None:
        return None

    availability_zone = None
    if "Placement" in instance and "AvailabilityZone" in instance["Placement"]:
        availability_zone = instance["Placement"]["AvailabilityZone"]

    launch_time = None
    if "LaunchTime" in instance:
        launch_time = instance["LaunchTime"]

    return {
        "instance_id": instance_id,
        "name": extract_tag_value(instance, "Name"),
        "state": instance["State"]["Name"],
        "instance_type": instance["InstanceType"],
        "launch_time": launch_time,
        "availability_zone": availability_zone,
        "volumes": extract_volumes_from_instance(instance),
        "tags": get_resource_tags(instance),
    }


def _check_resource_in_region(
    region: str,
    resource_id: str,
    config_tuple: tuple,
    aws_access_key_id: Optional[str],
    aws_secret_access_key: Optional[str],
) -> bool:
    """
    Check if a resource exists in a specific region.

    Args:
        region: AWS region to check
        resource_id: The resource ID to locate
        config_tuple: Configuration tuple (method_name, id_param, response_key, not_found_error)
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        True if resource exists in region, False otherwise
    """
    method_name, id_param, response_key, not_found_error = config_tuple

    try:
        ec2_client = create_ec2_client(
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        response = getattr(ec2_client, method_name)(**{id_param: [resource_id]})
        return bool(response[response_key])

    except ClientError as e:
        if not_found_error in str(e):
            return False
        raise


def find_resource_region(
    resource_type: str,
    resource_id: str,
    regions: Optional[list[str]] = None,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> Optional[str]:
    """
    Find which AWS region contains a specified resource.

    Args:
        resource_type: Type of resource ('volume', 'snapshot', 'ami', 'instance')
        resource_id: The resource ID to locate
        regions: Optional list of regions to search. If None, searches all regions.
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        Region name if found, None otherwise
    """
    if resource_type not in _RESOURCE_CONFIG:
        raise ValueError(f"Unsupported resource type: {resource_type}. " f"Supported types: {', '.join(_RESOURCE_CONFIG.keys())}")

    search_regions = regions or get_all_aws_regions(aws_access_key_id, aws_secret_access_key)

    for region in search_regions:
        if _check_resource_in_region(
            region,
            resource_id,
            _RESOURCE_CONFIG[resource_type],
            aws_access_key_id,
            aws_secret_access_key,
        ):
            return region

    return None
