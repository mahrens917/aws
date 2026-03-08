"""Unit tests for DatabaseConnection class from migration_state_v2.py."""

import sqlite3
from pathlib import Path

import pytest

from migration_state_managers import PhaseManager
from migration_state_v2 import DatabaseConnection


def test_database_connection_initialization(tmp_path: Path):
    """DatabaseConnection initializes with database path."""
    db_path = tmp_path / "test.db"
    db_conn = DatabaseConnection(str(db_path))

    assert db_conn.db_path == str(db_path)
    assert db_path.exists()


def test_database_connection_context_manager(tmp_path: Path):
    """DatabaseConnection.get_connection works as context manager."""
    db_path = tmp_path / "test.db"
    db_conn = DatabaseConnection(str(db_path))

    with db_conn.get_connection() as conn:
        assert isinstance(conn, sqlite3.Connection)
        assert conn.row_factory == sqlite3.Row


def test_database_connection_closes_properly(tmp_path: Path):
    """DatabaseConnection properly closes connections."""
    db_path = tmp_path / "test.db"
    db_conn = DatabaseConnection(str(db_path))

    with db_conn.get_connection() as conn:
        pass

    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_schema_files_table_created(tmp_path: Path):
    """DatabaseConnection creates files table."""
    db_path = tmp_path / "test.db"
    db_conn = DatabaseConnection(str(db_path))

    with db_conn.get_connection() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files'")
        assert cursor.fetchone() is not None


def test_schema_bucket_status_table_created(tmp_path: Path):
    """DatabaseConnection creates bucket_status table."""
    db_path = tmp_path / "test.db"
    db_conn = DatabaseConnection(str(db_path))

    with db_conn.get_connection() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bucket_status'")
        assert cursor.fetchone() is not None


def test_schema_migration_metadata_table_created(tmp_path: Path):
    """DatabaseConnection creates migration_metadata table."""
    db_path = tmp_path / "test.db"
    db_conn = DatabaseConnection(str(db_path))

    with db_conn.get_connection() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='migration_metadata'")
        assert cursor.fetchone() is not None


def test_schema_indices_created(tmp_path: Path):
    """DatabaseConnection creates required indices."""
    db_path = tmp_path / "test.db"
    db_conn = DatabaseConnection(str(db_path))

    with db_conn.get_connection() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indices = {row[0] for row in cursor.fetchall()}

        assert "idx_files_state" in indices
        assert "idx_files_storage_class" in indices
        assert "idx_files_bucket" in indices


def test_database_schema_migration_idempotent(tmp_path: Path):
    """DatabaseConnection schema migration is idempotent."""
    db_path = tmp_path / "test.db"

    _db_conn1 = DatabaseConnection(str(db_path))
    db_conn2 = DatabaseConnection(str(db_path))

    with db_conn2.get_connection() as conn:
        cursor = conn.execute("PRAGMA table_info(bucket_status)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "verified_file_count" in columns


def test_files_table_columns(tmp_path: Path):
    """Files table has all expected columns."""
    db_path = tmp_path / "test.db"
    db_conn = DatabaseConnection(str(db_path))

    with db_conn.get_connection() as conn:
        cursor = conn.execute("PRAGMA table_info(files)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {
            "bucket",
            "key",
            "size",
            "etag",
            "storage_class",
            "last_modified",
            "local_path",
            "local_checksum",
            "state",
            "error_message",
            "glacier_restore_requested_at",
            "glacier_restored_at",
            "created_at",
            "updated_at",
        }
        assert expected_columns.issubset(columns)


def test_bucket_status_table_columns(tmp_path: Path):
    """Bucket_status table has all expected columns."""
    db_path = tmp_path / "test.db"
    db_conn = DatabaseConnection(str(db_path))

    with db_conn.get_connection() as conn:
        cursor = conn.execute("PRAGMA table_info(bucket_status)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {
            "bucket",
            "file_count",
            "total_size",
            "storage_class_counts",
            "scan_complete",
            "sync_complete",
            "verify_complete",
            "delete_complete",
            "local_file_count",
            "verified_file_count",
            "size_verified_count",
            "checksum_verified_count",
            "total_bytes_verified",
            "created_at",
            "updated_at",
        }
        assert expected_columns.issubset(columns)


def test_migration_metadata_table_columns(tmp_path: Path):
    """Migration_metadata table has expected columns."""
    db_path = tmp_path / "test.db"
    db_conn = DatabaseConnection(str(db_path))

    with db_conn.get_connection() as conn:
        cursor = conn.execute("PRAGMA table_info(migration_metadata)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {"key", "value", "updated_at"}
        assert expected_columns.issubset(columns)


def test_phase_manager_raises_when_phase_missing(tmp_path: Path):
    """PhaseManager should fail fast when phase metadata is absent."""
    db_path = tmp_path / "test.db"
    db_conn = DatabaseConnection(str(db_path))
    phase_manager = PhaseManager(db_conn)

    with db_conn.get_connection() as conn:
        conn.execute("DELETE FROM migration_metadata WHERE key = 'current_phase'")
        conn.commit()

    with pytest.raises(RuntimeError):
        phase_manager.get_current_phase()
