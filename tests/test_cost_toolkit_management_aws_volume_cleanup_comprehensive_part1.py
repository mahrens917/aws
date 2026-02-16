"""Comprehensive tests for aws_volume_cleanup.py - Part 1."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.scripts.management.aws_volume_cleanup import (
    delete_snapshot,
    get_bucket_region,
    get_bucket_size_metrics,
    tag_volume_with_name,
)


class TestTagVolumeWithName:
    """Tests for tag_volume_with_name function."""

    @patch("cost_toolkit.scripts.management.aws_volume_cleanup.boto3.client")
    def test_tag_volume_success(self, mock_boto3_client, capsys):
        """Test successfully tagging a volume."""
        mock_ec2_client = MagicMock()
        mock_boto3_client.return_value = mock_ec2_client

        result = tag_volume_with_name("vol-123456", "test-volume", "us-east-1")

        assert result is True
        mock_ec2_client.create_tags.assert_called_once_with(Resources=["vol-123456"], Tags=[{"Key": "Name", "Value": "test-volume"}])
        captured = capsys.readouterr()
        assert "Successfully tagged volume" in captured.out
        assert "vol-123456" in captured.out
        assert "test-volume" in captured.out

    @patch("cost_toolkit.scripts.management.aws_volume_cleanup.boto3.client")
    def test_tag_volume_error(self, mock_boto3_client, capsys):
        """Test error tagging a volume."""
        mock_ec2_client = MagicMock()
        mock_boto3_client.return_value = mock_ec2_client
        mock_ec2_client.create_tags.side_effect = ClientError({"Error": {"Code": "InvalidVolume.NotFound"}}, "create_tags")

        result = tag_volume_with_name("vol-invalid", "test-volume", "us-east-1")

        assert result is False
        captured = capsys.readouterr()
        assert "Error tagging volume" in captured.out

    @patch("cost_toolkit.scripts.management.aws_volume_cleanup.boto3.client")
    def test_tag_volume_different_regions(self, mock_boto3_client):
        """Test tagging volumes in different regions."""
        mock_ec2_client = MagicMock()
        mock_boto3_client.return_value = mock_ec2_client

        tag_volume_with_name("vol-123", "volume1", "us-west-2")

        mock_boto3_client.assert_called_with("ec2", region_name="us-west-2")


class TestDeleteSnapshot:
    """Tests for delete_snapshot function."""

    @patch("cost_toolkit.scripts.management.aws_volume_cleanup.boto3.client")
    def test_delete_snapshot_success(self, mock_boto3_client, capsys):
        """Test successfully deleting a snapshot."""
        mock_ec2_client = MagicMock()
        mock_boto3_client.return_value = mock_ec2_client

        mock_ec2_client.describe_snapshots.return_value = {
            "Snapshots": [
                {
                    "VolumeSize": 100,
                    "Description": "Test snapshot",
                    "StartTime": datetime(2025, 11, 13, 12, 0, 0),
                }
            ]
        }

        result = delete_snapshot("snap-123456", "us-east-1")

        assert result is True
        mock_ec2_client.describe_snapshots.assert_called_once_with(SnapshotIds=["snap-123456"])
        mock_ec2_client.delete_snapshot.assert_called_once_with(SnapshotId="snap-123456")

        captured = capsys.readouterr()
        assert "Successfully deleted snapshot" in captured.out
        assert "snap-123456" in captured.out
        assert "100 GB" in captured.out
        assert "$5.00" in captured.out

    @patch("cost_toolkit.scripts.management.aws_volume_cleanup.boto3.client")
    def test_delete_snapshot_error(self, mock_boto3_client, capsys):
        """Test error deleting a snapshot."""
        mock_ec2_client = MagicMock()
        mock_boto3_client.return_value = mock_ec2_client
        mock_ec2_client.describe_snapshots.side_effect = ClientError({"Error": {"Code": "InvalidSnapshot.NotFound"}}, "describe_snapshots")

        result = delete_snapshot("snap-invalid", "us-east-1")

        assert result is False
        captured = capsys.readouterr()
        assert "Error deleting snapshot" in captured.out

    @patch("cost_toolkit.scripts.management.aws_volume_cleanup.boto3.client")
    def test_delete_snapshot_different_sizes(self, mock_boto3_client, capsys):
        """Test deleting snapshots of different sizes."""
        mock_ec2_client = MagicMock()
        mock_boto3_client.return_value = mock_ec2_client

        mock_ec2_client.describe_snapshots.return_value = {
            "Snapshots": [
                {
                    "VolumeSize": 50,
                    "Description": "Small snapshot",
                    "StartTime": datetime(2025, 11, 13, 12, 0, 0),
                }
            ]
        }

        delete_snapshot("snap-123456", "us-east-1")

        captured = capsys.readouterr()
        assert "50 GB" in captured.out
        assert "$2.50" in captured.out

    @patch("cost_toolkit.scripts.management.aws_volume_cleanup.boto3.client")
    def test_delete_snapshot_no_description(self, mock_boto3_client, capsys):
        """Test deleting snapshot with no description."""
        mock_ec2_client = MagicMock()
        mock_boto3_client.return_value = mock_ec2_client

        mock_ec2_client.describe_snapshots.return_value = {
            "Snapshots": [{"VolumeSize": 100, "StartTime": datetime(2025, 11, 13, 12, 0, 0)}]
        }

        delete_snapshot("snap-123456", "us-east-1")

        captured = capsys.readouterr()
        assert "Description: None" in captured.out


class TestGetBucketRegion:
    """Tests for get_bucket_region function."""

    def test_get_bucket_region_us_east_1(self, capsys):
        """Test getting bucket region for us-east-1."""
        # Mock get_bucket_location to return us-east-1
        with patch("cost_toolkit.scripts.aws_s3_operations.get_bucket_location") as mock_get_location:
            mock_get_location.return_value = "us-east-1"

            result = get_bucket_region("test-bucket")

            assert result == "us-east-1"
            captured = capsys.readouterr()
            assert "Region: us-east-1" in captured.out

    def test_get_bucket_region_other_region(self, capsys):
        """Test getting bucket region for non-us-east-1."""
        # Mock get_bucket_location to return us-west-2
        with patch("cost_toolkit.scripts.aws_s3_operations.get_bucket_location") as mock_get_location:
            mock_get_location.return_value = "us-west-2"

            result = get_bucket_region("test-bucket")

            assert result == "us-west-2"
            captured = capsys.readouterr()
            assert "Region: us-west-2" in captured.out

    def test_get_bucket_region_error(self):
        """Test error getting bucket region."""
        # Mock get_bucket_location to raise ClientError
        with patch("cost_toolkit.scripts.aws_s3_operations.create_s3_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client
            mock_client.get_bucket_location.side_effect = ClientError({"Error": {"Code": "NoSuchBucket"}}, "get_bucket_location")

            with pytest.raises(ClientError):
                get_bucket_region("non-existent")


class TestGetBucketSizeMetrics:
    """Tests for get_bucket_size_metrics function."""

    @patch("cost_toolkit.scripts.management.aws_volume_cleanup.boto3.client")
    def test_get_bucket_size_large_bucket(self, mock_boto3_client, capsys):
        """Test getting size metrics for large bucket."""
        mock_cloudwatch = MagicMock()
        mock_boto3_client.return_value = mock_cloudwatch

        mock_cloudwatch.get_metric_statistics.return_value = {
            "Datapoints": [
                {
                    "Timestamp": datetime.now(timezone.utc),
                    "Average": 5 * 1024**3,
                }
            ]
        }

        get_bucket_size_metrics("large-bucket", "us-east-1")

        captured = capsys.readouterr()
        assert "Size: 5.00 GB" in captured.out
        assert "Est. monthly cost" in captured.out

    @patch("cost_toolkit.scripts.management.aws_volume_cleanup.boto3.client")
    def test_get_bucket_size_small_bucket(self, mock_boto3_client, capsys):
        """Test getting size metrics for small bucket."""
        mock_cloudwatch = MagicMock()
        mock_boto3_client.return_value = mock_cloudwatch

        mock_cloudwatch.get_metric_statistics.return_value = {
            "Datapoints": [
                {
                    "Timestamp": datetime.now(timezone.utc),
                    "Average": 100 * 1024**2,
                }
            ]
        }

        get_bucket_size_metrics("small-bucket", "us-east-1")

        captured = capsys.readouterr()
        assert "Size: 100.00 MB" in captured.out
        assert "<$0.01" in captured.out

    @patch("cost_toolkit.scripts.management.aws_volume_cleanup.boto3.client")
    def test_get_bucket_size_no_data(self, mock_boto3_client, capsys):
        """Test getting size metrics with no data."""
        mock_cloudwatch = MagicMock()
        mock_boto3_client.return_value = mock_cloudwatch

        mock_cloudwatch.get_metric_statistics.return_value = {"Datapoints": []}

        get_bucket_size_metrics("bucket", "us-east-1")

        captured = capsys.readouterr()
        assert "No recent data available" in captured.out

    @patch("cost_toolkit.scripts.management.aws_volume_cleanup.boto3.client")
    def test_get_bucket_size_error(self, mock_boto3_client, capsys):
        """Test error getting bucket size metrics."""
        mock_cloudwatch = MagicMock()
        mock_boto3_client.return_value = mock_cloudwatch

        mock_cloudwatch.get_metric_statistics.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "get_metric_statistics")

        get_bucket_size_metrics("bucket", "us-east-1")

        captured = capsys.readouterr()
        assert "Unable to determine" in captured.out

    @patch("cost_toolkit.scripts.management.aws_volume_cleanup.boto3.client")
    def test_get_bucket_size_unknown_region(self, mock_boto3_client):
        """Test getting size metrics for unknown region defaults to us-east-1."""
        mock_cloudwatch = MagicMock()
        mock_boto3_client.return_value = mock_cloudwatch

        mock_cloudwatch.get_metric_statistics.return_value = {"Datapoints": []}

        get_bucket_size_metrics("bucket", "Unknown")

        mock_boto3_client.assert_called_with("cloudwatch", region_name="us-east-1")
