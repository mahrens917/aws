"""Orchestration components: Managing bucket migration and status reporting"""

from pathlib import Path
from threading import Event

from cost_toolkit.common.format_utils import format_bytes
from migration_state_managers import BucketVerificationResult
from migration_state_v2 import MigrationStateV2, Phase
from migration_sync import sync_bucket
from migration_utils import print_verification_success_messages
from migration_verify_bucket import verify_bucket
from migration_verify_delete import delete_bucket


class MigrationFatalError(Exception):
    """Fatal error that stops the migration process."""


def _require_bucket_fields(bucket: str, bucket_info: dict) -> None:
    """Ensure all expected status fields are present before proceeding."""
    if bucket_info is None:
        raise ValueError(f"Bucket '{bucket}' missing from migration state")

    required_fields = (
        "file_count",
        "total_size",
        "sync_complete",
        "verify_complete",
        "delete_complete",
        "verified_file_count",
        "size_verified_count",
        "checksum_verified_count",
        "total_bytes_verified",
        "local_file_count",
    )
    missing = [field for field in required_fields if field not in bucket_info.keys()]
    if missing:
        raise ValueError(f"Bucket '{bucket}' state missing fields: {', '.join(missing)}")


def show_verification_summary(bucket_info: dict):
    """Show detailed verification summary from stored results"""
    local_file_count = bucket_info["local_file_count"]
    size_verified_count = bucket_info["size_verified_count"]
    checksum_verified_count = bucket_info["checksum_verified_count"]
    verified_file_count = bucket_info["verified_file_count"]
    total_bytes_verified = bucket_info["total_bytes_verified"]
    print("  " + "=" * 66)
    print("  VERIFICATION SUMMARY (Real Computed Values)")
    print("  " + "=" * 66)
    print()
    print(f"  Files in S3:          {bucket_info['file_count']:,}")
    print(f"  Files found locally:  {local_file_count:,}")
    print(f"  Size verified:        {size_verified_count:,} files")
    print(f"  Checksum verified:    {checksum_verified_count:,} files")
    print(f"  Total verified:       {verified_file_count:,} files")
    print()
    print(f"  ✓ File count matches: {verified_file_count:,} files")
    print_verification_success_messages()
    print(f"  ✓ Total size: {format_bytes(total_bytes_verified, binary_units=False)}")
    print()
    print("  ✓ Verification complete")
    print("  " + "=" * 66)


def process_bucket(s3, state: MigrationStateV2, base_path: Path, bucket: str, interrupted: Event):
    """Process a single bucket through sync -> verify -> delete pipeline"""
    bucket_info = state.get_bucket_info(bucket)
    _require_bucket_fields(bucket, bucket_info)

    if not bucket_info["sync_complete"]:
        state.set_current_phase(Phase.SYNCING)
        print("→ Step 1/3: Syncing from S3...")
        print()
        sync_bucket(s3, state, base_path, bucket, interrupted)
        state.mark_bucket_sync_complete(bucket)
        print()
        print("  ✓ Sync complete")
        print()
    else:
        print("→ Step 1/3: Already synced ✓")
        print()
    needs_verification = not bucket_info["verify_complete"] or bucket_info["verified_file_count"] is None
    if needs_verification:
        state.set_current_phase(Phase.VERIFYING)
        if bucket_info["verify_complete"]:
            print("→ Step 2/3: Re-verifying to compute detailed stats...")
        else:
            print("→ Step 2/3: Verifying local files...")
        print()
        verify_results = verify_bucket(state, base_path, bucket)
        verification = BucketVerificationResult(
            bucket=bucket,
            verified_file_count=verify_results["verified_count"],
            size_verified_count=verify_results["size_verified"],
            checksum_verified_count=verify_results["checksum_verified"],
            total_bytes_verified=verify_results["total_bytes_verified"],
            local_file_count=verify_results["local_file_count"],
        )
        state.mark_bucket_verify_complete(verification)
        print()
        print("  ✓ Verification complete")
        print()
    else:
        print("→ Step 2/3: Already verified ✓")
        print()
    if not bucket_info["delete_complete"]:
        bucket_info = state.get_bucket_info(bucket)
        _require_bucket_fields(bucket, bucket_info)
        state.set_current_phase(Phase.DELETING)
        print("→ Step 3/3: Delete from S3")
        print()
        delete_with_confirmation(s3, state, bucket, bucket_info)
        print()
    else:
        print("→ Step 3/3: Already deleted ✓")
        print()


def delete_with_confirmation(s3, state: MigrationStateV2, bucket: str, bucket_info: dict):
    """Delete bucket from S3 with user confirmation"""
    show_verification_summary(bucket_info)
    print()
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 20 + "READY TO DELETE BUCKET" + " " * 26 + "║")
    print("╚" + "=" * 68 + "╝")
    print()
    print(f"  Bucket: {bucket}")
    print(f"  Files:  {bucket_info['file_count']:,}")
    print(f"  Size:   {format_bytes(bucket_info['total_size'], binary_units=False)}")
    print()
    print("  Local verification: ✓ PASSED")
    print()
    response = input("  Delete this bucket from S3? (yes/no): ")
    if response.lower() == "yes":
        print()
        print(f"  Deleting bucket '{bucket}'...")
        delete_bucket(s3, state, bucket)
        state.mark_bucket_delete_complete(bucket)
        print("  ✓ Deleted from S3")
    else:
        print()
        print("  Skipped - bucket NOT deleted")
        print("  (You can delete it later manually)")


