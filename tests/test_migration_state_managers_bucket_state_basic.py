"""Unit tests for BucketStateManager basic operations from migration_state_managers.py"""

# pylint: disable=redefined-outer-name  # pytest fixtures

import json

import pytest

from migration_state_managers import BucketScanStatus, BucketStateManager, BucketVerificationResult

DEFAULT_BUCKET = "test-bucket"
DEFAULT_FILE_COUNT = 100
DEFAULT_TOTAL_SIZE = 5_000_000
UPDATED_FILE_COUNT = 150
UPDATED_TOTAL_SIZE = 7_000_000
DOUBLE_TOTAL_SIZE = 10_000_000
STANDARD_STORAGE_COUNTS = {"STANDARD": 80}
MIXED_STORAGE_COUNTS = {"STANDARD": 80, "GLACIER": 20}
FULL_STANDARD_STORAGE = {"STANDARD": DEFAULT_FILE_COUNT}
CHECKSUM_VERIFIED_COUNT = 95


# Shared fixtures for BucketStateManager tests
@pytest.fixture
def bucket_mgr(db_conn):
    """Create BucketStateManager instance"""
    return BucketStateManager(db_conn)


def test_save_bucket_status_inserts_record(bucket_mgr, db_conn):
    """Test saving bucket status"""
    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket=DEFAULT_BUCKET,
            file_count=DEFAULT_FILE_COUNT,
            total_size=DEFAULT_TOTAL_SIZE,
            storage_classes=MIXED_STORAGE_COUNTS,
            scan_complete=True,
        )
    )

    with db_conn.get_connection() as conn:
        row = conn.execute("SELECT * FROM bucket_status WHERE bucket = ?", (DEFAULT_BUCKET,)).fetchone()

    assert row is not None
    assert row["bucket"] == DEFAULT_BUCKET
    assert row["file_count"] == DEFAULT_FILE_COUNT
    assert row["total_size"] == DEFAULT_TOTAL_SIZE
    assert row["scan_complete"] == 1
    storage_classes = json.loads(row["storage_class_counts"])
    assert storage_classes == MIXED_STORAGE_COUNTS


def test_save_bucket_status_updates_existing(bucket_mgr, db_conn):
    """Test that saving bucket status updates existing record"""
    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket=DEFAULT_BUCKET,
            file_count=DEFAULT_FILE_COUNT,
            total_size=DEFAULT_TOTAL_SIZE,
            storage_classes=STANDARD_STORAGE_COUNTS,
            scan_complete=False,
        )
    )

    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket=DEFAULT_BUCKET,
            file_count=UPDATED_FILE_COUNT,
            total_size=UPDATED_TOTAL_SIZE,
            storage_classes={"STANDARD": UPDATED_FILE_COUNT},
            scan_complete=True,
        )
    )

    with db_conn.get_connection() as conn:
        row = conn.execute("SELECT * FROM bucket_status WHERE bucket = ?", (DEFAULT_BUCKET,)).fetchone()

    assert row["file_count"] == UPDATED_FILE_COUNT
    assert row["total_size"] == UPDATED_TOTAL_SIZE
    assert row["scan_complete"] == 1


def test_save_bucket_status_preserves_created_at(bucket_mgr, db_conn):
    """Test that created_at timestamp is preserved on update"""
    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket=DEFAULT_BUCKET,
            file_count=DEFAULT_FILE_COUNT,
            total_size=DEFAULT_TOTAL_SIZE,
            storage_classes=STANDARD_STORAGE_COUNTS,
        )
    )

    with db_conn.get_connection() as conn:
        original = conn.execute(
            "SELECT created_at FROM bucket_status WHERE bucket = ?",
            (DEFAULT_BUCKET,),
        ).fetchone()
        original_time = original["created_at"]

    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket=DEFAULT_BUCKET,
            file_count=2 * DEFAULT_FILE_COUNT,
            total_size=DOUBLE_TOTAL_SIZE,
            storage_classes={"STANDARD": 2 * DEFAULT_FILE_COUNT},
        )
    )

    with db_conn.get_connection() as conn:
        updated = conn.execute(
            "SELECT created_at FROM bucket_status WHERE bucket = ?",
            (DEFAULT_BUCKET,),
        ).fetchone()

    assert updated["created_at"] == original_time


