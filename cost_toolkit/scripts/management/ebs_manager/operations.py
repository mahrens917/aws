"""
AWS EBS Volume Operations Module
Handles volume deletion and information retrieval operations.
"""

from datetime import datetime, timezone
from typing import Dict

import boto3
from botocore.exceptions import ClientError

from .exceptions import VolumeNotFoundError
from .utils import find_volume_region, get_instance_name, get_volume_tags


def _extract_basic_volume_info(volume: Dict, volume_id: str, region: str) -> Dict:
    """
    Extract basic volume information from AWS describe response.

    Args:
        volume: Volume data from describe_volumes API
        volume_id: The EBS volume ID
        region: AWS region where volume exists

    Returns:
        Dictionary with basic volume attributes
    """
    return {
        "volume_id": volume_id,
        "region": region,
        "size_gb": volume["Size"],
        "volume_type": volume["VolumeType"],
        "state": volume["State"],
        "create_time": volume["CreateTime"],
        "availability_zone": volume["AvailabilityZone"],
        "encrypted": volume["Encrypted"],
        "iops": volume.get("Iops"),
        "throughput": volume.get("Throughput"),
        "tags": get_volume_tags(volume),
    }


def _extract_attachment_info(volume: Dict, region: str) -> Dict:
    """
    Extract volume attachment information.

    Args:
        volume: Volume data from describe_volumes API
        region: AWS region where volume exists

    Returns:
        Dictionary with attachment details or None values if not attached
    """
    attachments = []
    if "Attachments" in volume:
        attachments = volume["Attachments"]
    if attachments:
        attachment = attachments[0]
        instance_id = attachment["InstanceId"]
        return {
            "attached_to_instance_id": instance_id,
            "attached_to_instance_name": get_instance_name(instance_id, region),
            "device": attachment["Device"],
            "attach_time": attachment["AttachTime"],
            "delete_on_termination": attachment["DeleteOnTermination"],
        }
    return {
        "attached_to_instance_id": None,
        "attached_to_instance_name": "Not attached",
        "device": None,
        "attach_time": None,
        "delete_on_termination": None,
    }


def _get_last_read_activity(cloudwatch_client, volume_id: str) -> str:
    """
    Query CloudWatch for last volume read activity.

    Args:
        cloudwatch_client: Boto3 CloudWatch client
        volume_id: The EBS volume ID

    Returns:
        Timestamp of last read activity or error/status message
    """
    try:
        end_time = datetime.now(timezone.utc)
        start_time = end_time.replace(day=1)  # Start of current month

        metrics_response = cloudwatch_client.get_metric_statistics(
            Namespace="AWS/EBS",
            MetricName="VolumeReadOps",
            Dimensions=[{"Name": "VolumeId", "Value": volume_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,  # Daily
            Statistics=["Sum"],
        )

        if metrics_response["Datapoints"]:
            sorted_datapoints = sorted(metrics_response["Datapoints"], key=lambda x: x["Timestamp"], reverse=True)
            return sorted_datapoints[0]["Timestamp"]

    except ClientError as e:
        return f"Error retrieving metrics: {str(e)}"
    return "No recent activity"


def get_volume_detailed_info(volume_id: str) -> Dict:
    """
    Get comprehensive information about a specific EBS volume.

    Args:
        volume_id: The EBS volume ID to analyze

    Returns:
        Dictionary containing detailed volume information
    """
    region = find_volume_region(volume_id)
    if not region:
        raise VolumeNotFoundError(volume_id)
    ec2_client = boto3.client("ec2", region_name=region)
    cloudwatch_client = boto3.client("cloudwatch", region_name=region)

    # Get volume details
    response = ec2_client.describe_volumes(VolumeIds=[volume_id])
    volume = response["Volumes"][0]

    # Build comprehensive volume information
    volume_info = _extract_basic_volume_info(volume, volume_id, region)
    volume_info.update(_extract_attachment_info(volume, region))
    volume_info["last_read_activity"] = _get_last_read_activity(cloudwatch_client, volume_id)

    return volume_info


def delete_ebs_volume(volume_id: str, force: bool = False) -> bool:
    """
    Delete an EBS volume after safety checks.

    Args:
        volume_id: The EBS volume ID to delete
        force: Skip safety prompts if True

    Returns:
        True if deletion successful, False otherwise
    """
    region = find_volume_region(volume_id)
    if not region:
        print(f"Volume {volume_id} not found in any region")
        return False

    ec2_client = boto3.client("ec2", region_name=region)

    # Get volume information before deletion
    try:
        response = ec2_client.describe_volumes(VolumeIds=[volume_id])
        volume = response["Volumes"][0]
    except ec2_client.exceptions.ClientError as e:
        print(f"Error retrieving volume {volume_id}: {str(e)}")
        return False

    # Safety checks
    if volume["State"] == "in-use":
        print(f"Volume {volume_id} is currently attached to an instance")
        print("   You must detach the volume before deletion")
        return False

    # Display volume information
    print(f"Volume to delete: {volume_id}")
    print(f"   Region: {region}")
    print(f"   Size: {volume['Size']} GB")
    print(f"   Type: {volume['VolumeType']}")
    print(f"   State: {volume['State']}")
    print(f"   Created: {volume['CreateTime']}")

    tags = get_volume_tags(volume)
    if tags:
        print("   Tags:")
        for key, value in tags.items():
            print(f"     {key}: {value}")

    # Confirmation prompt unless forced
    if not force:
        print("\nWARNING: This action cannot be undone!")
        confirmation = input("Type 'DELETE' to confirm volume deletion: ")
        if confirmation != "DELETE":
            print("Deletion cancelled")
            return False

    # Perform deletion
    try:
        ec2_client.delete_volume(VolumeId=volume_id)
        print(f"Volume {volume_id} deletion initiated successfully")
        print("   The volume will be permanently deleted within a few minutes")
    except ClientError as e:
        print(f"Error deleting volume {volume_id}: {str(e)}")
        return False

    return True


if __name__ == "__main__":
    pass
