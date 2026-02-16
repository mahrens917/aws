"""Comprehensive tests for aws_network_interface_deep_audit.py - Part 2."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.audit.aws_network_interface_deep_audit import (
    _check_detached_eni,
    _check_instance_attachment,
    investigate_network_interface,
)


class TestCheckInstanceAttachmentOrphanedStates:
    """Tests for _check_instance_attachment with orphaned instance states."""

    def test_check_attachment_instance_terminated(self, capsys):
        """Test attachment check with terminated instance."""
        ec2 = MagicMock()
        ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "State": {"Name": "terminated"},
                            "InstanceType": "t2.small",
                        }
                    ]
                }
            ]
        }

        attachment = {
            "InstanceId": "i-terminated",
            "Status": "attached",
            "AttachTime": "2024-01-01T00:00:00Z",
        }

        result = _check_instance_attachment(ec2, attachment)

        assert result == "orphaned"
        captured = capsys.readouterr()
        assert "Instance is terminated - ENI may be orphaned" in captured.out

    def test_check_attachment_instance_shutting_down(self, capsys):
        """Test attachment check with shutting-down instance."""
        ec2 = MagicMock()
        ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "State": {"Name": "shutting-down"},
                            "InstanceType": "t2.medium",
                        }
                    ]
                }
            ]
        }

        attachment = {
            "InstanceId": "i-shutting-down",
            "Status": "attached",
            "AttachTime": "2024-01-01T00:00:00Z",
        }

        result = _check_instance_attachment(ec2, attachment)

        assert result == "orphaned"
        captured = capsys.readouterr()
        assert "Instance is shutting-down - ENI may be orphaned" in captured.out

    def test_check_attachment_instance_not_found(self, capsys):
        """Test attachment check with non-existent instance."""
        ec2 = MagicMock()
        ec2.exceptions.ClientError = ClientError
        ec2.describe_instances.side_effect = ClientError(
            {"Error": {"Code": "InvalidInstanceID.NotFound", "Message": "Not found"}},
            "DescribeInstances",
        )

        attachment = {
            "InstanceId": "i-nonexistent",
            "Status": "attached",
            "AttachTime": "2024-01-01T00:00:00Z",
        }

        result = _check_instance_attachment(ec2, attachment)

        assert result == "orphaned"
        captured = capsys.readouterr()
        assert "Instance i-nonexistent does not exist - ENI is orphaned!" in captured.out


class TestCheckInstanceAttachmentStoppedAndErrors:
    """Tests for _check_instance_attachment with stopped instances and errors."""

    def test_check_attachment_instance_stopped(self, capsys):
        """Test attachment check with stopped instance."""
        ec2 = MagicMock()
        ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "State": {"Name": "stopped"},
                            "InstanceType": "t2.large",
                        }
                    ]
                }
            ]
        }

        attachment = {
            "InstanceId": "i-stopped",
            "Status": "attached",
            "AttachTime": "2024-01-01T00:00:00Z",
        }

        result = _check_instance_attachment(ec2, attachment)

        assert result == "attached_stopped"
        captured = capsys.readouterr()
        assert "Instance is stopped - ENI attached to stopped instance" in captured.out

    def test_check_attachment_instance_stopping(self, capsys):
        """Test attachment check with stopping instance."""
        ec2 = MagicMock()
        ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "State": {"Name": "stopping"},
                            "InstanceType": "m5.xlarge",
                        }
                    ]
                }
            ]
        }

        attachment = {
            "InstanceId": "i-stopping",
            "Status": "attached",
            "AttachTime": "2024-01-01T00:00:00Z",
        }

        result = _check_instance_attachment(ec2, attachment)

        assert result == "attached_stopped"
        captured = capsys.readouterr()
        assert "Instance is stopping - ENI attached to stopped instance" in captured.out

    def test_check_attachment_other_client_error(self, capsys):
        """Test attachment check with other ClientError."""
        ec2 = MagicMock()
        ec2.exceptions.ClientError = ClientError
        ec2.describe_instances.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            "DescribeInstances",
        )

        attachment = {
            "InstanceId": "i-denied",
            "Status": "attached",
            "AttachTime": "2024-01-01T00:00:00Z",
        }

        result = _check_instance_attachment(ec2, attachment)

        assert result == "error"
        captured = capsys.readouterr()
        assert "Error checking instance:" in captured.out


class TestCheckDetachedEni:
    """Tests for _check_detached_eni function."""

    def test_check_detached_eni_standard_interface(self, capsys):
        """Test checking detached standard interface."""
        eni = {
            "InterfaceType": "interface",
        }

        result = _check_detached_eni(eni)

        assert result == "detached"
        captured = capsys.readouterr()
        assert "No attachment information - likely detached" in captured.out

    def test_check_detached_eni_special_interface_type(self, capsys):
        """Test checking detached special interface type."""
        eni = {
            "InterfaceType": "nat_gateway",
        }

        result = _check_detached_eni(eni)

        assert result == "aws_service"
        captured = capsys.readouterr()
        assert "Special interface type: nat_gateway" in captured.out

    def test_check_detached_eni_with_eip(self, capsys):
        """Test checking detached ENI with Elastic IP."""
        eni = {
            "InterfaceType": "interface",
            "Association": {
                "PublicIp": "1.2.3.4",
                "AllocationId": "eipalloc-123456",
            },
        }

        result = _check_detached_eni(eni)

        assert result == "eip_attached"
        captured = capsys.readouterr()
        assert "Public IP: 1.2.3.4" in captured.out
        assert "EIP Allocation: eipalloc-123456" in captured.out

    def test_check_detached_eni_missing_interface_type(self, capsys):
        """Test checking detached ENI with missing interface type."""
        eni = {}

        result = _check_detached_eni(eni)

        assert result == "aws_service"
        captured = capsys.readouterr()
        assert "No attachment information - likely detached" in captured.out

    def test_check_detached_eni_empty_association(self, capsys):  # pylint: disable=unused-argument
        """Test checking detached ENI with empty association."""
        eni = {
            "InterfaceType": "interface",
            "Association": {},
        }

        result = _check_detached_eni(eni)

        assert result == "detached"

    def test_check_detached_eni_network_load_balancer(self, capsys):
        """Test checking detached ENI for network load balancer."""
        eni = {
            "InterfaceType": "network_load_balancer",
        }

        result = _check_detached_eni(eni)

        assert result == "aws_service"
        captured = capsys.readouterr()
        assert "Special interface type: network_load_balancer" in captured.out

    def test_check_detached_eni_lambda_interface(self, capsys):
        """Test checking detached ENI for Lambda."""
        eni = {
            "InterfaceType": "lambda",
        }

        result = _check_detached_eni(eni)

        assert result == "aws_service"
        captured = capsys.readouterr()
        assert "Special interface type: lambda" in captured.out


class TestInvestigateNetworkInterfaceRunningInstances:  # pylint: disable=too-few-public-methods
    """Tests for investigate_network_interface with running instances."""

    def test_investigate_interface_with_running_instance(self, capsys):
        """Test investigating interface attached to running instance."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_network_interfaces.return_value = {
            "NetworkInterfaces": [
                {
                    "Status": "in-use",
                    "InterfaceType": "interface",
                    "Description": "Primary interface",
                    "VpcId": "vpc-123",
                    "SubnetId": "subnet-456",
                    "Attachment": {
                        "InstanceId": "i-running",
                        "Status": "attached",
                        "AttachTime": "2024-01-01T00:00:00Z",
                    },
                }
            ]
        }
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "State": {"Name": "running"},
                            "InstanceType": "t2.micro",
                        }
                    ]
                }
            ]
        }

        with patch("cost_toolkit.scripts.audit.aws_network_interface_deep_audit.boto3.client") as mock_client:
            mock_client.return_value = mock_ec2
            result = investigate_network_interface(
                "us-east-1",
                "eni-12345",
                "test-key",
                "test-secret",
            )

        assert result == "active"
        captured = capsys.readouterr()
        assert "Deep Analysis: eni-12345" in captured.out
        assert "Status: in-use" in captured.out
        assert "Instance is active" in captured.out

        mock_client.assert_called_once_with(
            "ec2",
            region_name="us-east-1",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
        )
        mock_ec2.describe_network_interfaces.assert_called_once_with(NetworkInterfaceIds=["eni-12345"])


