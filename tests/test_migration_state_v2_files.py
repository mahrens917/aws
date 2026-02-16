"""Unit tests for MigrationStateV2 file and Glacier operations."""

from pathlib import Path

from migration_state_managers import FileMetadata
from migration_state_v2 import DatabaseConnection, MigrationStateV2
from tests.assertions import assert_equal


def test_migration_state_v2_initialization(tmp_path: Path):
    """MigrationStateV2 initializes with database and managers."""
    db_path = tmp_path / "test.db"
    state = MigrationStateV2(str(db_path))

    assert isinstance(state.db_conn, DatabaseConnection)
    assert hasattr(state, "files")
    assert hasattr(state, "buckets")
    assert hasattr(state, "phases")


def test_migration_state_v2_add_file(tmp_path: Path):
    """MigrationStateV2.add_file delegates to FileStateManager."""
    db_path = tmp_path / "test.db"
    state = MigrationStateV2(str(db_path))

    state.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="test-key.txt",
            size=1024,
            etag="abc123",
            storage_class="STANDARD",
            last_modified="2025-10-31T00:00:00Z",
        )
    )

    with state.db_conn.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM files WHERE bucket = ? AND key = ?",
            ("test-bucket", "test-key.txt"),
        )
        row = cursor.fetchone()
        assert row is not None
        assert_equal(row["size"], 1024)
        assert row["storage_class"] == "STANDARD"


def test_migration_state_v2_add_file_idempotent(tmp_path: Path):
    """MigrationStateV2.add_file is idempotent."""
    db_path = tmp_path / "test.db"
    state = MigrationStateV2(str(db_path))

    state.add_file(
        FileMetadata(
            bucket="bucket1",
            key="key1",
            size=100,
            etag="e1",
            storage_class="STANDARD",
            last_modified="2025-10-31T00:00:00Z",
        )
    )

    state.add_file(
        FileMetadata(
            bucket="bucket1",
            key="key1",
            size=100,
            etag="e1",
            storage_class="STANDARD",
            last_modified="2025-10-31T00:00:00Z",
        )
    )

    with state.db_conn.get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM files")
        count = cursor.fetchone()[0]
        assert count == 1


def test_migration_state_v2_mark_glacier_restore_requested(tmp_path: Path):
    """MigrationStateV2.mark_glacier_restore_requested updates file state."""
    db_path = tmp_path / "test.db"
    state = MigrationStateV2(str(db_path))

    state.add_file(
        FileMetadata(
            bucket="bucket1",
            key="glacier-key",
            size=1000,
            etag="e1",
            storage_class="GLACIER",
            last_modified="2025-10-31T00:00:00Z",
        )
    )

    state.mark_glacier_restore_requested("bucket1", "glacier-key")

    with state.db_conn.get_connection() as conn:
        cursor = conn.execute(
            "SELECT glacier_restore_requested_at FROM files WHERE bucket = ? AND key = ?",
            ("bucket1", "glacier-key"),
        )
        row = cursor.fetchone()
        assert row["glacier_restore_requested_at"] is not None


def test_migration_state_v2_mark_glacier_restored(tmp_path: Path):
    """MigrationStateV2.mark_glacier_restored updates file state."""
    db_path = tmp_path / "test.db"
    state = MigrationStateV2(str(db_path))

    state.add_file(
        FileMetadata(
            bucket="bucket1",
            key="glacier-key",
            size=1000,
            etag="e1",
            storage_class="GLACIER",
            last_modified="2025-10-31T00:00:00Z",
        )
    )

    state.mark_glacier_restore_requested("bucket1", "glacier-key")
    state.mark_glacier_restored("bucket1", "glacier-key")

    with state.db_conn.get_connection() as conn:
        cursor = conn.execute(
            "SELECT glacier_restored_at FROM files WHERE bucket = ? AND key = ?",
            ("bucket1", "glacier-key"),
        )
        row = cursor.fetchone()
        assert row["glacier_restored_at"] is not None


def test_migration_state_v2_get_glacier_files_needing_restore(tmp_path: Path):
    """MigrationStateV2.get_glacier_files_needing_restore returns GLACIER files."""
    db_path = tmp_path / "test.db"
    state = MigrationStateV2(str(db_path))

    state.add_file(
        FileMetadata(
            bucket="b1",
            key="glacier1",
            size=100,
            etag="e1",
            storage_class="GLACIER",
            last_modified="2025-10-31T00:00:00Z",
        )
    )
    state.add_file(
        FileMetadata(
            bucket="b1",
            key="standard1",
            size=100,
            etag="e2",
            storage_class="STANDARD",
            last_modified="2025-10-31T00:00:00Z",
        )
    )

    files = state.get_glacier_files_needing_restore()

    assert len(files) == 1
    assert files[0]["key"] == "glacier1"
    assert files[0]["storage_class"] == "GLACIER"


def test_migration_state_v2_get_files_restoring(tmp_path: Path):
    """MigrationStateV2.get_files_restoring returns in-progress restores."""
    db_path = tmp_path / "test.db"
    state = MigrationStateV2(str(db_path))

    state.add_file(
        FileMetadata(
            bucket="b1",
            key="glacier1",
            size=100,
            etag="e1",
            storage_class="GLACIER",
            last_modified="2025-10-31T00:00:00Z",
        )
    )
    state.mark_glacier_restore_requested("b1", "glacier1")

    files = state.get_files_restoring()

    assert len(files) == 1
    assert files[0]["key"] == "glacier1"
