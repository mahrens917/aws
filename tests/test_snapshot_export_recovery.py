"""Tests for cost_toolkit/scripts/optimization/snapshot_export_fixed/recovery.py module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.scripts.optimization.snapshot_export_fixed.recovery import (
    check_existing_completed_exports,
    cleanup_temporary_ami,
    get_snapshots_to_export,
)
from cost_toolkit.scripts.snapshot_export_common import SAMPLE_SNAPSHOTS


@pytest.fixture(name="s3_client")
def fixture_s3_client():
    """Create a mock S3 client."""
    client = MagicMock()
    client.exceptions.NoSuchBucket = type("NoSuchBucket", (Exception,), {})
    return client


@pytest.fixture(name="ec2_client")
def fixture_ec2_client():
    """Create a mock EC2 client."""
    client = MagicMock()
    return client


def test_cleanup_temporary_ami_success(ec2_client, capsys):
    """Test cleanup_temporary_ami successfully deregisters AMI."""
    result = cleanup_temporary_ami(ec2_client, "ami-12345678", "us-east-1")

    assert result is True
    ec2_client.deregister_image.assert_called_once_with(ImageId="ami-12345678")

    captured = capsys.readouterr()
    assert "Cleaning up temporary AMI: ami-12345678" in captured.out
    assert "Successfully cleaned up AMI ami-12345678" in captured.out


def test_cleanup_temporary_ami_with_different_ami_ids(ec2_client):
    """Test cleanup_temporary_ami with various AMI IDs."""
    test_ami_ids = ["ami-abc123", "ami-xyz789", "ami-test-001"]

    for ami_id in test_ami_ids:
        ec2_client.reset_mock()
        result = cleanup_temporary_ami(ec2_client, ami_id, "us-west-2")

        assert result is True
        ec2_client.deregister_image.assert_called_once_with(ImageId=ami_id)


def test_cleanup_temporary_ami_different_regions(ec2_client):
    """Test cleanup_temporary_ami works with different regions."""
    regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-northeast-1"]

    for region in regions:
        ec2_client.reset_mock()
        result = cleanup_temporary_ami(ec2_client, "ami-12345678", region)

        assert result is True
        ec2_client.deregister_image.assert_called_once()


def test_check_existing_completed_exports_with_exports(s3_client, capsys):
    """Test check_existing_completed_exports finds existing exports."""
    test_date = datetime(2024, 1, 15)

    s3_client.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "ebs-snapshots/ami-123/export-task-001.vmdk",
                "Size": 107374182400,
                "LastModified": test_date,
            },
            {
                "Key": "ebs-snapshots/ami-456/export-task-002.vmdk",
                "Size": 53687091200,
                "LastModified": test_date,
            },
        ]
    }

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "cost_toolkit.scripts.optimization.snapshot_export_fixed.recovery.datetime",
            MagicMock(now=lambda: test_date),
        )
        result = check_existing_completed_exports(s3_client, "us-east-1")

    assert len(result) == 2
    assert result[0]["export_task_id"] == "export-task-001"
    assert result[0]["ami_id"] == "ami-123"
    assert result[0]["s3_key"] == "ebs-snapshots/ami-123/export-task-001.vmdk"
    assert result[0]["size_bytes"] == 107374182400

    assert result[1]["export_task_id"] == "export-task-002"
    assert result[1]["ami_id"] == "ami-456"

    captured = capsys.readouterr()
    assert "Found 2 completed exports:" in captured.out


def test_check_existing_completed_exports_no_exports(s3_client, capsys):
    """Test check_existing_completed_exports when no exports exist."""
    s3_client.list_objects_v2.return_value = {}

    result = check_existing_completed_exports(s3_client, "us-east-1")

    assert len(result) == 0
    captured = capsys.readouterr()
    # Should not show "Found N completed exports" message
    assert "Found" not in captured.out or "0" in captured.out


def test_check_existing_completed_exports_bucket_not_found(s3_client, capsys):
    """Test check_existing_completed_exports when bucket doesn't exist."""
    s3_client.list_objects_v2.side_effect = s3_client.exceptions.NoSuchBucket()

    result = check_existing_completed_exports(s3_client, "us-east-1")

    assert len(result) == 0
    captured = capsys.readouterr()
    assert "No existing exports found (bucket doesn't exist)" in captured.out


