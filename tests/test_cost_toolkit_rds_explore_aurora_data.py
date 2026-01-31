"""Comprehensive tests for cost_toolkit/scripts/rds/explore_aurora_data.py."""

from __future__ import annotations

from unittest import mock
from unittest.mock import patch

import pytest

from cost_toolkit.scripts.rds import explore_aurora_data
from tests.conftest_rds_shared import (
    TestConstantsShared,
    TestParseRequiredPortShared,
    TestRequireEnvVarShared,
)

EXPLORE_MODULE = "cost_toolkit.scripts.rds.explore_aurora_data"

# Re-export shared test classes for aurora data module
TestConstants = TestConstantsShared
TestRequireEnvVar = TestRequireEnvVarShared
TestParseRequiredPort = TestParseRequiredPortShared


class TestExploreAuroraDatabase:
    """Tests for explore_aurora_database function.

    Note: Most psycopg2-dependent tests are simplified because psycopg2 is
    conditionally imported and complex mocking doesn't provide significant value.
    """

    @patch("cost_toolkit.scripts.rds.explore_aurora_data.PSYCOPG2_AVAILABLE", False)
    def test_psycopg2_not_available(self, capsys):
        """Test when psycopg2 is not available."""
        explore_aurora_data.explore_aurora_database()

        captured = capsys.readouterr()
        assert "psycopg2 module not found" in captured.out
        assert "pip install psycopg2-binary" in captured.out

    def test_function_exists(self):
        """Test that explore_aurora_database function exists."""
        assert hasattr(explore_aurora_data, "explore_aurora_database")
        assert callable(explore_aurora_data.explore_aurora_database)


@patch("cost_toolkit.scripts.rds.explore_aurora_data.explore_aurora_database")
def test_main_calls_explore(mock_explore):
    """Test that main calls explore_aurora_database."""
    explore_aurora_data.main()

    mock_explore.assert_called_once()


class TestLoadAuroraSettings:
    """Tests for _load_aurora_settings function."""

    def test_load_aurora_settings_complete(self):
        """Test loading complete Aurora settings."""
        env = {
            "AURORA_HOST": "aurora.example.com",
            "AURORA_PORT": "5432",
            "AURORA_DATABASE": "testdb",
            "AURORA_USERNAME": "admin",
            "AURORA_PASSWORD": "password123",
        }
        with patch.dict("os.environ", env):
            host, port, database, username, password = explore_aurora_data._load_aurora_settings()  # pylint: disable=protected-access
            assert host == "aurora.example.com"
            assert port == 5432
            assert database == "testdb"
            assert username == "admin"
            assert password == "password123"

    def test_load_aurora_settings_missing_host(self):
        """Test loading Aurora settings with missing HOST."""
        env = {
            "AURORA_PORT": "5432",
            "AURORA_DATABASE": "testdb",
            "AURORA_USERNAME": "admin",
            "AURORA_PASSWORD": "password123",
        }
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(RuntimeError, match="AURORA_HOST is required"):
                explore_aurora_data._load_aurora_settings()  # pylint: disable=protected-access


class TestExploreAuroraReturnValues:
    """Tests for explore_aurora_database return values."""

    @patch("cost_toolkit.scripts.rds.explore_aurora_data.PSYCOPG2_AVAILABLE", False)
    def test_explore_returns_false_when_psycopg2_unavailable(self):
        """Test that explore returns False when psycopg2 is unavailable."""
        result = explore_aurora_data.explore_aurora_database()
        assert result is False

    @patch("cost_toolkit.scripts.rds.explore_aurora_data.PSYCOPG2_AVAILABLE", True)
    @patch("cost_toolkit.scripts.rds.explore_aurora_data._load_aurora_settings")
    def test_explore_returns_false_when_password_missing(self, mock_load, capsys):
        """Test that explore returns False when password is empty."""
        mock_load.return_value = ("host", 5432, "db", "user", "")
        result = explore_aurora_data.explore_aurora_database()
        assert result is False
        captured = capsys.readouterr()
        assert "Aurora credentials not configured" in captured.out


class TestMainReturnCode:
    """Tests for main function return codes."""

    @patch("cost_toolkit.scripts.rds.explore_aurora_data.explore_aurora_database")
    def test_main_returns_zero_on_success(self, mock_explore):
        """Test that main returns 0 when explore succeeds."""
        mock_explore.return_value = True
        result = explore_aurora_data.main()
        assert result == 0

    @patch("cost_toolkit.scripts.rds.explore_aurora_data.explore_aurora_database")
    def test_main_returns_one_on_failure(self, mock_explore):
        """Test that main returns 1 when explore fails."""
        mock_explore.return_value = False
        result = explore_aurora_data.main()
        assert result == 1


