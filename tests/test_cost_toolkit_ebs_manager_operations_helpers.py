"""Tests for cost_toolkit/scripts/management/ebs_manager/operations.py - helper functions"""

# pylint: disable=unused-argument

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.scripts.management.ebs_manager.operations import (
    VolumeNotFoundError,
    _extract_attachment_info,
    _extract_basic_volume_info,
    _get_last_read_activity,
    get_volume_detailed_info,
)
from tests.assertions import assert_equal


# Test VolumeNotFoundError
def test_volume_not_found_error():
    """Test VolumeNotFoundError exception."""
    error = VolumeNotFoundError("vol-123")
    assert_equal(str(error), "Volume vol-123 not found in any region")


# Test _extract_basic_volume_info
def test_extract_basic_volume_info():
    """Test _extract_basic_volume_info extracts basic volume data."""
    volume = {
        "Size": 100,
        "VolumeType": "gp3",
        "State": "available",
        "CreateTime": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "AvailabilityZone": "us-east-1a",
        "Encrypted": True,
        "Iops": 3000,
        "Throughput": 125,
        "Tags": [{"Key": "Name", "Value": "test-volume"}],
    }

    result = _extract_basic_volume_info(volume, "vol-123", "us-east-1")

    assert_equal(result["volume_id"], "vol-123")
    assert_equal(result["region"], "us-east-1")
    assert_equal(result["size_gb"], 100)
    assert_equal(result["volume_type"], "gp3")
    assert_equal(result["state"], "available")
    assert_equal(result["create_time"], datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
    assert_equal(result["availability_zone"], "us-east-1a")
    assert_equal(result["encrypted"], True)
    assert_equal(result["iops"], 3000)
    assert_equal(result["throughput"], 125)
    assert_equal(result["tags"], {"Name": "test-volume"})


def test_extract_basic_volume_info_without_iops_throughput():
    """Test _extract_basic_volume_info handles missing IOPS and Throughput."""
    volume = {
        "Size": 50,
        "VolumeType": "standard",
        "State": "in-use",
        "CreateTime": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "AvailabilityZone": "us-west-2a",
        "Encrypted": False,
        "Tags": [],
    }

    result = _extract_basic_volume_info(volume, "vol-456", "us-west-2")

    assert result["iops"] is None
    assert result["throughput"] is None


# Test _extract_attachment_info
@patch("cost_toolkit.scripts.management.ebs_manager.operations.get_instance_name")
def test_extract_attachment_info_with_attachment(mock_get_instance_name):
    """Test _extract_attachment_info extracts attachment data."""
    mock_get_instance_name.return_value = "test-instance"
    volume = {
        "Attachments": [
            {
                "InstanceId": "i-123",
                "Device": "/dev/sda1",
                "AttachTime": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                "DeleteOnTermination": True,
            }
        ]
    }

    result = _extract_attachment_info(volume, "us-east-1")

    assert_equal(result["attached_to_instance_id"], "i-123")
    assert_equal(result["attached_to_instance_name"], "test-instance")
    assert_equal(result["device"], "/dev/sda1")
    assert_equal(result["attach_time"], datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
    assert_equal(result["delete_on_termination"], True)
    mock_get_instance_name.assert_called_once_with("i-123", "us-east-1")


def test_extract_attachment_info_no_attachment():
    """Test _extract_attachment_info handles unattached volumes."""
    volume = {"Attachments": []}

    result = _extract_attachment_info(volume, "us-east-1")

    assert_equal(result["attached_to_instance_id"], None)
    assert_equal(result["attached_to_instance_name"], "Not attached")
    assert_equal(result["device"], None)
    assert_equal(result["attach_time"], None)
    assert_equal(result["delete_on_termination"], None)


def test_extract_attachment_info_missing_attachments_key():
    """Test _extract_attachment_info handles missing Attachments key."""
    volume = {}

    result = _extract_attachment_info(volume, "us-east-1")

    assert_equal(result["attached_to_instance_id"], None)
    assert_equal(result["attached_to_instance_name"], "Not attached")


# Test _get_last_read_activity
@patch("cost_toolkit.scripts.management.ebs_manager.operations.datetime")
def test_get_last_read_activity_with_data(mock_datetime_cls):
    """Test _get_last_read_activity returns last read timestamp."""
    mock_now = datetime(2024, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    mock_datetime_cls.now.return_value = mock_now

    mock_cloudwatch = MagicMock()
    mock_cloudwatch.get_metric_statistics.return_value = {
        "Datapoints": [
            {"Timestamp": datetime(2024, 3, 10, 12, 0, 0, tzinfo=timezone.utc), "Sum": 100},
            {"Timestamp": datetime(2024, 3, 12, 14, 0, 0, tzinfo=timezone.utc), "Sum": 50},
            {"Timestamp": datetime(2024, 3, 8, 8, 0, 0, tzinfo=timezone.utc), "Sum": 200},
        ]
    }

    result = _get_last_read_activity(mock_cloudwatch, "vol-123")

    assert_equal(result, datetime(2024, 3, 12, 14, 0, 0, tzinfo=timezone.utc))
    mock_cloudwatch.get_metric_statistics.assert_called_once()
    call_args = mock_cloudwatch.get_metric_statistics.call_args
    assert_equal(call_args[1]["Namespace"], "AWS/EBS")
    assert_equal(call_args[1]["MetricName"], "VolumeReadOps")
    assert_equal(call_args[1]["Dimensions"], [{"Name": "VolumeId", "Value": "vol-123"}])
    assert_equal(call_args[1]["Period"], 86400)
    assert_equal(call_args[1]["Statistics"], ["Sum"])


def test_get_last_read_activity_no_data():
    """Test _get_last_read_activity returns message when no data."""
    mock_cloudwatch = MagicMock()
    mock_cloudwatch.get_metric_statistics.return_value = {"Datapoints": []}

    result = _get_last_read_activity(mock_cloudwatch, "vol-123")

    assert_equal(result, "No recent activity")


def test_get_last_read_activity_client_error():
    """Test _get_last_read_activity handles ClientError."""
    mock_cloudwatch = MagicMock()
    mock_cloudwatch.get_metric_statistics.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Not authorized"}}, "GetMetricStatistics"
    )

    result = _get_last_read_activity(mock_cloudwatch, "vol-123")

    assert "Error retrieving metrics:" in result


# Test get_volume_detailed_info
@patch("cost_toolkit.scripts.management.ebs_manager.operations.find_volume_region")
@patch("boto3.client")
def test_get_volume_detailed_info_success(mock_boto_client, mock_find_region):
    """Test get_volume_detailed_info returns comprehensive volume info."""
    mock_find_region.return_value = "us-east-1"

    mock_ec2 = MagicMock()
    mock_cloudwatch = MagicMock()

    def client_side_effect(service, region_name):
        if service == "ec2":
            return mock_ec2
        return mock_cloudwatch

    mock_boto_client.side_effect = client_side_effect

    mock_ec2.describe_volumes.return_value = {
        "Volumes": [
            {
                "Size": 100,
                "VolumeType": "gp3",
                "State": "available",
                "CreateTime": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                "AvailabilityZone": "us-east-1a",
                "Encrypted": True,
                "Iops": 3000,
                "Throughput": 125,
                "Tags": [{"Key": "Name", "Value": "test-volume"}],
                "Attachments": [],
            }
        ]
    }

    mock_cloudwatch.get_metric_statistics.return_value = {"Datapoints": []}

    result = get_volume_detailed_info("vol-123")

    assert_equal(result["volume_id"], "vol-123")
    assert_equal(result["region"], "us-east-1")
    assert_equal(result["size_gb"], 100)
    assert_equal(result["attached_to_instance_name"], "Not attached")
    assert_equal(result["last_read_activity"], "No recent activity")
    mock_find_region.assert_called_once_with("vol-123")


@patch("cost_toolkit.scripts.management.ebs_manager.operations.find_volume_region")
def test_get_volume_detailed_info_volume_not_found(mock_find_region):
    """Test get_volume_detailed_info raises VolumeNotFoundError when volume not found."""
    mock_find_region.return_value = None

    with pytest.raises(VolumeNotFoundError) as exc_info:
        get_volume_detailed_info("vol-nonexistent")

    assert_equal(str(exc_info.value), "Volume vol-nonexistent not found in any region")
