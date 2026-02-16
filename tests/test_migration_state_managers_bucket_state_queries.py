"""Unit tests for BucketStateManager query operations from migration_state_managers.py"""

# pylint: disable=redefined-outer-name  # pytest fixtures

import pytest

from migration_state_managers import (
    BucketScanStatus,
    BucketStateManager,
    FileMetadata,
    FileStateManager,
)

BUCKET_A_FILE_COUNT = 100
BUCKET_B_FILE_COUNT = 200
BUCKET_C_FILE_COUNT = 300
BUCKET_A_TOTAL_SIZE = 1_000_000
BUCKET_B_TOTAL_SIZE = 2_000_000
BUCKET_C_TOTAL_SIZE = 3_000_000
MIXED_STORAGE_COUNTS = {"STANDARD": 80, "GLACIER": 20}
SMALL_SCAN_FILE_COUNT = 2
SMALL_SCAN_TOTAL_SIZE = 3_000
SINGLE_FILE_COUNT = 1
SINGLE_BUCKET_TOTAL_SIZE = 3_000
STANDARD_FILE_SIZE_BYTES = 1_000
GLACIER_FILE_SIZE_BYTES = 2_000
SECOND_BUCKET_FILE_SIZE_BYTES = 3_000
SUMMARY_BUCKET_COUNT = 2
SUMMARY_FILE_TOTAL = 3
SUMMARY_TOTAL_SIZE = 6_000
SUMMARY_STANDARD_CLASS_COUNT = 2
SUMMARY_GLACIER_CLASS_COUNT = 1
INCOMPLETE_BUCKET_COUNT = 10
INCOMPLETE_BUCKET_SIZE = 100_000
COMPLETE_BUCKET_COUNT = 5
COMPLETE_BUCKET_SIZE = 50_000


# Shared fixtures for BucketStateManager query tests
@pytest.fixture
def bucket_mgr(db_conn):
    """Create BucketStateManager instance"""
    return BucketStateManager(db_conn)


class TestGetAllBuckets:
    """Test get_all_buckets operations"""

    def test_get_all_buckets(self, bucket_mgr):
        """Test retrieving all buckets"""
        bucket_mgr.save_bucket_status(
            BucketScanStatus(
                bucket="bucket-a",
                file_count=BUCKET_A_FILE_COUNT,
                total_size=BUCKET_A_TOTAL_SIZE,
                storage_classes={"STANDARD": BUCKET_A_FILE_COUNT},
            )
        )
        bucket_mgr.save_bucket_status(
            BucketScanStatus(
                bucket="bucket-b",
                file_count=BUCKET_B_FILE_COUNT,
                total_size=BUCKET_B_TOTAL_SIZE,
                storage_classes={"STANDARD": BUCKET_B_FILE_COUNT},
            )
        )
        bucket_mgr.save_bucket_status(
            BucketScanStatus(
                bucket="bucket-c",
                file_count=BUCKET_C_FILE_COUNT,
                total_size=BUCKET_C_TOTAL_SIZE,
                storage_classes={"STANDARD": BUCKET_C_FILE_COUNT},
            )
        )

        buckets = bucket_mgr.get_all_buckets()

        assert buckets == ["bucket-a", "bucket-b", "bucket-c"]

    def test_get_all_buckets_empty(self, bucket_mgr):
        """Test getting all buckets when none exist"""
        buckets = bucket_mgr.get_all_buckets()

        assert buckets == []


def test_get_completed_buckets_for_phase(bucket_mgr):
    """Test retrieving buckets completed for a specific phase"""
    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket="bucket-a",
            file_count=BUCKET_A_FILE_COUNT,
            total_size=BUCKET_A_TOTAL_SIZE,
            storage_classes={"STANDARD": BUCKET_A_FILE_COUNT},
        )
    )
    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket="bucket-b",
            file_count=BUCKET_B_FILE_COUNT,
            total_size=BUCKET_B_TOTAL_SIZE,
            storage_classes={"STANDARD": BUCKET_B_FILE_COUNT},
        )
    )
    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket="bucket-c",
            file_count=BUCKET_C_FILE_COUNT,
            total_size=BUCKET_C_TOTAL_SIZE,
            storage_classes={"STANDARD": BUCKET_C_FILE_COUNT},
        )
    )

    bucket_mgr.mark_bucket_sync_complete("bucket-a")
    bucket_mgr.mark_bucket_sync_complete("bucket-b")

    buckets = bucket_mgr.get_completed_buckets_for_phase("sync_complete")

    assert sorted(buckets) == ["bucket-a", "bucket-b"]


