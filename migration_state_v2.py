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
    PhaseManager,
)
from migration_types import Phase


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


class _FileOperationsMixin:
    """Common file operations delegated to FileStateManager."""

    files: "FileStateManager"

    def add_file(self, metadata: "FileMetadata"):
        """Record metadata for a discovered object."""
        return self.files.add_file(metadata)

    def mark_glacier_restore_requested(self, bucket: str, key: str):
        """Track that a Glacier restore request has been issued."""
        return self.files.mark_glacier_restore_requested(bucket, key)

    def mark_glacier_restored(self, bucket: str, key: str):
        """Mark that a Glacier object finished restoration."""
        return self.files.mark_glacier_restored(bucket, key)

    def get_glacier_files_needing_restore(self) -> List[Dict]:
        """Return Glacier objects still waiting on restore requests."""
        return self.files.get_glacier_files_needing_restore()

    def get_files_restoring(self) -> List[Dict]:
        """Return Glacier objects currently restoring."""
        return self.files.get_files_restoring()


class _BucketOperationsMixin:
    """Common bucket operations delegated to BucketStateManager."""

    buckets: "BucketStateManager"

    def save_bucket_status(self, status: "BucketScanStatus"):
        """Persist bucket scan counts and totals."""
        return self.buckets.save_bucket_status(status)

    def mark_bucket_sync_complete(self, bucket: str):
        """Flag that bucket sync finished."""
        return self.buckets.mark_bucket_sync_complete(bucket)

    def mark_bucket_verify_complete(self, verification: "BucketVerificationResult"):
        """Pass verification metrics through to the bucket state manager."""
        return self.buckets.mark_bucket_verify_complete(verification)

    def mark_bucket_delete_complete(self, bucket: str):
        """Flag that a bucket was deleted."""
        return self.buckets.mark_bucket_delete_complete(bucket)

    def get_all_buckets(self) -> List[str]:
        """Return every bucket tracked in the database."""
        return self.buckets.get_all_buckets()

    def get_completed_buckets_for_phase(self, phase_field: str) -> List[str]:
        """Return buckets that completed a requested boolean phase field."""
        return self.buckets.get_completed_buckets_for_phase(phase_field)

    def get_bucket_info(self, bucket: str) -> Dict:
        """Fetch the stored status row for *bucket*."""
        return self.buckets.get_bucket_info(bucket)

    def get_bucket_status(self, bucket: str) -> "BucketStatus":
        """Fetch bucket status as a typed object; fail fast if missing."""
        info = self.get_bucket_info(bucket)
        if not info:
            raise ValueError(f"Bucket '{bucket}' not found in migration state")
        return BucketStatus(info)

    def get_scan_summary(self) -> Dict:
        """Return high level statistics for scanned buckets."""
        return self.buckets.get_scan_summary()


class _PhaseOperationsMixin:
    """Common phase operations delegated to PhaseManager."""

    phases: "PhaseManager"

    def get_current_phase(self) -> Phase:
        """Return the enum value representing the current phase."""
        return self.phases.get_phase()

    def set_current_phase(self, phase: Phase):
        """Persist the new active migration phase."""
        return self.phases.set_phase(phase)


class MigrationStateV2(_FileOperationsMixin, _BucketOperationsMixin, _PhaseOperationsMixin):
    """Migration state management delegating to specialized managers"""

    def __init__(self, db_path: str):
        self.db_conn = DatabaseConnection(db_path)
        self.files = FileStateManager(self.db_conn)
        self.buckets = BucketStateManager(self.db_conn)
        self.phases = PhaseManager(self.db_conn)