class TestExploreWithSuccessfulConnection:
    """Tests for successful Aurora database connection."""

    @patch("cost_toolkit.scripts.rds.explore_aurora_data._load_aurora_settings")
    @patch("cost_toolkit.scripts.rds.explore_aurora_data._resolve_psycopg2")
    def test_explore_with_successful_connection(self, mock_resolve, mock_load):
        """Test explore_aurora_database with successful database connection."""
        mock_psycopg2 = mock.Mock()
        mock_connection = mock.Mock()
        mock_cursor = mock.Mock()
        mock_psycopg2.connect.return_value = mock_connection
        mock_connection.cursor.return_value = mock_cursor

        mock_resolve.return_value = mock_psycopg2
        mock_load.return_value = ("localhost", 5432, "testdb", "admin", "password")

        with patch(f"{EXPLORE_MODULE}.print_database_version_info"):
            with patch(f"{EXPLORE_MODULE}.list_databases"):
                with patch(f"{EXPLORE_MODULE}.list_schemas"):
                    with patch(f"{EXPLORE_MODULE}.list_tables", return_value=[]):
                        with patch(f"{EXPLORE_MODULE}.list_views"):
                            with patch(f"{EXPLORE_MODULE}.analyze_tables", return_value=0):
                                with patch(f"{EXPLORE_MODULE}.get_database_size"):
                                    with patch(f"{EXPLORE_MODULE}.list_functions"):
                                        result = explore_aurora_data.explore_aurora_database()

        assert result is True
        mock_connection.close.assert_called_once()
        mock_cursor.close.assert_called_once()


class TestExploreWithConnectionError:
    """Tests for Aurora database connection failures."""

    @patch("cost_toolkit.scripts.rds.explore_aurora_data._load_aurora_settings")
    @patch("cost_toolkit.scripts.rds.explore_aurora_data._resolve_psycopg2")
    def test_explore_connection_error(self, mock_resolve, mock_load, capsys):
        """Test explore_aurora_database with connection error."""
        mock_psycopg2 = mock.Mock()
        mock_psycopg2.Error = Exception
        mock_psycopg2.connect.side_effect = Exception("Connection failed")

        mock_resolve.return_value = mock_psycopg2
        mock_load.return_value = ("localhost", 5432, "testdb", "admin", "password")

        result = explore_aurora_data.explore_aurora_database()

        assert result is False
        captured = capsys.readouterr()
        assert "Connection failed" in captured.out


class TestExploreEmptyDatabase:
    """Tests for Aurora database exploration with no data."""

    @patch("cost_toolkit.scripts.rds.explore_aurora_data._load_aurora_settings")
    @patch("cost_toolkit.scripts.rds.explore_aurora_data._resolve_psycopg2")
    def test_explore_with_empty_database(self, mock_resolve, mock_load, capsys):
        """Test explore_aurora_database when database has no tables."""
        mock_psycopg2 = mock.Mock()
        mock_connection = mock.Mock()
        mock_cursor = mock.Mock()
        mock_psycopg2.connect.return_value = mock_connection
        mock_connection.cursor.return_value = mock_cursor

        mock_resolve.return_value = mock_psycopg2
        mock_load.return_value = ("localhost", 5432, "testdb", "admin", "password")

        with patch(f"{EXPLORE_MODULE}.print_database_version_info"):
            with patch(f"{EXPLORE_MODULE}.list_databases"):
                with patch(f"{EXPLORE_MODULE}.list_schemas"):
                    with patch(f"{EXPLORE_MODULE}.list_tables", return_value=[]):
                        with patch(f"{EXPLORE_MODULE}.list_views"):
                            with patch(f"{EXPLORE_MODULE}.analyze_tables", return_value=0):
                                with patch(f"{EXPLORE_MODULE}.get_database_size"):
                                    with patch(f"{EXPLORE_MODULE}.list_functions"):
                                        result = explore_aurora_data.explore_aurora_database()

        assert result is True
        captured = capsys.readouterr()
        assert "empty" in captured.out.lower() or "no user data" in captured.out.lower()


class TestExploreWithData:
    """Tests for Aurora database exploration with populated data."""

    @patch("cost_toolkit.scripts.rds.explore_aurora_data._load_aurora_settings")
    @patch("cost_toolkit.scripts.rds.explore_aurora_data._resolve_psycopg2")
    def test_explore_with_data_in_database(self, mock_resolve, mock_load, capsys):
        """Test explore_aurora_database when database contains data."""
        mock_psycopg2 = mock.Mock()
        mock_connection = mock.Mock()
        mock_cursor = mock.Mock()
        mock_psycopg2.connect.return_value = mock_connection
        mock_connection.cursor.return_value = mock_cursor

        mock_resolve.return_value = mock_psycopg2
        mock_load.return_value = ("localhost", 5432, "testdb", "admin", "password")

        with patch(f"{EXPLORE_MODULE}.print_database_version_info"):
            with patch(f"{EXPLORE_MODULE}.list_databases"):
                with patch(f"{EXPLORE_MODULE}.list_schemas"):
                    with patch(f"{EXPLORE_MODULE}.list_tables", return_value=[{"name": "test_table"}]):
                        with patch(f"{EXPLORE_MODULE}.list_views"):
                            with patch(f"{EXPLORE_MODULE}.analyze_tables", return_value=100):
                                with patch(f"{EXPLORE_MODULE}.get_database_size"):
                                    with patch(f"{EXPLORE_MODULE}.list_functions"):
                                        result = explore_aurora_data.explore_aurora_database()

        assert result is True
        captured = capsys.readouterr()
        assert "completed" in captured.out.lower()
