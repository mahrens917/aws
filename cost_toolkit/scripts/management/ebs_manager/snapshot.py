"""
AWS EBS Volume Snapshot Operations Module
Handles snapshot creation and related operations.
"""

from datetime import datetime, timezone
from typing import Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .exceptions import VolumeNotFoundError
from .utils import find_volume_region, get_volume_tags


class VolumeRetrievalError(ValueError):
    """Raised when there is an error retrieving volume information."""

    def __init__(self, volume_id: str, error: Exception):
        super().__init__(f"Error retrieving volume {volume_id}: {str(error)}")


class SnapshotCreationError(ValueError):
    """Raised when there is an error creating a snapshot."""

    def __init__(self, volume_id: str, error: Exception):
        super().__init__(f"Error creating snapshot for volume {volume_id}: {str(error)}")


def _generate_snapshot_description(volume_name, volume_id, volume_size):
    """Generate default snapshot description."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"Snapshot of {volume_name} ({volume_id}) - {volume_size}GB - {timestamp}"


def _create_snapshot_tags(volume_tags, volume_id):
    """Create tags for the snapshot based on volume tags."""
    snapshot_tags = []
    for key, value in volume_tags.items():
        if key == "Name":
            snapshot_tags.append({"Key": "Name", "Value": f"{value}-snapshot"})
        else:
            snapshot_tags.append({"Key": key, "Value": value})

    # Add additional metadata tags
    snapshot_tags.extend(
        [
            {"Key": "SourceVolume", "Value": volume_id},
            {"Key": "CreatedBy", "Value": "aws_ebs_volume_manager"},
            {
                "Key": "CreatedDate",
                "Value": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            },
        ]
    )
    return snapshot_tags


def create_volume_snapshot(volume_id: str, description: Optional[str] = None) -> Dict:
    """
    Create a snapshot of an EBS volume.

    Args:
        volume_id: The EBS volume ID to snapshot
        description: Optional description for the snapshot

    Returns:
        Dictionary containing snapshot information
    """
    region = find_volume_region(volume_id)
    if not region:
        raise VolumeNotFoundError(volume_id)
    ec2_client = boto3.client("ec2", region_name=region)

    # Get volume information for the description
    try:
        response = ec2_client.describe_volumes(VolumeIds=[volume_id])
        volume = response["Volumes"][0]
        volume_size = volume["Size"]
        volume_tags = get_volume_tags(volume)
        volume_name = volume_tags.get("Name")

        # Create default description if none provided
        if not description:
            description = _generate_snapshot_description(volume_name, volume_id, volume_size)

    except (BotoCoreError, ClientError, KeyError, IndexError, Exception) as exc:
        raise VolumeRetrievalError(volume_id, exc) from exc

    # Create the snapshot
    try:
        snapshot_response = ec2_client.create_snapshot(VolumeId=volume_id, Description=description)
        snapshot_id = snapshot_response["SnapshotId"]

        # Add tags to the snapshot to match the volume
        if volume_tags:
            snapshot_tags = _create_snapshot_tags(volume_tags, volume_id)
            ec2_client.create_tags(Resources=[snapshot_id], Tags=snapshot_tags)

        return {
            "snapshot_id": snapshot_id,
            "volume_id": volume_id,
            "region": region,
            "description": description,
            "state": snapshot_response["State"],
            "start_time": snapshot_response["StartTime"],
            "volume_size": volume_size,
            "volume_name": volume_name,
        }

    except (BotoCoreError, ClientError) as exc:
        raise SnapshotCreationError(volume_id, exc) from exc


if __name__ == "__main__":  # pragma: no cover - script entry point
    pass
