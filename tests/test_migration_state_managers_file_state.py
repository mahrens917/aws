"""Unit tests for FileStateManager from migration_state_managers.py"""

# pylint: disable=redefined-outer-name  # pytest fixtures

from datetime import datetime, timezone

import pytest

from migration_state_managers import FileMetadata, FileStateManager
from tests.assertions import assert_equal


@pytest.fixture
def file_mgr(db_conn):
    """Create FileStateManager instance"""
    return FileStateManager(db_conn)


def test_add_file_inserts_file_record(file_mgr, db_conn):
    """Test adding a file to the database"""
    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="path/to/file.txt",
            size=1024,
            etag="abc123",
            storage_class="STANDARD",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    with db_conn.get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM files WHERE bucket = ? AND key = ?",
            ("test-bucket", "path/to/file.txt"),
        ).fetchone()

    assert row is not None
    assert row["bucket"] == "test-bucket"
    assert row["key"] == "path/to/file.txt"
    assert_equal(row["size"], 1024)
    assert row["etag"] == "abc123"
    assert row["storage_class"] == "STANDARD"
    assert row["state"] == "discovered"


def test_add_file_is_idempotent(file_mgr, db_conn):
    """Test that adding the same file twice doesn't raise an error"""
    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="path/to/file.txt",
            size=1024,
            etag="abc123",
            storage_class="STANDARD",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="path/to/file.txt",
            size=1024,
            etag="abc123",
            storage_class="STANDARD",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    with db_conn.get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM files WHERE bucket = ? AND key = ?",
            ("test-bucket", "path/to/file.txt"),
        ).fetchone()

    assert_equal(count["cnt"], 1)


def test_add_file_sets_timestamps(file_mgr, db_conn):
    """Test that created_at and updated_at are set"""
    before_time = datetime.now(timezone.utc).isoformat()
    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="file.txt",
            size=100,
            etag="def456",
            storage_class="STANDARD",
            last_modified="2024-01-01T00:00:00Z",
        )
    )
    after_time = datetime.now(timezone.utc).isoformat()

    with db_conn.get_connection() as conn:
        row = conn.execute(
            "SELECT created_at, updated_at FROM files WHERE bucket = ? AND key = ?",
            ("test-bucket", "file.txt"),
        ).fetchone()

    assert row["created_at"] is not None
    assert row["updated_at"] is not None
    assert before_time <= row["created_at"] <= after_time


def test_mark_glacier_restore_requested(file_mgr, db_conn):
    """Test marking a file for glacier restore"""
    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="glacier-file.txt",
            size=5000,
            etag="ghi789",
            storage_class="GLACIER",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    file_mgr.mark_glacier_restore_requested("test-bucket", "glacier-file.txt")

    with db_conn.get_connection() as conn:
        row = conn.execute(
            "SELECT glacier_restore_requested_at FROM files WHERE bucket = ? AND key = ?",
            ("test-bucket", "glacier-file.txt"),
        ).fetchone()

    assert row["glacier_restore_requested_at"] is not None


def test_mark_glacier_restored(file_mgr, db_conn):
    """Test marking a file as restored from glacier"""
    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="glacier-file.txt",
            size=5000,
            etag="ghi789",
            storage_class="GLACIER",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    file_mgr.mark_glacier_restore_requested("test-bucket", "glacier-file.txt")
    file_mgr.mark_glacier_restored("test-bucket", "glacier-file.txt")

    with db_conn.get_connection() as conn:
        row = conn.execute(
            "SELECT glacier_restored_at FROM files WHERE bucket = ? AND key = ?",
            ("test-bucket", "glacier-file.txt"),
        ).fetchone()

    assert row["glacier_restored_at"] is not None


def test_get_glacier_files_needing_restore(file_mgr):
    """Test retrieving Glacier files that need restore"""
    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="standard.txt",
            size=100,
            etag="std123",
            storage_class="STANDARD",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="glacier1.txt",
            size=1000,
            etag="glac1",
            storage_class="GLACIER",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="archive1.txt",
            size=2000,
            etag="arch1",
            storage_class="DEEP_ARCHIVE",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="glacier2.txt",
            size=1500,
            etag="glac2",
            storage_class="GLACIER",
            last_modified="2024-01-01T00:00:00Z",
        )
    )
    file_mgr.mark_glacier_restore_requested("test-bucket", "glacier2.txt")

    files = file_mgr.get_glacier_files_needing_restore()

    keys = [f["key"] for f in files]
    assert "glacier1.txt" in keys
    assert "archive1.txt" in keys
    assert "glacier2.txt" not in keys
    assert "standard.txt" not in keys
    assert_equal(len(files), 2)


def test_get_files_restoring(file_mgr):
    """Test retrieving files currently being restored"""
    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="standard.txt",
            size=100,
            etag="std123",
            storage_class="STANDARD",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="glacier1.txt",
            size=1000,
            etag="glac1",
            storage_class="GLACIER",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="glacier2.txt",
            size=1500,
            etag="glac2",
            storage_class="GLACIER",
            last_modified="2024-01-01T00:00:00Z",
        )
    )
    file_mgr.mark_glacier_restore_requested("test-bucket", "glacier2.txt")

    file_mgr.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="glacier3.txt",
            size=2000,
            etag="glac3",
            storage_class="GLACIER",
            last_modified="2024-01-01T00:00:00Z",
        )
    )
    file_mgr.mark_glacier_restore_requested("test-bucket", "glacier3.txt")
    file_mgr.mark_glacier_restored("test-bucket", "glacier3.txt")

    files = file_mgr.get_files_restoring()

    keys = [f["key"] for f in files]
    assert "glacier2.txt" in keys
    assert "glacier3.txt" not in keys
    assert "glacier1.txt" not in keys
    assert "standard.txt" not in keys
    assert_equal(len(files), 1)


def test_multiple_buckets_tracked_separately(file_mgr, db_conn):
    """Test that files from different buckets are tracked separately"""
    file_mgr.add_file(
        FileMetadata(
            bucket="bucket-a",
            key="file.txt",
            size=100,
            etag="abc",
            storage_class="STANDARD",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    file_mgr.add_file(
        FileMetadata(
            bucket="bucket-b",
            key="file.txt",
            size=200,
            etag="def",
            storage_class="STANDARD",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    with db_conn.get_connection() as conn:
        row_a = conn.execute(
            "SELECT size FROM files WHERE bucket = ? AND key = ?",
            ("bucket-a", "file.txt"),
        ).fetchone()
        row_b = conn.execute(
            "SELECT size FROM files WHERE bucket = ? AND key = ?",
            ("bucket-b", "file.txt"),
        ).fetchone()

    assert_equal(row_a["size"], 100)
    assert_equal(row_b["size"], 200)
