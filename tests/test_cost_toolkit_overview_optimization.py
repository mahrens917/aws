"""Tests for cost_toolkit/overview/optimization.py module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.common.cost_utils import calculate_ebs_volume_cost
from cost_toolkit.overview.optimization import (
    _check_old_snapshots,
    _check_unattached_ebs_volumes,
    _check_unused_elastic_ips,
    _scan_region_for_unattached_volumes,
    analyze_optimization_opportunities,
)
from tests.conftest_test_values import TEST_UNATTACHED_VOLUME_COUNT


def test_calculate_volume_cost_gp3():
    """Test calculate_ebs_volume_cost for gp3 volumes."""
    cost = calculate_ebs_volume_cost(100, "gp3")
    assert cost == 8.0  # 100 * 0.08


def test_calculate_volume_cost_gp2():
    """Test calculate_ebs_volume_cost for gp2 volumes."""
    cost = calculate_ebs_volume_cost(100, "gp2")
    assert cost == 10.0  # 100 * 0.10


def test_calculate_volume_cost_unknown_type():
    """Test calculate_ebs_volume_cost for unknown volume types."""
    cost = calculate_ebs_volume_cost(100, "io1")
    assert cost == 12.5  # 100 * 0.125 for io1


def test_scan_region_for_unattached_volumes_with_volumes():
    """Test _scan_region_for_unattached_volumes finds unattached volumes."""
    with patch("boto3.client") as mock_client:
        mock_ec2 = MagicMock()
        mock_ec2.describe_volumes.return_value = {
            "Volumes": [
                {
                    "VolumeId": "vol-1",
                    "Size": 10,
                    "VolumeType": "gp3",
                    "Attachments": [],
                },
                {
                    "VolumeId": "vol-2",
                    "Size": 20,
                    "VolumeType": "gp2",
                    "Attachments": [],
                },
            ]
        }
        mock_client.return_value = mock_ec2

        count, cost = _scan_region_for_unattached_volumes("us-east-1")

        assert count == TEST_UNATTACHED_VOLUME_COUNT
        assert cost > 0


def test_scan_region_for_unattached_volumes_all_attached():
    """Test _scan_region_for_unattached_volumes when all volumes are attached."""
    with patch("boto3.client") as mock_client:
        mock_ec2 = MagicMock()
        mock_ec2.describe_volumes.return_value = {
            "Volumes": [
                {
                    "VolumeId": "vol-1",
                    "Size": 10,
                    "VolumeType": "gp3",
                    "Attachments": [{"InstanceId": "i-123"}],
                }
            ]
        }
        mock_client.return_value = mock_ec2

        count, cost = _scan_region_for_unattached_volumes("us-east-1")

        assert count == 0
        assert cost == 0.0


def test_scan_region_for_unattached_volumes_error():
    """Test _scan_region_for_unattached_volumes raises errors."""
    with patch("boto3.client") as mock_client:
        mock_ec2 = MagicMock()
        mock_ec2.describe_volumes.side_effect = ClientError({"Error": {"Code": "TestError"}}, "test")
        mock_client.return_value = mock_ec2

        with pytest.raises(ClientError):
            _scan_region_for_unattached_volumes("us-east-1")


def test_check_unattached_ebs_volumes_with_volumes():
    """Test _check_unattached_ebs_volumes returns recommendation."""
    with patch("cost_toolkit.overview.optimization.get_all_aws_regions") as mock_regions:
        with patch("cost_toolkit.overview.optimization._scan_region_for_unattached_volumes") as mock_scan:
            mock_regions.return_value = ["us-east-1"]
            mock_scan.return_value = (5, 50.0)

            result = _check_unattached_ebs_volumes()

            assert result is not None
            assert result["category"] == "EBS Optimization"
            assert result["potential_savings"] == 50.0


def test_check_unattached_ebs_volumes_none_found():
    """Test _check_unattached_ebs_volumes when no unattached volumes exist."""
    with patch("cost_toolkit.overview.optimization.get_all_aws_regions") as mock_regions:
        with patch("cost_toolkit.overview.optimization._scan_region_for_unattached_volumes") as mock_scan:
            mock_regions.return_value = ["us-east-1"]
            mock_scan.return_value = (0, 0.0)

            result = _check_unattached_ebs_volumes()

            assert result is None


def test_check_unused_elastic_ips_with_unused():
    """Test _check_unused_elastic_ips finds unused IPs."""
    with patch("cost_toolkit.overview.optimization.get_all_aws_regions", return_value=["us-east-1"]):
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_addresses.return_value = {
                "Addresses": [
                    {"PublicIp": "1.2.3.4"},  # No InstanceId
                    {"PublicIp": "5.6.7.8", "InstanceId": "i-123"},  # Attached
                ]
            }
            mock_client.return_value = mock_ec2

            result = _check_unused_elastic_ips()

            assert result is not None
            assert result["category"] == "VPC Optimization"
            assert "Elastic IPs" in result["description"]


def test_check_unused_elastic_ips_all_used():
    """Test _check_unused_elastic_ips when all IPs are in use."""
    with patch("cost_toolkit.overview.optimization.get_all_aws_regions", return_value=["us-east-1"]):
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_addresses.return_value = {
                "Addresses": [
                    {"PublicIp": "1.2.3.4", "InstanceId": "i-123"},
                    {"PublicIp": "5.6.7.8", "InstanceId": "i-456"},
                ]
            }
            mock_client.return_value = mock_ec2

            result = _check_unused_elastic_ips()

            assert result is None


def test_check_unused_elastic_ips_error():
    """Test _check_unused_elastic_ips raises errors."""
    with patch("cost_toolkit.overview.optimization.get_all_aws_regions", return_value=["us-east-1"]):
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_addresses.side_effect = ClientError({"Error": {"Code": "TestError"}}, "test")
            mock_client.return_value = mock_ec2

            with pytest.raises(ClientError):
                _check_unused_elastic_ips()


def test_check_unattached_ebs_volumes_client_error():
    """Test _check_unattached_ebs_volumes raises ClientError."""
    with patch("cost_toolkit.overview.optimization.get_all_aws_regions") as mock_regions:
        mock_regions.side_effect = ClientError({"Error": {"Code": "TestError"}}, "test")

        with pytest.raises(ClientError):
            _check_unattached_ebs_volumes()


def test_check_unused_elastic_ips_regional_error():
    """Test _check_unused_elastic_ips raises on first regional error."""
    with patch("cost_toolkit.overview.optimization.get_all_aws_regions", return_value=["us-east-1"]):
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            # First region fails
            mock_ec2.describe_addresses.side_effect = ClientError({"Error": {"Code": "TestError"}}, "test")
            mock_client.return_value = mock_ec2

            with pytest.raises(ClientError):
                _check_unused_elastic_ips()


def test_check_old_snapshots_with_old_snapshots():
    """Test _check_old_snapshots finds old snapshots."""
    with patch("cost_toolkit.overview.optimization.get_all_aws_regions") as mock_regions:
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            old_date = datetime.now(tz=timezone.utc) - timedelta(days=100)
            recent_date = datetime.now(tz=timezone.utc) - timedelta(days=10)

            mock_ec2.describe_snapshots.return_value = {
                "Snapshots": [
                    {"SnapshotId": "snap-1", "StartTime": old_date, "VolumeSize": 100},
                    {"SnapshotId": "snap-2", "StartTime": recent_date, "VolumeSize": 50},
                    {"SnapshotId": "snap-3", "StartTime": old_date, "VolumeSize": 200},
                ]
            }
            mock_client.return_value = mock_ec2
            mock_regions.return_value = ["us-east-1"]

            result = _check_old_snapshots()

            assert result is not None
            assert result["category"] == "Snapshot Optimization"
            assert result["risk"] == "Medium"
            assert "90 days" in result["description"]


def test_check_old_snapshots_no_old_snapshots():
    """Test _check_old_snapshots when no old snapshots exist."""
    with patch("cost_toolkit.overview.optimization.get_all_aws_regions") as mock_regions:
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            recent_date = datetime.now(tz=timezone.utc) - timedelta(days=10)

            mock_ec2.describe_snapshots.return_value = {
                "Snapshots": [
                    {"SnapshotId": "snap-1", "StartTime": recent_date, "VolumeSize": 100},
                ]
            }
            mock_client.return_value = mock_ec2
            mock_regions.return_value = ["us-east-1"]

            result = _check_old_snapshots()

            assert result is None


def test_check_old_snapshots_regional_error():
    """Test _check_old_snapshots raises on regional errors."""
    with patch("cost_toolkit.overview.optimization.get_all_aws_regions") as mock_regions:
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_snapshots.side_effect = ClientError({"Error": {"Code": "TestError"}}, "test")
            mock_client.return_value = mock_ec2
            mock_regions.return_value = ["us-east-1"]

            with pytest.raises(ClientError):
                _check_old_snapshots()


def test_check_old_snapshots_client_error():
    """Test _check_old_snapshots raises on top-level ClientError."""
    with patch("cost_toolkit.overview.optimization.get_all_aws_regions") as mock_regions:
        mock_regions.side_effect = ClientError({"Error": {"Code": "TestError"}}, "test")

        with pytest.raises(ClientError):
            _check_old_snapshots()


def test_check_old_snapshots_single_old_snapshot():
    """Test _check_old_snapshots detects a single old snapshot."""
    with patch("cost_toolkit.overview.optimization.get_all_aws_regions") as mock_regions:
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            old_date = datetime.now(tz=timezone.utc) - timedelta(days=100)

            mock_ec2.describe_snapshots.return_value = {
                "Snapshots": [
                    {"SnapshotId": "snap-1", "StartTime": old_date, "VolumeSize": 100},
                ]
            }
            mock_client.return_value = mock_ec2
            mock_regions.return_value = ["us-east-1"]

            result = _check_old_snapshots()

            assert result is not None
            assert result["category"] == "Snapshot Optimization"


def test_analyze_optimization_opportunities_all_checks():
    """Test analyze_optimization_opportunities with all opportunities."""
    with patch("cost_toolkit.overview.optimization._check_unattached_ebs_volumes") as mock_ebs:
        with patch("cost_toolkit.overview.optimization._check_unused_elastic_ips") as mock_eip:
            with patch("cost_toolkit.overview.optimization._check_old_snapshots") as mock_snapshots:
                mock_ebs.return_value = {
                    "category": "EBS Optimization",
                    "description": "Test EBS",
                    "potential_savings": 50.0,
                    "risk": "Low",
                    "action": "Test action",
                }
                mock_eip.return_value = {
                    "category": "VPC Optimization",
                    "description": "Test EIP",
                    "potential_savings": 10.0,
                    "risk": "Low",
                    "action": "Test action",
                }
                mock_snapshots.return_value = {
                    "category": "Snapshot Optimization",
                    "description": "Test Snapshots",
                    "potential_savings": 30.0,
                    "risk": "Medium",
                    "action": "Test action",
                }

                result = analyze_optimization_opportunities()

                assert len(result) == 3
                assert result[0]["category"] == "EBS Optimization"
                assert result[1]["category"] == "VPC Optimization"
                assert result[2]["category"] == "Snapshot Optimization"


def test_analyze_optimization_opportunities_partial_checks():
    """Test analyze_optimization_opportunities with some None results."""
    with patch("cost_toolkit.overview.optimization._check_unattached_ebs_volumes") as mock_ebs:
        with patch("cost_toolkit.overview.optimization._check_unused_elastic_ips") as mock_eip:
            with patch("cost_toolkit.overview.optimization._check_old_snapshots") as mock_snapshots:
                mock_ebs.return_value = {
                    "category": "EBS Optimization",
                    "description": "Test EBS",
                    "potential_savings": 50.0,
                    "risk": "Low",
                    "action": "Test action",
                }
                mock_eip.return_value = None
                mock_snapshots.return_value = None

                result = analyze_optimization_opportunities()

                assert len(result) == 1
                assert result[0]["category"] == "EBS Optimization"


def test_analyze_optimization_opportunities_no_opportunities():
    """Test analyze_optimization_opportunities with no opportunities."""
    with patch("cost_toolkit.overview.optimization._check_unattached_ebs_volumes") as mock_ebs:
        with patch("cost_toolkit.overview.optimization._check_unused_elastic_ips") as mock_eip:
            with patch("cost_toolkit.overview.optimization._check_old_snapshots") as mock_snapshots:
                mock_ebs.return_value = None
                mock_eip.return_value = None
                mock_snapshots.return_value = None

                result = analyze_optimization_opportunities()

                assert len(result) == 0
                assert not result