def test_mark_bucket_sync_complete(bucket_mgr, db_conn):
    """Test marking bucket as synced"""
    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket=DEFAULT_BUCKET,
            file_count=DEFAULT_FILE_COUNT,
            total_size=DEFAULT_TOTAL_SIZE,
            storage_classes=FULL_STANDARD_STORAGE,
        )
    )

    bucket_mgr.mark_bucket_sync_complete(DEFAULT_BUCKET)

    with db_conn.get_connection() as conn:
        row = conn.execute(
            "SELECT sync_complete FROM bucket_status WHERE bucket = ?",
            (DEFAULT_BUCKET,),
        ).fetchone()

    assert row["sync_complete"] == 1


def test_mark_bucket_verify_complete(bucket_mgr, db_conn):
    """Test marking bucket as verified"""
    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket=DEFAULT_BUCKET,
            file_count=DEFAULT_FILE_COUNT,
            total_size=DEFAULT_TOTAL_SIZE,
            storage_classes=FULL_STANDARD_STORAGE,
        )
    )

    bucket_mgr.mark_bucket_verify_complete(
        BucketVerificationResult(
            bucket=DEFAULT_BUCKET,
            verified_file_count=DEFAULT_FILE_COUNT,
            size_verified_count=DEFAULT_FILE_COUNT,
            checksum_verified_count=CHECKSUM_VERIFIED_COUNT,
            total_bytes_verified=DEFAULT_TOTAL_SIZE,
            local_file_count=DEFAULT_FILE_COUNT,
        )
    )

    with db_conn.get_connection() as conn:
        row = conn.execute("SELECT * FROM bucket_status WHERE bucket = ?", (DEFAULT_BUCKET,)).fetchone()

    assert row["verify_complete"] == 1
    assert row["verified_file_count"] == DEFAULT_FILE_COUNT
    assert row["size_verified_count"] == DEFAULT_FILE_COUNT
    assert row["checksum_verified_count"] == CHECKSUM_VERIFIED_COUNT
    assert row["total_bytes_verified"] == DEFAULT_TOTAL_SIZE
    assert row["local_file_count"] == DEFAULT_FILE_COUNT


def test_mark_bucket_verify_complete_with_partial_data(bucket_mgr, db_conn):
    """Test marking bucket verified with only some verification fields"""
    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket=DEFAULT_BUCKET,
            file_count=DEFAULT_FILE_COUNT,
            total_size=DEFAULT_TOTAL_SIZE,
            storage_classes=FULL_STANDARD_STORAGE,
        )
    )

    bucket_mgr.mark_bucket_verify_complete(
        BucketVerificationResult(
            bucket=DEFAULT_BUCKET,
            verified_file_count=DEFAULT_FILE_COUNT,
            size_verified_count=DEFAULT_FILE_COUNT,
        )
    )

    with db_conn.get_connection() as conn:
        row = conn.execute("SELECT * FROM bucket_status WHERE bucket = ?", (DEFAULT_BUCKET,)).fetchone()

    assert row["verify_complete"] == 1
    assert row["verified_file_count"] == DEFAULT_FILE_COUNT
    assert row["size_verified_count"] == DEFAULT_FILE_COUNT
    assert row["checksum_verified_count"] is None


def test_mark_bucket_delete_complete(bucket_mgr, db_conn):
    """Test marking bucket as deleted from S3"""
    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket=DEFAULT_BUCKET,
            file_count=DEFAULT_FILE_COUNT,
            total_size=DEFAULT_TOTAL_SIZE,
            storage_classes=FULL_STANDARD_STORAGE,
        )
    )

    bucket_mgr.mark_bucket_delete_complete(DEFAULT_BUCKET)

    with db_conn.get_connection() as conn:
        row = conn.execute(
            "SELECT delete_complete FROM bucket_status WHERE bucket = ?",
            (DEFAULT_BUCKET,),
        ).fetchone()

    assert row["delete_complete"] == 1