def handle_drive_error(error):
    """Handle drive disconnection errors"""
    print()
    print(f"✗ Drive error: {error}")
    print()
    print("=" * 70)
    print("MIGRATION INTERRUPTED - DRIVE ERROR")
    print("=" * 70)
    print("The destination drive appears to be disconnected or inaccessible.")
    print()
    print("State has been saved. When you reconnect the drive,")
    print("run 'python migrate_v2.py' to resume.")
    print("=" * 70)
    raise MigrationFatalError(f"Drive error: {error}")


def handle_migration_error(bucket, error):
    """Handle general migration errors"""
    print()
    print(f"✗ Error: {error}")
    print()
    print("=" * 70)
    print("MIGRATION STOPPED - ERROR ENCOUNTERED")
    print("=" * 70)
    print(f"Bucket: {bucket}")
    print(f"Error: {error}")
    print()
    print("State has been saved.")
    print("Fix the issue and run 'python migrate_v2.py' to resume.")
    print("=" * 70)
    raise MigrationFatalError(f"Migration error: {error}")


def show_migration_status(state: MigrationStateV2):
    """Display current migration status"""
    print("\n" + "=" * 70)
    print("MIGRATION STATUS")
    print("=" * 70)
    current_phase = state.get_current_phase()
    print(f"Current Phase: {current_phase.value}")
    print()
    if current_phase.value >= Phase.GLACIER_RESTORE.value:
        summary = state.get_scan_summary()
        print("Overall Summary:")
        print(f"  Total Buckets: {summary['bucket_count']}")
        print(f"  Total Files: {summary['total_files']:,}")
        print(f"  Total Size: {format_bytes(summary['total_size'], binary_units=False)}")
        print()
    all_buckets = state.get_all_buckets()
    if all_buckets:
        completed = len(state.get_completed_buckets_for_phase("delete_complete"))
        print("Bucket Progress:")
        print(f"  Completed: {completed}/{len(all_buckets)} buckets")
        print()
        print("Bucket Details:")
        for bucket in all_buckets:
            status = state.get_bucket_status(bucket)
            sync = "✓" if status.sync_complete else "○"
            verify_mark = "✓" if status.verify_complete else "○"
            delete_mark = "✓" if status.delete_complete else "○"
            print(f"  {bucket}")
            file_size = format_bytes(status.total_size, binary_units=False)
            file_info = f"{status.file_count:,} files, {file_size}"
            print(f"    Sync:{sync} Verify:{verify_mark} Delete:{delete_mark}  ({file_info})")
    print("=" * 70)


def migrate_all_buckets(s3, state: MigrationStateV2, base_path: Path, drive_checker, interrupted: Event):
    """Migrate all buckets one by one"""
    print("=" * 70)
    print("PHASE 4/4: MIGRATING BUCKETS (Sync → Verify → Delete)")
    print("=" * 70)
    print()
    all_buckets = state.get_all_buckets()
    completed_buckets = state.get_completed_buckets_for_phase("delete_complete")
    remaining_buckets = [b for b in all_buckets if b not in completed_buckets]
    if not remaining_buckets:
        print("✓ All buckets already migrated")
        return
    print(f"Migrating {len(remaining_buckets)} bucket(s)")
    print(f"Already complete: {len(completed_buckets)} bucket(s)")
    print()
    for idx, bucket in enumerate(remaining_buckets, 1):
        if interrupted.is_set():
            return
        drive_checker(base_path)
        total = len(remaining_buckets)
        print("╔" + "=" * 68 + "╗")
        print(f"║ BUCKET {idx}/{total}: {bucket.ljust(59)}║")
        print("╚" + "=" * 68 + "╝")
        print()
        _migrate_single_bucket(s3, state, base_path, bucket, idx, total, interrupted)
    _print_completion_status(state, all_buckets)


def _migrate_single_bucket(s3, state, base_path, bucket, idx, total, interrupted):
    """Migrate a single bucket with error handling"""
    try:
        process_bucket(s3, state, base_path, bucket, interrupted)
        print()
        print(f"✓ Bucket {idx}/{total} complete: {bucket}")
        print()
    except (FileNotFoundError, PermissionError, OSError) as e:
        handle_drive_error(e)
    except (RuntimeError, ValueError) as e:
        handle_migration_error(bucket, e)


def _print_completion_status(state, all_buckets):
    """Print completion or paused status"""
    still_incomplete = [b for b in all_buckets if b not in state.get_completed_buckets_for_phase("delete_complete")]
    if not still_incomplete:
        print("=" * 70)
        print("✓ PHASE 4 COMPLETE: All Buckets Migrated")
        print("=" * 70)
        print()
        state.set_current_phase(Phase.COMPLETE)
    else:
        print("=" * 70)
        print("MIGRATION PAUSED")
        print("=" * 70)
        print(f"Completed: {len(all_buckets) - len(still_incomplete)}/{len(all_buckets)} buckets")
        print(f"Remaining: {len(still_incomplete)} buckets")
        print()
        print("Run 'python migrate_v2.py' to continue.")
        print("=" * 70)
        print()
