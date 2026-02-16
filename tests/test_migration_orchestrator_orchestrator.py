"""Unit tests for migrate_all_buckets function from migration_orchestrator.py

Tests cover:
- Multi-bucket migration orchestration
- Error handling for drive and migration errors
- Completion status reporting
"""

from threading import Event
from unittest import mock

import pytest

from migration_orchestrator import (
    MigrationFatalError,
    _print_completion_status,
    handle_drive_error,
    handle_migration_error,
    migrate_all_buckets,
)
from migration_state_v2 import Phase
from tests.assertions import assert_equal


@pytest.fixture
def mock_dependencies(tmp_path):
    """Create mock dependencies"""
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


class TestOrchestratorBasicMigration:
    """Tests for basic multi-bucket migration orchestration"""

    def test_migrate_all_buckets_single_bucket(self, mock_dependencies):
        """Test migrate_all_buckets with single bucket"""
        mock_dependencies["state"].get_all_buckets.return_value = ["bucket-1"]
        mock_dependencies["state"].get_completed_buckets_for_phase.return_value = []

        with (
            mock.patch("builtins.print"),
            mock.patch("migration_orchestrator.process_bucket") as mock_process,
        ):
            migrate_all_buckets(
                mock_dependencies["s3"],
                mock_dependencies["state"],
                mock_dependencies["base_path"],
                mock_dependencies["drive_checker"],
                Event(),
            )

        mock_dependencies["drive_checker"].assert_called_once()
        mock_process.assert_called_once()

    def test_migrate_all_buckets_multiple_buckets(self, mock_dependencies):
        """Test migrate_all_buckets with multiple buckets"""
        buckets = ["bucket-1", "bucket-2", "bucket-3"]
        mock_dependencies["state"].get_all_buckets.return_value = buckets
        mock_dependencies["state"].get_completed_buckets_for_phase.return_value = []

        with (
            mock.patch("builtins.print"),
            mock.patch("migration_orchestrator.process_bucket") as mock_process,
        ):
            migrate_all_buckets(
                mock_dependencies["s3"],
                mock_dependencies["state"],
                mock_dependencies["base_path"],
                mock_dependencies["drive_checker"],
                Event(),
            )

        assert_equal(mock_process.call_count, 3)


class TestOrchestratorCompletedBuckets:
    """Tests for orchestrator handling of already-completed buckets"""

    def test_migrate_all_buckets_skips_already_completed(self, mock_dependencies):
        """Test migrate_all_buckets skips already completed buckets"""
        all_buckets = ["bucket-1", "bucket-2"]
        completed_buckets = ["bucket-1"]
        mock_dependencies["state"].get_all_buckets.return_value = all_buckets
        mock_dependencies["state"].get_completed_buckets_for_phase.return_value = completed_buckets

        with (
            mock.patch("builtins.print"),
            mock.patch("migration_orchestrator.process_bucket") as mock_process,
        ):
            migrate_all_buckets(
                mock_dependencies["s3"],
                mock_dependencies["state"],
                mock_dependencies["base_path"],
                mock_dependencies["drive_checker"],
                Event(),
            )

        # Only bucket-2 should be processed
        mock_process.assert_called_once()

    def test_migrate_all_buckets_all_already_complete(self, mock_dependencies):
        """Test migrate_all_buckets when all buckets are complete"""
        all_buckets = ["bucket-1", "bucket-2"]
        mock_dependencies["state"].get_all_buckets.return_value = all_buckets
        mock_dependencies["state"].get_completed_buckets_for_phase.return_value = all_buckets

        with mock.patch("builtins.print") as mock_print:
            migrate_all_buckets(
                mock_dependencies["s3"],
                mock_dependencies["state"],
                mock_dependencies["base_path"],
                mock_dependencies["drive_checker"],
                Event(),
            )

        printed_text = " ".join([str(call) for call in mock_print.call_args_list])
        assert "already migrated" in printed_text


class TestOrchestratorInterruption:
    """Tests for orchestrator interruption handling"""

    def __repr__(self):
        return f"{self.__class__.__name__}()"

    def test_migrate_all_buckets_respects_interrupted_flag(self, mock_dependencies):
        """Test migrate_all_buckets stops when interrupted"""
        all_buckets = ["bucket-1", "bucket-2", "bucket-3"]
        mock_dependencies["state"].get_all_buckets.return_value = all_buckets
        mock_dependencies["state"].get_completed_buckets_for_phase.return_value = []

        interrupted = Event()

        # Set interrupted flag during processing
        def side_effect(*_args, **_kwargs):
            interrupted.set()

        with (
            mock.patch("builtins.print"),
            mock.patch("migration_orchestrator.process_bucket", side_effect=side_effect) as mock_process,
        ):
            migrate_all_buckets(
                mock_dependencies["s3"],
                mock_dependencies["state"],
                mock_dependencies["base_path"],
                mock_dependencies["drive_checker"],
                interrupted,
            )

        # Only first bucket should be processed before interruption
        assert mock_process.call_count == 1


