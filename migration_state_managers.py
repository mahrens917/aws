"""State manager classes for file, bucket, and phase operations"""

import sqlite3
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Dict, List, Optional

from migration_types import Phase

_PACKAGE_PREFIX = f"{__package__}." if __package__ else ""
get_utc_now = import_module(f"{_PACKAGE_PREFIX}migration_utils").get_utc_now

if TYPE_CHECKING:
    from migration_state_v2 import DatabaseConnection


@dataclass
class BucketScanStatus:
    """Payload describing the results of a bucket scan."""

    bucket: str
    file_count: int
    total_size: int
    storage_classes: Dict[str, int]
    scan_complete: bool = False


@dataclass
class BucketVerificationResult:
    """Payload describing verification metrics for a bucket."""

    bucket: str
    verified_file_count: Optional[int] = None
    size_verified_count: Optional[int] = None
    checksum_verified_count: Optional[int] = None
    total_bytes_verified: Optional[int] = None
    local_file_count: Optional[int] = None


@dataclass
class FileMetadata:
    """Payload describing a discovered S3 object."""

    bucket: str
    key: str
    size: int
    etag: str
    storage_class: str
    last_modified: str


def save_bucket_status_to_db(conn, status: BucketScanStatus):
    """Helper to save bucket status to database"""
    import json

    now = get_utc_now()
    storage_json = json.dumps(status.storage_classes)
    conn.execute(
        """INSERT OR REPLACE INTO bucket_status
        (bucket, file_count, total_size, storage_class_counts,
        scan_complete, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?,
        COALESCE((SELECT created_at FROM bucket_status WHERE bucket = ?), ?), ?)""",
        (
            status.bucket,
            status.file_count,
            status.total_size,
            storage_json,
            status.scan_complete,
            status.bucket,
            now,
            now,
        ),
    )
    conn.commit()


def update_bucket_verification(conn, verification: BucketVerificationResult):
    """Helper to update bucket verification status"""
    now = get_utc_now()
    conn.execute(
        """UPDATE bucket_status SET verify_complete = 1, verified_file_count = ?,
        size_verified_count = ?, checksum_verified_count = ?, total_bytes_verified = ?,
        local_file_count = ?, updated_at = ? WHERE bucket = ?""",
        (
            verification.verified_file_count,
            verification.size_verified_count,
            verification.checksum_verified_count,
            verification.total_bytes_verified,
            verification.local_file_count,
            now,
            verification.bucket,
        ),
    )
    conn.commit()


def update_bucket_flag(conn, bucket: str, flag_name: str):
    """Helper to update a boolean flag"""
    now = get_utc_now()
    conn.execute(
        f"UPDATE bucket_status SET {flag_name} = 1, updated_at = ? WHERE bucket = ?",
        (now, bucket),
    )
    conn.commit()


def get_all_buckets_from_db(conn) -> List[str]:
    """Get list of all buckets"""
    return [r["bucket"] for r in conn.execute("SELECT bucket FROM bucket_status ORDER BY bucket")]


def get_completed_buckets_for_phase_from_db(conn, phase_field: str) -> List[str]:
    """Get buckets that completed a specific phase"""
    return [r["bucket"] for r in conn.execute(f"SELECT bucket FROM bucket_status WHERE {phase_field} = 1 ORDER BY bucket")]


def get_bucket_info_from_db(conn, bucket: str) -> Dict:
    """Get bucket information"""
    row = conn.execute("SELECT * FROM bucket_status WHERE bucket = ?", (bucket,)).fetchone()
    return dict(row) if row else {}


def get_storage_class_counts(conn) -> Dict[str, int]:
    """Get storage class counts from database"""
    cursor = conn.execute("SELECT storage_class, COUNT(*) as count FROM files GROUP BY storage_class")
    return {r["storage_class"]: r["count"] for r in cursor.fetchall()}


def get_scan_summary_from_db(conn) -> Dict:
    """Get summary of scanned buckets"""
    cursor = conn.execute(
        """SELECT COUNT(*) as bucket_count,
        COALESCE(SUM(file_count), 0) as total_files,
        COALESCE(SUM(total_size), 0) as total_size
        FROM bucket_status WHERE scan_complete = 1"""
    )
    row = cursor.fetchone()
    storage_classes = get_storage_class_counts(conn)
    return {
        "bucket_count": row["bucket_count"],
        "total_files": row["total_files"],
        "total_size": row["total_size"],
        "storage_classes": storage_classes,
    }


