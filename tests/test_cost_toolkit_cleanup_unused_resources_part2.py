"""Comprehensive tests for aws_cleanup_unused_resources.py - Part 2."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.cleanup.unused_security_groups import (
    analyze_security_groups_usage,
    delete_unused_security_groups,
)
from cost_toolkit.scripts.cleanup.unused_subnets import (
    _categorize_subnets,
    _collect_used_subnets_from_elb,
    _collect_used_subnets_from_nat_gateways,
    _collect_used_subnets_from_rds,
    analyze_subnet_usage,
)


class TestCollectUsedSubnetsFromNatGateways:
    """Tests for _collect_used_subnets_from_nat_gateways function."""

    def test_collect_from_nat_gateways(self):
        """Test collecting subnets from NAT gateways."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_nat_gateways.return_value = {
            "NatGateways": [
                {"State": "available", "SubnetId": "subnet-nat1"},
                {"State": "pending", "SubnetId": "subnet-nat2"},
            ]
        }

        result = _collect_used_subnets_from_nat_gateways(mock_ec2)

        assert result == {"subnet-nat1", "subnet-nat2"}

    def test_collect_excludes_deleted_nat_gateways(self):
        """Test that deleted NAT gateways are excluded."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_nat_gateways.return_value = {
            "NatGateways": [
                {"State": "deleted", "SubnetId": "subnet-nat1"},
                {"State": "available", "SubnetId": "subnet-nat2"},
            ]
        }

        result = _collect_used_subnets_from_nat_gateways(mock_ec2)

        assert result == {"subnet-nat2"}


class TestCollectUsedSubnetsFromRds:
    """Tests for _collect_used_subnets_from_rds function."""

    def test_collect_from_rds_subnet_groups(self):
        """Test collecting subnets from RDS subnet groups."""
        with patch("boto3.client") as mock_boto3:
            mock_rds = MagicMock()
            mock_boto3.return_value = mock_rds
            mock_rds.describe_db_subnet_groups.return_value = {
                "DBSubnetGroups": [
                    {
                        "Subnets": [
                            {"SubnetIdentifier": "subnet-rds1"},
                            {"SubnetIdentifier": "subnet-rds2"},
                        ]
                    },
                    {"Subnets": [{"SubnetIdentifier": "subnet-rds3"}]},
                ]
            }

            result = _collect_used_subnets_from_rds("us-east-1")

            assert result == {"subnet-rds1", "subnet-rds2", "subnet-rds3"}

    def test_collect_from_rds_with_error(self, capsys):
        """Test error handling when checking RDS subnets."""
        with patch("boto3.client") as mock_boto3:
            mock_rds = MagicMock()
            mock_boto3.return_value = mock_rds
            mock_rds.describe_db_subnet_groups.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "describe_db_subnet_groups")

            result = _collect_used_subnets_from_rds("us-east-1")

            assert result == set()
            captured = capsys.readouterr()
            assert "Warning: Could not check RDS subnets" in captured.out


class TestCollectUsedSubnetsFromElb:
    """Tests for _collect_used_subnets_from_elb function."""

    def test_collect_from_load_balancers(self):
        """Test collecting subnets from load balancers."""
        with patch("boto3.client") as mock_boto3:
            mock_elbv2 = MagicMock()
            mock_boto3.return_value = mock_elbv2
            mock_elbv2.describe_load_balancers.return_value = {
                "LoadBalancers": [
                    {
                        "AvailabilityZones": [
                            {"SubnetId": "subnet-lb1"},
                            {"SubnetId": "subnet-lb2"},
                        ]
                    },
                    {"AvailabilityZones": [{"SubnetId": "subnet-lb3"}]},
                ]
            }

            result = _collect_used_subnets_from_elb("us-east-1")

            assert result == {"subnet-lb1", "subnet-lb2", "subnet-lb3"}

    def test_collect_from_elb_with_error(self, capsys):
        """Test error handling when checking ELB subnets."""
        with patch("boto3.client") as mock_boto3:
            mock_elbv2 = MagicMock()
            mock_boto3.return_value = mock_elbv2
            mock_elbv2.describe_load_balancers.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "describe_load_balancers")

            result = _collect_used_subnets_from_elb("us-east-1")

            assert result == set()
            captured = capsys.readouterr()
            assert "Warning: Could not check ELB subnets" in captured.out


class TestCategorizeSubnets:
    """Tests for _categorize_subnets function."""

    def test_categorize_used_and_unused(self):
        """Test categorizing used and unused subnets."""
        all_subnets = [
            {"SubnetId": "subnet-used1"},
            {"SubnetId": "subnet-used2"},
            {"SubnetId": "subnet-unused1"},
        ]
        used_subnets = {"subnet-used1", "subnet-used2"}

        unused, used = _categorize_subnets(all_subnets, used_subnets)

        assert len(used) == 2
        assert len(unused) == 1
        assert unused[0]["SubnetId"] == "subnet-unused1"

    def test_categorize_all_unused(self):
        """Test when all subnets are unused."""
        all_subnets = [{"SubnetId": "subnet-1"}, {"SubnetId": "subnet-2"}]
        used_subnets = set()

        unused, used = _categorize_subnets(all_subnets, used_subnets)

        assert len(unused) == 2
        assert len(used) == 0


class TestAnalyzeSecurityGroupsUsage:
    """Tests for analyze_security_groups_usage function."""

    def test_analyze_success(self, capsys):
        """Test successful security group analysis."""
        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2
            mock_ec2.describe_security_groups.return_value = {
                "SecurityGroups": [
                    {"GroupId": "sg-default", "GroupName": "default", "VpcId": "vpc-1"},
                    {"GroupId": "sg-used", "GroupName": "used-sg", "VpcId": "vpc-1"},
                    {"GroupId": "sg-unused", "GroupName": "unused-sg", "VpcId": "vpc-1"},
                ]
            }
            mock_ec2.describe_instances.return_value = {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "State": {"Name": "running"},
                                "SecurityGroups": [{"GroupId": "sg-used"}],
                            }
                        ]
                    }
                ]
            }
            mock_ec2.describe_network_interfaces.return_value = {"NetworkInterfaces": []}

            with patch(
                "cost_toolkit.scripts.cleanup.unused_security_groups._collect_used_sgs_from_rds",
                return_value=set(),
            ):
                with patch(
                    "cost_toolkit.scripts.cleanup.unused_security_groups._collect_used_sgs_from_elb",
                    return_value=set(),
                ):
                    result = analyze_security_groups_usage("us-east-1")

            assert len(result["unused"]) == 1
            assert len(result["used"]) == 1
            assert len(result["default"]) == 1
            captured = capsys.readouterr()
            assert "Analyzing Security Group usage" in captured.out

    def test_analyze_with_client_error(self, capsys):
        """Test analysis with client error."""
        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2
            mock_ec2.describe_security_groups.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "describe_security_groups")

            result = analyze_security_groups_usage("us-east-1")

            assert result == {"unused": [], "used": [], "default": []}
            captured = capsys.readouterr()
            assert "Error analyzing security groups" in captured.out


class TestAnalyzeSubnetUsage:
    """Tests for analyze_subnet_usage function."""

    def test_analyze_success(self, capsys):
        """Test successful subnet analysis."""
        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2
            mock_ec2.describe_subnets.return_value = {
                "Subnets": [
                    {
                        "SubnetId": "subnet-used",
                        "VpcId": "vpc-1",
                        "AvailabilityZone": "us-east-1a",
                        "CidrBlock": "10.0.1.0/24",
                    },
                    {
                        "SubnetId": "subnet-unused",
                        "VpcId": "vpc-1",
                        "AvailabilityZone": "us-east-1b",
                        "CidrBlock": "10.0.2.0/24",
                    },
                ]
            }
            mock_ec2.describe_instances.return_value = {
                "Reservations": [{"Instances": [{"State": {"Name": "running"}, "SubnetId": "subnet-used"}]}]
            }
            mock_ec2.describe_network_interfaces.return_value = {"NetworkInterfaces": []}
            mock_ec2.describe_nat_gateways.return_value = {"NatGateways": []}

            with patch(
                "cost_toolkit.scripts.cleanup.unused_subnets._collect_used_subnets_from_rds",
                return_value=set(),
            ):
                with patch(
                    "cost_toolkit.scripts.cleanup.unused_subnets._collect_used_subnets_from_elb",
                    return_value=set(),
                ):
                    result = analyze_subnet_usage("us-east-1")

            assert len(result["unused"]) == 1
            assert len(result["used"]) == 1
            captured = capsys.readouterr()
            assert "Analyzing Subnet usage" in captured.out

    def test_analyze_with_client_error(self, capsys):
        """Test analysis with client error."""
        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2
            mock_ec2.describe_subnets.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "describe_subnets")

            result = analyze_subnet_usage("us-east-1")

            assert result == {"unused": [], "used": []}
            captured = capsys.readouterr()
            assert "Error analyzing subnets" in captured.out


class TestDeleteUnusedSecurityGroups:
    """Tests for delete_unused_security_groups function."""

    def test_delete_success(self, capsys):
        """Test successful deletion of security groups."""
        unused_sgs = [
            {"GroupId": "sg-1", "GroupName": "test-sg-1"},
            {"GroupId": "sg-2", "GroupName": "test-sg-2"},
        ]

        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2

            result = delete_unused_security_groups(unused_sgs, "us-east-1")

            assert result is True
            assert mock_ec2.delete_security_group.call_count == 2
            captured = capsys.readouterr()
            assert "Deleted: 2" in captured.out

    def test_delete_empty_list(self, capsys):
        """Test deletion with empty list."""
        result = delete_unused_security_groups([], "us-east-1")

        assert result is True
        captured = capsys.readouterr()
        assert "No unused security groups to delete" in captured.out

    def test_delete_with_partial_failure(self, capsys):
        """Test deletion with some failures."""
        unused_sgs = [
            {"GroupId": "sg-1", "GroupName": "test-sg-1"},
            {"GroupId": "sg-2", "GroupName": "test-sg-2"},
        ]

        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2
            mock_ec2.delete_security_group.side_effect = [
                None,
                ClientError({"Error": {"Code": "DependencyViolation"}}, "delete_security_group"),
            ]

            result = delete_unused_security_groups(unused_sgs, "us-east-1")

            assert result is False
            captured = capsys.readouterr()
            assert "Deleted: 1" in captured.out
            assert "Failed: 1" in captured.out

    def test_delete_with_client_error(self, capsys):
        """Test deletion with client error."""
        with patch("boto3.client") as mock_boto3:
            mock_boto3.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "create_client")

            result = delete_unused_security_groups([{"GroupId": "sg-1"}], "us-east-1")

            assert result is False
            captured = capsys.readouterr()
            assert "Error deleting security groups" in captured.out