class TestInvestigateNetworkInterfaceDetached:
    """Tests for investigate_network_interface with detached interfaces."""

    def test_investigate_interface_detached(self, capsys):
        """Test investigating detached interface."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_network_interfaces.return_value = {
            "NetworkInterfaces": [
                {
                    "Status": "available",
                    "InterfaceType": "interface",
                    "Description": "Detached interface",
                    "VpcId": "vpc-123",
                    "SubnetId": "subnet-456",
                }
            ]
        }

        with patch("cost_toolkit.scripts.audit.aws_network_interface_deep_audit.boto3.client") as mock_client:
            mock_client.return_value = mock_ec2
            result = investigate_network_interface(
                "us-east-1",
                "eni-detached",
                "test-key",
                "test-secret",
            )

        assert result == "detached"
        captured = capsys.readouterr()
        assert "Deep Analysis: eni-detached" in captured.out
        assert "No attachment information - likely detached" in captured.out

    def test_investigate_interface_with_eip(self, capsys):
        """Test investigating detached interface with Elastic IP."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_network_interfaces.return_value = {
            "NetworkInterfaces": [
                {
                    "Status": "available",
                    "InterfaceType": "interface",
                    "Description": "Interface with EIP",
                    "VpcId": "vpc-123",
                    "SubnetId": "subnet-456",
                    "Association": {
                        "PublicIp": "54.210.123.45",
                        "AllocationId": "eipalloc-abc123",
                    },
                }
            ]
        }

        with patch("cost_toolkit.scripts.audit.aws_network_interface_deep_audit.boto3.client") as mock_client:
            mock_client.return_value = mock_ec2
            result = investigate_network_interface(
                "us-east-1",
                "eni-with-eip",
                "test-key",
                "test-secret",
            )

        assert result == "eip_attached"
        captured = capsys.readouterr()
        assert "Public IP: 54.210.123.45" in captured.out
        assert "EIP Allocation: eipalloc-abc123" in captured.out
