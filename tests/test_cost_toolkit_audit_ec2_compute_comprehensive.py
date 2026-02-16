"""Comprehensive tests for aws_ec2_compute_detailed_audit.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.scripts.audit.aws_ec2_compute_detailed_audit import (
    _build_instance_info,
    _print_instance_details,
    _print_network_and_tags,
    _print_region_summary,
    analyze_ec2_instances_in_region,
    get_all_regions,
    get_instance_hourly_cost,
)
from tests.aws_region_test_utils import assert_regions_error, assert_regions_success


class TestGetAllRegions:
    """Tests for get_all_regions function."""

    @patch("cost_toolkit.common.aws_common.create_ec2_client")
    def test_get_regions_success(self, mock_create_client, monkeypatch):
        """Test successful retrieval of regions."""
        assert_regions_success(get_all_regions, mock_create_client, monkeypatch)

    @patch("cost_toolkit.common.aws_common.create_ec2_client")
    def test_get_regions_client_error(self, mock_create_client, monkeypatch):
        """Test error handling when getting regions fails."""
        assert_regions_error(get_all_regions, mock_create_client, monkeypatch)


class TestBuildInstanceInfo:
    """Tests for _build_instance_info function."""

    def _assert_core_instance_fields(self, result):
        """Helper to assert core instance identification fields."""
        assert result["instance_id"] == "i-123456"
        assert result["instance_type"] == "t3.micro"
        assert result["state"] == "running"
        assert result["region"] == "us-east-1"

    def _assert_cost_fields(self, result):
        """Helper to assert cost-related fields."""
        assert result["hourly_cost"] == 0.0104
        assert result["monthly_cost"] == 7.488

    def _assert_network_fields(self, result):
        """Helper to assert network-related fields."""
        assert result["platform"] == "windows"
        assert result["vpc_id"] == "vpc-123"
        assert result["public_ip"] == "1.2.3.4"
        assert result["private_ip"] == "10.0.1.5"

    def test_build_complete_instance_info(self):
        """Test building instance info with all fields."""
        instance = {
            "InstanceId": "i-123456",
            "InstanceType": "t3.micro",
            "State": {"Name": "running"},
            "LaunchTime": "2024-01-01T00:00:00Z",
            "Platform": "windows",
            "VpcId": "vpc-123",
            "SubnetId": "subnet-123",
            "PublicIpAddress": "1.2.3.4",
            "PrivateIpAddress": "10.0.1.5",
            "Tags": [{"Key": "Name", "Value": "test-instance"}],
        }

        result = _build_instance_info(instance, "us-east-1", 0.0104, 7.488)

        self._assert_core_instance_fields(result)
        self._assert_cost_fields(result)
        self._assert_network_fields(result)
        assert len(result["tags"]) == 1

    def test_build_minimal_instance_info(self):
        """Test building instance info with minimal fields."""
        instance = {
            "InstanceId": "i-789012",
            "InstanceType": "t2.nano",
            "State": {"Name": "stopped"},
        }

        result = _build_instance_info(instance, "us-west-2", 0.0058, 4.176)

        assert result["instance_id"] == "i-789012"
        assert result["instance_type"] == "t2.nano"
        assert result["state"] == "stopped"
        assert result["platform"] is None
        assert result["vpc_id"] is None
        assert result["public_ip"] is None
        assert result["tags"] == []


class TestPrintInstanceDetails:
    """Tests for _print_instance_details function."""

    def test_print_running_instance(self, capsys):
        """Test printing running instance details."""
        instance_info = {
            "platform": "Linux/UNIX",
            "launch_time": "2024-01-01T00:00:00Z",
        }

        _print_instance_details(
            "i-123",
            "t3.micro",
            "running",
            instance_info,
            hourly_cost=0.0104,
            monthly_cost=7.488,
        )

        captured = capsys.readouterr()
        assert "Instance: i-123" in captured.out
        assert "Type: t3.micro" in captured.out
        assert "State: running" in captured.out
        assert "Platform: Linux/UNIX" in captured.out
        assert "Hourly Cost: $0.0104" in captured.out
        assert "Monthly Cost (if running 24/7): $7.49" in captured.out

    def test_print_stopped_instance(self, capsys):
        """Test printing stopped instance details."""
        instance_info = {
            "platform": "Windows",
            "launch_time": "2024-01-01T00:00:00Z",
        }

        _print_instance_details(
            "i-456",
            "t2.small",
            "stopped",
            instance_info,
            hourly_cost=0.023,
            monthly_cost=16.56,
        )

        captured = capsys.readouterr()
        assert "Instance: i-456" in captured.out
        assert "State: stopped" in captured.out
        assert "Monthly Cost: $0.00 (stopped - only EBS storage charges)" in captured.out

    def test_print_terminated_instance(self, capsys):
        """Test printing terminated instance details."""
        instance_info = {
            "platform": "Linux/UNIX",
            "launch_time": "2024-01-01T00:00:00Z",
        }

        _print_instance_details(
            "i-789",
            "t3.small",
            "terminated",
            instance_info,
            hourly_cost=0.0208,
            monthly_cost=14.976,
        )

        captured = capsys.readouterr()
        assert "State: terminated" in captured.out
        assert "Monthly Cost: $0.00 (terminated)" in captured.out


class TestPrintNetworkAndTags:
    """Tests for _print_network_and_tags function."""

    def test_print_with_ips_and_tags(self, capsys):
        """Test printing network info and tags."""
        instance_info = {
            "public_ip": "1.2.3.4",
            "private_ip": "10.0.1.5",
            "tags": [
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},
            ],
        }

        _print_network_and_tags(instance_info)

        captured = capsys.readouterr()
        assert "Public IP: 1.2.3.4" in captured.out
        assert "Private IP: 10.0.1.5" in captured.out
        assert "Name: web-server" in captured.out
        assert "Environment: production" in captured.out

    def test_print_without_ips(self, capsys):
        """Test printing when no IPs present."""
        instance_info = {
            "public_ip": None,
            "private_ip": None,
            "tags": [],
        }

        _print_network_and_tags(instance_info)

        captured = capsys.readouterr()
        assert "Public IP" not in captured.out
        assert "Private IP" not in captured.out


def test_print_region_summary_print_summary(capsys):
    """Test printing region summary."""
    instances = [
        {"state": "running", "monthly_cost": 10.0},
        {"state": "running", "monthly_cost": 20.0},
        {"state": "stopped", "monthly_cost": 0.0},
        {"state": "terminated", "monthly_cost": 0.0},
    ]

    _print_region_summary("us-east-1", instances, 30.0)

    captured = capsys.readouterr()
    assert "Region Summary for us-east-1" in captured.out
    assert "Running instances: 2" in captured.out
    assert "Stopped instances: 1" in captured.out
    assert "Terminated instances: 1" in captured.out
    assert "Total monthly compute cost: $30.00" in captured.out


class TestAnalyzeEc2Instances:
    """Tests for analyze_ec2_instances_in_region function."""

    def test_analyze_with_instances(self, capsys):
        """Test analyzing region with instances."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_instances.return_value = {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-123",
                                "InstanceType": "t3.micro",
                                "State": {"Name": "running"},
                                "LaunchTime": "2024-01-01T00:00:00Z",
                                "Tags": [],
                            }
                        ]
                    }
                ]
            }
            mock_client.return_value = mock_ec2

            with patch(
                "cost_toolkit.scripts.audit.aws_ec2_compute_detailed_audit.get_instance_hourly_cost",
                return_value=0.0104,
            ):
                instances = analyze_ec2_instances_in_region("us-east-1")

        assert len(instances) == 1
        assert instances[0]["instance_id"] == "i-123"
        captured = capsys.readouterr()
        assert "Analyzing EC2 Compute in us-east-1" in captured.out

    def test_analyze_no_instances(self, capsys):
        """Test analyzing region with no instances."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_instances.return_value = {"Reservations": []}
            mock_client.return_value = mock_ec2

            instances = analyze_ec2_instances_in_region("us-west-2")

        assert len(instances) == 0
        captured = capsys.readouterr()
        assert "No EC2 instances found in us-west-2" in captured.out

    def test_analyze_client_error(self, capsys):
        """Test error handling when analyzing instances."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_instances.side_effect = ClientError({"Error": {"Code": "UnauthorizedOperation"}}, "describe_instances")
            mock_client.return_value = mock_ec2

            instances = analyze_ec2_instances_in_region("eu-west-1")

        assert not instances
        captured = capsys.readouterr()
        assert "Error analyzing EC2 in eu-west-1" in captured.out


