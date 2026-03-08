"""State management for S3 migration V2 using SQLite
with bucket-level tracking and phase management."""

import json
import sqlite3
from contextlib import contextmanager
from typing import Dict, List

from migration_state_managers import (
    BucketScanStatus,
    BucketStateManager,
    BucketVerificationResult,
    FileMetadata,
    FileStateManager,
    Phase,
    PhaseManager,
)


class BucketStatus:
    """Bucket processing status"""

    def __init__(self, row: Dict):
        self.bucket = row["bucket"]
        self.file_count = row["file_count"]
        self.total_size = row["total_size"]
        self.storage_classes = json.loads(row["storage_class_counts"]) if row["storage_class_counts"] else {}
        self.scan_complete = bool(row["scan_complete"])
        self.sync_complete = bool(row["sync_complete"])
        self.verify_complete = bool(row["verify_complete"])
        self.delete_complete = bool(row["delete_complete"])


FILE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS files (
        bucket TEXT NOT NULL,
        key TEXT NOT NULL,
        size INTEGER NOT NULL,
        etag TEXT,
        storage_class TEXT,
        last_modified TEXT,
        local_path TEXT,
        local_checksum TEXT,
        state TEXT NOT NULL,
        error_message TEXT,
        glacier_restore_requested_at TEXT,
        glacier_restored_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (bucket, key)
    )
"""

BUCKET_STATUS_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS bucket_status (
        bucket TEXT PRIMARY KEY,
        file_count INTEGER NOT NULL,
        total_size INTEGER NOT NULL,
        storage_class_counts TEXT,
        scan_complete BOOLEAN DEFAULT 0,
        sync_complete BOOLEAN DEFAULT 0,
        verify_complete BOOLEAN DEFAULT 0,
        delete_complete BOOLEAN DEFAULT 0,
        local_file_count INTEGER,
        verified_file_count INTEGER,
        size_verified_count INTEGER,
        checksum_verified_count INTEGER,
        total_bytes_verified INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""

METADATA_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS migration_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""

TABLE_DEFINITIONS = (
    FILE_TABLE_SQL,
    BUCKET_STATUS_TABLE_SQL,
    METADATA_TABLE_SQL,
)

INDEX_DEFINITIONS = (
    "CREATE INDEX IF NOT EXISTS idx_files_state ON files(state)",
    "CREATE INDEX IF NOT EXISTS idx_files_storage_class ON files(storage_class)",
    "CREATE INDEX IF NOT EXISTS idx_files_bucket ON files(bucket)",
)

BUCKET_STATUS_MIGRATIONS = (
    "verified_file_count INTEGER",
    "size_verified_count INTEGER",
    "checksum_verified_count INTEGER",
    "total_bytes_verified INTEGER",
)


class DatabaseConnection:
    """Handles database connection and schema initialization"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    @property
    def path(self):
        """Return the database file path."""
        return self.db_path

    @contextmanager
    def get_connection(self):
        """Yield a SQLite connection with the configured row factory."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self):
        with self.get_connection() as conn:
            self._create_tables(conn)
            self._create_indices(conn)
            self._migrate_existing_schema(conn)
            conn.commit()

    def _create_tables(self, conn):
        for statement in TABLE_DEFINITIONS:
            conn.execute(statement)

    def _create_indices(self, conn):
        for statement in INDEX_DEFINITIONS:
            conn.execute(statement)

    def _migrate_existing_schema(self, conn):
        for column in BUCKET_STATUS_MIGRATIONS:
            try:
                conn.execute(f"ALTER TABLE bucket_status ADD COLUMN {column}")
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "duplicate column name" in message:
                    continue
                raise


class MigrationStateV2(FileStateManager, BucketStateManager, PhaseManager):
    """Migration state management combining file, bucket, and phase operations"""

    def __init__(self, db_path: str):
        db_conn = DatabaseConnection(db_path)
        FileStateManager.__init__(self, db_conn)
        BucketStateManager.__init__(self, db_conn)
        PhaseManager.__init__(self, db_conn)

    def get_bucket_status(self, bucket: str) -> "BucketStatus":
        """Fetch bucket status as a typed object; fail fast if missing."""
        info = self.get_bucket_info(bucket)
        if not info:
            raise ValueError(f"Bucket '{bucket}' not found in migration state")
        return BucketStatus(info)
