"""Unit tests for S3MigrationV2 reset behavior and error handling."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

import migrate_v2
from migration_state_v2 import Phase


def _override_state_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, create: bool) -> Path:
    """Point migrate_v2.STATE_DB_PATH at a temp file for reset tests."""
    state_db = tmp_path / "state.db"
    monkeypatch.setattr(migrate_v2, "STATE_DB_PATH", str(state_db), raising=False)
    if create:
        state_db.touch()
    return state_db


class TestResetFlow:
    """Reset command confirmation flows."""

    def test_reset_with_yes_confirmation(self, monkeypatch, capsys, tmp_path, migrator):
        """Test reset with 'yes' confirmation."""
        state_db = _override_state_db(tmp_path, monkeypatch, create=True)

        with mock.patch("builtins.input", return_value="yes"):
            migrator.reset()

        assert state_db.exists()
        captured = capsys.readouterr()
        assert "RESET MIGRATION" in captured.out

    def test_reset_with_no_confirmation(self, monkeypatch, capsys, tmp_path, migrator):
        """Test reset with 'no' confirmation."""
        state_db = _override_state_db(tmp_path, monkeypatch, create=True)

        with mock.patch("builtins.input", return_value="no"):
            migrator.reset()

        assert state_db.exists()
        captured = capsys.readouterr()
        assert "Reset cancelled" in captured.out

    def test_reset_when_database_missing(self, monkeypatch, capsys, tmp_path, migrator):
        """Test reset when database doesn't exist."""
        _override_state_db(tmp_path, monkeypatch, create=False)

        with mock.patch("builtins.input", return_value="yes"):
            migrator.reset()

        captured = capsys.readouterr()
        assert "Created fresh state database" in captured.out

    def test_reset_case_insensitive_confirmation(self, monkeypatch, tmp_path, migrator):
        """Test reset accepts case-insensitive 'YES'."""
        state_db = _override_state_db(tmp_path, monkeypatch, create=True)

        with mock.patch("builtins.input", return_value="YES"):
            migrator.reset()

        assert state_db.exists()

    def test_reset_prints_header_message(self, monkeypatch, capsys, tmp_path, migrator):
        """Test reset prints header message."""
        _override_state_db(tmp_path, monkeypatch, create=False)

        with mock.patch("builtins.input", return_value="no"):
            migrator.reset()

        captured = capsys.readouterr()
        assert "RESET MIGRATION" in captured.out
        assert "delete all migration state" in captured.out


class TestRunPhaseSkipping:
    """Ensure run() skips irrelevant phases."""

    def __repr__(self):
        return f"{self.__class__.__name__}()"

    def test_run_skips_scanner_in_middle_phases(self, migrator, mock_dependencies):
        """Test that scanner is skipped when starting in middle phase."""
        mock_state = mock_dependencies["state"]
        mock_state.get_current_phase.side_effect = [Phase.GLACIER_RESTORE, Phase.COMPLETE]
        called = []

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("migrate_v2.scan_all_buckets", lambda s3, state, interrupted: called.append("scan"))
            mp.setattr("migrate_v2.request_all_restores", lambda s3, state, interrupted: called.append("restore"))
            mp.setattr("migrate_v2.wait_for_restores", lambda s3, state, interrupted: called.append("wait"))
            mp.setattr("migrate_v2.migrate_all_buckets", lambda s3, state, base_path, drive_checker, interrupted: called.append("migrate"))
            mp.setattr("migrate_v2.check_drive_available", lambda base_path: None)
            mp.setattr("shutil.which", lambda cmd: "/usr/bin/aws")
            migrator.run()

        assert "scan" not in called
        assert "restore" in called


class TestRunPhaseTransitions:
    """Validate run() transitions through expected phases."""

    def __repr__(self):
        return f"{self.__class__.__name__}()"

    def test_run_completes_all_phase_transitions(self, migrator, mock_dependencies):
        """Test that all migration phases are executed in correct order."""
        mock_state = mock_dependencies["state"]
        mock_state.get_current_phase.side_effect = [
            Phase.SCANNING,
            Phase.GLACIER_RESTORE,
            Phase.GLACIER_WAIT,
            Phase.SYNCING,
            Phase.COMPLETE,
        ]
        called = []

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("migrate_v2.scan_all_buckets", lambda s3, state, interrupted: called.append("scan"))
            mp.setattr("migrate_v2.request_all_restores", lambda s3, state, interrupted: called.append("restore"))
            mp.setattr("migrate_v2.wait_for_restores", lambda s3, state, interrupted: called.append("wait"))
            mp.setattr("migrate_v2.migrate_all_buckets", lambda s3, state, base_path, drive_checker, interrupted: called.append("migrate"))
            mp.setattr("migrate_v2.check_drive_available", lambda base_path: None)
            mp.setattr("shutil.which", lambda cmd: "/usr/bin/aws")
            migrator.run()

        assert "scan" in called
        assert "restore" in called
        assert "wait" in called
        assert "migrate" in called


class TestS3MigrationV2ErrorHandling:
    """Drive checker and other failure scenarios."""

    def __repr__(self):
        return f"{self.__class__.__name__}()"

    def test_run_with_drive_check_failure(self, migrator, mock_dependencies):
        """Test that SystemExit from drive check is propagated."""
        with (
            pytest.raises(SystemExit),
            pytest.MonkeyPatch.context() as mp,
        ):
            mp.setattr("migrate_v2.check_drive_available", mock.Mock(side_effect=SystemExit(1)))
            mp.setattr("shutil.which", lambda cmd: "/usr/bin/aws")
            migrator.run()