class TestSingleBucketDriveErrors:
    """Tests for single bucket migration drive error handling"""

    def test_migrate_single_bucket_handles_file_not_found_error(self, mock_dependencies):
        """Test _migrate_single_bucket handles FileNotFoundError"""
        mock_dependencies["state"].get_all_buckets.return_value = ["bucket-1"]
        mock_dependencies["state"].get_completed_buckets_for_phase.return_value = []

        with (
            mock.patch("builtins.print"),
            mock.patch("migration_orchestrator.process_bucket", side_effect=FileNotFoundError("Local path not found")),
        ):
            with pytest.raises(MigrationFatalError) as exc_info:
                migrate_all_buckets(
                    mock_dependencies["s3"],
                    mock_dependencies["state"],
                    mock_dependencies["base_path"],
                    mock_dependencies["drive_checker"],
                    Event(),
                )

        assert "Drive error" in str(exc_info.value)

    def test_migrate_single_bucket_handles_permission_error(self, mock_dependencies):
        """Test _migrate_single_bucket handles PermissionError"""
        mock_dependencies["state"].get_all_buckets.return_value = ["bucket-1"]
        mock_dependencies["state"].get_completed_buckets_for_phase.return_value = []

        with (
            mock.patch("builtins.print"),
            mock.patch("migration_orchestrator.process_bucket", side_effect=PermissionError("Permission denied")),
        ):
            with pytest.raises(MigrationFatalError) as exc_info:
                migrate_all_buckets(
                    mock_dependencies["s3"],
                    mock_dependencies["state"],
                    mock_dependencies["base_path"],
                    mock_dependencies["drive_checker"],
                    Event(),
                )

        assert "Drive error" in str(exc_info.value)


class TestSingleBucketMigrationErrors:
    """Tests for single bucket migration error handling"""

    def test_migrate_single_bucket_handles_runtime_error(self, mock_dependencies):
        """Test _migrate_single_bucket handles RuntimeError from migration"""
        mock_dependencies["state"].get_all_buckets.return_value = ["bucket-1"]
        mock_dependencies["state"].get_completed_buckets_for_phase.return_value = []

        with (
            mock.patch("builtins.print"),
            mock.patch("migration_orchestrator.process_bucket", side_effect=RuntimeError("Sync failed")),
        ):
            with pytest.raises(MigrationFatalError) as exc_info:
                migrate_all_buckets(
                    mock_dependencies["s3"],
                    mock_dependencies["state"],
                    mock_dependencies["base_path"],
                    mock_dependencies["drive_checker"],
                    Event(),
                )

        assert "Migration error" in str(exc_info.value)


class TestErrorHandlers:
    """Tests for global error handler functions"""

    def test_handle_drive_error_prints_error_message(self):
        """Test handle_drive_error prints proper error message"""
        error = FileNotFoundError("Drive not found")

        with mock.patch("builtins.print") as mock_print:
            with pytest.raises(MigrationFatalError) as exc_info:
                handle_drive_error(error)

        assert "Drive error" in str(exc_info.value)
        printed_text = " ".join([str(call) for call in mock_print.call_args_list])
        assert "Drive error" in printed_text
        assert "MIGRATION INTERRUPTED" in printed_text

    def test_handle_migration_error_prints_error_details(self):
        """Test handle_migration_error prints error details"""
        error = RuntimeError("Sync failed")
        bucket = "test-bucket"

        with mock.patch("builtins.print") as mock_print:
            with pytest.raises(MigrationFatalError) as exc_info:
                handle_migration_error(bucket, error)

        assert "Migration error" in str(exc_info.value)
        printed_text = " ".join([str(call) for call in mock_print.call_args_list])
        assert "MIGRATION STOPPED" in printed_text
        assert "test-bucket" in printed_text


class TestCompletionStatusReporting:
    """Tests for completion status reporting"""

    def test_print_completion_status_all_complete(self, mock_dependencies):
        """Test _print_completion_status when all buckets complete"""
        all_buckets = ["bucket-1", "bucket-2"]
        mock_dependencies["state"].get_completed_buckets_for_phase.return_value = all_buckets

        with mock.patch("builtins.print") as mock_print:
            _print_completion_status(mock_dependencies["state"], all_buckets)

        mock_dependencies["state"].set_current_phase.assert_called_once_with(Phase.COMPLETE)
        printed_text = " ".join([str(call) for call in mock_print.call_args_list])
        assert "PHASE 4 COMPLETE" in printed_text

    def test_print_completion_status_partial_complete(self, mock_dependencies):
        """Test _print_completion_status when some buckets remain"""
        all_buckets = ["bucket-1", "bucket-2", "bucket-3"]
        completed_buckets = ["bucket-1"]
        mock_dependencies["state"].get_completed_buckets_for_phase.return_value = completed_buckets

        with mock.patch("builtins.print") as mock_print:
            _print_completion_status(mock_dependencies["state"], all_buckets)

        mock_dependencies["state"].set_current_phase.assert_not_called()
        printed_text = " ".join([str(call) for call in mock_print.call_args_list])
        assert "MIGRATION PAUSED" in printed_text
        assert "Completed: 1/3" in printed_text
        assert "Remaining: 2" in printed_text
