"""Comprehensive tests for aws_elastic_ip_audit.py - Part 1: Region auditing tests."""

from __future__ import annotations

from unittest.mock import patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.audit.aws_elastic_ip_audit import (
    _scan_all_regions,
    audit_elastic_ips_in_region,
)


class TestAuditElasticIpsInRegionSuccess:
    """Tests for audit_elastic_ips_in_region function - success cases."""

    def test_audit_region_no_addresses(self):
        """Test auditing region with no Elastic IPs."""
        with patch(
            "cost_toolkit.scripts.audit.aws_elastic_ip_audit.describe_addresses",
            return_value=[],
        ):
            result = audit_elastic_ips_in_region("us-east-1", "test-key", "test-secret")

        assert result is None

    def test_audit_region_with_associated_eips(self):
        """Test auditing region with associated Elastic IPs."""
        addresses = [
            {
                "AllocationId": "eipalloc-123",
                "PublicIp": "1.2.3.4",
                "Domain": "vpc",
                "InstanceId": "i-123",
                "AssociationId": "eipassoc-123",
                "NetworkInterfaceId": "eni-123",
                "PrivateIpAddress": "10.0.0.1",
                "Tags": [{"Key": "Name", "Value": "test-eip"}],
            }
        ]

        with patch(
            "cost_toolkit.scripts.audit.aws_elastic_ip_audit.describe_addresses",
            return_value=addresses,
        ):
            result = audit_elastic_ips_in_region("us-east-1", "test-key", "test-secret")

        assert result is not None
        assert result["region"] == "us-east-1"
        assert result["total_eips"] == 1
        assert len(result["associated_eips"]) == 1
        assert len(result["unassociated_eips"]) == 0
        assert result["total_monthly_cost"] == 0
        assert result["associated_eips"][0]["allocation_id"] == "eipalloc-123"
        assert result["associated_eips"][0]["public_ip"] == "1.2.3.4"
        assert result["associated_eips"][0]["instance_id"] == "i-123"

    def test_audit_region_with_unassociated_eips(self):
        """Test auditing region with unassociated Elastic IPs."""
        addresses = [
            {
                "AllocationId": "eipalloc-456",
                "PublicIp": "5.6.7.8",
                "Domain": "vpc",
                "Tags": [{"Key": "Environment", "Value": "dev"}],
            }
        ]

        with patch(
            "cost_toolkit.scripts.audit.aws_elastic_ip_audit.describe_addresses",
            return_value=addresses,
        ):
            result = audit_elastic_ips_in_region("us-west-2", "test-key", "test-secret")

        assert result is not None
        assert result["region"] == "us-west-2"
        assert result["total_eips"] == 1
        assert len(result["associated_eips"]) == 0
        assert len(result["unassociated_eips"]) == 1
        assert result["total_monthly_cost"] == 3.65
        assert result["unassociated_eips"][0]["allocation_id"] == "eipalloc-456"
        assert result["unassociated_eips"][0]["public_ip"] == "5.6.7.8"
        assert result["unassociated_eips"][0]["monthly_cost"] == 3.65


class TestAuditElasticIpsInRegionEdgeCases:
    """Tests for audit_elastic_ips_in_region function - edge cases and errors."""

    def test_audit_region_with_mixed_eips(self):
        """Test auditing region with both associated and unassociated EIPs."""
        addresses = [
            {
                "AllocationId": "eipalloc-111",
                "PublicIp": "1.1.1.1",
                "Domain": "vpc",
                "InstanceId": "i-111",
                "AssociationId": "eipassoc-111",
            },
            {
                "AllocationId": "eipalloc-222",
                "PublicIp": "2.2.2.2",
                "Domain": "vpc",
            },
            {
                "AllocationId": "eipalloc-333",
                "PublicIp": "3.3.3.3",
                "Domain": "vpc",
                "NetworkInterfaceId": "eni-333",
            },
        ]

        with patch(
            "cost_toolkit.scripts.audit.aws_elastic_ip_audit.describe_addresses",
            return_value=addresses,
        ):
            result = audit_elastic_ips_in_region("eu-west-1", "test-key", "test-secret")

        assert result is not None
        assert result["total_eips"] == 3
        assert len(result["associated_eips"]) == 2
        assert len(result["unassociated_eips"]) == 1
        assert result["total_monthly_cost"] == 3.65

    def test_audit_region_with_network_interface_only(self):
        """Test EIP associated with network interface but no instance."""
        addresses = [
            {
                "AllocationId": "eipalloc-444",
                "PublicIp": "4.4.4.4",
                "Domain": "vpc",
                "NetworkInterfaceId": "eni-444",
                "PrivateIpAddress": "10.0.0.2",
            }
        ]

        with patch(
            "cost_toolkit.scripts.audit.aws_elastic_ip_audit.describe_addresses",
            return_value=addresses,
        ):
            result = audit_elastic_ips_in_region("us-east-1", "test-key", "test-secret")

        assert result is not None
        assert len(result["associated_eips"]) == 1
        assert len(result["unassociated_eips"]) == 0
        assert result["total_monthly_cost"] == 0

    def test_audit_region_with_missing_fields(self):
        """Test handling of addresses with missing optional fields."""
        addresses = [
            {
                "AllocationId": "eipalloc-555",
                "PublicIp": "5.5.5.5",
            }
        ]

        with patch(
            "cost_toolkit.scripts.audit.aws_elastic_ip_audit.describe_addresses",
            return_value=addresses,
        ):
            result = audit_elastic_ips_in_region("us-east-1", "test-key", "test-secret")

        assert result is not None
        assert result["unassociated_eips"][0]["domain"] is None
        assert result["unassociated_eips"][0]["instance_id"] is None
        assert result["unassociated_eips"][0]["tags"] == []


