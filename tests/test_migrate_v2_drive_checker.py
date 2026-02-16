"""Unit tests for check_drive_available function in migrate_v2.py.

Tests cover:
- check_drive_available with various scenarios (parent exists, permission denied, etc.)
- Edge cases for check_drive_available
"""

from pathlib import Path
from unittest import mock

import pytest

from migrate_v2 import check_drive_available


class TestCheckDriveAvailable:
    """Tests for check_drive_available function."""

    def test_check_available_parent_does_not_exist(self, tmp_path, capsys):
        """check_drive_available exits when parent directory does not exist."""
        # Create a path whose parent doesn't exist
        base_path = tmp_path / "nonexistent" / "s3_backup"

        with pytest.raises(SystemExit) as exc_info:
            check_drive_available(base_path)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "DRIVE NOT AVAILABLE" in captured.out
        assert "Expected:" in captured.out

    def test_check_available_parent_exists_creates_directory(self, tmp_path):
        """check_drive_available creates base directory when parent exists."""
        base_path = tmp_path / "s3_backup"

        # Should not raise
        check_drive_available(base_path)

        # Directory should be created
        assert base_path.exists()
        assert base_path.is_dir()

    def test_check_available_directory_already_exists(self, tmp_path):
        """check_drive_available succeeds if directory already exists."""
        base_path = tmp_path / "s3_backup"
        base_path.mkdir(parents=True)

        # Should not raise
        check_drive_available(base_path)
        assert base_path.exists()

    def test_check_available_permission_denied(self, tmp_path, capsys):
        """check_drive_available exits when directory creation raises PermissionError."""
        base_path = tmp_path / "s3_backup"

        # Mock mkdir to raise PermissionError
        with mock.patch.object(Path, "mkdir", side_effect=PermissionError()):
            with pytest.raises(SystemExit) as exc_info:
                check_drive_available(base_path)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "PERMISSION DENIED" in captured.out
        assert "Cannot write to destination:" in captured.out


class TestCheckDriveAvailableEdgeCases:
    """Tests for edge cases in check_drive_available."""

    def test_check_available_creates_single_subdirectory(self, tmp_path):
        """check_drive_available creates single subdirectory under existing parent."""
        nested_path = tmp_path / "s3_backup"

        check_drive_available(nested_path)

        # Directory should be created
        assert nested_path.exists()
        # Parent must already exist (requirement of check_drive_available)
        assert nested_path.parent.exists()

    def test_check_available_idempotent(self, tmp_path):
        """check_drive_available can be called multiple times safely."""
        base_path = tmp_path / "s3_backup"

        # Call twice
        check_drive_available(base_path)
        check_drive_available(base_path)

        # Should still exist
        assert base_path.exists()
