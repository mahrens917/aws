"""Tests for instance termination core functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.scripts.cleanup.aws_instance_termination import (
    get_instance_details,
    get_volume_details,
    main,
    terminate_instance_safely,
)
from tests.ec2_instance_test_utils import (
    build_describe_empty_client,
    build_describe_not_found_client,
)


class TestTerminateInstanceSafely:
    """Test safe instance termination functionality."""

    def test_terminate_success(self):
        """Test successful safe termination."""
        with patch("boto3.client") as mock_client:
            with patch("cost_toolkit.scripts.cleanup.aws_instance_termination.get_instance_details") as mock_get:
                with patch("cost_toolkit.scripts.cleanup.aws_instance_termination._WAIT_EVENT") as mock_event:
                    mock_ec2 = MagicMock()
                    mock_client.return_value = mock_ec2
                    instance_info = {
                        "instance_id": "i-123",
                        "name": "test",
                        "state": "running",
                        "instance_type": "t2.micro",
                        "launch_time": "2024-01-01",
                        "availability_zone": "us-east-1a",
                        "volumes": [],
                        "region": "us-east-1",
                    }
                    mock_get.side_effect = [
                        instance_info,
                        {**instance_info, "state": "shutting-down"},
                    ]
                    mock_ec2.terminate_instances.return_value = {
                        "TerminatingInstances": [
                            {
                                "CurrentState": {"Name": "shutting-down"},
                                "PreviousState": {"Name": "running"},
                            }
                        ]
                    }
                    result = terminate_instance_safely("i-123", "us-east-1")
                    assert result is True
                    mock_event.wait.assert_called_once_with(10)

    def test_already_terminated(self, capsys):
        """Test termination of already terminated instance."""
        with patch("boto3.client"):
            with patch("cost_toolkit.scripts.cleanup.aws_instance_termination.get_instance_details") as mock_get:
                instance_info = {
                    "instance_id": "i-123",
                    "name": "test",
                    "state": "terminated",
                    "instance_type": "t2.micro",
                    "launch_time": "2024-01-01",
                    "availability_zone": "us-east-1a",
                    "volumes": [],
                    "region": "us-east-1",
                }
                mock_get.return_value = instance_info
                result = terminate_instance_safely("i-123", "us-east-1")
                assert result is True
                captured = capsys.readouterr()
                assert "already terminated" in captured.out

    def test_instance_not_found(self):
        """Test handling of instance not found error."""
        with patch("boto3.client"):
            with patch(
                "cost_toolkit.scripts.cleanup.aws_instance_termination.get_instance_details",
                return_value=None,
            ):
                result = terminate_instance_safely("i-notfound", "us-east-1")
                assert result is False

    def test_termination_error(self, capsys):
        """Test error handling during termination."""
        with patch("boto3.client") as mock_client:
            with patch("cost_toolkit.scripts.cleanup.aws_instance_termination.get_instance_details") as mock_get:
                mock_ec2 = MagicMock()
                mock_ec2.terminate_instances.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "terminate_instances")
                mock_client.return_value = mock_ec2
                instance_info = {
                    "instance_id": "i-123",
                    "name": "test",
                    "state": "running",
                    "instance_type": "t2.micro",
                    "launch_time": "2024-01-01",
                    "availability_zone": "us-east-1a",
                    "volumes": [],
                    "region": "us-east-1",
                }
                mock_get.return_value = instance_info
                result = terminate_instance_safely("i-123", "us-east-1")
                assert result is False
                captured = capsys.readouterr()
                assert "Error terminating instance" in captured.out


class TestGetInstanceDetails:
    """Test get_instance_details function."""

    def test_get_instance_details_success(self):
        """Test successful retrieval of instance details."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_instances.return_value = {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-123",
                                "Tags": [{"Key": "Name", "Value": "TestInstance"}],
                                "State": {"Name": "running"},
                                "InstanceType": "t2.micro",
                                "LaunchTime": "2024-01-01",
                                "Placement": {"AvailabilityZone": "us-east-1a"},
                                "BlockDeviceMappings": [],
                            }
                        ]
                    }
                ]
            }
            mock_client.return_value = mock_ec2

            details = get_instance_details("i-123", "us-east-1")

            assert details is not None
            assert details["instance_id"] == "i-123"
            assert details["name"] == "TestInstance"
            assert details["state"] == "running"
            assert details["instance_type"] == "t2.micro"
            assert details["region"] == "us-east-1"

    def test_get_instance_details_client_error(self):
        """Test error handling in get_instance_details - raises ClientError (fail-fast)."""
        with patch("boto3.client") as mock_client:
            mock_client.return_value = build_describe_not_found_client()

            with pytest.raises(ClientError):
                get_instance_details("i-notfound", "us-east-1")

    def test_get_instance_details_no_reservations(self):
        """Test get_instance_details when no reservations returned."""
        with patch("boto3.client") as mock_client:
            mock_client.return_value = build_describe_empty_client()

            details = get_instance_details("i-123", "us-east-1")

            assert details is None


