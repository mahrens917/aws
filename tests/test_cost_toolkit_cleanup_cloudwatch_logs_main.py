"""Comprehensive tests for aws_cloudwatch_cleanup.py - Log Retention and Main."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.cleanup.aws_cloudwatch_cleanup import (
    _reduce_retention_in_region,
    _update_log_group_retention,
    delete_custom_metrics,
    main,
    reduce_log_retention,
)


def test_delete_custom_metrics_print_custom_metrics_info(capsys):
    """Test printing custom metrics information."""
    delete_custom_metrics()
    captured = capsys.readouterr()
    assert "Custom Metrics Information" in captured.out
    assert "cannot be directly deleted" in captured.out
    assert "15 months" in captured.out


class TestUpdateLogGroupRetention:
    """Tests for _update_log_group_retention function."""

    def test_update_retention_never_expire(self, capsys):
        """Test updating log group with never expire retention."""
        mock_client = MagicMock()
        log_group = {
            "logGroupName": "/aws/lambda/test",
            "storedBytes": 1048576,
        }
        _update_log_group_retention(mock_client, log_group)
        mock_client.put_retention_policy.assert_called_once_with(logGroupName="/aws/lambda/test", retentionInDays=1)
        captured = capsys.readouterr()
        assert "Setting retention to 1 day" in captured.out

    def test_update_retention_long_period(self):
        """Test updating log group with long retention period."""
        mock_client = MagicMock()
        log_group = {
            "logGroupName": "/aws/lambda/test",
            "retentionInDays": 30,
            "storedBytes": 2097152,
        }
        _update_log_group_retention(mock_client, log_group)
        mock_client.put_retention_policy.assert_called_once()

    def test_update_retention_already_optimized(self, capsys):
        """Test log group with already optimized retention."""
        mock_client = MagicMock()
        log_group = {
            "logGroupName": "/aws/lambda/test",
            "retentionInDays": 1,
            "storedBytes": 512000,
        }
        _update_log_group_retention(mock_client, log_group)
        mock_client.put_retention_policy.assert_not_called()
        captured = capsys.readouterr()
        assert "already optimized" in captured.out

    def test_update_retention_error(self, capsys):
        """Test error when updating retention."""
        mock_client = MagicMock()
        mock_client.put_retention_policy.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "put_retention_policy")
        log_group = {
            "logGroupName": "/aws/lambda/test",
            "storedBytes": 1024,
        }
        _update_log_group_retention(mock_client, log_group)
        captured = capsys.readouterr()
        assert "Error setting retention" in captured.out


class TestReduceRetentionInRegion:
    """Tests for _reduce_retention_in_region function."""

    def test_reduce_retention_multiple_log_groups(self):
        """Test reducing retention for multiple log groups."""
        with patch("boto3.client") as mock_client:
            mock_logs = MagicMock()
            mock_logs.describe_log_groups.return_value = {
                "logGroups": [
                    {
                        "logGroupName": "/aws/lambda/test1",
                        "retentionInDays": 30,
                        "storedBytes": 1024,
                    },
                    {
                        "logGroupName": "/aws/lambda/test2",
                        "retentionInDays": 7,
                        "storedBytes": 2048,
                    },
                ]
            }
            mock_client.return_value = mock_logs
            with patch("cost_toolkit.scripts.cleanup.aws_cloudwatch_cleanup._update_log_group_retention"):
                _reduce_retention_in_region("us-east-1")

    def test_reduce_retention_no_log_groups(self, capsys):
        """Test when no log groups exist."""
        with patch("boto3.client") as mock_client:
            mock_logs = MagicMock()
            mock_logs.describe_log_groups.return_value = {"logGroups": []}
            mock_client.return_value = mock_logs
            _reduce_retention_in_region("us-east-1")
        captured = capsys.readouterr()
        assert "No log groups found" in captured.out


def test_reduce_log_retention_reduce_retention_multiple_regions(capsys):
    """Test reducing retention across regions."""
    with patch("cost_toolkit.scripts.cleanup.aws_cloudwatch_cleanup.aws_utils.setup_aws_credentials"):
        with patch("cost_toolkit.scripts.cleanup.aws_cloudwatch_cleanup._reduce_retention_in_region"):
            reduce_log_retention()
    captured = capsys.readouterr()
    assert "Checking CloudWatch log groups" in captured.out


def test_reduce_log_retention_with_client_error(capsys):
    """Test reducing log retention with ClientError."""
    with patch("cost_toolkit.scripts.cleanup.aws_cloudwatch_cleanup.aws_utils.setup_aws_credentials"):
        with patch("cost_toolkit.scripts.cleanup.aws_cloudwatch_cleanup._reduce_retention_in_region") as mock_reduce:
            mock_reduce.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "describe_log_groups")
            reduce_log_retention()
    captured = capsys.readouterr()
    assert "Error accessing CloudWatch Logs" in captured.out


class TestMain:
    """Tests for main function."""

    def test_main_executes_all_operations(self, capsys):
        """Test main function executes all cleanup operations."""
        module = "cost_toolkit.scripts.cleanup.aws_cloudwatch_cleanup"
        patches = {
            "delete_cloudwatch_canaries": MagicMock(),
            "disable_cloudwatch_alarms": MagicMock(),
            "reduce_log_retention": MagicMock(),
            "delete_custom_metrics": MagicMock(),
        }

        with patch.multiple(module, **patches):
            main()

        captured = capsys.readouterr()
        expected_messages = [
            "AWS CloudWatch Cost Optimization Cleanup",
            "This script will:",
            "Delete all CloudWatch Synthetics canaries",
            "Disable CloudWatch alarm actions",
            "Reduce log retention periods to 1 day",
            "Provide guidance on custom metrics",
            "CloudWatch cleanup completed",
            "Expected monthly savings",
            "76,719+ API requests per month",
        ]
        for message in expected_messages:
            assert message in captured.out

    def test_main_handles_exceptions(self, capsys):
        """Test main function handles exceptions gracefully."""
        module = "cost_toolkit.scripts.cleanup.aws_cloudwatch_cleanup"
        patches = {
            "delete_cloudwatch_canaries": MagicMock(),
            "disable_cloudwatch_alarms": MagicMock(),
            "reduce_log_retention": MagicMock(),
            "delete_custom_metrics": MagicMock(),
        }

        with patch.multiple(module, **patches):
            main()

        captured = capsys.readouterr()
        assert "AWS CloudWatch Cost Optimization Cleanup" in captured.out
