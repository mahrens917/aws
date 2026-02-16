"""Unit tests for S3MigrationV2 core functionality in migrate_v2.py.

Tests cover:
- S3MigrationV2 initialization
- Signal handler
- run() method for all phases
- Phase transitions and state management
"""

import signal

import pytest

from migration_state_v2 import Phase


class TestS3MigrationV2Initialization:
    """Tests for S3MigrationV2 initialization."""

    def test_dependencies_are_wired(self, migrator, mock_dependencies):
        """S3MigrationV2 stores the provided dependencies unchanged."""
        assert migrator.s3 == mock_dependencies["s3"]
        assert migrator.state == mock_dependencies["state"]
        assert migrator.base_path == mock_dependencies["base_path"]

    def test_initial_interrupted_flag_is_not_set(self, migrator):
        """S3MigrationV2 starts in a non-interrupted state."""
        assert not migrator.interrupted.is_set()


def test_signal_handler_sets_interrupted_event(migrator):
    """Signal handler sets interrupted Event."""
    with pytest.raises(SystemExit) as exc_info:
        migrator.signal_handler(signal.SIGINT, None)

    assert exc_info.value.code == 0
    assert migrator.interrupted.is_set()


def test_signal_handler_prints_message(migrator, capsys):
    """Signal handler prints interruption message."""
    with pytest.raises(SystemExit):
        migrator.signal_handler(signal.SIGINT, None)

    captured = capsys.readouterr()
    assert "MIGRATION INTERRUPTED" in captured.out
    assert "State has been saved" in captured.out


def test_run_already_complete(migrator, mock_dependencies, capsys):
    """run() shows completion message when already complete."""
    mock_dependencies["state"].get_current_phase.return_value = Phase.COMPLETE

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("migrate_v2.check_drive_available", lambda base_path: None)
        mp.setattr("migrate_v2.show_migration_status", lambda state: None)
        mp.setattr("shutil.which", lambda cmd: "/usr/bin/aws")
        migrator.run()

    captured = capsys.readouterr()
    assert "Migration already complete" in captured.out


def test_run_from_scanning_phase(migrator, mock_dependencies, capsys):
    """run() executes all phases starting from SCANNING."""
    mock_dependencies["state"].get_current_phase.side_effect = [
        Phase.SCANNING,
        Phase.SYNCING,
        Phase.COMPLETE,
    ]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("migrate_v2.scan_all_buckets", lambda s3, state, interrupted: None)
        mp.setattr("migrate_v2.request_all_restores", lambda s3, state, interrupted: None)
        mp.setattr("migrate_v2.wait_for_restores", lambda s3, state, interrupted: None)
        mp.setattr("migrate_v2.migrate_all_buckets", lambda s3, state, base_path, drive_checker, interrupted: None)
        mp.setattr("migrate_v2.check_drive_available", lambda base_path: None)
        mp.setattr("shutil.which", lambda cmd: "/usr/bin/aws")
        migrator.run()

    captured = capsys.readouterr()
    assert "S3 MIGRATION V2" in captured.out


def test_run_calls_check_drive_available(migrator, mock_dependencies):
    """run() calls check_drive_available before starting."""
    mock_dependencies["state"].get_current_phase.return_value = Phase.COMPLETE
    called = []

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("migrate_v2.check_drive_available", lambda base_path: called.append(base_path))
        mp.setattr("migrate_v2.show_migration_status", lambda state: None)
        mp.setattr("shutil.which", lambda cmd: "/usr/bin/aws")
        migrator.run()

    assert len(called) == 1


def test_show_status(migrator, mock_dependencies):
    """show_status() delegates to show_migration_status."""
    called = []

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("migrate_v2.show_migration_status", lambda state: called.append(state))
        migrator.show_status()

    assert len(called) == 1
    assert called[0] == mock_dependencies["state"]
