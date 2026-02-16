"""Unit tests for S3MigrationV2 signal handling and interruption in migrate_v2.py.

Tests cover:
- Signal handler integration
- Interruption handling during migration
"""

import signal

import pytest

from migration_state_v2 import Phase


def test_signal_handler_sets_interrupted_event(migrator):
    """Signal handler sets the interrupted Event."""
    with pytest.raises(SystemExit):
        migrator.signal_handler(signal.SIGINT, None)

    # Verify the Event is set
    assert migrator.interrupted.is_set()


def test_run_handles_interrupted_scanning(migrator, mock_dependencies):
    """run() handles interruption during scanning."""
    called = []

    # Set up to interrupt during scanning
    def interrupt_during_scan(s3, state, interrupted):
        interrupted.set()
        called.append("scan")

    mock_dependencies["state"].get_current_phase.return_value = Phase.SCANNING

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("migrate_v2.scan_all_buckets", interrupt_during_scan)
        mp.setattr("migrate_v2.request_all_restores", lambda s3, state, interrupted: called.append("restore"))
        mp.setattr("migrate_v2.wait_for_restores", lambda s3, state, interrupted: called.append("wait"))
        mp.setattr("migrate_v2.migrate_all_buckets", lambda s3, state, base_path, drive_checker, interrupted: called.append("migrate"))
        mp.setattr("migrate_v2.check_drive_available", lambda base_path: None)
        mp.setattr("shutil.which", lambda cmd: "/usr/bin/aws")
        migrator.run()

    # Scanner should have been called
    assert "scan" in called
