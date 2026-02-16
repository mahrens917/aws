"""Comprehensive tests for aws_ebs_audit.py."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.common.cost_utils import calculate_ebs_volume_cost
from cost_toolkit.scripts.audit.aws_ebs_audit import (
    _audit_region,
    _get_attachment_info,
    _print_old_snapshots,
    _print_recommendations,
    _print_unattached_volumes,
    _print_volume_breakdown,
    _process_snapshot,
    _process_volume,
    audit_ebs_volumes,
    get_all_regions,
)
from tests.aws_region_test_utils import assert_regions_error, assert_regions_success


class TestGetAllRegions:
    """Tests for get_all_regions function."""

    @patch("cost_toolkit.common.aws_common.create_ec2_client")
    def test_get_regions_success(self, mock_create_client, monkeypatch):
        """Test successful retrieval of regions."""
        monkeypatch.delenv("COST_TOOLKIT_STATIC_AWS_REGIONS", raising=False)
        assert_regions_success(get_all_regions, mock_create_client, monkeypatch)

    @patch("cost_toolkit.common.aws_common.create_ec2_client")
    def test_get_regions_error(self, mock_create_client, monkeypatch):
        """Test error when retrieving regions."""
        assert_regions_error(get_all_regions, mock_create_client, monkeypatch)


def test_calculate_volume_cost_calculate_volume_costs():
    """Test cost calculations for different volume types."""
    assert calculate_ebs_volume_cost(100, "gp3") == 8.0
    assert calculate_ebs_volume_cost(50, "gp2") == 5.0
    assert calculate_ebs_volume_cost(80, "io1") == 10.0
    with pytest.raises(ValueError, match="Unknown volume type: unknown-type"):
        calculate_ebs_volume_cost(100, "unknown-type")


def test_get_attachment_info_get_attachment_info():
    """Test getting attachment info for various scenarios."""
    assert _get_attachment_info({"Attachments": [{"InstanceId": "i-123456"}]}) == "Instance: i-123456"
    assert _get_attachment_info({"Attachments": []}) == "Not attached"
    assert _get_attachment_info({}) == "Not attached"


class TestProcessVolume:
    """Tests for _process_volume function."""

    def test_process_attached_volume(self, capsys):
        """Test processing attached volumes."""
        volume = {
            "VolumeId": "vol-123",
            "Size": 100,
            "VolumeType": "gp3",
            "State": "in-use",
            "Attachments": [{"InstanceId": "i-123"}],
        }
        result = _process_volume(volume, "us-east-1")
        assert result["volume_id"] == "vol-123"
        assert result["size_gb"] == 100
        assert result["volume_type"] == "gp3"
        assert result["state"] == "in-use"
        assert "Instance: i-123" in result["attached_to"]
        assert result["monthly_cost"] == 8.0
        captured = capsys.readouterr()
        assert "vol-123" in captured.out
        assert "$8.00" in captured.out

    def test_process_unattached_volume(self):
        """Test processing unattached volumes."""
        volume = {
            "VolumeId": "vol-456",
            "Size": 50,
            "VolumeType": "gp2",
            "State": "available",
            "Attachments": [],
        }
        result = _process_volume(volume, "us-west-2")
        assert result["attached_to"] == "Not attached"
        assert result["monthly_cost"] == 5.0


def test_process_snapshot_process_snapshot(capsys):
    """Test processing snapshots with and without descriptions."""
    snapshot = {
        "SnapshotId": "snap-123",
        "VolumeSize": 200,
        "State": "completed",
        "StartTime": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "Description": "Test snapshot",
    }
    result = _process_snapshot(snapshot, "us-east-1")
    assert result["snapshot_id"] == "snap-123"
    assert result["size_gb"] == 200
    assert result["state"] == "completed"
    assert result["description"] == "Test snapshot"
    assert result["monthly_cost"] == 10.0
    captured = capsys.readouterr()
    assert "snap-123" in captured.out
    assert "$10.00" in captured.out
    snapshot2 = {
        "SnapshotId": "snap-456",
        "VolumeSize": 100,
        "State": "completed",
        "StartTime": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    result2 = _process_snapshot(snapshot2, "us-east-1")
    assert result2["description"] is None


def test_audit_region_audit_region(capsys):
    """Test auditing region with and without resources."""
    with patch("boto3.client") as mock_client:
        mock_ec2 = MagicMock()
        mock_ec2.describe_volumes.return_value = {
            "Volumes": [
                {
                    "VolumeId": "vol-1",
                    "Size": 100,
                    "VolumeType": "gp3",
                    "State": "in-use",
                    "Attachments": [{"InstanceId": "i-1"}],
                }
            ]
        }
        mock_ec2.describe_snapshots.return_value = {
            "Snapshots": [
                {
                    "SnapshotId": "snap-1",
                    "VolumeSize": 50,
                    "State": "completed",
                    "StartTime": datetime(2024, 1, 1, tzinfo=timezone.utc),
                    "Description": "Test",
                }
            ]
        }
        mock_client.return_value = mock_ec2
        volumes, snapshots = _audit_region("us-east-1")
    assert len(volumes) == 1
    assert len(snapshots) == 1
    captured = capsys.readouterr()
    assert "Auditing EBS resources" in captured.out
    with patch("boto3.client") as mock_client:
        mock_ec2 = MagicMock()
        mock_ec2.describe_volumes.return_value = {"Volumes": []}
        mock_ec2.describe_snapshots.return_value = {"Snapshots": []}
        mock_client.return_value = mock_ec2
        volumes, snapshots = _audit_region("us-east-1")
    assert not volumes
    assert not snapshots


def test_print_volume_breakdown_print_breakdown(capsys):
    """Test printing volume breakdown."""
    volume_details = [
        {
            "volume_type": "gp3",
            "size_gb": 100,
            "monthly_cost": 8.0,
        },
        {
            "volume_type": "gp3",
            "size_gb": 50,
            "monthly_cost": 4.0,
        },
        {
            "volume_type": "gp2",
            "size_gb": 200,
            "monthly_cost": 20.0,
        },
    ]

    _print_volume_breakdown(volume_details)

    captured = capsys.readouterr()
    assert "Volume Breakdown by Type" in captured.out
    assert "gp3: 2 volumes, 150 GB total, $12.00/month" in captured.out
    assert "gp2: 1 volumes, 200 GB total, $20.00/month" in captured.out


def test_print_unattached_volumes_print_unattached_volumes(capsys):
    """Test printing unattached and attached volumes."""
    volume_details = [
        {
            "region": "us-east-1",
            "volume_id": "vol-1",
            "size_gb": 100,
            "volume_type": "gp3",
            "attached_to": "Not attached",
            "monthly_cost": 8.0,
        },
        {
            "region": "us-east-1",
            "volume_id": "vol-2",
            "size_gb": 50,
            "volume_type": "gp2",
            "attached_to": "Instance: i-123",
            "monthly_cost": 5.0,
        },
    ]
    result = _print_unattached_volumes(volume_details)
    assert len(result) == 1
    assert result[0]["volume_id"] == "vol-1"
    captured = capsys.readouterr()
    assert "UNATTACHED VOLUMES" in captured.out
    assert "$8.00/month" in captured.out
    volume_details2 = [
        {
            "region": "us-east-1",
            "volume_id": "vol-1",
            "attached_to": "Instance: i-123",
            "monthly_cost": 8.0,
        },
    ]
    result2 = _print_unattached_volumes(volume_details2)
    assert not result2


def test_print_old_snapshots_print_old_snapshots(capsys):
    """Test printing old and new snapshots."""
    old_time = datetime.now(timezone.utc).replace(day=1, month=1, year=2020)
    snapshot_details = [
        {
            "region": "us-east-1",
            "snapshot_id": "snap-1",
            "size_gb": 100,
            "start_time": old_time,
            "monthly_cost": 5.0,
        },
        {
            "region": "us-east-2",
            "snapshot_id": "snap-2",
            "size_gb": 200,
            "start_time": datetime.now(timezone.utc),
            "monthly_cost": 10.0,
        },
    ]
    _print_old_snapshots(snapshot_details)
    captured = capsys.readouterr()
    assert "SNAPSHOT AGE ANALYSIS" in captured.out
    assert "snap-1" in captured.out
    snapshot_details2 = [
        {
            "snapshot_id": "snap-1",
            "start_time": datetime.now(timezone.utc),
            "monthly_cost": 5.0,
        },
    ]
    _print_old_snapshots(snapshot_details2)
    captured = capsys.readouterr()
    assert "less than 30 days old" in captured.out


def test_print_recommendations_print_recommendations(capsys):
    """Test recommendations for various scenarios."""
    unattached_volumes = [
        {"volume_id": "vol-1", "monthly_cost": 8.0},
        {"volume_id": "vol-2", "monthly_cost": 5.0},
    ]
    _print_recommendations(unattached_volumes, [])
    captured = capsys.readouterr()
    assert "RECOMMENDATIONS" in captured.out
    assert "Consider deleting 2 unattached volumes" in captured.out
    assert "$13.00/month" in captured.out
    old_snapshots = [
        {"snapshot_id": "snap-1", "monthly_cost": 10.0},
        {"snapshot_id": "snap-2", "monthly_cost": 5.0},
    ]
    _print_recommendations([], old_snapshots)
    captured = capsys.readouterr()
    assert "Review 2 old snapshots" in captured.out
    assert "$15.00/month" in captured.out
    _print_recommendations([], [])
    captured = capsys.readouterr()
    assert "All EBS resources appear to be in active use" in captured.out


def test_audit_ebs_volumes_audit_volumes(capsys):
    """Test successful EBS audit and error handling."""
    with patch("cost_toolkit.scripts.audit.aws_ebs_audit.setup_aws_credentials"):
        with patch(
            "cost_toolkit.scripts.audit.aws_ebs_audit.get_all_regions",
            return_value=["us-east-1"],
        ):
            with patch("cost_toolkit.scripts.audit.aws_ebs_audit._audit_region") as mock_audit:
                with patch("cost_toolkit.scripts.audit.aws_ebs_audit._print_volume_breakdown"):
                    with patch(
                        "cost_toolkit.scripts.audit.aws_ebs_audit._print_unattached_volumes",
                        return_value=[],
                    ):
                        with patch(
                            "cost_toolkit.scripts.audit.aws_ebs_audit._print_old_snapshots",
                            return_value=[],
                        ):
                            with patch("cost_toolkit.scripts.audit.aws_ebs_audit._print_recommendations"):
                                mock_audit.return_value = (
                                    [{"monthly_cost": 8.0}],
                                    [{"monthly_cost": 5.0}],
                                )
                                audit_ebs_volumes()
    captured = capsys.readouterr()
    assert "AWS EBS Volume & Snapshot Audit" in captured.out
    assert "OVERALL EBS SUMMARY" in captured.out
    with patch("cost_toolkit.scripts.audit.aws_ebs_audit.setup_aws_credentials"):
        with patch(
            "cost_toolkit.scripts.audit.aws_ebs_audit.get_all_regions",
            return_value=["us-east-1"],
        ):
            with patch("cost_toolkit.scripts.audit.aws_ebs_audit._audit_region") as mock_audit:
                with patch(
                    "cost_toolkit.scripts.audit.aws_ebs_audit._print_unattached_volumes",
                    return_value=[],
                ):
                    with patch(
                        "cost_toolkit.scripts.audit.aws_ebs_audit._print_old_snapshots",
                        return_value=[],
                    ):
                        with patch("cost_toolkit.scripts.audit.aws_ebs_audit._print_recommendations"):
                            mock_audit.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "describe_volumes")
                            audit_ebs_volumes()
    captured = capsys.readouterr()
    assert "Error auditing" in captured.out