class TestGetBucketInfo:
    """Test get_bucket_info operations"""

    def test_get_bucket_info(self, bucket_mgr):
        """Test retrieving bucket information"""
        bucket_mgr.save_bucket_status(
            BucketScanStatus(
                bucket="test-bucket",
                file_count=BUCKET_A_FILE_COUNT,
                total_size=BUCKET_A_TOTAL_SIZE,
                storage_classes=MIXED_STORAGE_COUNTS,
                scan_complete=True,
            )
        )

        info = bucket_mgr.get_bucket_info("test-bucket")

        assert info["bucket"] == "test-bucket"
        assert info["file_count"] == BUCKET_A_FILE_COUNT
        assert info["total_size"] == BUCKET_A_TOTAL_SIZE
        assert info["scan_complete"] == 1

    def test_get_bucket_info_nonexistent(self, bucket_mgr):
        """Test retrieving info for nonexistent bucket"""
        info = bucket_mgr.get_bucket_info("nonexistent-bucket")

        assert info == {}


def test_get_scan_summary(bucket_mgr, db_conn):
    """Test getting scan summary"""
    file_manager = FileStateManager(db_conn)
    file_manager.add_file(
        FileMetadata(
            bucket="bucket-a",
            key="file1.txt",
            size=STANDARD_FILE_SIZE_BYTES,
            etag="abc1",
            storage_class="STANDARD",
            last_modified="2024-01-01T00:00:00Z",
        )
    )
    file_manager.add_file(
        FileMetadata(
            bucket="bucket-a",
            key="file2.txt",
            size=GLACIER_FILE_SIZE_BYTES,
            etag="abc2",
            storage_class="GLACIER",
            last_modified="2024-01-01T00:00:00Z",
        )
    )
    file_manager.add_file(
        FileMetadata(
            bucket="bucket-b",
            key="file3.txt",
            size=SECOND_BUCKET_FILE_SIZE_BYTES,
            etag="def1",
            storage_class="STANDARD",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket="bucket-a",
            file_count=SMALL_SCAN_FILE_COUNT,
            total_size=SMALL_SCAN_TOTAL_SIZE,
            storage_classes={"STANDARD": 1, "GLACIER": 1},
            scan_complete=True,
        )
    )
    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket="bucket-b",
            file_count=SINGLE_FILE_COUNT,
            total_size=SINGLE_BUCKET_TOTAL_SIZE,
            storage_classes={"STANDARD": 1},
            scan_complete=True,
        )
    )

    summary = bucket_mgr.get_scan_summary()

    assert summary["bucket_count"] == SUMMARY_BUCKET_COUNT
    assert summary["total_files"] == SUMMARY_FILE_TOTAL
    assert summary["total_size"] == SUMMARY_TOTAL_SIZE
    assert summary["storage_classes"]["STANDARD"] == SUMMARY_STANDARD_CLASS_COUNT
    assert summary["storage_classes"]["GLACIER"] == SUMMARY_GLACIER_CLASS_COUNT


def test_get_scan_summary_excludes_incomplete_scans(bucket_mgr):
    """Test that scan summary only includes complete scans"""
    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket="incomplete-bucket",
            file_count=INCOMPLETE_BUCKET_COUNT,
            total_size=INCOMPLETE_BUCKET_SIZE,
            storage_classes={"STANDARD": INCOMPLETE_BUCKET_COUNT},
            scan_complete=False,
        )
    )

    bucket_mgr.save_bucket_status(
        BucketScanStatus(
            bucket="complete-bucket",
            file_count=COMPLETE_BUCKET_COUNT,
            total_size=COMPLETE_BUCKET_SIZE,
            storage_classes={"STANDARD": COMPLETE_BUCKET_COUNT},
            scan_complete=True,
        )
    )

    summary = bucket_mgr.get_scan_summary()

    assert summary["bucket_count"] == 1
    assert summary["total_files"] == COMPLETE_BUCKET_COUNT
    assert summary["total_size"] == COMPLETE_BUCKET_SIZE
