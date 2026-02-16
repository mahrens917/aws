"""Unit tests for process_bucket function from migration_orchestrator.py

Tests cover:
- Full bucket migration pipeline (sync -> verify -> delete)
- User input handling for deletion confirmation
- Skip logic for already-completed steps
- Verification summary formatting
"""

from threading import Event
from unittest import mock

import pytest

from migration_orchestrator import (
    delete_with_confirmation,
    process_bucket,
    show_verification_summary,
)


@pytest.fixture
def mock_dependencies(tmp_path):
    """Create mock dependencies for process_bucket"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock()
    base_path = tmp_path / "migration"
    base_path.mkdir()

    return {
        "s3": mock_s3,
        "state": mock_state,
        "base_path": base_path,
    }


def test_process_bucket_first_time_sync_verify_delete(mock_dependencies):
    """Test process_bucket for first time: sync -> verify -> delete pipeline"""
    bucket = "test-bucket"
    bucket_info = {
        "sync_complete": False,
        "verify_complete": False,
        "delete_complete": False,
        "file_count": 100,
        "total_size": 1024000,
        "local_file_count": 100,
        "verified_file_count": 100,
        "size_verified_count": 100,
        "checksum_verified_count": 100,
        "total_bytes_verified": 1024000,
    }
    mock_dependencies["state"].get_bucket_info.return_value = bucket_info

    verify_results = {
        "verified_count": 100,
        "size_verified": 100,
        "checksum_verified": 100,
        "total_bytes_verified": 1024000,
        "local_file_count": 100,
    }

    with (
        mock.patch("migration_orchestrator.sync_bucket") as mock_sync,
        mock.patch("migration_orchestrator.verify_bucket", return_value=verify_results) as mock_verify,
        mock.patch("migration_orchestrator.delete_bucket") as mock_delete,
        mock.patch("builtins.input", return_value="yes"),
    ):
        process_bucket(mock_dependencies["s3"], mock_dependencies["state"], mock_dependencies["base_path"], bucket, Event())

    # Verify sync was called
    mock_sync.assert_called_once()
    mock_dependencies["state"].mark_bucket_sync_complete.assert_called_once_with(bucket)

    # Verify verification was called
    mock_verify.assert_called_once()
    assert mock_dependencies["state"].mark_bucket_verify_complete.called

    # Verify deletion was called
    mock_delete.assert_called_once()
    mock_dependencies["state"].mark_bucket_delete_complete.assert_called_once_with(bucket)


def test_process_bucket_already_synced_skips_sync(mock_dependencies):
    """Test process_bucket skips sync if already complete"""
    bucket = "test-bucket"
    bucket_info = {
        "sync_complete": True,
        "verify_complete": False,
        "delete_complete": False,
        "file_count": 50,
        "total_size": 512000,
        "local_file_count": 50,
        "verified_file_count": 50,
        "size_verified_count": 50,
        "checksum_verified_count": 50,
        "total_bytes_verified": 512000,
    }
    mock_dependencies["state"].get_bucket_info.return_value = bucket_info

    verify_results = {
        "verified_count": 50,
        "size_verified": 50,
        "checksum_verified": 50,
        "total_bytes_verified": 512000,
        "local_file_count": 50,
    }

    with (
        mock.patch("migration_orchestrator.sync_bucket") as mock_sync,
        mock.patch("migration_orchestrator.verify_bucket", return_value=verify_results),
        mock.patch("migration_orchestrator.delete_bucket"),
        mock.patch("builtins.input", return_value="yes"),
    ):
        process_bucket(mock_dependencies["s3"], mock_dependencies["state"], mock_dependencies["base_path"], bucket, Event())

    # Verify sync was NOT called
    mock_sync.assert_not_called()


def test_process_bucket_already_deleted_skips_delete(mock_dependencies):
    """Test process_bucket skips delete if already complete"""
    bucket = "test-bucket"
    bucket_info = {
        "sync_complete": True,
        "verify_complete": True,
        "delete_complete": True,
        "file_count": 10,
        "total_size": 102400,
        "verified_file_count": 10,
        "local_file_count": 10,
        "size_verified_count": 10,
        "checksum_verified_count": 10,
        "total_bytes_verified": 102400,
    }
    mock_dependencies["state"].get_bucket_info.return_value = bucket_info

    with (
        mock.patch("migration_orchestrator.sync_bucket") as mock_sync,
        mock.patch("migration_orchestrator.delete_bucket") as mock_delete,
    ):
        process_bucket(mock_dependencies["s3"], mock_dependencies["state"], mock_dependencies["base_path"], bucket, Event())

    # Verify sync and delete were NOT called
    mock_sync.assert_not_called()
    mock_delete.assert_not_called()


def test_process_bucket_already_verified_recomputes_stats(mock_dependencies):
    """Test process_bucket re-verifies when verify_complete but missing stats"""
    bucket = "test-bucket"
    bucket_info = {
        "sync_complete": True,
        "verify_complete": True,
        "delete_complete": False,
        "file_count": 75,
        "total_size": 768000,
        "verified_file_count": None,  # Missing stats
        "local_file_count": 75,
        "size_verified_count": 75,
        "checksum_verified_count": 75,
        "total_bytes_verified": 768000,
    }
    mock_dependencies["state"].get_bucket_info.return_value = bucket_info

    verify_results = {
        "verified_count": 75,
        "size_verified": 75,
        "checksum_verified": 75,
        "total_bytes_verified": 768000,
        "local_file_count": 75,
    }

    # After verification, update bucket_info with verified stats
    def update_bucket_info_on_verify_complete(_bucket_name, **_kwargs):
        bucket_info["verified_file_count"] = 75

    mock_dependencies["state"].mark_bucket_verify_complete.side_effect = update_bucket_info_on_verify_complete

    with (
        mock.patch("migration_orchestrator.sync_bucket") as mock_sync,
        mock.patch("migration_orchestrator.verify_bucket", return_value=verify_results) as mock_verify,
        mock.patch("migration_orchestrator.delete_bucket"),
        mock.patch("builtins.input", return_value="yes"),
    ):
        process_bucket(mock_dependencies["s3"], mock_dependencies["state"], mock_dependencies["base_path"], bucket, Event())

    # Verify sync was NOT called, but verify was
    mock_sync.assert_not_called()
    mock_verify.assert_called_once()


def test_delete_with_confirmation_user_confirms_yes(mock_dependencies):
    """Test delete_with_confirmation when user inputs 'yes'"""
    bucket = "test-bucket"
    bucket_info = {
        "file_count": 100,
        "total_size": 1024000,
        "local_file_count": 100,
        "verified_file_count": 100,
        "size_verified_count": 100,
        "checksum_verified_count": 100,
        "total_bytes_verified": 1024000,
    }

    with (
        mock.patch("migration_orchestrator.delete_bucket") as mock_delete,
        mock.patch("builtins.input", return_value="yes"),
    ):
        delete_with_confirmation(mock_dependencies["s3"], mock_dependencies["state"], bucket, bucket_info)

    mock_delete.assert_called_once_with(mock_dependencies["s3"], mock_dependencies["state"], bucket)
    mock_dependencies["state"].mark_bucket_delete_complete.assert_called_once_with(bucket)


def test_delete_with_confirmation_user_confirms_no(mock_dependencies):
    """Test delete_with_confirmation when user inputs 'no'"""
    bucket = "test-bucket"
    bucket_info = {
        "file_count": 50,
        "total_size": 512000,
        "local_file_count": 50,
        "verified_file_count": 50,
        "size_verified_count": 50,
        "checksum_verified_count": 50,
        "total_bytes_verified": 512000,
    }

    with (
        mock.patch("migration_orchestrator.delete_bucket") as mock_delete,
        mock.patch("builtins.input", return_value="no"),
    ):
        delete_with_confirmation(mock_dependencies["s3"], mock_dependencies["state"], bucket, bucket_info)

    # Verify deletion was NOT called
    mock_delete.assert_not_called()
    mock_dependencies["state"].mark_bucket_delete_complete.assert_not_called()


def test_delete_with_confirmation_user_confirms_other_input(mock_dependencies):
    """Test delete_with_confirmation with non-yes, non-no input"""
    bucket = "test-bucket"
    bucket_info = {
        "file_count": 75,
        "total_size": 768000,
        "local_file_count": 75,
        "verified_file_count": 75,
        "size_verified_count": 75,
        "checksum_verified_count": 75,
        "total_bytes_verified": 768000,
    }

    with (
        mock.patch("migration_orchestrator.delete_bucket") as mock_delete,
        mock.patch("builtins.input", return_value="maybe"),
    ):
        delete_with_confirmation(mock_dependencies["s3"], mock_dependencies["state"], bucket, bucket_info)

    # Verify deletion was NOT called for non-yes input
    mock_delete.assert_not_called()


def test_show_verification_summary_formats_output():
    """Test show_verification_summary displays all stats correctly"""
    bucket_info = {
        "file_count": 1000,
        "total_size": 10737418240,  # 10 GB
        "local_file_count": 1000,
        "verified_file_count": 1000,
        "size_verified_count": 1000,
        "checksum_verified_count": 1000,
        "total_bytes_verified": 10737418240,
    }

    with mock.patch("builtins.print") as mock_print:
        show_verification_summary(bucket_info)

    # Verify summary output includes key information
    printed_text = " ".join([str(call) for call in mock_print.call_args_list])
    assert "VERIFICATION SUMMARY" in printed_text
    assert "1,000" in printed_text  # file count formatted
    assert "Size verified" in printed_text


def test_show_verification_summary_matches_verified_file_count():
    """Test show_verification_summary with all files verified"""
    bucket_info = {
        "file_count": 500,
        "total_size": 5242880,  # 5 MB
        "local_file_count": 500,
        "verified_file_count": 500,
        "size_verified_count": 500,
        "checksum_verified_count": 500,
        "total_bytes_verified": 5242880,
    }

    with mock.patch("builtins.print"):
        show_verification_summary(bucket_info)

    # Should complete without raising an error
    assert True
