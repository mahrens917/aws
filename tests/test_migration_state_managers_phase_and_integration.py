"""Unit tests for PhaseManager and integration tests for migration_state_managers.py"""

# pylint: disable=redefined-outer-name  # pytest fixtures

import pytest

from migration_state_managers import (
    BucketScanStatus,
    BucketVerificationResult,
    FileMetadata,
    PhaseManager,
)
from migration_state_v2 import MigrationStateV2, Phase
from tests.assertions import assert_equal


# Shared fixtures for PhaseManager tests
@pytest.fixture
def phase_mgr(db_conn):
    """Create PhaseManager instance"""
    return PhaseManager(db_conn)


def testphase_manager_initialization_sets_scanning(db_conn):
    """Test that new PhaseManager initializes to SCANNING phase"""
    pm = PhaseManager(db_conn)
    phase = pm.get_phase()

    assert phase == Phase.SCANNING


def test_set_phase_and_get_phase(phase_mgr):
    """Test setting and getting phases"""
    phase_mgr.set_phase(Phase.GLACIER_RESTORE)
    assert phase_mgr.get_phase() == Phase.GLACIER_RESTORE

    phase_mgr.set_phase(Phase.GLACIER_WAIT)
    assert phase_mgr.get_phase() == Phase.GLACIER_WAIT

    phase_mgr.set_phase(Phase.SYNCING)
    assert phase_mgr.get_phase() == Phase.SYNCING

    phase_mgr.set_phase(Phase.VERIFYING)
    assert phase_mgr.get_phase() == Phase.VERIFYING

    phase_mgr.set_phase(Phase.DELETING)
    assert phase_mgr.get_phase() == Phase.DELETING

    phase_mgr.set_phase(Phase.COMPLETE)
    assert phase_mgr.get_phase() == Phase.COMPLETE


class TestPhasePersistence:
    """Test phase persistence"""

    def test_phase_persistence_across_instances(self, db_conn):
        """Test that phase is persisted and can be retrieved by new instance"""
        phase_manager1 = PhaseManager(db_conn)
        phase_manager1.set_phase(Phase.GLACIER_RESTORE)

        phase_manager2 = PhaseManager(db_conn)
        assert phase_manager2.get_phase() == Phase.GLACIER_RESTORE

    def test_phase_updates_are_persisted(self, phase_mgr, db_conn):
        """Test that phase updates are stored in database"""
        phase_mgr.set_phase(Phase.SYNCING)

        with db_conn.get_connection() as conn:
            row = conn.execute("SELECT value FROM migration_metadata WHERE key = 'current_phase'").fetchone()

        assert row["value"] == Phase.SYNCING.value


def test_get_phase_returns_phase_enum(phase_mgr):
    """Test that get_phase returns Phase enum type"""
    phase = phase_mgr.get_phase()

    assert isinstance(phase, Phase)
    assert phase in Phase


def testphase_manager_multiple_set_operations(phase_mgr):
    """Test multiple consecutive set operations"""
    phases = list(Phase)

    for phase in phases:
        phase_mgr.set_phase(phase)
        assert phase_mgr.get_phase() == phase


# Shared fixtures for integration tests
@pytest.fixture
def migration_state(temp_db):
    """Create MigrationStateV2 instance"""
    return MigrationStateV2(temp_db)


def test_full_migration_workflow(migration_state):
    """Test a complete migration workflow"""
    migration_state.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="file1.txt",
            size=1000,
            etag="abc1",
            storage_class="STANDARD",
            last_modified="2024-01-01T00:00:00Z",
        )
    )
    migration_state.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="file2.txt",
            size=2000,
            etag="abc2",
            storage_class="GLACIER",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    migration_state.save_bucket_status(
        BucketScanStatus(
            bucket="test-bucket", file_count=2, total_size=3000, storage_classes={"STANDARD": 1, "GLACIER": 1}, scan_complete=True
        )
    )

    assert migration_state.get_current_phase() == Phase.SCANNING

    migration_state.set_current_phase(Phase.GLACIER_RESTORE)
    glacier_files = migration_state.get_glacier_files_needing_restore()
    assert len(glacier_files) == 1


