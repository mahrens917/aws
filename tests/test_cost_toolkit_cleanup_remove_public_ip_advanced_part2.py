"""Comprehensive tests for aws_remove_public_ip_advanced.py - Part 2."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced import (
    _verify_and_cleanup,
    main,
    remove_public_ip_by_network_interface_replacement,
    simple_stop_start_without_public_ip,
)


def test_verify_and_cleanup_success(capsys):
    """Test successful verification and cleanup."""
    mock_ec2 = MagicMock()
    mock_instance = {"State": {"Name": "running"}}
    with patch(
        "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
        return_value=mock_instance,
    ):
        with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
            result = _verify_and_cleanup(mock_ec2, "i-123", "eni-old", "us-east-1")
    assert result is True
    mock_ec2.delete_network_interface.assert_called_once_with(NetworkInterfaceId="eni-old")
    captured = capsys.readouterr()
    assert "Public IP successfully removed" in captured.out


def test_verify_and_cleanup_still_has_public_ip(capsys):
    """Test verification when public IP still exists."""
    mock_ec2 = MagicMock()
    mock_instance = {"State": {"Name": "running"}, "PublicIpAddress": "1.2.3.4"}
    with patch(
        "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
        return_value=mock_instance,
    ):
        with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
            result = _verify_and_cleanup(mock_ec2, "i-123", "eni-old", "us-east-1")
    assert result is False
    captured = capsys.readouterr()
    assert "still has public IP" in captured.out


def test_verify_and_cleanup_eni_deletion_error(capsys):
    """Test cleanup when ENI deletion fails."""
    mock_ec2 = MagicMock()
    mock_ec2.delete_network_interface.side_effect = ClientError(
        {"Error": {"Code": "InvalidNetworkInterfaceID.NotFound"}},
        "delete_network_interface",
    )
    mock_instance = {"State": {"Name": "running"}}
    with patch(
        "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
        return_value=mock_instance,
    ):
        with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
            result = _verify_and_cleanup(mock_ec2, "i-123", "eni-old", "us-east-1")
    assert result is True  # Still succeeds even if ENI cleanup fails
    captured = capsys.readouterr()
    assert "Could not delete old ENI" in captured.out


def test_remove_public_ip_already_removed(capsys):
    """Test when instance already has no public IP."""
    mock_instance = {
        "State": {"Name": "running"},
        "VpcId": "vpc-123",
        "SubnetId": "subnet-123",
        "SecurityGroups": [{"GroupId": "sg-123"}],
        "NetworkInterfaces": [{"NetworkInterfaceId": "eni-123", "Attachment": {}}],
    }
    with patch(
        "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
        return_value=mock_instance,
    ):
        with patch("boto3.client"):
            result = remove_public_ip_by_network_interface_replacement("i-123", "us-east-1")
    assert result is True
    captured = capsys.readouterr()
    assert "already has no public IP" in captured.out


class TestNetworkInterfaceReplacementErrors:
    """Error cases for remove_public_ip_by_network_interface_replacement function."""

    def test_remove_public_ip_eni_creation_fails(self):
        """Test when ENI creation fails."""
        mock_instance = {
            "State": {"Name": "running"},
            "PublicIpAddress": "1.2.3.4",
            "VpcId": "vpc-123",
            "SubnetId": "subnet-123",
            "SecurityGroups": [{"GroupId": "sg-123"}],
            "NetworkInterfaces": [{"NetworkInterfaceId": "eni-123", "Attachment": {}}],
        }
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
            return_value=mock_instance,
        ):
            with patch("boto3.client") as mock_client:
                mock_ec2 = MagicMock()
                mock_ec2.create_network_interface.side_effect = ClientError(
                    {"Error": {"Code": "InvalidSubnetID"}}, "create_network_interface"
                )
                mock_client.return_value = mock_ec2
                result = remove_public_ip_by_network_interface_replacement("i-123", "us-east-1")
        assert result is False

    def test_remove_public_ip_replace_eni_fails(self):
        """Test when ENI replacement fails."""
        mock_instance = {
            "State": {"Name": "running"},
            "PublicIpAddress": "1.2.3.4",
            "VpcId": "vpc-123",
            "SubnetId": "subnet-123",
            "SecurityGroups": [{"GroupId": "sg-123"}],
            "NetworkInterfaces": [{"NetworkInterfaceId": "eni-old", "Attachment": {"AttachmentId": "attach-123"}}],
        }
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
            return_value=mock_instance,
        ):
            with patch("boto3.client") as mock_client:
                mock_ec2 = MagicMock()
                mock_ec2.create_network_interface.return_value = {"NetworkInterface": {"NetworkInterfaceId": "eni-new"}}
                mock_ec2.detach_network_interface.side_effect = ClientError(
                    {"Error": {"Code": "InvalidAttachmentID"}}, "detach_network_interface"
                )
                mock_client.return_value = mock_ec2
                with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
                    result = remove_public_ip_by_network_interface_replacement("i-123", "us-east-1")
        assert result is False

    def test_remove_public_ip_start_instance_fails(self, capsys):
        """Test when starting instance fails."""
        mock_instance = {
            "State": {"Name": "running"},
            "PublicIpAddress": "1.2.3.4",
            "VpcId": "vpc-123",
            "SubnetId": "subnet-123",
            "SecurityGroups": [{"GroupId": "sg-123"}],
            "NetworkInterfaces": [{"NetworkInterfaceId": "eni-old", "Attachment": {"AttachmentId": "attach-123"}}],
        }
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
            return_value=mock_instance,
        ):
            with patch("boto3.client") as mock_client:
                mock_ec2 = MagicMock()
                mock_ec2.create_network_interface.return_value = {"NetworkInterface": {"NetworkInterfaceId": "eni-new"}}
                mock_ec2.start_instances.side_effect = ClientError({"Error": {"Code": "IncorrectInstanceState"}}, "start_instances")
                mock_client.return_value = mock_ec2
                with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
                    result = remove_public_ip_by_network_interface_replacement("i-123", "us-east-1")
        assert result is False
        captured = capsys.readouterr()
        assert "Error starting instance" in captured.out


class TestSimpleStopStartWithoutPublicIp:
    """Tests for simple_stop_start_without_public_ip function."""

    def test_simple_stop_start_success(self, capsys):
        """Test successful simple stop/start method."""
        mock_instance_before = {
            "State": {"Name": "running"},
            "SubnetId": "subnet-123",
            "PublicIpAddress": "1.2.3.4",
        }
        mock_instance_after = {"State": {"Name": "running"}, "SubnetId": "subnet-123"}
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
            side_effect=[mock_instance_before, mock_instance_after],
        ):
            with patch("boto3.client") as mock_client:
                mock_ec2 = MagicMock()
                mock_client.return_value = mock_ec2
                with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
                    result = simple_stop_start_without_public_ip("i-123", "us-east-1")
        assert result is True
        mock_ec2.modify_subnet_attribute.assert_called_once()
        captured = capsys.readouterr()
        assert "Public IP successfully removed" in captured.out

    def test_simple_stop_start_still_has_public_ip(self, capsys):
        """Test when instance still has public IP after restart."""
        mock_instance = {
            "State": {"Name": "running"},
            "SubnetId": "subnet-123",
            "PublicIpAddress": "1.2.3.4",
        }
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
            return_value=mock_instance,
        ):
            with patch("boto3.client") as mock_client:
                mock_ec2 = MagicMock()
                mock_client.return_value = mock_ec2
                with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
                    result = simple_stop_start_without_public_ip("i-123", "us-east-1")
        assert result is False
        captured = capsys.readouterr()
        assert "still has public IP" in captured.out

    def test_simple_stop_start_error(self, capsys):
        """Test simple method with error."""
        mock_instance = {"State": {"Name": "running"}, "SubnetId": "subnet-123"}
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.get_instance_info",
            return_value=mock_instance,
        ):
            with patch("boto3.client") as mock_client:
                mock_ec2 = MagicMock()
                mock_ec2.stop_instances.side_effect = ClientError({"Error": {"Code": "IncorrectInstanceState"}}, "stop_instances")
                mock_client.return_value = mock_ec2
                result = simple_stop_start_without_public_ip("i-123", "us-east-1")
        assert result is False
        captured = capsys.readouterr()
        assert "Error in simple public IP removal" in captured.out


class TestMain:
    """Tests for main function."""

    def test_main_simple_method_success(self, capsys):
        """Test main when simple method succeeds."""
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.simple_stop_start_without_public_ip",
            return_value=True,
        ):
            main()
        captured = capsys.readouterr()
        assert "Successfully removed public IP" in captured.out

    def test_main_simple_fails_advanced_succeeds(self, capsys):
        """Test main when simple fails but advanced succeeds."""
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.simple_stop_start_without_public_ip",
            return_value=False,
        ):
            with patch(
                "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.remove_public_ip_by_network_interface_replacement",
                return_value=True,
            ):
                main()
        captured = capsys.readouterr()
        assert "ATTEMPTING ADVANCED METHOD" in captured.out
        assert "Successfully removed public IP" in captured.out

    def test_main_both_methods_fail(self, capsys):
        """Test main when both methods fail."""
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.simple_stop_start_without_public_ip",
            return_value=False,
        ):
            with patch(
                "cost_toolkit.scripts.cleanup.aws_remove_public_ip_advanced.remove_public_ip_by_network_interface_replacement",
                return_value=False,
            ):
                main()
        captured = capsys.readouterr()
        assert "Failed to remove public IP" in captured.out
        assert "manual intervention" in captured.out
