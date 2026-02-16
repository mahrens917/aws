"""Comprehensive tests for aws_security_group_dependencies.py - Part 1: Core Functions."""

from __future__ import annotations

from unittest.mock import MagicMock

from cost_toolkit.scripts.audit.aws_security_group_dependencies import (
    _check_inbound_rules,
    _check_outbound_rules,
    _collect_instance_deps,
    _collect_network_interface_deps,
    _collect_sg_rule_refs,
)
from tests.security_group_test_utils import sample_sg_with_reference


class TestCollectNetworkInterfaceDeps:
    """Tests for _collect_network_interface_deps function."""

    def test_collect_network_interfaces(self):
        """Test collecting network interfaces."""
        mock_client = MagicMock()
        mock_client.describe_network_interfaces.return_value = {
            "NetworkInterfaces": [
                {
                    "NetworkInterfaceId": "eni-123",
                    "Status": "in-use",
                    "Description": "Primary network interface",
                    "Attachment": {"InstanceId": "i-123"},
                    "VpcId": "vpc-123",
                    "SubnetId": "subnet-123",
                }
            ]
        }

        result = _collect_network_interface_deps(mock_client, "sg-123")

        assert len(result) == 1
        assert result[0]["interface_id"] == "eni-123"
        assert result[0]["status"] == "in-use"
        assert result[0]["description"] == "Primary network interface"
        assert result[0]["vpc_id"] == "vpc-123"

    def test_collect_network_interfaces_no_description(self):
        """Test collecting network interfaces without description."""
        mock_client = MagicMock()
        mock_client.describe_network_interfaces.return_value = {
            "NetworkInterfaces": [
                {
                    "NetworkInterfaceId": "eni-456",
                    "Status": "available",
                    "Attachment": {},
                    "VpcId": "vpc-456",
                    "SubnetId": "subnet-456",
                }
            ]
        }

        result = _collect_network_interface_deps(mock_client, "sg-456")

        assert len(result) == 1
        assert result[0]["description"] is None

    def test_collect_network_interfaces_empty(self):
        """Test collecting with no network interfaces."""
        mock_client = MagicMock()
        mock_client.describe_network_interfaces.return_value = {"NetworkInterfaces": []}

        result = _collect_network_interface_deps(mock_client, "sg-123")

        assert len(result) == 0


class TestCollectInstanceDeps:
    """Tests for _collect_instance_deps function."""

    def test_collect_instances(self):
        """Test collecting instances."""
        mock_client = MagicMock()
        mock_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-123",
                            "State": {"Name": "running"},
                            "InstanceType": "t2.micro",
                            "VpcId": "vpc-123",
                            "Tags": [{"Key": "Name", "Value": "web-server"}],
                        }
                    ]
                }
            ]
        }

        result = _collect_instance_deps(mock_client, "sg-123")

        assert len(result) == 1
        assert result[0]["instance_id"] == "i-123"
        assert result[0]["state"] == "running"
        assert result[0]["instance_type"] == "t2.micro"
        assert result[0]["name"] == "web-server"

    def test_collect_instances_unnamed(self):
        """Test collecting instances without Name tag."""
        mock_client = MagicMock()
        mock_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-456",
                            "State": {"Name": "stopped"},
                            "InstanceType": "t3.small",
                            "VpcId": "vpc-456",
                            "Tags": [{"Key": "Environment", "Value": "prod"}],
                        }
                    ]
                }
            ]
        }

        result = _collect_instance_deps(mock_client, "sg-456")

        assert len(result) == 1
        assert result[0]["name"] is None

    def test_collect_instances_multiple_reservations(self):
        """Test collecting instances across multiple reservations."""
        mock_client = MagicMock()
        mock_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-123",
                            "State": {"Name": "running"},
                            "InstanceType": "t2.micro",
                            "Tags": [],
                        }
                    ]
                },
                {
                    "Instances": [
                        {
                            "InstanceId": "i-456",
                            "State": {"Name": "running"},
                            "InstanceType": "t2.small",
                            "Tags": [],
                        }
                    ]
                },
            ]
        }

        result = _collect_instance_deps(mock_client, "sg-789")

        assert len(result) == 2


