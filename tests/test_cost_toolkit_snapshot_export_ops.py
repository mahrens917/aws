"""Tests for snapshot export fixed operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cost_toolkit.scripts.optimization.snapshot_export_common import (
    create_ami_from_snapshot,
    create_s3_bucket_if_not_exists,
)
from cost_toolkit.scripts.optimization.snapshot_export_fixed.constants import (
    ExportTaskDeletedException,
)
from cost_toolkit.scripts.optimization.snapshot_export_fixed.export_helpers import (
    validate_export_task_exists,
)
from tests.assertions import assert_equal


def test_create_s3_bucket_if_not_exists():
    """Test create_s3_bucket_if_not_exists when bucket exists."""
    mock_s3 = MagicMock()
    mock_s3.head_bucket.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}

    result = create_s3_bucket_if_not_exists(mock_s3, "test-bucket", "us-east-1")

    assert_equal(result, True)
    mock_s3.head_bucket.assert_called_once_with(Bucket="test-bucket")


def test_create_ami_from_snapshot():
    """Test create_ami_from_snapshot creates AMI and waits."""
    mock_ec2 = MagicMock()

    with patch(
        "cost_toolkit.scripts.optimization.snapshot_export_common._register_ami",
        return_value="ami-12345",
    ) as mock_register:
        with patch(
            "cost_toolkit.scripts.optimization.snapshot_export_common.wait_for_ami_available",
            return_value="ami-12345",
        ) as mock_wait:
            result = create_ami_from_snapshot(mock_ec2, "snap-123", "test snapshot description")

            assert_equal(result, "ami-12345")
            mock_register.assert_called_once_with(
                mock_ec2,
                "snap-123",
                "test snapshot description",
                volume_type="gp3",
                boot_mode=None,
                ena_support=True,
                attempt_suffix="",
            )
            mock_wait.assert_called_once()


def test_validate_export_task_exists_success():
    """Test validate_export_task_exists when task exists."""
    mock_ec2 = MagicMock()
    mock_task = {"ExportImageTaskId": "export-123", "Status": "active"}
    mock_ec2.describe_export_image_tasks.return_value = {"ExportImageTasks": [mock_task]}

    result = validate_export_task_exists(mock_ec2, "export-123")

    assert_equal(result, mock_task)
    mock_ec2.describe_export_image_tasks.assert_called_once_with(ExportImageTaskIds=["export-123"])


def test_validate_export_task_exists_raises_when_deleted():
    """Test validate_export_task_exists raises exception when task deleted."""
    mock_ec2 = MagicMock()
    mock_ec2.describe_export_image_tasks.return_value = {"ExportImageTasks": []}

    try:
        validate_export_task_exists(mock_ec2, "export-deleted")
        assert False, "Expected ExportTaskDeletedException to be raised"
    except ExportTaskDeletedException as exc:
        assert "export-deleted" in str(exc)
        assert "no longer exists" in str(exc)
