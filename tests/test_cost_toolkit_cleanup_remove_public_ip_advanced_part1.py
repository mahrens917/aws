"""Comprehensive tests for aws_remove_public_ip_advanced.py - Part 1."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced import (
    _create_new_eni,
    _get_instance_details,
    _replace_eni,
    _stop_instance,
)


class TestGetInstanceDetails:
    """Tests for _get_instance_details function."""

    def test_get_instance_details_running(self, capsys):
        """Test getting details for running instance."""
        mock_instance = {
            "State": {"Name": "running"},
            "PublicIpAddress": "1.2.3.4",
            "VpcId": "vpc-123",
            "SubnetId": "subnet-123",
            "SecurityGroups": [{"GroupId": "sg-123"}, {"GroupId": "sg-456"}],
            "NetworkInterfaces": [{"NetworkInterfaceId": "eni-123", "Attachment": {"AttachmentId": "attach-123"}}],
        }
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
            return_value=mock_instance,
        ):
            mock_ec2 = MagicMock()
            details = _get_instance_details(mock_ec2, "i-123", "us-east-1")
            assert details.state == "running"
            assert details.public_ip == "1.2.3.4"
            assert details.vpc_id == "vpc-123"
            assert details.subnet_id == "subnet-123"
            assert details.security_groups == ["sg-123", "sg-456"]
            assert details.current_eni_id == "eni-123"
        captured = capsys.readouterr()
        assert "Getting instance details" in captured.out

    def test_get_instance_details_stopped(self, capsys):
        """Test getting details for stopped instance."""
        mock_instance = {
            "State": {"Name": "stopped"},
            "VpcId": "vpc-123",
            "SubnetId": "subnet-123",
            "SecurityGroups": [{"GroupId": "sg-123"}],
            "NetworkInterfaces": [{"NetworkInterfaceId": "eni-456", "Attachment": {}}],
        }
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
            return_value=mock_instance,
        ):
            details = _get_instance_details(MagicMock(), "i-123", "us-east-1")
            assert details.state == "stopped"
            assert details.public_ip is None
        captured = capsys.readouterr()
        assert "stopped" in captured.out

    def test_get_instance_details_no_public_ip(self):
        """Test getting details for instance without public IP."""
        mock_instance = {
            "State": {"Name": "running"},
            "VpcId": "vpc-123",
            "SubnetId": "subnet-123",
            "SecurityGroups": [],
            "NetworkInterfaces": [{"NetworkInterfaceId": "eni-789", "Attachment": {}}],
        }
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
            return_value=mock_instance,
        ):
            details = _get_instance_details(MagicMock(), "i-123", "us-east-1")
            assert details.public_ip is None


class TestStopInstance:
    """Tests for _stop_instance function."""

    def test_stop_instance_running(self, capsys):
        """Test stopping a running instance."""
        mock_ec2 = MagicMock()
        _stop_instance(mock_ec2, "i-123", "running")
        mock_ec2.stop_instances.assert_called_once_with(InstanceIds=["i-123"])
        mock_ec2.get_waiter.assert_called_once_with("instance_stopped")
        captured = capsys.readouterr()
        assert "Stopping instance" in captured.out

    def test_stop_instance_already_stopped(self, capsys):
        """Test stopping an already stopped instance."""
        mock_ec2 = MagicMock()
        _stop_instance(mock_ec2, "i-123", "stopped")
        mock_ec2.stop_instances.assert_not_called()
        captured = capsys.readouterr()
        assert "Stopping instance" not in captured.out

    def test_stop_instance_stopping_state(self):
        """Test stopping instance in stopping state."""
        mock_ec2 = MagicMock()
        _stop_instance(mock_ec2, "i-123", "stopping")
        mock_ec2.stop_instances.assert_not_called()


class TestCreateNewEni:
    """Tests for _create_new_eni function."""

    def test_create_new_eni_success(self, capsys):
        """Test successful ENI creation."""
        mock_ec2 = MagicMock()
        mock_ec2.create_network_interface.return_value = {"NetworkInterface": {"NetworkInterfaceId": "eni-new123"}}
        with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
            eni_id = _create_new_eni(mock_ec2, "subnet-123", ["sg-123"], "i-123")
        assert eni_id == "eni-new123"
        mock_ec2.create_network_interface.assert_called_once_with(
            SubnetId="subnet-123",
            Groups=["sg-123"],
            Description="Replacement ENI for i-123 - no public IP",
        )
        captured = capsys.readouterr()
        assert "Creating new network interface" in captured.out

    def test_create_new_eni_error(self, capsys):
        """Test ENI creation with error."""
        mock_ec2 = MagicMock()
        mock_ec2.create_network_interface.side_effect = ClientError(
            {"Error": {"Code": "InvalidSubnetID.NotFound"}}, "create_network_interface"
        )
        eni_id = _create_new_eni(mock_ec2, "subnet-bad", ["sg-123"], "i-123")
        assert eni_id is None
        captured = capsys.readouterr()
        assert "Error creating new ENI" in captured.out

    def test_create_new_eni_multiple_security_groups(self):
        """Test ENI creation with multiple security groups."""
        mock_ec2 = MagicMock()
        mock_ec2.create_network_interface.return_value = {"NetworkInterface": {"NetworkInterfaceId": "eni-multi"}}
        with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
            eni_id = _create_new_eni(mock_ec2, "subnet-123", ["sg-1", "sg-2", "sg-3"], "i-456")
        assert eni_id == "eni-multi"
        call_args = mock_ec2.create_network_interface.call_args[1]
        assert call_args["Groups"] == ["sg-1", "sg-2", "sg-3"]


class TestReplaceEni:
    """Tests for _replace_eni function."""

    def test_replace_eni_success(self, capsys):
        """Test successful ENI replacement."""
        mock_ec2 = MagicMock()
        current_eni = {
            "NetworkInterfaceId": "eni-old",
            "Attachment": {"AttachmentId": "attach-123"},
        }
        with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
            result = _replace_eni(mock_ec2, "i-123", current_eni, "eni-new")
        assert result is True
        mock_ec2.detach_network_interface.assert_called_once_with(AttachmentId="attach-123", Force=True)
        mock_ec2.attach_network_interface.assert_called_once_with(NetworkInterfaceId="eni-new", InstanceId="i-123", DeviceIndex=0)
        captured = capsys.readouterr()
        assert "Detaching current network interface" in captured.out
        assert "Attaching new network interface" in captured.out

    def test_replace_eni_detach_error(self, capsys):
        """Test ENI replacement with detach error."""
        mock_ec2 = MagicMock()
        mock_ec2.detach_network_interface.side_effect = ClientError(
            {"Error": {"Code": "InvalidAttachmentID.NotFound"}}, "detach_network_interface"
        )
        current_eni = {
            "NetworkInterfaceId": "eni-old",
            "Attachment": {"AttachmentId": "attach-bad"},
        }
        result = _replace_eni(mock_ec2, "i-123", current_eni, "eni-new")
        assert result is False
        mock_ec2.attach_network_interface.assert_not_called()
        captured = capsys.readouterr()
        assert "Error detaching ENI" in captured.out

    def test_replace_eni_attach_error(self, capsys):
        """Test ENI replacement with attach error."""
        mock_ec2 = MagicMock()
        mock_ec2.attach_network_interface.side_effect = ClientError(
            {"Error": {"Code": "InvalidNetworkInterfaceID.NotFound"}},
            "attach_network_interface",
        )
        current_eni = {
            "NetworkInterfaceId": "eni-old",
            "Attachment": {"AttachmentId": "attach-123"},
        }
        with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
            result = _replace_eni(mock_ec2, "i-123", current_eni, "eni-new")
        assert result is False
        captured = capsys.readouterr()
        assert "Error attaching new ENI" in captured.out
