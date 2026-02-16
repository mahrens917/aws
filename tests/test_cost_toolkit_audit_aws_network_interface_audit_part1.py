"""Comprehensive tests for aws_network_interface_audit.py - Part 1: Helper Functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cost_toolkit.scripts.audit.aws_network_interface_audit import (
    _build_interface_info,
    _categorize_interface,
    get_all_regions,
)


class TestGetAllRegions:
    """Tests for get_all_regions function."""

    @patch("cost_toolkit.common.aws_common.create_ec2_client")
    def test_get_all_regions_success(self, mock_create_client, monkeypatch):
        """Test successfully retrieving all AWS regions."""
        monkeypatch.delenv("COST_TOOLKIT_STATIC_AWS_REGIONS", raising=False)
        mock_ec2_client = MagicMock()
        mock_create_client.return_value = mock_ec2_client
        mock_ec2_client.describe_regions.return_value = {
            "Regions": [
                {"RegionName": "us-east-1"},
                {"RegionName": "us-west-2"},
                {"RegionName": "eu-west-1"},
            ]
        }

        regions = get_all_regions()

        assert regions == ["us-east-1", "us-west-2", "eu-west-1"]
        mock_create_client.assert_called_once()
        mock_ec2_client.describe_regions.assert_called_once()

    @patch("cost_toolkit.common.aws_common.create_ec2_client")
    def test_get_all_regions_uses_us_east_1(self, mock_create_ec2, monkeypatch):
        """Test that get_all_regions uses us-east-1 as region."""
        monkeypatch.delenv("COST_TOOLKIT_STATIC_AWS_REGIONS", raising=False)
        mock_ec2_client = MagicMock()
        mock_ec2_client.describe_regions.return_value = {"Regions": []}
        mock_create_ec2.return_value = mock_ec2_client

        get_all_regions()

        mock_create_ec2.assert_called_once()
        call_args = mock_create_ec2.call_args
        assert call_args[1]["region"] == "us-east-1" or call_args[0][0] == "us-east-1"

    @patch("cost_toolkit.common.aws_common.create_ec2_client")
    def test_get_all_regions_single_region(self, mock_create_ec2, monkeypatch):
        """Test retrieving single region."""
        monkeypatch.delenv("COST_TOOLKIT_STATIC_AWS_REGIONS", raising=False)
        mock_ec2_client = MagicMock()
        mock_ec2_client.describe_regions.return_value = {"Regions": [{"RegionName": "ap-south-1"}]}
        mock_create_ec2.return_value = mock_ec2_client

        regions = get_all_regions()

        assert regions == ["ap-south-1"]
        mock_create_ec2.assert_called_once()


class TestBuildInterfaceInfoComplete:
    """Tests for _build_interface_info function with complete data."""

    def _assert_interface_basic_fields(self, result, expected_values):
        """Helper to assert basic interface fields."""
        assert result["interface_id"] == expected_values["interface_id"]
        assert result["name"] == expected_values["name"]
        assert result["status"] == expected_values["status"]
        assert result["type"] == expected_values["type"]

    def _assert_interface_network_fields(self, result, expected_values):
        """Helper to assert network-related fields."""
        assert result["vpc_id"] == expected_values["vpc_id"]
        assert result["subnet_id"] == expected_values["subnet_id"]
        assert result["private_ip"] == expected_values["private_ip"]
        assert result["public_ip"] == expected_values["public_ip"]

    def _assert_interface_attachment_fields(self, result, expected_values):
        """Helper to assert attachment-related fields."""
        assert result["attached_to"] == expected_values["attached_to"]
        assert result["attachment_status"] == expected_values["attachment_status"]
        assert result["description"] == expected_values["description"]
        assert result["tags"] == expected_values["tags"]

    def test_build_interface_info_full_data(self):
        """Test building interface info with all fields present."""
        eni = {
            "NetworkInterfaceId": "eni-12345678",
            "Status": "in-use",
            "InterfaceType": "interface",
            "VpcId": "vpc-abcdef",
            "SubnetId": "subnet-12345",
            "PrivateIpAddress": "10.0.1.5",
            "Association": {"PublicIp": "54.123.45.67"},
            "Attachment": {
                "InstanceId": "i-1234567890",
                "Status": "attached",
            },
            "Description": "Primary network interface",
            "Tags": [
                {"Key": "Name", "Value": "web-server-eni"},
                {"Key": "Environment", "Value": "production"},
            ],
        }

        result = _build_interface_info(eni)

        expected_basic = {
            "interface_id": "eni-12345678",
            "name": "web-server-eni",
            "status": "in-use",
            "type": "interface",
        }
        expected_network = {
            "vpc_id": "vpc-abcdef",
            "subnet_id": "subnet-12345",
            "private_ip": "10.0.1.5",
            "public_ip": "54.123.45.67",
        }
        expected_attachment = {
            "attached_to": "i-1234567890",
            "attachment_status": "attached",
            "description": "Primary network interface",
            "tags": {"Name": "web-server-eni", "Environment": "production"},
        }

        self._assert_interface_basic_fields(result, expected_basic)
        self._assert_interface_network_fields(result, expected_network)
        self._assert_interface_attachment_fields(result, expected_attachment)

    def test_build_interface_info_lambda_interface(self):
        """Test building interface info for Lambda ENI."""
        eni = {
            "NetworkInterfaceId": "eni-lambda",
            "Status": "in-use",
            "InterfaceType": "lambda",
            "Description": "AWS Lambda VPC ENI",
        }

        result = _build_interface_info(eni)

        assert result["type"] == "lambda"
        assert result["description"] == "AWS Lambda VPC ENI"


class TestBuildInterfaceInfoSpecialTypes:
    """Tests for _build_interface_info with special interface types."""

    def test_build_interface_info_nat_gateway_interface(self):
        """Test building interface info for NAT Gateway ENI."""
        eni = {
            "NetworkInterfaceId": "eni-nat",
            "Status": "in-use",
            "InterfaceType": "nat_gateway",
            "Description": "Interface for NAT Gateway",
        }

        result = _build_interface_info(eni)

        assert result["type"] == "nat_gateway"

    def test_build_interface_info_multiple_tags(self):
        """Test building interface info with multiple tags."""
        eni = {
            "NetworkInterfaceId": "eni-tags",
            "Status": "available",
            "Tags": [
                {"Key": "Name", "Value": "test-eni"},
                {"Key": "Owner", "Value": "admin"},
                {"Key": "Project", "Value": "migration"},
            ],
        }

        result = _build_interface_info(eni)

        assert result["name"] == "test-eni"
        assert result["tags"] == {
            "Name": "test-eni",
            "Owner": "admin",
            "Project": "migration",
        }


class TestBuildInterfaceInfoMinimal:
    """Tests for _build_interface_info function with minimal or missing data."""

    def _assert_default_interface_values(self, result, interface_id, status):
        """Helper to assert default values for minimal interface data."""
        assert result["interface_id"] == interface_id
        assert result["status"] == status
        assert result["name"] is None
        assert result["type"] is None

    def _assert_default_network_values(self, result):
        """Helper to assert default network field values."""
        assert result["vpc_id"] is None
        assert result["subnet_id"] is None
        assert result["private_ip"] is None
        assert result["public_ip"] is None

    def _assert_default_attachment_values(self, result):
        """Helper to assert default attachment field values."""
        assert result["attached_to"] is None
        assert result["attachment_status"] is None
        assert result["description"] is None
        assert result["tags"] == {}

    def test_build_interface_info_minimal_data(self):
        """Test building interface info with minimal required fields."""
        eni = {
            "NetworkInterfaceId": "eni-minimal",
            "Status": "available",
        }

        result = _build_interface_info(eni)

        self._assert_default_interface_values(result, "eni-minimal", "available")
        self._assert_default_network_values(result)
        self._assert_default_attachment_values(result)

    def test_build_interface_info_no_tags(self):
        """Test building interface info with no tags."""
        eni = {
            "NetworkInterfaceId": "eni-notags",
            "Status": "in-use",
        }

        result = _build_interface_info(eni)

        assert result["name"] is None
        assert result["tags"] == {}

    def test_build_interface_info_no_public_ip(self):
        """Test building interface info without public IP association."""
        eni = {
            "NetworkInterfaceId": "eni-nopublic",
            "Status": "in-use",
            "PrivateIpAddress": "10.0.1.10",
        }

        result = _build_interface_info(eni)

        assert result["public_ip"] is None
        assert result["private_ip"] == "10.0.1.10"

    def test_build_interface_info_with_attachment_no_instance(self):
        """Test building interface info with attachment but no instance ID."""
        eni = {
            "NetworkInterfaceId": "eni-attach",
            "Status": "in-use",
            "Attachment": {
                "Status": "attached",
            },
        }

        result = _build_interface_info(eni)

        assert result["attached_to"] is None
        assert result["attachment_status"] == "attached"


class TestCategorizeInterface:
    """Tests for _categorize_interface function."""

    def test_categorize_unused_interface(self):
        """Test categorizing an unused interface."""
        result = _categorize_interface("available", {})
        assert result == "unused"

    def test_categorize_attached_interface_with_instance(self):
        """Test categorizing an interface attached to instance."""
        attachment = {"InstanceId": "i-12345", "Status": "attached"}
        result = _categorize_interface("in-use", attachment)
        assert result == "attached"

    def test_categorize_in_use_no_attachment(self):
        """Test categorizing in-use interface without attachment info."""
        result = _categorize_interface("in-use", {})
        assert result == "attached"

    def test_categorize_available_with_attachment(self):
        """Test categorizing available interface with attachment data."""
        attachment = {"Status": "detached"}
        result = _categorize_interface("available", attachment)
        assert result == "attached"

    def test_categorize_attaching_status(self):
        """Test categorizing interface in attaching state."""
        attachment = {"InstanceId": "i-12345", "Status": "attaching"}
        result = _categorize_interface("attaching", attachment)
        assert result == "attached"

    def test_categorize_detaching_status(self):
        """Test categorizing interface in detaching state."""
        attachment = {"Status": "detaching"}
        result = _categorize_interface("detaching", attachment)
        assert result == "attached"