class TestGetVolumeDetails:
    """Test get_volume_details function."""

    def test_get_volume_details_success(self):
        """Test successful retrieval of volume details."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_volumes.return_value = {
                "Volumes": [
                    {
                        "VolumeId": "vol-123",
                        "Tags": [{"Key": "Name", "Value": "DataVolume"}],
                        "Size": 100,
                        "VolumeType": "gp3",
                        "State": "available",
                        "Encrypted": True,
                    }
                ]
            }
            mock_client.return_value = mock_ec2

            details = get_volume_details("vol-123", "us-east-1")

            assert details is not None
            assert details["volume_id"] == "vol-123"
            assert details["name"] == "DataVolume"
            assert details["size"] == 100
            assert details["volume_type"] == "gp3"
            assert details["encrypted"] is True

    def test_get_volume_details_no_name_tag(self):
        """Test volume details when no Name tag exists."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_volumes.return_value = {
                "Volumes": [
                    {
                        "VolumeId": "vol-123",
                        "Tags": [{"Key": "Env", "Value": "prod"}],
                        "Size": 50,
                        "VolumeType": "gp2",
                        "State": "in-use",
                        "Encrypted": False,
                    }
                ]
            }
            mock_client.return_value = mock_ec2

            details = get_volume_details("vol-123", "us-east-1")

            assert details["name"] is None

    def test_get_volume_details_client_error(self, capsys):
        """Test error handling in get_volume_details."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_volumes.side_effect = ClientError({"Error": {"Code": "InvalidVolume.NotFound"}}, "describe_volumes")
            mock_client.return_value = mock_ec2

            details = get_volume_details("vol-notfound", "us-east-1")

            assert details is None
            captured = capsys.readouterr()
            assert "Error getting volume details" in captured.out


def test_main_function_user_confirms(capsys, monkeypatch):
    """Test main function when user confirms termination."""
    monkeypatch.setattr("builtins.input", lambda _: "TERMINATE")

    with patch("cost_toolkit.scripts.cleanup.aws_instance_termination.setup_aws_credentials"):
        with patch(
            "cost_toolkit.scripts.cleanup.aws_instance_termination.terminate_instance_safely",
            return_value=True,
        ):
            main(["--use-default-target"])

    captured = capsys.readouterr()
    assert "Instance termination initiated successfully" in captured.out


def test_main_function_user_cancels(capsys, monkeypatch):
    """Test main function when user cancels termination."""
    monkeypatch.setattr("builtins.input", lambda _: "NO")

    with patch("cost_toolkit.scripts.cleanup.aws_instance_termination.setup_aws_credentials"):
        main(["--use-default-target"])

    captured = capsys.readouterr()
    assert "Termination cancelled" in captured.out


def test_main_function_termination_fails(capsys, monkeypatch):
    """Test main function when termination fails."""
    monkeypatch.setattr("builtins.input", lambda _: "TERMINATE")

    with patch("cost_toolkit.scripts.cleanup.aws_instance_termination.setup_aws_credentials"):
        with patch(
            "cost_toolkit.scripts.cleanup.aws_instance_termination.terminate_instance_safely",
            return_value=False,
        ):
            main(["--use-default-target"])

    captured = capsys.readouterr()
    assert "termination failed" in captured.out
