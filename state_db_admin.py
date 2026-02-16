"""Shared helpers for managing the migrate_v2 SQLite state database."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Union

from migration_state_v2 import MigrationStateV2

Pathish = Union[str, Path]
BATCH_INSERT_SIZE = 1000


def recreate_state_db(db_path: Pathish) -> Path:
    """Delete and recreate the migrate_v2 state database schema."""

    path = Path(db_path).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    # Instantiating MigrationStateV2 runs the schema bootstrap logic.
    MigrationStateV2(str(path))
    return path


def _bucket_dirs(base: Path) -> Iterator[tuple[str, Path]]:
    """Yield bucket name and directory path pairs from base path."""
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        yield child.name, child


def _iter_files(bucket_dir: Path) -> Iterator[Path]:
    """Recursively yield all file paths within a bucket directory."""
    for root, _, files in os.walk(bucket_dir):
        root_path = Path(root)
        for name in files:
            yield root_path / name


def _build_file_row(
    bucket_name: str,
    file_path: Path,
    bucket_dir: Path,
    created_at: str,
    default_state: str,
) -> tuple | None:
    """Build a database row tuple for a single file, or None if file is inaccessible.

    Args:
        bucket_name: Name of the S3 bucket
        file_path: Path to the local file
        bucket_dir: Directory containing the bucket files
        created_at: ISO timestamp for record creation
        default_state: Default state value for the file record

    Returns:
        Tuple of file metadata for database insertion, or None if file cannot be accessed.

    Note:
        Returns None for inaccessible files to allow batch processing to continue.
        Callers should handle None values appropriately.
    """
    try:
        stat = file_path.stat()
    except OSError:
        # File may have been deleted or permissions changed during scan
        return None
    key = file_path.relative_to(bucket_dir).as_posix()
    last_modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    return (
        bucket_name,
        key,
        stat.st_size,
        None,
        "STANDARD",
        last_modified,
        str(file_path),
        None,
        default_state,
        None,
        None,
        None,
        created_at,
        last_modified,
    )


def _insert_file_rows(
    conn: sqlite3.Connection,
    rows: list[tuple],
    insert_sql: str,
):
    """Insert accumulated rows and commit to database."""
    if rows:
        conn.executemany(insert_sql, rows)
        conn.commit()


def reseed_state_db_from_local_drive(
    base_path: Pathish,
    db_path: Pathish,
    *,
    default_state: str = "synced",
) -> tuple[Path, int, int]:
    """Rebuild the migrate_v2 database by scanning the local drive layout."""
    base = Path(base_path).expanduser().resolve()
    if not base.exists():
        raise FileNotFoundError(f"Base path does not exist: {base}")
    db_file = recreate_state_db(db_path)
    created_at = datetime.now(timezone.utc).isoformat()

    insert_sql = """
        INSERT INTO files (
            bucket, key, size, etag, storage_class, last_modified,
            local_path, local_checksum, state, error_message,
            glacier_restore_requested_at, glacier_restored_at,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    total_files = 0
    total_bytes = 0
    rows: list[tuple] = []

    with sqlite3.connect(str(db_file)) as conn:
        for bucket_name, bucket_dir in _bucket_dirs(base):
            for file_path in _iter_files(bucket_dir):
                row = _build_file_row(bucket_name, file_path, bucket_dir, created_at, default_state)
                if row is None:
                    continue
                rows.append(row)
                total_files += 1
                total_bytes += row[2]
                if len(rows) >= BATCH_INSERT_SIZE:
                    _insert_file_rows(conn, rows, insert_sql)
                    rows.clear()
        _insert_file_rows(conn, rows, insert_sql)
    return db_file, total_files, total_bytes


__all__ = ["recreate_state_db", "reseed_state_db_from_local_drive"]
