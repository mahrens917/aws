"""Comprehensive tests for aws_check_instance_status.py."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.migration.aws_check_instance_status import (
    _check_system_logs,
    _check_user_data,
    _print_instance_info,
    _print_migration_lines,
    _print_troubleshooting,
    check_instance_status,
    main,
)


@patch("cost_toolkit.scripts.migration.aws_check_instance_status._print_troubleshooting")
@patch("cost_toolkit.scripts.migration.aws_check_instance_status._check_system_logs")
@patch("cost_toolkit.scripts.migration.aws_check_instance_status._check_user_data")
@patch("cost_toolkit.scripts.migration.aws_check_instance_status._print_instance_info")
@patch("cost_toolkit.scripts.migration.aws_check_instance_status.aws_utils.setup_aws_credentials")
@patch("cost_toolkit.scripts.migration.aws_check_instance_status.boto3.client")
def test_setup_credentials_calls_utils(
    mock_boto_client,
    mock_setup_creds,
    _mock_print_info,
    _mock_check_user_data,
    _mock_check_logs,
    _mock_troubleshooting,
):
    """check_instance_status should initialize AWS credentials before EC2 calls."""
    mock_ec2 = MagicMock()
    mock_ec2.describe_instances.return_value = {"Reservations": [{"Instances": [{"State": {"Name": "running"}}]}]}
    mock_boto_client.return_value = mock_ec2

    check_instance_status()

    mock_setup_creds.assert_called_once()
    mock_boto_client.assert_called_once_with("ec2", region_name="eu-west-2")


class TestPrintInstanceInfo:
    """Tests for _print_instance_info function."""

    def test_print_instance_info_output(self, capsys):
        """Test instance info is printed correctly."""
        instance = {
            "State": {"Name": "running"},
            "LaunchTime": "2024-01-01T00:00:00Z",
            "InstanceType": "t2.micro",
        }

        _print_instance_info(instance, "i-123456")

        captured = capsys.readouterr()
        assert "INSTANCE STATUS" in captured.out
        assert "Instance ID: i-123456" in captured.out
        assert "State: running" in captured.out
        assert "Instance Type: t2.micro" in captured.out

    def test_print_instance_info_handles_missing_launch_time(self, capsys):
        """Test when launch time is not present."""
        instance = {
            "State": {"Name": "stopped"},
            "InstanceType": "t3.small",
        }

        _print_instance_info(instance, "i-789")

        captured = capsys.readouterr()
        assert "Launch Time: None" in captured.out


class TestCheckUserData:
    """Tests for _check_user_data function."""

    def test_check_user_data_exists(self, capsys):
        """Test checking instance with user data."""
        mock_ec2 = MagicMock()
        user_data_script = "#!/bin/bash\necho 'EBS to S3 Migration Script'\n"
        encoded = base64.b64encode(user_data_script.encode("utf-8")).decode("utf-8")
        mock_ec2.describe_instance_attribute.return_value = {"UserData": {"Value": encoded}}

        _check_user_data(mock_ec2, "i-123")

        captured = capsys.readouterr()
        assert "USER DATA STATUS" in captured.out
        assert "User Data is configured" in captured.out
        assert "Script size:" in captured.out
        assert "Migration script detected" in captured.out

    def test_check_user_data_no_migration_script(self, capsys):
        """Test when user data exists but no migration script."""
        mock_ec2 = MagicMock()
        user_data = "#!/bin/bash\necho 'Hello World'\n"
        encoded = base64.b64encode(user_data.encode("utf-8")).decode("utf-8")
        mock_ec2.describe_instance_attribute.return_value = {"UserData": {"Value": encoded}}

        _check_user_data(mock_ec2, "i-123")

        captured = capsys.readouterr()
        assert "Migration script not found" in captured.out

    def test_check_user_data_not_configured(self, capsys):
        """Test when no user data is configured."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_instance_attribute.return_value = {}

        _check_user_data(mock_ec2, "i-123")

        captured = capsys.readouterr()
        assert "No User Data configured" in captured.out

    def test_check_user_data_handles_error(self, capsys):
        """Test error handling when retrieving user data."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_instance_attribute.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "describe_instance_attribute")

        _check_user_data(mock_ec2, "i-123")

        captured = capsys.readouterr()
        assert "Could not retrieve User Data" in captured.out


class TestPrintMigrationLines:
    """Tests for _print_migration_lines function."""

    def test_print_migration_lines_finds_keywords(self, capsys):
        """Test migration-related lines are identified."""
        lines = [
            "Starting instance",
            "Mounting volumes",
            "aws s3 sync completed",
            "Random log line",
            "Migration successful",
        ]

        _print_migration_lines(lines)

        captured = capsys.readouterr()
        assert "Migration-related console output" in captured.out
        assert "Mounting volumes" in captured.out
        assert "aws s3 sync completed" in captured.out
        assert "Migration successful" in captured.out

    def test_print_migration_lines_no_matches(self, capsys):
        """Test when no migration keywords found."""
        lines = [
            "System booting",
            "Network initialized",
            "Service started",
        ]

        _print_migration_lines(lines)

        captured = capsys.readouterr()
        assert "No migration-specific output found" in captured.out
        assert "Last few console lines" in captured.out

    def test_print_migration_lines_truncates(self, capsys):
        """Test output is limited to last 10 migration lines."""
        lines = [f"migration step {i}" for i in range(20)]

        _print_migration_lines(lines)

        captured = capsys.readouterr()
        output_lines = [line for line in captured.out.split("\n") if "migration step" in line]
        assert len(output_lines) <= 10

    def test_print_migration_lines_case_insensitive(self, capsys):
        """Test keyword matching is case insensitive."""
        lines = [
            "MIGRATION STARTED",
            "Mount complete",
            "S3 SYNC RUNNING",
        ]

        _print_migration_lines(lines)

        captured = capsys.readouterr()
        assert "MIGRATION STARTED" in captured.out
        assert "Mount complete" in captured.out


class TestCheckSystemLogs:
    """Tests for _check_system_logs function."""

    def test_check_logs_with_output(self, capsys):
        """Test checking system logs with console output."""
        mock_ec2 = MagicMock()
        console_output = "Booting system\nMounting volumes\nMigration started\n"
        mock_ec2.get_console_output.return_value = {"Output": console_output}

        _check_system_logs(mock_ec2, "i-123")

        captured = capsys.readouterr()
        assert "CHECKING SYSTEM LOGS" in captured.out

    def test_check_logs_no_output(self, capsys):
        """Test when no console output available."""
        mock_ec2 = MagicMock()
        mock_ec2.get_console_output.return_value = {}

        _check_system_logs(mock_ec2, "i-123")

        captured = capsys.readouterr()
        assert "No console output available yet" in captured.out

    def test_check_logs_handles_error(self, capsys):
        """Test error handling when retrieving console output."""
        mock_ec2 = MagicMock()
        mock_ec2.get_console_output.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "get_console_output")

        _check_system_logs(mock_ec2, "i-123")

        captured = capsys.readouterr()
        assert "Could not retrieve console output" in captured.out


def test_print_troubleshooting_output(capsys):
    """Test troubleshooting info is printed."""
    _print_troubleshooting()

    captured = capsys.readouterr()
    assert "TROUBLESHOOTING" in captured.out
    assert "User Data may have failed" in captured.out
    assert "manual intervention" in captured.out
    assert "console output" in captured.out
    assert "SSM" in captured.out


class TestCheckInstanceStatus:
    """Tests for check_instance_status function."""

    def test_check_status_success(self, capsys):
        """Test successful instance status check."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_instances.return_value = {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "State": {"Name": "running"},
                                "InstanceType": "t2.micro",
                                "LaunchTime": "2024-01-01",
                                "Tags": [{"Key": "Name", "Value": "test"}],
                            }
                        ]
                    }
                ]
            }
            mock_ec2.describe_instance_attribute.return_value = {}
            mock_ec2.get_console_output.return_value = {}
            mock_client.return_value = mock_ec2
            check_instance_status()
        captured = capsys.readouterr()
        assert "AWS Instance Status Check" in captured.out

    def test_check_status_uses_correct_region(self):
        """Test check uses correct AWS region."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_instances.return_value = {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "State": {"Name": "running"},
                                "InstanceType": "t2.micro",
                                "Tags": [],
                            }
                        ]
                    }
                ]
            }
            mock_ec2.describe_instance_attribute.return_value = {}
            mock_ec2.get_console_output.return_value = {}
            mock_client.return_value = mock_ec2
            check_instance_status()
        mock_client.assert_called_once_with("ec2", region_name="eu-west-2")


class TestCheckInstanceStatusErrors:
    """Error handling and helper function tests for check_instance_status."""

    def test_check_status_handles_error(self, capsys):
        """Test error handling during status check."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_ec2.describe_instances.side_effect = ClientError({"Error": {"Code": "InvalidInstanceID.NotFound"}}, "describe_instances")
            mock_client.return_value = mock_ec2
            check_instance_status()
        captured = capsys.readouterr()
        assert "Error checking instance status" in captured.out

    def test_check_status_calls_all_checks(self):
        """Test all check functions are called."""
        with patch("boto3.client") as mock_client:
            with (
                patch("cost_toolkit.scripts.migration.aws_check_instance_status._print_instance_info") as mock_info,
                patch("cost_toolkit.scripts.migration.aws_check_instance_status._check_user_data") as mock_user,
                patch("cost_toolkit.scripts.migration.aws_check_instance_status._check_system_logs") as mock_logs,
                patch("cost_toolkit.scripts.migration.aws_check_instance_status._print_troubleshooting") as mock_trouble,
            ):
                mock_ec2 = MagicMock()
                mock_ec2.describe_instances.return_value = {"Reservations": [{"Instances": [{"State": {"Name": "running"}}]}]}
                mock_client.return_value = mock_ec2
                check_instance_status()
        mock_info.assert_called_once()
        mock_user.assert_called_once()
        mock_logs.assert_called_once()
        mock_trouble.assert_called_once()


def test_main_calls_check_instance_status():
    """Test main function calls check_instance_status."""
    with patch("cost_toolkit.scripts.migration.aws_check_instance_status.check_instance_status") as mock_check:
        main()
    mock_check.assert_called_once()