class FileStateManager:
    """Manages file-level state operations"""

    def __init__(self, db_conn: "DatabaseConnection"):
        self.db_conn = db_conn

    def add_file(self, metadata: "FileMetadata"):
        """Add a discovered file to tracking database (idempotent)"""
        now = get_utc_now()
        with self.db_conn.get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO files
                    (bucket, key, size, etag, storage_class, last_modified,
                     state, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'discovered', ?, ?)
                """,
                    (
                        metadata.bucket,
                        metadata.key,
                        metadata.size,
                        metadata.etag,
                        metadata.storage_class,
                        metadata.last_modified,
                        now,
                        now,
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed" not in str(e):
                    raise
                # File already exists - expected for duplicate entries

    def mark_glacier_restore_requested(self, bucket: str, key: str):
        """Mark that Glacier restore has been requested"""
        now = get_utc_now()
        with self.db_conn.get_connection() as conn:
            conn.execute(
                """UPDATE files SET glacier_restore_requested_at = ?,
                updated_at = ? WHERE bucket = ? AND key = ?""",
                (now, now, bucket, key),
            )
            conn.commit()

    def mark_glacier_restored(self, bucket: str, key: str):
        """Mark that Glacier restore is complete"""
        now = get_utc_now()
        with self.db_conn.get_connection() as conn:
            conn.execute(
                """UPDATE files SET glacier_restored_at = ?,
                updated_at = ? WHERE bucket = ? AND key = ?""",
                (now, now, bucket, key),
            )
            conn.commit()

    def get_glacier_files_needing_restore(self) -> List[Dict]:
        """Get Glacier files that need restore requests"""
        with self.db_conn.get_connection() as conn:
            cursor = conn.execute(
                """SELECT * FROM files WHERE storage_class IN ('GLACIER', 'DEEP_ARCHIVE')
                AND glacier_restore_requested_at IS NULL"""
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_files_restoring(self) -> List[Dict]:
        """Get files currently being restored"""
        with self.db_conn.get_connection() as conn:
            cursor = conn.execute(
                """SELECT * FROM files WHERE storage_class IN ('GLACIER', 'DEEP_ARCHIVE')
                AND glacier_restore_requested_at IS NOT NULL
                AND glacier_restored_at IS NULL"""
            )
            return [dict(row) for row in cursor.fetchall()]


class BucketStateManager:
    """Manages bucket-level state operations"""

    def __init__(self, db_conn: "DatabaseConnection"):
        self.db_conn = db_conn

    def save_bucket_status(self, status: BucketScanStatus):
        """Save or update bucket status"""
        with self.db_conn.get_connection() as conn:
            save_bucket_status_to_db(conn, status)

    def mark_bucket_sync_complete(self, bucket: str):
        """Mark bucket as synced"""
        with self.db_conn.get_connection() as conn:
            update_bucket_flag(conn, bucket, "sync_complete")

    def mark_bucket_verify_complete(self, verification: BucketVerificationResult):
        """Mark bucket as verified and store verification results"""
        with self.db_conn.get_connection() as conn:
            update_bucket_verification(conn, verification)

    def mark_bucket_delete_complete(self, bucket: str):
        """Mark bucket as deleted from S3"""
        with self.db_conn.get_connection() as conn:
            update_bucket_flag(conn, bucket, "delete_complete")

    def get_all_buckets(self) -> List[str]:
        """Get list of all buckets"""
        with self.db_conn.get_connection() as conn:
            return get_all_buckets_from_db(conn)

    def get_completed_buckets_for_phase(self, phase_field: str) -> List[str]:
        """Get buckets that completed a specific phase"""
        with self.db_conn.get_connection() as conn:
            return get_completed_buckets_for_phase_from_db(conn, phase_field)

    def get_bucket_info(self, bucket: str) -> Dict:
        """Get bucket information"""
        with self.db_conn.get_connection() as conn:
            return get_bucket_info_from_db(conn, bucket)

    def get_scan_summary(self) -> Dict:
        """Get summary of scanned buckets"""
        with self.db_conn.get_connection() as conn:
            return get_scan_summary_from_db(conn)


class PhaseManager:
    """Manages migration phase tracking"""

    def __init__(self, db_conn: "DatabaseConnection"):
        self.db_conn = db_conn
        self._init_phase()

    def _init_phase(self):
        """Initialize phase if not set"""
        with self.db_conn.get_connection() as conn:
            cursor = conn.execute("SELECT value FROM migration_metadata WHERE key = 'current_phase'")
            if not cursor.fetchone():
                self.set_phase(Phase.SCANNING)

    def get_phase(self) -> "Phase":
        """Get current migration phase"""
        with self.db_conn.get_connection() as conn:
            cursor = conn.execute("SELECT value FROM migration_metadata WHERE key = 'current_phase'")
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("Migration phase metadata is missing. Reset the state DB to avoid resuming from an unknown phase.")
            return Phase(row["value"])

    def set_phase(self, phase: "Phase"):
        """Set current migration phase"""
        now = get_utc_now()
        with self.db_conn.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO migration_metadata
                (key, value, updated_at) VALUES ('current_phase', ?, ?)""",
                (phase.value, now),
            )
            conn.commit()
