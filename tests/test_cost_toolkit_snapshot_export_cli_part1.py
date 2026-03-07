"""Tests for cost_toolkit/scripts/optimization/snapshot_export_fixed/cli.py - Part 1"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.scripts.optimization.snapshot_export_fixed.cli import (
    _build_export_result,
    _setup_aws_clients,
    _setup_s3_bucket_for_export,
    export_single_snapshot_to_s3,
)
from cost_toolkit.scripts.optimization.snapshot_export_fixed.constants import (
    ExportTaskDeletedException,
    ExportTaskStuckException,
)
from tests.assertions import assert_equal


# Tests for _setup_aws_clients
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.create_ec2_and_s3_clients")
def test_setup_aws_clients(mock_create_clients):
    """Test _setup_aws_clients creates EC2 and S3 clients."""
    mock_ec2 = MagicMock()
    mock_s3 = MagicMock()
    mock_create_clients.return_value = (mock_ec2, mock_s3)

    ec2_client, s3_client = _setup_aws_clients("us-east-1", "access_key", "secret_key")

    assert_equal(ec2_client, mock_ec2)
    assert_equal(s3_client, mock_s3)
    mock_create_clients.assert_called_once_with("us-east-1", "access_key", "secret_key")


# Tests for _setup_s3_bucket_for_export
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.setup_s3_bucket_versioning")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.create_s3_bucket_with_region")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.create_s3_bucket_if_not_exists")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.check_existing_completed_exports")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.datetime")
@patch("builtins.print")
def test_setup_s3_bucket_for_export_existing_bucket(
    _mock_print,
    mock_datetime,
    mock_check_exports,
    mock_create_if_not_exists,
    _mock_create_with_region,
    mock_setup_versioning,
):
    """Test _setup_s3_bucket_for_export when bucket already exists."""
    mock_datetime.now.return_value.strftime.return_value = "20250114"
    mock_s3 = MagicMock()
    mock_check_exports.return_value = []
    mock_create_if_not_exists.return_value = True

    bucket_name = _setup_s3_bucket_for_export(mock_s3, "us-west-2")

    assert_equal(bucket_name, "ebs-snapshot-archive-us-west-2-20250114")
    mock_check_exports.assert_called_once_with(mock_s3, "us-west-2")
    mock_create_if_not_exists.assert_called_once_with(mock_s3, "ebs-snapshot-archive-us-west-2-20250114", "us-west-2")
    mock_setup_versioning.assert_called_once_with(mock_s3, "ebs-snapshot-archive-us-west-2-20250114")


@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.setup_s3_bucket_versioning")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.create_s3_bucket_with_region")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.create_s3_bucket_if_not_exists")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.check_existing_completed_exports")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.datetime")
@patch("builtins.print")
def test_setup_s3_bucket_for_export_creates_new_bucket(
    _mock_print,
    mock_datetime,
    mock_check_exports,
    mock_create_if_not_exists,
    mock_create_with_region,
    mock_setup_versioning,
):
    """Test _setup_s3_bucket_for_export when bucket needs to be created."""
    mock_datetime.now.return_value.strftime.return_value = "20250114"
    mock_s3 = MagicMock()
    mock_s3.exceptions.NoSuchBucket = type("NoSuchBucket", (Exception,), {})
    mock_check_exports.return_value = []
    mock_create_if_not_exists.side_effect = mock_s3.exceptions.NoSuchBucket()

    bucket_name = _setup_s3_bucket_for_export(mock_s3, "eu-west-1")

    assert_equal(bucket_name, "ebs-snapshot-archive-eu-west-1-20250114")
    mock_create_with_region.assert_called_once_with(mock_s3, "ebs-snapshot-archive-eu-west-1-20250114", "eu-west-1")
    mock_setup_versioning.assert_called_once()


# Tests for _build_export_result
def test_build_export_result():
    """Test _build_export_result creates correct result dictionary."""
    savings = {
        "monthly_savings": 12.50,
        "annual_savings": 150.00,
        "ebs_cost": 20.00,
        "s3_cost": 7.50,
        "savings_percentage": 62.5,
    }

    result = _build_export_result(
        "snap-123",
        "ami-456",
        "test-bucket",
        s3_key="exports/test.vmdk",
        export_task_id="export-789",
        size_gb=100,
        savings=savings,
    )

    assert_equal(result["snapshot_id"], "snap-123")
    assert_equal(result["ami_id"], "ami-456")
    assert_equal(result["bucket_name"], "test-bucket")
    assert_equal(result["s3_key"], "exports/test.vmdk")
    assert_equal(result["export_task_id"], "export-789")
    assert_equal(result["size_gb"], 100)
    assert_equal(result["monthly_savings"], 12.50)
    assert_equal(result["success"], True)


# Tests for export_single_snapshot_to_s3
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.cleanup_temporary_ami")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.calculate_cost_savings")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.verify_s3_export_final")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.export_ami_to_s3_with_recovery")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.create_ami_from_snapshot")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli._setup_s3_bucket_for_export")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli._setup_aws_clients")
@patch("builtins.print")
def test_export_single_snapshot_to_s3_success(  # pylint: disable=too-many-positional-arguments
    _mock_print,
    mock_setup_clients,
    mock_setup_bucket,
    mock_create_ami,
    mock_export_ami,
    mock_verify_s3,
    mock_calculate_savings,
    mock_cleanup_ami,
):
    """Test export_single_snapshot_to_s3 successful export."""
    mock_ec2 = MagicMock()
    mock_s3 = MagicMock()
    mock_setup_clients.return_value = (mock_ec2, mock_s3)
    mock_setup_bucket.return_value = "test-bucket"
    mock_create_ami.return_value = "ami-123"
    mock_export_ami.return_value = ("export-456", "exports/ami-123/export-456.vmdk")
    mock_verify_s3.return_value = {"size_gb": 50.0}
    mock_calculate_savings.return_value = {
        "monthly_savings": 1.35,
        "annual_savings": 16.20,
        "ebs_cost": 2.50,
        "s3_cost": 1.15,
        "savings_percentage": 54.0,
    }

    snapshot_info = {
        "snapshot_id": "snap-789",
        "region": "us-east-1",
        "size_gb": 50,
        "description": "Test snapshot",
    }

    result = export_single_snapshot_to_s3(snapshot_info, "access_key", "secret_key")

    assert_equal(result["snapshot_id"], "snap-789")
    assert_equal(result["ami_id"], "ami-123")
    assert_equal(result["bucket_name"], "test-bucket")
    assert_equal(result["s3_key"], "exports/ami-123/export-456.vmdk")
    assert_equal(result["export_task_id"], "export-456")
    assert_equal(result["success"], True)
    mock_cleanup_ami.assert_called_once_with(mock_ec2, "ami-123", "us-east-1")


@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.cleanup_temporary_ami")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.export_ami_to_s3_with_recovery")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.create_ami_from_snapshot")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli._setup_s3_bucket_for_export")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli._setup_aws_clients")
@patch("builtins.print")
def test_export_single_snapshot_to_s3_export_deleted_cleans_up_ami(
    _mock_print,
    mock_setup_clients,
    mock_setup_bucket,
    mock_create_ami,
    mock_export_ami,
    mock_cleanup_ami,
):
    """Test export_single_snapshot_to_s3 cleans up AMI when export is deleted."""
    mock_ec2 = MagicMock()
    mock_s3 = MagicMock()
    mock_setup_clients.return_value = (mock_ec2, mock_s3)
    mock_setup_bucket.return_value = "test-bucket"
    mock_create_ami.return_value = "ami-123"
    mock_export_ami.side_effect = ExportTaskDeletedException("Export was deleted")

    snapshot_info = {
        "snapshot_id": "snap-789",
        "region": "us-east-1",
        "size_gb": 50,
        "description": "Test snapshot",
    }

    with pytest.raises(ExportTaskDeletedException):
        export_single_snapshot_to_s3(snapshot_info, "access_key", "secret_key")

    mock_cleanup_ami.assert_called_once_with(mock_ec2, "ami-123", "us-east-1")


@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.cleanup_temporary_ami")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.export_ami_to_s3_with_recovery")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.create_ami_from_snapshot")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli._setup_s3_bucket_for_export")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli._setup_aws_clients")
@patch("builtins.print")
def test_export_single_snapshot_to_s3_export_stuck_cleans_up_ami(
    _mock_print,
    mock_setup_clients,
    mock_setup_bucket,
    mock_create_ami,
    mock_export_ami,
    mock_cleanup_ami,
):
    """Test export_single_snapshot_to_s3 cleans up AMI when export is stuck."""
    mock_ec2 = MagicMock()
    mock_s3 = MagicMock()
    mock_setup_clients.return_value = (mock_ec2, mock_s3)
    mock_setup_bucket.return_value = "test-bucket"
    mock_create_ami.return_value = "ami-123"
    mock_export_ami.side_effect = ExportTaskStuckException("Export stuck")

    snapshot_info = {
        "snapshot_id": "snap-789",
        "region": "us-east-1",
        "size_gb": 50,
        "description": "Test snapshot",
    }

    with pytest.raises(ExportTaskStuckException):
        export_single_snapshot_to_s3(snapshot_info, "access_key", "secret_key")

    mock_cleanup_ami.assert_called_once_with(mock_ec2, "ami-123", "us-east-1")


@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.cleanup_temporary_ami")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.export_ami_to_s3_with_recovery")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.create_ami_from_snapshot")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli._setup_s3_bucket_for_export")
@patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli._setup_aws_clients")
@patch("builtins.print")
def test_export_single_snapshot_to_s3_client_error_cleans_up_ami(
    _mock_print,
    mock_setup_clients,
    mock_setup_bucket,
    mock_create_ami,
    mock_export_ami,
    mock_cleanup_ami,
):
    """Test export_single_snapshot_to_s3 cleans up AMI on client error."""
    mock_ec2 = MagicMock()
    mock_s3 = MagicMock()
    mock_setup_clients.return_value = (mock_ec2, mock_s3)
    mock_setup_bucket.return_value = "test-bucket"
    mock_create_ami.return_value = "ami-123"
    mock_export_ami.side_effect = ClientError({"Error": {"Code": "InternalError"}}, "ExportImage")

    snapshot_info = {
        "snapshot_id": "snap-789",
        "region": "us-east-1",
        "size_gb": 50,
        "description": "Test snapshot",
    }

    with pytest.raises(ClientError):
        export_single_snapshot_to_s3(snapshot_info, "access_key", "secret_key")

    mock_cleanup_ami.assert_called_once_with(mock_ec2, "ami-123", "us-east-1")


# Integration-style test for the complete flow
def test_export_single_snapshot_to_s3_integration():
    """Integration test for export_single_snapshot_to_s3."""
    with (
        patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.datetime") as mock_datetime,
        patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.create_ec2_and_s3_clients") as mock_create_clients,
        patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.check_existing_completed_exports") as mock_check_exports,
        patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.create_s3_bucket_if_not_exists") as mock_create_if_exists,
        patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.setup_s3_bucket_versioning") as mock_setup_versioning,
        patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.create_ami_from_snapshot") as mock_create_ami,
        patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.export_ami_to_s3_with_recovery") as mock_export_ami,
        patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.verify_s3_export_final") as mock_verify_s3,
        patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.calculate_cost_savings") as mock_calculate_savings,
        patch("cost_toolkit.scripts.optimization.snapshot_export_fixed.cli.cleanup_temporary_ami") as mock_cleanup,
        patch("builtins.print"),
    ):
        mock_datetime.now.return_value.strftime.return_value = "20250114"
        mock_ec2 = MagicMock()
        mock_s3 = MagicMock()
        mock_create_clients.return_value = (mock_ec2, mock_s3)
        mock_check_exports.return_value = []
        mock_create_if_exists.return_value = True
        mock_setup_versioning.return_value = True
        mock_create_ami.return_value = "ami-integration-test"
        mock_export_ami.return_value = (
            "export-task-123",
            "exports/ami-integration-test/export.vmdk",
        )
        mock_verify_s3.return_value = {"size_gb": 100.0}
        mock_calculate_savings.return_value = {
            "monthly_savings": 2.70,
            "annual_savings": 32.40,
            "ebs_cost": 5.00,
            "s3_cost": 2.30,
            "savings_percentage": 54.0,
        }

        snapshot_info = {
            "snapshot_id": "snap-integration",
            "region": "us-east-1",
            "size_gb": 100,
            "description": "Integration test snapshot",
        }

        result = export_single_snapshot_to_s3(snapshot_info, "test_key", "test_secret")

        assert_equal(result["snapshot_id"], "snap-integration")
        assert_equal(result["ami_id"], "ami-integration-test")
        assert_equal(result["export_task_id"], "export-task-123")
        assert_equal(result["success"], True)

        mock_create_clients.assert_called_once_with("us-east-1", "test_key", "test_secret")
        mock_create_ami.assert_called_once_with(mock_ec2, "snap-integration", "Integration test snapshot")
        mock_export_ami.assert_called_once()
        mock_verify_s3.assert_called_once()
        mock_cleanup.assert_called_once_with(mock_ec2, "ami-integration-test", "us-east-1")
