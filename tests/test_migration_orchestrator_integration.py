"""Integration tests for migration_orchestrator.py

Tests cover:
- Complete migration pipeline (sync -> verify -> delete)
- Multi-bucket orchestration with errors
- Resumable migration state preservation
"""

from threading import Event
from unittest import mock

import pytest

from migration_orchestrator import (
    MigrationFatalError,
    migrate_all_buckets,
    process_bucket,
)


@pytest.fixture
def mock_deps(tmp_path):
    """Create mock dependencies for integration tests"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock()
    mock_drive_checker = mock.Mock()
    base_path = tmp_path / "migration"
    base_path.mkdir()

    return {
        "s3": mock_s3,
        "state": mock_state,
        "base_path": base_path,
        "drive_checker": mock_drive_checker,
    }


def test_full_bucket_migration_pipeline(mock_deps):
    """Test complete migration pipeline: sync -> verify -> delete"""
    bucket = "test-bucket"
    bucket_info = {
        "sync_complete": False,
        "verify_complete": False,
        "delete_complete": False,
        "file_count": 100,
        "total_size": 1000000,
        "local_file_count": 100,
        "verified_file_count": 100,
        "size_verified_count": 100,
        "checksum_verified_count": 100,
        "total_bytes_verified": 1000000,
    }
    mock_deps["state"].get_bucket_info.return_value = bucket_info

    verify_results = {
        "verified_count": 100,
        "size_verified": 100,
        "checksum_verified": 100,
        "total_bytes_verified": 1000000,
        "local_file_count": 100,
    }

    with (
        mock.patch("migration_orchestrator.sync_bucket") as mock_sync,
        mock.patch("migration_orchestrator.verify_bucket", return_value=verify_results) as mock_verify,
        mock.patch("migration_orchestrator.delete_bucket") as mock_delete,
        mock.patch("builtins.input", return_value="yes"),
    ):
        process_bucket(mock_deps["s3"], mock_deps["state"], mock_deps["base_path"], bucket, Event())

    # Verify all steps completed in order
    mock_sync.assert_called_once()
    mock_verify.assert_called_once()
    mock_delete.assert_called_once()


def test_multi_bucket_orchestration_with_one_error(mock_deps):
    """Test orchestration stops on error in one bucket"""
    all_buckets = ["bucket-1", "bucket-2"]
    mock_deps["state"].get_all_buckets.return_value = all_buckets
    mock_deps["state"].get_completed_buckets_for_phase.return_value = []

    with (
        mock.patch("builtins.print"),
        mock.patch("migration_orchestrator.process_bucket", side_effect=RuntimeError("Sync failed")),
    ):
        with pytest.raises(MigrationFatalError) as exc_info:
            migrate_all_buckets(
                mock_deps["s3"],
                mock_deps["state"],
                mock_deps["base_path"],
                mock_deps["drive_checker"],
                Event(),
            )

    assert "Migration error" in str(exc_info.value)


def test_resumable_migration_state_preserved(mock_deps):
    """Test that migration state is preserved for resumption"""
    all_buckets = ["bucket-1", "bucket-2", "bucket-3"]
    completed_buckets = ["bucket-1", "bucket-2"]  # Two already done
    mock_deps["state"].get_all_buckets.return_value = all_buckets
    mock_deps["state"].get_completed_buckets_for_phase.return_value = completed_buckets

    with (
        mock.patch("builtins.print"),
        mock.patch("migration_orchestrator.process_bucket") as mock_process,
    ):
        migrate_all_buckets(
            mock_deps["s3"],
            mock_deps["state"],
            mock_deps["base_path"],
            mock_deps["drive_checker"],
            Event(),
        )

    # Only bucket-3 should be processed
    mock_process.assert_called_once()
    call_args = mock_process.call_args
    assert call_args[0][3] == "bucket-3"
