"""Tests for cost_toolkit/scripts/management/ebs_manager/snapshot.py - snapshot operations"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.scripts.management.ebs_manager.snapshot import (
    SnapshotCreationError,
    VolumeNotFoundError,
    VolumeRetrievalError,
    create_volume_snapshot,
)
from tests.assertions import assert_equal
from tests.conftest_test_values import TEST_LARGE_VOLUME_SIZE_GIB


# Main function tests - success paths
@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.get_volume_tags")
@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.find_volume_region")
@patch("boto3.client")
def test_create_volume_snapshot_success_with_tags(mock_boto_client, mock_find_region, mock_get_tags):
    """Test create_volume_snapshot successful snapshot creation with tags."""
    mock_find_region.return_value = "us-west-2"

    mock_ec2 = MagicMock()
    mock_boto_client.return_value = mock_ec2

    mock_ec2.describe_volumes.return_value = {
        "Volumes": [
            {
                "VolumeId": "vol-1234567890abcdef0",
                "Size": 100,
                "Tags": [{"Key": "Name", "Value": "test-volume"}],
            }
        ]
    }

    mock_get_tags.return_value = {"Name": "test-volume", "Environment": "prod"}

    mock_ec2.create_snapshot.return_value = {
        "SnapshotId": "snap-abc123",
        "State": "pending",
        "StartTime": datetime(2025, 3, 15, 14, 30, 0, tzinfo=timezone.utc),
    }

    with patch("cost_toolkit.scripts.management.ebs_manager.snapshot.datetime") as mock_dt:
        mock_now = datetime(2025, 3, 15, 14, 30, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = mock_now

        result = create_volume_snapshot("vol-1234567890abcdef0")

    assert_equal(result["snapshot_id"], "snap-abc123")
    assert_equal(result["volume_id"], "vol-1234567890abcdef0")
    assert_equal(result["region"], "us-west-2")
    assert_equal(result["state"], "pending")
    assert_equal(result["volume_size"], 100)
    assert_equal(result["volume_name"], "test-volume")
    assert "Snapshot of test-volume (vol-1234567890abcdef0) - 100GB" in result["description"]

    mock_find_region.assert_called_once_with("vol-1234567890abcdef0")
    mock_boto_client.assert_called_once_with("ec2", region_name="us-west-2")
    mock_ec2.describe_volumes.assert_called_once_with(VolumeIds=["vol-1234567890abcdef0"])
    mock_ec2.create_snapshot.assert_called_once()
    mock_ec2.create_tags.assert_called_once()


@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.get_volume_tags")
@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.find_volume_region")
@patch("boto3.client")
def test_create_volume_snapshot_success_custom_description(mock_boto_client, mock_find_region, mock_get_tags):
    """Test create_volume_snapshot with custom description."""
    mock_find_region.return_value = "us-east-1"

    mock_ec2 = MagicMock()
    mock_boto_client.return_value = mock_ec2

    mock_ec2.describe_volumes.return_value = {
        "Volumes": [
            {
                "VolumeId": "vol-custom123",
                "Size": 50,
                "Tags": [{"Key": "Name", "Value": "custom-volume"}],
            }
        ]
    }

    mock_get_tags.return_value = {"Name": "custom-volume"}

    mock_ec2.create_snapshot.return_value = {
        "SnapshotId": "snap-custom123",
        "State": "pending",
        "StartTime": datetime(2025, 3, 15, 10, 0, 0, tzinfo=timezone.utc),
    }

    custom_desc = "My custom snapshot description"
    result = create_volume_snapshot("vol-custom123", description=custom_desc)

    assert_equal(result["description"], custom_desc)
    mock_ec2.create_snapshot.assert_called_once_with(VolumeId="vol-custom123", Description=custom_desc)


@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.get_volume_tags")
@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.find_volume_region")
@patch("boto3.client")
def test_create_volume_snapshot_success_no_tags(mock_boto_client, mock_find_region, mock_get_tags):
    """Test create_volume_snapshot with volume that has no tags."""
    mock_find_region.return_value = "eu-west-1"

    mock_ec2 = MagicMock()
    mock_boto_client.return_value = mock_ec2

    mock_ec2.describe_volumes.return_value = {
        "Volumes": [
            {
                "VolumeId": "vol-notags",
                "Size": 20,
            }
        ]
    }

    mock_get_tags.return_value = {}

    mock_ec2.create_snapshot.return_value = {
        "SnapshotId": "snap-notags",
        "State": "pending",
        "StartTime": datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
    }

    with patch("cost_toolkit.scripts.management.ebs_manager.snapshot.datetime") as mock_dt:
        mock_now = datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = mock_now

        result = create_volume_snapshot("vol-notags")

    assert result["volume_name"] is None
    assert_equal(result["snapshot_id"], "snap-notags")
    # Should not call create_tags when no volume tags exist
    mock_ec2.create_tags.assert_not_called()


@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.get_volume_tags")
@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.find_volume_region")
@patch("boto3.client")
def test_create_volume_snapshot_success_unnamed_volume(mock_boto_client, mock_find_region, mock_get_tags):
    """Test create_volume_snapshot with volume that has tags but no Name tag."""
    mock_find_region.return_value = "ap-southeast-1"

    mock_ec2 = MagicMock()
    mock_boto_client.return_value = mock_ec2

    mock_ec2.describe_volumes.return_value = {
        "Volumes": [
            {
                "VolumeId": "vol-noname",
                "Size": 75,
                "Tags": [{"Key": "Environment", "Value": "dev"}],
            }
        ]
    }

    mock_get_tags.return_value = {"Environment": "dev"}

    mock_ec2.create_snapshot.return_value = {
        "SnapshotId": "snap-noname",
        "State": "pending",
        "StartTime": datetime(2025, 3, 15, 8, 0, 0, tzinfo=timezone.utc),
    }

    with patch("cost_toolkit.scripts.management.ebs_manager.snapshot.datetime") as mock_dt:
        mock_now = datetime(2025, 3, 15, 8, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = mock_now

        result = create_volume_snapshot("vol-noname")

    assert result["volume_name"] is None
    assert_equal(result["snapshot_id"], "snap-noname")
    # Should still call create_tags because volume has other tags
    mock_ec2.create_tags.assert_called_once()


# Main function tests - error paths
@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.find_volume_region")
def test_create_volume_snapshot_volume_not_found(mock_find_region):
    """Test create_volume_snapshot raises VolumeNotFoundError when volume not found."""
    mock_find_region.return_value = None

    with pytest.raises(VolumeNotFoundError) as exc_info:
        create_volume_snapshot("vol-nonexistent")

    assert "vol-nonexistent not found in any region" in str(exc_info.value)
    mock_find_region.assert_called_once_with("vol-nonexistent")


@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.find_volume_region")
@patch("boto3.client")
def test_create_volume_snapshot_retrieval_error_client_error(mock_boto_client, mock_find_region):
    """Test create_volume_snapshot raises VolumeRetrievalError on ClientError."""
    mock_find_region.return_value = "us-west-2"

    mock_ec2 = MagicMock()
    mock_boto_client.return_value = mock_ec2

    mock_ec2.describe_volumes.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "Not authorized"}},
        "DescribeVolumes",
    )

    with pytest.raises(VolumeRetrievalError) as exc_info:
        create_volume_snapshot("vol-error123")

    assert "Error retrieving volume vol-error123" in str(exc_info.value)
    mock_find_region.assert_called_once_with("vol-error123")
    mock_ec2.describe_volumes.assert_called_once_with(VolumeIds=["vol-error123"])


@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.find_volume_region")
@patch("boto3.client")
def test_create_volume_snapshot_retrieval_error_generic_exception(mock_boto_client, mock_find_region):
    """Test create_volume_snapshot raises VolumeRetrievalError on generic exception."""
    mock_find_region.return_value = "us-east-1"

    mock_ec2 = MagicMock()
    mock_boto_client.return_value = mock_ec2

    mock_ec2.describe_volumes.side_effect = Exception("Network timeout")

    with pytest.raises(VolumeRetrievalError) as exc_info:
        create_volume_snapshot("vol-timeout")

    assert "Error retrieving volume vol-timeout: Network timeout" in str(exc_info.value)


@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.get_volume_tags")
@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.find_volume_region")
@patch("boto3.client")
def test_create_volume_snapshot_creation_error_on_create_snapshot(mock_boto_client, mock_find_region, mock_get_tags):
    """Test create_volume_snapshot raises SnapshotCreationError when snapshot creation fails."""
    mock_find_region.return_value = "us-west-2"

    mock_ec2 = MagicMock()
    mock_boto_client.return_value = mock_ec2

    mock_ec2.describe_volumes.return_value = {
        "Volumes": [
            {
                "VolumeId": "vol-failcreate",
                "Size": 100,
                "Tags": [{"Key": "Name", "Value": "fail-volume"}],
            }
        ]
    }

    mock_get_tags.return_value = {"Name": "fail-volume"}

    mock_ec2.create_snapshot.side_effect = ClientError(
        {"Error": {"Code": "SnapshotCreationPerVolumeRateExceeded", "Message": "Rate exceeded"}},
        "CreateSnapshot",
    )

    with pytest.raises(SnapshotCreationError) as exc_info:
        create_volume_snapshot("vol-failcreate")

    assert "Error creating snapshot for volume vol-failcreate" in str(exc_info.value)
    mock_ec2.describe_volumes.assert_called_once()
    mock_ec2.create_snapshot.assert_called_once()


@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.get_volume_tags")
@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.find_volume_region")
@patch("boto3.client")
def test_create_volume_snapshot_creation_error_on_create_tags(mock_boto_client, mock_find_region, mock_get_tags):
    """Test create_volume_snapshot raises SnapshotCreationError when tagging fails."""
    mock_find_region.return_value = "us-west-2"

    mock_ec2 = MagicMock()
    mock_boto_client.return_value = mock_ec2

    mock_ec2.describe_volumes.return_value = {
        "Volumes": [
            {
                "VolumeId": "vol-failtag",
                "Size": 100,
                "Tags": [{"Key": "Name", "Value": "tag-fail-volume"}],
            }
        ]
    }

    mock_get_tags.return_value = {"Name": "tag-fail-volume"}

    mock_ec2.create_snapshot.return_value = {
        "SnapshotId": "snap-failtag",
        "State": "pending",
        "StartTime": datetime(2025, 3, 15, 14, 30, 0, tzinfo=timezone.utc),
    }

    mock_ec2.create_tags.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "Cannot create tags"}},
        "CreateTags",
    )

    with pytest.raises(SnapshotCreationError) as exc_info:
        create_volume_snapshot("vol-failtag")

    assert "Error creating snapshot for volume vol-failtag" in str(exc_info.value)
    mock_ec2.create_snapshot.assert_called_once()
    mock_ec2.create_tags.assert_called_once()


# Edge case tests
@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.get_volume_tags")
@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.find_volume_region")
@patch("boto3.client")
def test_create_volume_snapshot_large_volume(mock_boto_client, mock_find_region, mock_get_tags):
    """Test create_volume_snapshot with large volume size."""
    mock_find_region.return_value = "us-east-1"

    mock_ec2 = MagicMock()
    mock_boto_client.return_value = mock_ec2

    large_size = TEST_LARGE_VOLUME_SIZE_GIB  # 16 TiB

    mock_ec2.describe_volumes.return_value = {
        "Volumes": [
            {
                "VolumeId": "vol-large",
                "Size": large_size,
                "Tags": [{"Key": "Name", "Value": "large-volume"}],
            }
        ]
    }

    mock_get_tags.return_value = {"Name": "large-volume"}

    mock_ec2.create_snapshot.return_value = {
        "SnapshotId": "snap-large",
        "State": "pending",
        "StartTime": datetime(2025, 3, 15, 10, 0, 0, tzinfo=timezone.utc),
    }

    with patch("cost_toolkit.scripts.management.ebs_manager.snapshot.datetime") as mock_dt:
        mock_now = datetime(2025, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = mock_now

        result = create_volume_snapshot("vol-large")

    assert_equal(result["volume_size"], large_size)
    assert f"{large_size}GB" in result["description"]


@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.get_volume_tags")
@patch("cost_toolkit.scripts.management.ebs_manager.snapshot.find_volume_region")
@patch("boto3.client")
def test_create_volume_snapshot_special_characters_in_tags(mock_boto_client, mock_find_region, mock_get_tags):
    """Test create_volume_snapshot with special characters in volume tags."""
    mock_find_region.return_value = "us-west-2"

    mock_ec2 = MagicMock()
    mock_boto_client.return_value = mock_ec2

    mock_ec2.describe_volumes.return_value = {
        "Volumes": [
            {
                "VolumeId": "vol-special",
                "Size": 50,
                "Tags": [{"Key": "Name", "Value": "volume-with-special-chars!@#"}],
            }
        ]
    }

    mock_get_tags.return_value = {"Name": "volume-with-special-chars!@#"}

    mock_ec2.create_snapshot.return_value = {
        "SnapshotId": "snap-special",
        "State": "pending",
        "StartTime": datetime(2025, 3, 15, 11, 0, 0, tzinfo=timezone.utc),
    }

    with patch("cost_toolkit.scripts.management.ebs_manager.snapshot.datetime") as mock_dt:
        mock_now = datetime(2025, 3, 15, 11, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = mock_now

        result = create_volume_snapshot("vol-special")

    assert_equal(result["volume_name"], "volume-with-special-chars!@#")
    assert "volume-with-special-chars!@#" in result["description"]
