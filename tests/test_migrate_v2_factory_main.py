"""Unit tests for factory function and main entry point in migrate_v2.py.

Tests cover:
- create_migrator factory function
- main entry point with argparse handling
- Edge cases for main() function
"""

import sys
from unittest import mock

import pytest

from migrate_v2 import S3MigrationV2, create_migrator, main


class TestCreateMigrator:
    """Tests for create_migrator factory function."""

    @pytest.fixture
    def mock_config(self):
        """Mock config module."""
        with mock.patch("migrate_v2.config") as mock_cfg:
            mock_cfg.STATE_DB_PATH = "/tmp/state.db"
            mock_cfg.LOCAL_BASE_PATH = "/tmp/s3_backup"
            yield mock_cfg

    def test_create_migrator_returns_s3_migration_v2(self):
        """create_migrator returns S3MigrationV2 instance."""
        with (
            mock.patch("migrate_v2.MigrationStateV2"),
            mock.patch("migrate_v2.boto3.client"),
            mock.patch("migrate_v2.Path"),
        ):
            migrator = create_migrator()

            assert isinstance(migrator, S3MigrationV2)
            assert migrator.s3 is not None
            assert migrator.state is not None
            assert migrator.base_path is not None

    def test_create_migrator_instantiates_all_dependencies(self, mock_config):
        """create_migrator creates all required dependencies."""
        with (
            mock.patch("migrate_v2.MigrationStateV2") as mock_state_class,
            mock.patch("migrate_v2.boto3.client") as mock_boto3,
            mock.patch("migrate_v2.Path"),
        ):

            create_migrator()

            # Verify core dependencies were instantiated
            mock_state_class.assert_called_once_with(mock_config.STATE_DB_PATH)
            mock_boto3.assert_called_once_with("s3")


class TestMain:
    """Tests for main entry point."""

    @pytest.fixture
    def mock_migrator(self):
        """Mock migrator instance."""
        with mock.patch("migrate_v2.create_migrator") as mock_create:
            mock_migrator_instance = mock.Mock(spec=S3MigrationV2)
            mock_create.return_value = mock_migrator_instance
            yield mock_migrator_instance

    def test_main_no_command_runs_migration(self, mock_migrator, monkeypatch):
        """main() runs migration when no command provided."""
        monkeypatch.setattr(sys, "argv", ["migrate_v2.py"])

        main()

        mock_migrator.run.assert_called_once()
        mock_migrator.show_status.assert_not_called()
        mock_migrator.reset.assert_not_called()

    def test_main_status_command_shows_status(self, mock_migrator, monkeypatch):
        """main() shows status when 'status' command provided."""
        monkeypatch.setattr(sys, "argv", ["migrate_v2.py", "status"])

        main()

        mock_migrator.show_status.assert_called_once()
        mock_migrator.run.assert_not_called()
        mock_migrator.reset.assert_not_called()

    def test_main_reset_command_resets_state(self, mock_migrator, monkeypatch):
        """main() resets state when 'reset' command provided."""
        monkeypatch.setattr(sys, "argv", ["migrate_v2.py", "reset"])

        main()

        mock_migrator.reset.assert_called_once()
        mock_migrator.run.assert_not_called()
        mock_migrator.show_status.assert_not_called()

    def test_main_creates_migrator(self, monkeypatch):
        """main() creates migrator instance."""
        monkeypatch.setattr(sys, "argv", ["migrate_v2.py"])

        with mock.patch("migrate_v2.create_migrator") as mock_create:
            mock_create.return_value = mock.Mock(spec=S3MigrationV2)
            main()

            mock_create.assert_called_once()

    def test_main_help_text(self, capsys, monkeypatch):
        """main() displays help with -h flag."""
        monkeypatch.setattr(sys, "argv", ["migrate_v2.py", "-h"])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "S3 Bucket Migration Tool V2" in captured.out


class TestMainEdgeCases:
    """Tests for edge cases in main entry point."""

    def test_main_with_empty_args(self, monkeypatch):
        """main() runs migration with no command specified."""
        monkeypatch.setattr(sys, "argv", ["migrate_v2.py"])

        with mock.patch("migrate_v2.create_migrator") as mock_create:
            mock_migrator_instance = mock.Mock(spec=S3MigrationV2)
            mock_create.return_value = mock_migrator_instance

            main()

            mock_migrator_instance.run.assert_called_once()

    def test_main_parser_accepts_valid_commands(self, monkeypatch):
        """main() parser accepts status and reset commands."""
        for command in ["status", "reset"]:
            monkeypatch.setattr(sys, "argv", ["migrate_v2.py", command])

            with mock.patch("migrate_v2.create_migrator") as mock_create:
                mock_migrator_instance = mock.Mock(spec=S3MigrationV2)
                mock_create.return_value = mock_migrator_instance

                # Should not raise
                main()