def test_glacier_restore_workflow(migration_state):
    """Test complete glacier restore workflow"""
    migration_state.add_file(
        FileMetadata(
            bucket="test-bucket",
            key="file2.txt",
            size=2000,
            etag="abc2",
            storage_class="GLACIER",
            last_modified="2024-01-01T00:00:00Z",
        )
    )

    migration_state.mark_glacier_restore_requested("test-bucket", "file2.txt")
    glacier_files = migration_state.get_glacier_files_needing_restore()
    assert len(glacier_files) == 0

    restoring_files = migration_state.get_files_restoring()
    assert len(restoring_files) == 1

    migration_state.mark_glacier_restored("test-bucket", "file2.txt")
    restoring_files = migration_state.get_files_restoring()
    assert len(restoring_files) == 0


def test_phase_progression(migration_state):
    """Test progressing through migration phases"""
    migration_state.save_bucket_status(
        BucketScanStatus(
            bucket="test-bucket", file_count=2, total_size=3000, storage_classes={"STANDARD": 1, "GLACIER": 1}, scan_complete=True
        )
    )

    migration_state.set_current_phase(Phase.GLACIER_WAIT)
    assert migration_state.get_current_phase() == Phase.GLACIER_WAIT

    migration_state.set_current_phase(Phase.SYNCING)
    migration_state.mark_bucket_sync_complete("test-bucket")
    assert "test-bucket" in migration_state.get_completed_buckets_for_phase("sync_complete")

    migration_state.set_current_phase(Phase.VERIFYING)
    migration_state.mark_bucket_verify_complete(
        BucketVerificationResult(
            bucket="test-bucket",
            verified_file_count=2,
            size_verified_count=2,
            checksum_verified_count=2,
            total_bytes_verified=3000,
            local_file_count=2,
        )
    )

    migration_state.set_current_phase(Phase.DELETING)
    migration_state.mark_bucket_delete_complete("test-bucket")
    assert "test-bucket" in migration_state.get_completed_buckets_for_phase("delete_complete")

    migration_state.set_current_phase(Phase.COMPLETE)
    assert migration_state.get_current_phase() == Phase.COMPLETE


def test_multiple_buckets_independentstates(migration_state):
    """Test that multiple buckets maintain independent states"""
    migration_state.add_file(
        FileMetadata(
            bucket="bucket-a", key="file1.txt", size=1000, etag="abc1", storage_class="STANDARD", last_modified="2024-01-01T00:00:00Z"
        )
    )

    migration_state.add_file(
        FileMetadata(
            bucket="bucket-b", key="file2.txt", size=2000, etag="def1", storage_class="STANDARD", last_modified="2024-01-01T00:00:00Z"
        )
    )

    migration_state.save_bucket_status(
        BucketScanStatus(bucket="bucket-a", file_count=1, total_size=1000, storage_classes={"STANDARD": 1}, scan_complete=True)
    )
    migration_state.save_bucket_status(
        BucketScanStatus(bucket="bucket-b", file_count=1, total_size=2000, storage_classes={"STANDARD": 1}, scan_complete=True)
    )

    migration_state.mark_bucket_sync_complete("bucket-a")

    synced_buckets = migration_state.get_completed_buckets_for_phase("sync_complete")
    assert "bucket-a" in synced_buckets
    assert "bucket-b" not in synced_buckets


def test_get_scan_summary_integration(migration_state):
    """Test getting scan summary through integrated managers"""
    migration_state.add_file(
        FileMetadata(
            bucket="bucket-a", key="file1.txt", size=1000, etag="abc1", storage_class="STANDARD", last_modified="2024-01-01T00:00:00Z"
        )
    )
    migration_state.add_file(
        FileMetadata(
            bucket="bucket-a", key="file2.txt", size=2000, etag="abc2", storage_class="GLACIER", last_modified="2024-01-01T00:00:00Z"
        )
    )
    migration_state.add_file(
        FileMetadata(
            bucket="bucket-b", key="file3.txt", size=3000, etag="def1", storage_class="STANDARD", last_modified="2024-01-01T00:00:00Z"
        )
    )

    migration_state.save_bucket_status(
        BucketScanStatus(
            bucket="bucket-a", file_count=2, total_size=3000, storage_classes={"STANDARD": 1, "GLACIER": 1}, scan_complete=True
        )
    )
    migration_state.save_bucket_status(
        BucketScanStatus(bucket="bucket-b", file_count=1, total_size=3000, storage_classes={"STANDARD": 1}, scan_complete=True)
    )

    summary = migration_state.get_scan_summary()

    assert_equal(summary["bucket_count"], 2)
    assert_equal(summary["total_files"], 3)
    assert_equal(summary["total_size"], 6000)
    assert_equal(summary["storage_classes"]["STANDARD"], 2)
    assert_equal(summary["storage_classes"]["GLACIER"], 1)