class TestGetInstanceHourlyCost:
    """Tests for get_instance_hourly_cost function."""

    def test_known_instance_types(self):
        """Test cost calculation for known instance types."""
        assert get_instance_hourly_cost("t3.micro", "us-east-1") == 0.0104
        assert get_instance_hourly_cost("t2.small", "us-east-1") == 0.023
        assert get_instance_hourly_cost("c5.large", "us-east-1") == 0.085
        assert get_instance_hourly_cost("r5.xlarge", "us-east-1") == 0.252

    def test_regional_multipliers(self):
        """Test regional pricing multipliers."""
        base_cost = get_instance_hourly_cost("t3.micro", "us-east-1")
        us_west_cost = get_instance_hourly_cost("t3.micro", "us-west-1")
        eu_cost = get_instance_hourly_cost("t3.micro", "eu-west-1")

        assert us_west_cost > base_cost
        assert eu_cost > base_cost

    def test_unknown_instance_type(self):
        """Test error raised for unknown instance types."""
        with pytest.raises(ValueError, match="Unknown instance type: unknown.type"):
            get_instance_hourly_cost("unknown.type", "us-east-1")

    def test_unknown_region(self):
        """Test error raised for unknown regions."""
        with pytest.raises(ValueError, match="Unknown region: unknown-region-1"):
            get_instance_hourly_cost("t3.micro", "unknown-region-1")
