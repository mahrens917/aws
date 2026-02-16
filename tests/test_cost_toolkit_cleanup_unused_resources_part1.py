"""Comprehensive tests for aws_cleanup_unused_resources.py - Part 1."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.cleanup.unused_security_groups import (
    _categorize_security_groups,
    _collect_used_sgs_from_elb,
    _collect_used_sgs_from_enis,
    _collect_used_sgs_from_instances,
    _collect_used_sgs_from_rds,
)
from cost_toolkit.scripts.cleanup.unused_subnets import (
    _collect_used_subnets_from_enis,
    _collect_used_subnets_from_instances,
)


class TestCollectUsedSgsFromInstances:
    """Tests for _collect_used_sgs_from_instances function."""

    def test_collect_from_running_instances(self):
        """Test collecting SGs from running instances."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "State": {"Name": "running"},
                            "SecurityGroups": [{"GroupId": "sg-123"}, {"GroupId": "sg-456"}],
                        }
                    ]
                }
            ]
        }

        result = _collect_used_sgs_from_instances(mock_ec2)

        assert result == {"sg-123", "sg-456"}
        mock_ec2.describe_instances.assert_called_once()

    def test_collect_excludes_terminated_instances(self):
        """Test that terminated instances are excluded."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "State": {"Name": "terminated"},
                            "SecurityGroups": [{"GroupId": "sg-123"}],
                        },
                        {
                            "State": {"Name": "running"},
                            "SecurityGroups": [{"GroupId": "sg-456"}],
                        },
                    ]
                }
            ]
        }

        result = _collect_used_sgs_from_instances(mock_ec2)

        assert result == {"sg-456"}

    def test_collect_from_empty_response(self):
        """Test collecting from empty reservations."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {"Reservations": []}

        result = _collect_used_sgs_from_instances(mock_ec2)

        assert result == set()

    def test_collect_from_instances_without_sgs(self):
        """Test collecting from instances without SGs."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {"Reservations": [{"Instances": [{"State": {"Name": "running"}}]}]}

        result = _collect_used_sgs_from_instances(mock_ec2)

        assert result == set()


class TestCollectUsedSgsFromEnis:
    """Tests for _collect_used_sgs_from_enis function."""

    def test_collect_from_enis(self):
        """Test collecting SGs from network interfaces."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_network_interfaces.return_value = {
            "NetworkInterfaces": [
                {"Groups": [{"GroupId": "sg-111"}, {"GroupId": "sg-222"}]},
                {"Groups": [{"GroupId": "sg-333"}]},
            ]
        }

        result = _collect_used_sgs_from_enis(mock_ec2)

        assert result == {"sg-111", "sg-222", "sg-333"}
        mock_ec2.describe_network_interfaces.assert_called_once()

    def test_collect_from_empty_enis(self):
        """Test collecting from empty ENI response."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_network_interfaces.return_value = {}

        result = _collect_used_sgs_from_enis(mock_ec2)

        assert result == set()

    def test_collect_from_enis_without_groups(self):
        """Test collecting from ENIs without groups."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_network_interfaces.return_value = {"NetworkInterfaces": [{}]}

        result = _collect_used_sgs_from_enis(mock_ec2)

        assert result == set()


class TestCollectUsedSgsFromRds:
    """Tests for _collect_used_sgs_from_rds function."""

    def test_collect_from_rds_instances(self):
        """Test collecting SGs from RDS instances."""
        with patch("boto3.client") as mock_boto3:
            mock_rds = MagicMock()
            mock_boto3.return_value = mock_rds
            mock_rds.describe_db_instances.return_value = {
                "DBInstances": [
                    {
                        "VpcSecurityGroups": [
                            {"VpcSecurityGroupId": "sg-rds1"},
                            {"VpcSecurityGroupId": "sg-rds2"},
                        ]
                    },
                    {"VpcSecurityGroups": [{"VpcSecurityGroupId": "sg-rds3"}]},
                ]
            }

            result = _collect_used_sgs_from_rds("us-east-1")

            assert result == {"sg-rds1", "sg-rds2", "sg-rds3"}
            mock_boto3.assert_called_once_with("rds", region_name="us-east-1")

    def test_collect_from_rds_with_error(self, capsys):
        """Test error handling when checking RDS."""
        with patch("boto3.client") as mock_boto3:
            mock_rds = MagicMock()
            mock_boto3.return_value = mock_rds
            mock_rds.describe_db_instances.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "describe_db_instances")

            result = _collect_used_sgs_from_rds("us-east-1")

            assert result == set()
            captured = capsys.readouterr()
            assert "Warning: Could not check RDS security groups" in captured.out

    def test_collect_from_rds_empty_response(self):
        """Test collecting from empty RDS response."""
        with patch("boto3.client") as mock_boto3:
            mock_rds = MagicMock()
            mock_boto3.return_value = mock_rds
            mock_rds.describe_db_instances.return_value = {}

            result = _collect_used_sgs_from_rds("us-east-1")

            assert result == set()