class TestAuditElasticIpsInRegionErrors:
    """Tests for audit_elastic_ips_in_region function - error handling."""

    def test_audit_region_client_error(self, capsys):
        """Test handling of ClientError during audit."""
        with patch(
            "cost_toolkit.scripts.audit.aws_elastic_ip_audit.describe_addresses",
            side_effect=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
                "DescribeAddresses",
            ),
        ):
            result = audit_elastic_ips_in_region("us-east-1", "test-key", "test-secret")

        assert result is None
        captured = capsys.readouterr()
        assert "Error auditing region us-east-1" in captured.out

    def test_audit_region_multiple_unassociated_cost_accumulation(self):
        """Test cost accumulation with multiple unassociated EIPs."""
        addresses = [{"AllocationId": f"eipalloc-{i}", "PublicIp": f"1.2.3.{i}", "Domain": "vpc"} for i in range(5)]

        with patch(
            "cost_toolkit.scripts.audit.aws_elastic_ip_audit.describe_addresses",
            return_value=addresses,
        ):
            result = audit_elastic_ips_in_region("us-east-1", "test-key", "test-secret")

        assert result is not None
        assert len(result["unassociated_eips"]) == 5
        assert result["total_monthly_cost"] == 3.65 * 5


class TestScanAllRegionsWithResults:
    """Tests for _scan_all_regions function - regions with EIPs."""

    def test_scan_all_regions_with_eips(self, capsys):
        """Test scanning all regions with Elastic IPs found."""
        regions = ["us-east-1", "us-west-2"]
        region_data_1 = {
            "region": "us-east-1",
            "total_eips": 2,
            "associated_eips": [{"allocation_id": "eipalloc-1"}],
            "unassociated_eips": [{"allocation_id": "eipalloc-2"}],
            "total_monthly_cost": 3.65,
        }
        region_data_2 = {
            "region": "us-west-2",
            "total_eips": 1,
            "associated_eips": [],
            "unassociated_eips": [{"allocation_id": "eipalloc-3"}],
            "total_monthly_cost": 3.65,
        }

        with patch(
            "cost_toolkit.scripts.audit.aws_elastic_ip_audit.audit_elastic_ips_in_region",
            side_effect=[region_data_1, region_data_2],
        ):
            result = _scan_all_regions(regions, "test-key", "test-secret")

        regions_with_eips, total_eips, total_unassociated, total_monthly_cost = result
        assert len(regions_with_eips) == 2
        assert total_eips == 3
        assert total_unassociated == 2
        assert total_monthly_cost == 7.30

        captured = capsys.readouterr()
        assert "Found 2 Elastic IP(s)" in captured.out
        assert "Found 1 Elastic IP(s)" in captured.out
        assert "1 unassociated (costing $3.65/month)" in captured.out

    def test_scan_all_regions_mixed_results(self, capsys):  # pylint: disable=unused-argument
        """Test scanning regions with mixed results (some with EIPs, some without)."""
        regions = ["us-east-1", "us-west-2", "eu-west-1"]
        region_data = {
            "region": "us-west-2",
            "total_eips": 1,
            "associated_eips": [],
            "unassociated_eips": [{"allocation_id": "eipalloc-1"}],
            "total_monthly_cost": 3.65,
        }

        with patch(
            "cost_toolkit.scripts.audit.aws_elastic_ip_audit.audit_elastic_ips_in_region",
            side_effect=[None, region_data, None],
        ):
            result = _scan_all_regions(regions, "test-key", "test-secret")

        regions_with_eips, total_eips, total_unassociated, total_monthly_cost = result
        assert len(regions_with_eips) == 1
        assert total_eips == 1
        assert total_unassociated == 1
        assert total_monthly_cost == 3.65

    def test_scan_all_regions_only_associated(self, capsys):
        """Test scanning regions with only associated EIPs."""
        regions = ["us-east-1"]
        region_data = {
            "region": "us-east-1",
            "total_eips": 2,
            "associated_eips": [{"allocation_id": "eipalloc-1"}, {"allocation_id": "eipalloc-2"}],
            "unassociated_eips": [],
            "total_monthly_cost": 0,
        }

        with patch(
            "cost_toolkit.scripts.audit.aws_elastic_ip_audit.audit_elastic_ips_in_region",
            return_value=region_data,
        ):
            result = _scan_all_regions(regions, "test-key", "test-secret")

        regions_with_eips, total_eips, total_unassociated, total_monthly_cost = result
        assert len(regions_with_eips) == 1
        assert total_eips == 2
        assert total_unassociated == 0
        assert total_monthly_cost == 0

        captured = capsys.readouterr()
        assert "Found 2 Elastic IP(s)" in captured.out
        assert "unassociated" not in captured.out


class TestScanAllRegionsNoResults:  # pylint: disable=too-few-public-methods
    """Tests for _scan_all_regions function - regions without EIPs."""

    def test_scan_all_regions_no_eips(self, capsys):
        """Test scanning all regions with no Elastic IPs."""
        regions = ["us-east-1", "us-west-2"]

        with patch(
            "cost_toolkit.scripts.audit.aws_elastic_ip_audit.audit_elastic_ips_in_region",
            return_value=None,
        ):
            result = _scan_all_regions(regions, "test-key", "test-secret")

        regions_with_eips, total_eips, total_unassociated, total_monthly_cost = result
        assert not regions_with_eips
        assert total_eips == 0
        assert total_unassociated == 0
        assert total_monthly_cost == 0

        captured = capsys.readouterr()
        assert "Auditing region: us-east-1" in captured.out
        assert "Auditing region: us-west-2" in captured.out
        assert "No Elastic IPs found" in captured.out
