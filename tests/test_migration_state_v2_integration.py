"""Integration tests for MigrationStateV2 combining multiple operations."""

from pathlib import Path

from migration_state_managers import BucketScanStatus, BucketVerificationResult, FileMetadata
from migration_state_v2 import MigrationStateV2, Phase
from tests.assertions import assert_equal


def test_full_bucket_migration_workflow(tmp_path: Path):
    """Test complete workflow through all phases."""
    db_path = tmp_path / "test.db"
    state = MigrationStateV2(str(db_path))

    state.set_current_phase(Phase.SCANNING)
    assert state.get_current_phase() == Phase.SCANNING

    state.add_file(
        FileMetadata(bucket="bucket1", key="key1", size=100, etag="e1", storage_class="GLACIER", last_modified="2025-10-31T00:00:00Z")
    )
    state.add_file(
        FileMetadata(bucket="bucket1", key="key2", size=200, etag="e2", storage_class="STANDARD", last_modified="2025-10-31T00:00:00Z")
    )

    state.save_bucket_status(
        BucketScanStatus(bucket="bucket1", file_count=2, total_size=300, storage_classes={"GLACIER": 1, "STANDARD": 1}, scan_complete=True)
    )

    state.set_current_phase(Phase.GLACIER_RESTORE)
    glacier_files = state.get_glacier_files_needing_restore()
    assert_equal(len(glacier_files), 1)

    state.mark_glacier_restore_requested("bucket1", "key1")
    state.set_current_phase(Phase.GLACIER_WAIT)

    state.mark_glacier_restored("bucket1", "key1")
    state.set_current_phase(Phase.SYNCING)

    state.mark_bucket_sync_complete("bucket1")
    state.set_current_phase(Phase.VERIFYING)

    state.mark_bucket_verify_complete(
        BucketVerificationResult(
            bucket="bucket1",
            verified_file_count=2,
            size_verified_count=2,
            checksum_verified_count=1,
            total_bytes_verified=300,
            local_file_count=2,
        )
    )
    state.set_current_phase(Phase.DELETING)

    state.mark_bucket_delete_complete("bucket1")
    state.set_current_phase(Phase.COMPLETE)

    summary = state.get_scan_summary()
    assert_equal(summary["bucket_count"], 1)
    assert_equal(summary["total_files"], 2)
    assert_equal(summary["total_size"], 300)


def test_multiple_buckets_independent_status(tmp_path: Path):
    """Test multiple buckets can have independent status."""
    db_path = tmp_path / "test.db"
    state = MigrationStateV2(str(db_path))

    state.save_bucket_status(BucketScanStatus(bucket="bucket1", file_count=10, total_size=100, storage_classes={}))
    state.save_bucket_status(BucketScanStatus(bucket="bucket2", file_count=20, total_size=200, storage_classes={}))

    state.mark_bucket_sync_complete("bucket1")
    state.mark_bucket_verify_complete(BucketVerificationResult(bucket="bucket1"))

    completed_sync = state.get_completed_buckets_for_phase("sync_complete")
    completed_verify = state.get_completed_buckets_for_phase("verify_complete")

    assert "bucket1" in completed_sync
    assert "bucket2" not in completed_sync
    assert "bucket1" in completed_verify
    assert "bucket2" not in completed_verify


def test_storage_classes_aggregation(tmp_path: Path):
    """Test storage classes are properly aggregated in scan summary."""
    db_path = tmp_path / "test.db"
    state = MigrationStateV2(str(db_path))

    state.add_file(FileMetadata(bucket="b1", key="k1", size=100, etag="e1", storage_class="STANDARD", last_modified="2025-10-31T00:00:00Z"))
    state.add_file(FileMetadata(bucket="b1", key="k2", size=200, etag="e2", storage_class="GLACIER", last_modified="2025-10-31T00:00:00Z"))
    state.add_file(
        FileMetadata(bucket="b1", key="k3", size=300, etag="e3", storage_class="DEEP_ARCHIVE", last_modified="2025-10-31T00:00:00Z")
    )
    state.add_file(
        FileMetadata(bucket="b2", key="k4", size=400, etag="e4", storage_class="GLACIER_IR", last_modified="2025-10-31T00:00:00Z")
    )
    state.add_file(FileMetadata(bucket="b2", key="k5", size=100, etag="e5", storage_class="GLACIER", last_modified="2025-10-31T00:00:00Z"))

    state.save_bucket_status(BucketScanStatus(bucket="b1", file_count=3, total_size=600, storage_classes={}, scan_complete=True))
    state.save_bucket_status(BucketScanStatus(bucket="b2", file_count=2, total_size=500, storage_classes={}, scan_complete=True))

    summary = state.get_scan_summary()

    assert_equal(summary["storage_classes"]["STANDARD"], 1)
    assert_equal(summary["storage_classes"]["GLACIER"], 2)
    assert_equal(summary["storage_classes"]["DEEP_ARCHIVE"], 1)
    assert_equal(summary["storage_classes"]["GLACIER_IR"], 1)


def test_glacier_restore_workflow(tmp_path: Path):
    """Test complete Glacier restore workflow."""
    db_path = tmp_path / "test.db"
    state = MigrationStateV2(str(db_path))

    state.add_file(
        FileMetadata(bucket="b1", key="glacier1", size=100, etag="e1", storage_class="GLACIER", last_modified="2025-10-31T00:00:00Z")
    )
    state.add_file(
        FileMetadata(bucket="b1", key="glacier2", size=200, etag="e2", storage_class="DEEP_ARCHIVE", last_modified="2025-10-31T00:00:00Z")
    )

    needing_restore = state.get_glacier_files_needing_restore()
    assert_equal(len(needing_restore), 2)

    state.mark_glacier_restore_requested("b1", "glacier1")
    state.mark_glacier_restore_requested("b1", "glacier2")

    restoring = state.get_files_restoring()
    assert_equal(len(restoring), 2)

    state.mark_glacier_restored("b1", "glacier1")

    restoring = state.get_files_restoring()
    assert_equal(len(restoring), 1)
    assert restoring[0]["key"] == "glacier2"

    needing_restore = state.get_glacier_files_needing_restore()
    assert_equal(len(needing_restore), 0)