class TestCollectUsedSgsFromElb:
    """Tests for _collect_used_sgs_from_elb function."""

    def test_collect_from_load_balancers(self):
        """Test collecting SGs from load balancers."""
        with patch("boto3.client") as mock_boto3:
            mock_elbv2 = MagicMock()
            mock_boto3.return_value = mock_elbv2
            mock_elbv2.describe_load_balancers.return_value = {
                "LoadBalancers": [
                    {"SecurityGroups": ["sg-lb1", "sg-lb2"]},
                    {"SecurityGroups": ["sg-lb3"]},
                ]
            }

            result = _collect_used_sgs_from_elb("us-east-1")

            assert result == {"sg-lb1", "sg-lb2", "sg-lb3"}

    def test_collect_from_elb_with_error(self, capsys):
        """Test error handling when checking ELB."""
        with patch("boto3.client") as mock_boto3:
            mock_elbv2 = MagicMock()
            mock_boto3.return_value = mock_elbv2
            mock_elbv2.describe_load_balancers.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "describe_load_balancers")

            result = _collect_used_sgs_from_elb("us-east-1")

            assert result == set()
            captured = capsys.readouterr()
            assert "Warning: Could not check ELB security groups" in captured.out

    def test_collect_from_elb_empty_response(self):
        """Test collecting from empty ELB response."""
        with patch("boto3.client") as mock_boto3:
            mock_elbv2 = MagicMock()
            mock_boto3.return_value = mock_elbv2
            mock_elbv2.describe_load_balancers.return_value = {}

            result = _collect_used_sgs_from_elb("us-east-1")

            assert result == set()


class TestCategorizeSecurityGroups:
    """Tests for _categorize_security_groups function."""

    def test_categorize_all_types(self):
        """Test categorizing default, used, and unused SGs."""
        all_sgs = [
            {"GroupId": "sg-default", "GroupName": "default"},
            {"GroupId": "sg-used", "GroupName": "used-sg"},
            {"GroupId": "sg-unused", "GroupName": "unused-sg"},
        ]
        used_sgs = {"sg-used"}

        unused, used, default = _categorize_security_groups(all_sgs, used_sgs)

        assert len(default) == 1
        assert default[0]["GroupId"] == "sg-default"
        assert len(used) == 1
        assert used[0]["GroupId"] == "sg-used"
        assert len(unused) == 1
        assert unused[0]["GroupId"] == "sg-unused"

    def test_categorize_all_used(self):
        """Test when all SGs are used."""
        all_sgs = [
            {"GroupId": "sg-1", "GroupName": "sg1"},
            {"GroupId": "sg-2", "GroupName": "sg2"},
        ]
        used_sgs = {"sg-1", "sg-2"}

        unused, used, default = _categorize_security_groups(all_sgs, used_sgs)

        assert len(unused) == 0
        assert len(used) == 2
        assert len(default) == 0

    def test_categorize_empty_input(self):
        """Test with empty input."""
        unused, used, default = _categorize_security_groups([], set())

        assert len(unused) == 0
        assert len(used) == 0
        assert len(default) == 0


class TestCollectUsedSubnetsFromInstances:
    """Tests for _collect_used_subnets_from_instances function."""

    def test_collect_from_instances(self):
        """Test collecting subnets from instances."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {"State": {"Name": "running"}, "SubnetId": "subnet-1"},
                        {"State": {"Name": "stopped"}, "SubnetId": "subnet-2"},
                    ]
                }
            ]
        }

        result = _collect_used_subnets_from_instances(mock_ec2)

        assert result == {"subnet-1", "subnet-2"}

    def test_collect_excludes_terminated(self):
        """Test that terminated instances are excluded."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {"State": {"Name": "terminated"}, "SubnetId": "subnet-1"},
                        {"State": {"Name": "running"}, "SubnetId": "subnet-2"},
                    ]
                }
            ]
        }

        result = _collect_used_subnets_from_instances(mock_ec2)

        assert result == {"subnet-2"}


class TestCollectUsedSubnetsFromEnis:
    """Tests for _collect_used_subnets_from_enis function."""

    def test_collect_from_enis(self):
        """Test collecting subnets from ENIs."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_network_interfaces.return_value = {"NetworkInterfaces": [{"SubnetId": "subnet-a"}, {"SubnetId": "subnet-b"}]}

        result = _collect_used_subnets_from_enis(mock_ec2)

        assert result == {"subnet-a", "subnet-b"}

    def test_collect_from_empty_enis(self):
        """Test with empty ENI response."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_network_interfaces.return_value = {}

        result = _collect_used_subnets_from_enis(mock_ec2)

        assert result == set()
