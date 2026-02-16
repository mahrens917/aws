"""Comprehensive tests for aws_vpc_audit.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.audit.aws_vpc_audit import (
    _print_elastic_ip_details,
    _process_elastic_ip_address,
    audit_elastic_ips_in_region,
)
from cost_toolkit.scripts.aws_ec2_operations import get_all_regions
from tests.aws_region_test_utils import (
    ELASTIC_IP_RESPONSE,
    assert_regions_error,
    assert_regions_success,
)


class TestGetAllRegions:
    """Tests for get_all_regions function."""

    @patch("cost_toolkit.common.aws_common.create_ec2_client")
    def test_get_all_regions_success(self, mock_create_client, monkeypatch):
        """Test successful retrieval of regions."""
        assert_regions_success(get_all_regions, mock_create_client, monkeypatch)

    @patch("cost_toolkit.common.aws_common.create_ec2_client")
    def test_get_all_regions_client_error(self, mock_create_client, monkeypatch):
        """Test error handling when describe_regions fails."""
        assert_regions_error(get_all_regions, mock_create_client, monkeypatch)


class TestProcessElasticIpAddress:
    """Tests for _process_elastic_ip_address function."""

    def test_process_elastic_ip_in_use(self):
        """Test processing an in-use elastic IP."""
        addr = {
            "PublicIp": "54.123.45.67",
            "AllocationId": "eipalloc-123",
            "AssociationId": "eipassoc-456",
            "InstanceId": "i-123",
            "NetworkInterfaceId": "eni-123",
            "Domain": "vpc",
            "Tags": [{"Key": "Name", "Value": "prod-ip"}],
        }

        ip_info, monthly_cost = _process_elastic_ip_address(addr, "us-east-1")

        assert ip_info["public_ip"] == "54.123.45.67"
        assert ip_info["allocation_id"] == "eipalloc-123"
        assert ip_info["association_id"] == "eipassoc-456"
        assert ip_info["instance_id"] == "i-123"
        assert ip_info["status"] == "🟢 IN USE"
        assert ip_info["region"] == "us-east-1"
        assert abs(monthly_cost - 3.60) < 0.01

    def test_process_elastic_ip_idle(self):
        """Test processing an idle elastic IP."""
        addr = {
            "PublicIp": "54.123.45.68",
            "AllocationId": "eipalloc-456",
            "Domain": "vpc",
            "Tags": [],
        }

        ip_info, monthly_cost = _process_elastic_ip_address(addr, "us-west-2")

        assert ip_info["public_ip"] == "54.123.45.68"
        assert ip_info["status"] == "🔴 IDLE (COSTING MONEY)"
        assert ip_info["association_id"] is None
        assert ip_info["instance_id"] is None
        assert abs(monthly_cost - 3.60) < 0.01

    def test_process_elastic_ip_minimal_fields(self):
        """Test processing an elastic IP with minimal fields."""
        addr = {}

        ip_info, monthly_cost = _process_elastic_ip_address(addr, "eu-west-1")

        assert ip_info["public_ip"] is None
        assert ip_info["allocation_id"] is None
        assert ip_info["domain"] is None
        assert ip_info["tags"] == []
        assert abs(monthly_cost - 3.60) < 0.01


class TestPrintElasticIpDetails:
    """Tests for _print_elastic_ip_details function."""

    def test_print_elastic_ip_details_full(self, capsys):
        """Test printing full elastic IP details."""
        ip_info = {
            "public_ip": "54.123.45.67",
            "status": "🟢 IN USE",
            "allocation_id": "eipalloc-123",
            "instance_id": "i-123",
            "network_interface_id": "eni-123",
            "domain": "vpc",
            "monthly_cost_estimate": 3.60,
            "tags": [{"Key": "Name", "Value": "prod-ip"}],
        }

        _print_elastic_ip_details(ip_info)

        captured = capsys.readouterr()
        assert "Public IP: 54.123.45.67" in captured.out
        assert "Status: 🟢 IN USE" in captured.out
        assert "Allocation ID: eipalloc-123" in captured.out
        assert "Associated with: i-123" in captured.out
        assert "Domain: vpc" in captured.out
        assert "Estimated monthly cost: $3.60" in captured.out
        assert "Tags:" in captured.out
        assert "Name: prod-ip" in captured.out

    def test_print_elastic_ip_details_network_interface(self, capsys):
        """Test printing with network interface association."""
        ip_info = {
            "public_ip": "54.123.45.68",
            "status": "🟢 IN USE",
            "allocation_id": "eipalloc-456",
            "instance_id": None,
            "network_interface_id": "eni-456",
            "domain": "vpc",
            "monthly_cost_estimate": 3.60,
            "tags": [],
        }

        _print_elastic_ip_details(ip_info)

        captured = capsys.readouterr()
        assert "Associated with: eni-456" in captured.out

    def test_print_elastic_ip_details_nothing_associated(self, capsys):
        """Test printing with no associations."""
        ip_info = {
            "public_ip": "54.123.45.69",
            "status": "🔴 IDLE (COSTING MONEY)",
            "allocation_id": "eipalloc-789",
            "instance_id": None,
            "network_interface_id": None,
            "domain": "vpc",
            "monthly_cost_estimate": 3.60,
            "tags": [],
        }

        _print_elastic_ip_details(ip_info)

        captured = capsys.readouterr()
        assert "Associated with: Nothing" in captured.out

    def test_print_elastic_ip_details_no_tags(self, capsys):
        """Test printing with no tags."""
        ip_info = {
            "public_ip": "54.123.45.70",
            "status": "🟢 IN USE",
            "allocation_id": "eipalloc-999",
            "instance_id": "i-999",
            "network_interface_id": None,
            "domain": "vpc",
            "monthly_cost_estimate": 3.60,
            "tags": [],
        }

        _print_elastic_ip_details(ip_info)

        captured = capsys.readouterr()
        assert "Tags:" not in captured.out


class TestAuditElasticIpsInRegion:
    """Tests for audit_elastic_ips_in_region function."""

    def test_audit_elastic_ips_no_addresses(self, capsys):
        """Test when no elastic IPs exist."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_client.return_value = mock_ec2
            mock_ec2.describe_addresses.return_value = {"Addresses": []}

            result = audit_elastic_ips_in_region("us-east-1")

        assert len(result) == 0
        captured = capsys.readouterr()
        assert "No Elastic IP addresses found" in captured.out

    def test_audit_elastic_ips_success(self, capsys):
        """Test successful elastic IP audit."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_client.return_value = mock_ec2
            mock_ec2.describe_addresses.return_value = ELASTIC_IP_RESPONSE

            result = audit_elastic_ips_in_region("us-east-1")

        assert len(result) == 2
        assert result[0]["public_ip"] == "54.123.45.67"
        assert result[1]["public_ip"] == "54.123.45.68"
        captured = capsys.readouterr()
        assert "Region Summary for us-east-1" in captured.out
        assert "Total Elastic IPs: 2" in captured.out
        assert "Estimated monthly cost: $7.20" in captured.out

    def test_audit_elastic_ips_unauthorized_operation(self, capsys):
        """Test handling of unauthorized operation error."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_client.return_value = mock_ec2
            mock_ec2.describe_addresses.side_effect = ClientError({"Error": {"Code": "UnauthorizedOperation"}}, "describe_addresses")

            result = audit_elastic_ips_in_region("us-east-1")

        assert len(result) == 0
        captured = capsys.readouterr()
        assert "No permission to access us-east-1" in captured.out

    def test_audit_elastic_ips_other_error(self, capsys):
        """Test handling of other AWS errors."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_client.return_value = mock_ec2
            mock_ec2.describe_addresses.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "describe_addresses")

            result = audit_elastic_ips_in_region("us-east-1")

        assert len(result) == 0
        captured = capsys.readouterr()
        assert "Error auditing us-east-1" in captured.out