class TestCheckInboundRules:
    """Tests for _check_inbound_rules function."""

    def test_check_inbound_rules_with_reference(self):
        """Test checking inbound rules with matching group."""
        sg = sample_sg_with_reference()

        rules = _check_inbound_rules(sg, "sg-target")

        assert len(rules) == 1
        assert rules[0]["referencing_sg"] == "sg-source"
        assert rules[0]["referencing_sg_name"] == "source-sg"
        assert rules[0]["rule_type"] == "inbound"
        assert rules[0]["protocol"] == "tcp"
        assert rules[0]["port_range"] == "22-22"

    def test_check_inbound_rules_no_ports(self):
        """Test checking inbound rules without port specification."""
        sg = {
            "GroupId": "sg-source",
            "GroupName": "source-sg",
            "IpPermissions": [
                {
                    "IpProtocol": "-1",
                    "UserIdGroupPairs": [{"GroupId": "sg-target"}],
                }
            ],
        }

        rules = _check_inbound_rules(sg, "sg-target")

        assert len(rules) == 1
        assert rules[0]["port_range"] == "None-None"

    def test_check_inbound_rules_no_match(self):
        """Test checking inbound rules with no matching group."""
        sg = {
            "GroupId": "sg-source",
            "GroupName": "source-sg",
            "IpPermissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 80,
                    "ToPort": 80,
                    "UserIdGroupPairs": [{"GroupId": "sg-other"}],
                }
            ],
        }

        rules = _check_inbound_rules(sg, "sg-target")

        assert len(rules) == 0


class TestCheckOutboundRules:
    """Tests for _check_outbound_rules function."""

    def test_check_outbound_rules_with_reference(self):
        """Test checking outbound rules with matching group."""
        sg = {
            "GroupId": "sg-source",
            "GroupName": "source-sg",
            "IpPermissionsEgress": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "UserIdGroupPairs": [{"GroupId": "sg-target"}],
                }
            ],
        }

        rules = _check_outbound_rules(sg, "sg-target")

        assert len(rules) == 1
        assert rules[0]["rule_type"] == "outbound"
        assert rules[0]["protocol"] == "tcp"

    def test_check_outbound_rules_no_match(self):
        """Test checking outbound rules with no matching group."""
        sg = {
            "GroupId": "sg-source",
            "GroupName": "source-sg",
            "IpPermissionsEgress": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "UserIdGroupPairs": [{"GroupId": "sg-other"}],
                }
            ],
        }

        rules = _check_outbound_rules(sg, "sg-target")

        assert len(rules) == 0


class TestCollectSgRuleRefs:
    """Tests for _collect_sg_rule_refs function."""

    def test_collect_sg_rule_refs_success(self):
        """Test collecting security group rule references."""
        mock_client = MagicMock()
        mock_client.describe_security_groups.return_value = {
            "SecurityGroups": [
                {
                    "GroupId": "sg-target",
                    "GroupName": "target-sg",
                    "IpPermissions": [],
                    "IpPermissionsEgress": [],
                },
                {**sample_sg_with_reference(), "IpPermissionsEgress": []},
            ]
        }

        rules = _collect_sg_rule_refs(mock_client, "sg-target")

        assert len(rules) == 1
        assert rules[0]["referencing_sg"] == "sg-source"

    def test_collect_sg_rule_refs_skips_self(self):
        """Test that function skips the target group itself."""
        mock_client = MagicMock()
        mock_client.describe_security_groups.return_value = {
            "SecurityGroups": [
                {
                    "GroupId": "sg-target",
                    "GroupName": "target-sg",
                    "IpPermissions": [
                        {
                            "IpProtocol": "tcp",
                            "UserIdGroupPairs": [{"GroupId": "sg-target"}],
                        }
                    ],
                    "IpPermissionsEgress": [],
                }
            ]
        }

        rules = _collect_sg_rule_refs(mock_client, "sg-target")

        assert len(rules) == 0