def test_check_existing_completed_exports_client_error(s3_client, capsys):
    """Test check_existing_completed_exports handles ClientError."""
    s3_client.list_objects_v2.side_effect = ClientError({"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "ListObjectsV2")

    result = check_existing_completed_exports(s3_client, "us-east-1")

    assert len(result) == 0
    captured = capsys.readouterr()
    assert "Could not check existing exports" in captured.out


def test_check_existing_completed_exports_filters_vmdk_only(s3_client):
    """Test check_existing_completed_exports only returns .vmdk files."""
    test_date = datetime(2024, 1, 15)

    s3_client.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "ebs-snapshots/ami-123/export-task-001.vmdk",
                "Size": 107374182400,
                "LastModified": test_date,
            },
            {
                "Key": "ebs-snapshots/ami-123/export-task-001.json",
                "Size": 1024,
                "LastModified": test_date,
            },
            {
                "Key": "ebs-snapshots/ami-456/export-task-002.txt",
                "Size": 512,
                "LastModified": test_date,
            },
        ]
    }

    result = check_existing_completed_exports(s3_client, "us-east-1")

    # Should only return the .vmdk file
    assert len(result) == 1
    assert result[0]["s3_key"] == "ebs-snapshots/ami-123/export-task-001.vmdk"


def test_check_existing_completed_exports_with_prefix(s3_client):
    """Test check_existing_completed_exports uses correct prefix."""
    s3_client.list_objects_v2.return_value = {}

    check_existing_completed_exports(s3_client, "us-east-1")

    # Verify prefix, bucket name depends on current date
    s3_client.list_objects_v2.assert_called_once()
    call_args = s3_client.list_objects_v2.call_args[1]
    assert call_args["Prefix"] == "ebs-snapshots/"
    assert call_args["Bucket"].startswith("ebs-snapshot-archive-us-east-1-")


def test_check_existing_completed_exports_handles_malformed_keys(s3_client):
    """Test check_existing_completed_exports handles malformed S3 keys."""
    test_date = datetime(2024, 1, 15)

    s3_client.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "ebs-snapshots/ami-123/export-task-001.vmdk",
                "Size": 107374182400,
                "LastModified": test_date,
            },
            {
                "Key": "invalid-key.vmdk",  # Not enough parts when split by "/"
                "Size": 1024,
                "LastModified": test_date,
            },
            {
                "Key": "only-two/parts.vmdk",  # Only 2 parts, needs at least 3
                "Size": 1024,
                "LastModified": test_date,
            },
        ]
    }

    result = check_existing_completed_exports(s3_client, "us-east-1")

    # Should only return the valid key
    assert len(result) == 1
    assert result[0]["s3_key"] == "ebs-snapshots/ami-123/export-task-001.vmdk"


def test_check_existing_completed_exports_bucket_name_format():
    """Test check_existing_completed_exports uses correct bucket name format."""
    mock_s3_client = MagicMock()
    mock_s3_client.list_objects_v2.return_value = {}

    test_date = datetime(2024, 3, 15)

    with pytest.MonkeyPatch.context() as mp:
        mock_datetime = MagicMock()
        mock_datetime.now.return_value = test_date
        mp.setattr(
            "cost_toolkit.scripts.optimization.snapshot_export_fixed.recovery.datetime",
            mock_datetime,
        )

        check_existing_completed_exports(mock_s3_client, "eu-west-2")

    # Verify bucket name format: ebs-snapshot-archive-{region}-{YYYYMMDD}
    expected_bucket = "ebs-snapshot-archive-eu-west-2-20240315"
    mock_s3_client.list_objects_v2.assert_called_once()
    actual_bucket = mock_s3_client.list_objects_v2.call_args[1]["Bucket"]
    assert actual_bucket == expected_bucket


def test_check_existing_completed_exports_multiple_regions(s3_client):
    """Test check_existing_completed_exports with different regions."""
    s3_client.list_objects_v2.return_value = {}

    regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-northeast-1"]

    for region in regions:
        s3_client.reset_mock()
        check_existing_completed_exports(s3_client, region)

        s3_client.list_objects_v2.assert_called_once()


