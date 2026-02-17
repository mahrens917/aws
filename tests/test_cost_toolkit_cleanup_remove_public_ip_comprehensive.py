"""Comprehensive tests for aws_remove_public_ip.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.scripts.cleanup.aws_remove_public_ip import (
    get_instance_network_info,
    main,
    modify_network_interface,
    remove_public_ip_from_instance,
    retry_with_subnet_modification,
    start_instance,
    stop_instance_if_running,
    verify_public_ip_removed,
)


class TestGetInstanceNetworkInfo:
    """Tests for get_instance_network_info function."""

    def test_get_instance_network_info_running_with_public_ip(self, capsys):
        """Test getting details for running instance with public IP."""
        mock_instance = {
            "State": {"Name": "running"},
            "PublicIpAddress": "1.2.3.4",
            "NetworkInterfaces": [{"NetworkInterfaceId": "eni-123"}],
        }
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip.get_instance_info",
            return_value=mock_instance,
        ):
            _instance, state, public_ip, eni_id = get_instance_network_info("i-123", "us-east-1")
        assert state == "running"
        assert public_ip == "1.2.3.4"
        assert eni_id == "eni-123"
        captured = capsys.readouterr()
        assert "Getting instance details" in captured.out

    def test_get_instance_network_info_stopped(self):
        """Test getting details for stopped instance."""
        mock_instance = {
            "State": {"Name": "stopped"},
            "NetworkInterfaces": [{"NetworkInterfaceId": "eni-456"}],
        }
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip.get_instance_info",
            return_value=mock_instance,
        ):
            _instance, state, public_ip, eni_id = get_instance_network_info("i-456", "us-west-2")
        assert state == "stopped"
        assert public_ip is None
        assert eni_id == "eni-456"


class TestStopInstanceIfRunning:
    """Tests for stop_instance_if_running function."""

    def test_stop_running_instance(self, capsys):
        """Test stopping a running instance."""
        mock_ec2 = MagicMock()
        stop_instance_if_running(mock_ec2, "i-123", "running")
        mock_ec2.stop_instances.assert_called_once_with(InstanceIds=["i-123"])
        mock_ec2.get_waiter.assert_called_once_with("instance_stopped")
        captured = capsys.readouterr()
        assert "Stopping instance" in captured.out

    def test_stop_already_stopped_instance(self, capsys):
        """Test stopping an already stopped instance."""
        mock_ec2 = MagicMock()
        stop_instance_if_running(mock_ec2, "i-123", "stopped")
        mock_ec2.stop_instances.assert_not_called()
        captured = capsys.readouterr()
        assert "already stopped" in captured.out

    def test_stop_instance_other_state(self):
        """Test instance in other states."""
        mock_ec2 = MagicMock()
        stop_instance_if_running(mock_ec2, "i-123", "stopping")
        mock_ec2.stop_instances.assert_not_called()


class TestModifyNetworkInterface:
    """Tests for modify_network_interface function."""

    def test_modify_network_interface_success(self, capsys):
        """Test successful network interface modification."""
        mock_ec2 = MagicMock()
        modify_network_interface(mock_ec2, "i-123", "eni-123")
        mock_ec2.modify_network_interface_attribute.assert_called_once()
        mock_ec2.modify_instance_attribute.assert_called_once()
        captured = capsys.readouterr()
        assert "Network interface modified" in captured.out

    def test_modify_network_interface_error(self, capsys):
        """Test network interface modification with error."""
        mock_ec2 = MagicMock()
        mock_ec2.modify_network_interface_attribute.side_effect = ClientError(
            {"Error": {"Code": "InvalidNetworkInterfaceID"}},
            "modify_network_interface_attribute",
        )
        with pytest.raises(ClientError):
            modify_network_interface(mock_ec2, "i-123", "eni-invalid")
        captured = capsys.readouterr()
        assert "Network interface modification" in captured.out


def test_start_instance_success(capsys):
    """Test successful instance start."""
    mock_ec2 = MagicMock()
    start_instance(mock_ec2, "i-123")
    mock_ec2.start_instances.assert_called_once_with(InstanceIds=["i-123"])
    mock_ec2.get_waiter.assert_called_once_with("instance_running")
    captured = capsys.readouterr()
    assert "Starting instance" in captured.out


class TestRetryWithSubnetModification:
    """Tests for retry_with_subnet_modification function."""

    def test_retry_success(self, capsys):
        """Test successful retry with subnet modification."""
        mock_ec2 = MagicMock()
        mock_instance_final = {"State": {"Name": "running"}}
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip.get_instance_info",
            return_value=mock_instance_final,
        ):
            with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
                result = retry_with_subnet_modification(mock_ec2, "i-123", "subnet-123", "us-east-1")
        assert result is True
        mock_ec2.modify_subnet_attribute.assert_called_once()
        captured = capsys.readouterr()
        assert "Public IP successfully removed" in captured.out

    def test_retry_still_has_public_ip(self, capsys):
        """Test retry when public IP persists."""
        mock_ec2 = MagicMock()
        mock_instance_final = {"State": {"Name": "running"}, "PublicIpAddress": "1.2.3.4"}
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip.get_instance_info",
            return_value=mock_instance_final,
        ):
            with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
                result = retry_with_subnet_modification(mock_ec2, "i-123", "subnet-123", "us-east-1")
        assert result is False
        captured = capsys.readouterr()
        assert "still has public IP" in captured.out

    def test_retry_subnet_modification_error(self, capsys):
        """Test retry when subnet modification fails."""
        mock_ec2 = MagicMock()
        mock_ec2.modify_subnet_attribute.side_effect = ClientError({"Error": {"Code": "InvalidSubnetID"}}, "modify_subnet_attribute")
        result = retry_with_subnet_modification(mock_ec2, "i-123", "subnet-bad", "us-east-1")
        assert result is False
        captured = capsys.readouterr()
        assert "Error modifying subnet" in captured.out


class TestVerifyPublicIpRemoved:
    """Tests for verify_public_ip_removed function."""

    def test_verify_public_ip_removed_success(self, capsys):
        """Test verification when public IP is removed."""
        mock_ec2 = MagicMock()
        mock_instance = {"State": {"Name": "running"}, "SubnetId": "subnet-123"}
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip.get_instance_info",
            return_value=mock_instance,
        ):
            with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
                result = verify_public_ip_removed(mock_ec2, "i-123", "us-east-1")
        assert result is True
        captured = capsys.readouterr()
        assert "Public IP successfully removed" in captured.out

    def test_verify_public_ip_still_exists_retry_success(self):
        """Test verification with retry when public IP still exists."""
        mock_ec2 = MagicMock()
        mock_instance_first = {
            "State": {"Name": "running"},
            "PublicIpAddress": "1.2.3.4",
            "SubnetId": "subnet-123",
        }
        mock_instance_final = {"State": {"Name": "running"}, "SubnetId": "subnet-123"}
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip.get_instance_info",
            side_effect=[mock_instance_first, mock_instance_final],
        ):
            with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
                result = verify_public_ip_removed(mock_ec2, "i-123", "us-east-1")
        assert result is True
        mock_ec2.modify_subnet_attribute.assert_called_once()


class TestRemovePublicIpFromInstance:
    """Tests for remove_public_ip_from_instance function."""

    def test_remove_public_ip_already_removed(self, capsys):
        """Test when instance already has no public IP."""
        mock_instance = {
            "State": {"Name": "running"},
            "NetworkInterfaces": [{"NetworkInterfaceId": "eni-123"}],
        }
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip.get_instance_info",
            return_value=mock_instance,
        ):
            with patch("boto3.client"):
                result = remove_public_ip_from_instance("i-123", "us-east-1")
        assert result is True
        captured = capsys.readouterr()
        assert "already has no public IP" in captured.out

    def test_remove_public_ip_success(self):
        """Test successful public IP removal."""
        mock_instance_before = {
            "State": {"Name": "running"},
            "PublicIpAddress": "1.2.3.4",
            "NetworkInterfaces": [{"NetworkInterfaceId": "eni-123"}],
            "SubnetId": "subnet-123",
        }
        mock_instance_after = {
            "State": {"Name": "running"},
            "NetworkInterfaces": [{"NetworkInterfaceId": "eni-123"}],
            "SubnetId": "subnet-123",
        }
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip.get_instance_info",
            side_effect=[mock_instance_before, mock_instance_after],
        ):
            with patch("boto3.client") as mock_client:
                mock_ec2 = MagicMock()
                mock_client.return_value = mock_ec2
                with patch("cost_toolkit.scripts.cleanup.public_ip_common._WAIT_EVENT"):
                    result = remove_public_ip_from_instance("i-123", "us-east-1")
        assert result is True

    def test_remove_public_ip_error(self, capsys):
        """Test public IP removal with error."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_instances.side_effect = ClientError({"Error": {"Code": "InvalidInstanceID"}}, "describe_instances")
            mock_client.return_value = mock_ec2
            result = remove_public_ip_from_instance("i-bad", "us-east-1")
        assert result is False
        captured = capsys.readouterr()
        assert "Error removing public IP" in captured.out


class TestMain:
    """Tests for main function."""

    def test_main_success(self, capsys):
        """Test main function with successful execution."""
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip.remove_public_ip_from_instance",
            return_value=True,
        ):
            main(["--use-default-target"])
        captured = capsys.readouterr()
        assert "Successfully removed public IP" in captured.out
        assert "Cost savings: $3.60/month" in captured.out

    def test_main_failure(self, capsys):
        """Test main function when removal fails."""
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip.remove_public_ip_from_instance",
            return_value=False,
        ):
            main(["--use-default-target"])
        captured = capsys.readouterr()
        assert "Failed to remove public IP" in captured.out
        assert "Manual steps may be required" in captured.out

    def test_main_output_includes_warning(self, capsys):
        """Test that main prints appropriate warnings."""
        with patch(
            "cost_toolkit.scripts.cleanup.aws_remove_public_ip.remove_public_ip_from_instance",
            return_value=True,
        ):
            main(["--use-default-target"])
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "downtime" in captured.out