def test_check_existing_completed_exports_extracts_correct_fields(s3_client):
    """Test check_existing_completed_exports extracts all required fields."""
    test_date = datetime(2024, 1, 15, 10, 30, 45)

    s3_client.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "ebs-snapshots/ami-test-123/export-my-task.vmdk",
                "Size": 12345678,
                "LastModified": test_date,
            }
        ]
    }

    result = check_existing_completed_exports(s3_client, "us-east-1")

    assert len(result) == 1
    export = result[0]

    assert export["export_task_id"] == "export-my-task"
    assert export["ami_id"] == "ami-test-123"
    assert export["s3_key"] == "ebs-snapshots/ami-test-123/export-my-task.vmdk"
    assert export["size_bytes"] == 12345678
    assert export["last_modified"] == test_date


def test_get_snapshots_to_export_returns_sample_data():
    """Test get_snapshots_to_export returns SAMPLE_SNAPSHOTS."""
    result = get_snapshots_to_export("FAKE_KEY", "FAKE_SECRET")

    assert result == SAMPLE_SNAPSHOTS
    assert len(result) == 3


def test_get_snapshots_to_export_ignores_credentials():
    """Test get_snapshots_to_export ignores provided credentials."""
    # Should return same data regardless of credentials
    result_one = get_snapshots_to_export("KEY1", "SECRET1")
    result_two = get_snapshots_to_export("KEY2", "SECRET2")
    result_three = get_snapshots_to_export(None, None)

    assert result_one == result_two == result_three == SAMPLE_SNAPSHOTS


def test_get_snapshots_to_export_data_structure():
    """Test get_snapshots_to_export returns correct data structure."""
    result = get_snapshots_to_export("KEY", "SECRET")

    assert isinstance(result, list)
    for snapshot in result:
        assert "snapshot_id" in snapshot
        assert "region" in snapshot
        assert "size_gb" in snapshot
        assert "description" in snapshot


def test_cleanup_temporary_ami_region_parameter_unused(ec2_client):
    """Test cleanup_temporary_ami region parameter is not used in API call."""
    cleanup_temporary_ami(ec2_client, "ami-12345", "unused-region")

    # Verify only ImageId is passed, region is not used in the deregister call
    ec2_client.deregister_image.assert_called_once_with(ImageId="ami-12345")


def test_check_existing_completed_exports_prints_export_details(s3_client, capsys):
    """Test check_existing_completed_exports prints details of found exports."""
    test_date = datetime(2024, 1, 15)

    s3_client.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "ebs-snapshots/ami-abc/task-001.vmdk",
                "Size": 1000,
                "LastModified": test_date,
            }
        ]
    }

    check_existing_completed_exports(s3_client, "us-east-1")

    captured = capsys.readouterr()
    assert "task-001" in captured.out
    # Bucket name includes current date, just check the key path
    assert "ebs-snapshots/ami-abc/task-001.vmdk" in captured.out


def test_check_existing_completed_exports_empty_contents(s3_client):
    """Test check_existing_completed_exports with empty Contents list."""
    s3_client.list_objects_v2.return_value = {"Contents": []}

    result = check_existing_completed_exports(s3_client, "us-east-1")

    assert len(result) == 0


def test_check_existing_completed_exports_no_contents_key(s3_client):
    """Test check_existing_completed_exports when Contents key is missing."""
    s3_client.list_objects_v2.return_value = {"IsTruncated": False}

    result = check_existing_completed_exports(s3_client, "us-east-1")

    assert len(result) == 0


def test_cleanup_temporary_ami_prints_ami_id(ec2_client, capsys):
    """Test cleanup_temporary_ami prints the correct AMI ID in output."""
    ami_id = "ami-specific-test-123"
    cleanup_temporary_ami(ec2_client, ami_id, "us-east-1")

    captured = capsys.readouterr()
    assert ami_id in captured.out
    # Should appear twice: once in "Cleaning up" and once in "Successfully cleaned up"
    assert captured.out.count(ami_id) == 2
