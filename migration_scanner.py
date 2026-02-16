"""Phase 1-3: Scanning buckets and handling Glacier restores"""

from dataclasses import dataclass, field
from threading import Event

from botocore.exceptions import ClientError

import config as config_module
from cost_toolkit.common.format_utils import format_bytes
from migration_state_managers import BucketScanStatus, FileMetadata
from migration_state_v2 import MigrationStateV2, Phase

EXCLUDED_BUCKETS = config_module.EXCLUDED_BUCKETS
GLACIER_RESTORE_DAYS = config_module.GLACIER_RESTORE_DAYS
GLACIER_RESTORE_TIER = config_module.GLACIER_RESTORE_TIER


@dataclass
class _BucketStats:
    file_count: int = 0
    total_size: int = 0
    storage_classes: dict[str, int] = field(default_factory=dict)

    def record(self, size: int, storage_class: str):
        """Track a processed object size and storage class count."""
        self.file_count += 1
        self.total_size += size
        if storage_class in self.storage_classes:
            self.storage_classes[storage_class] += 1
        else:
            self.storage_classes[storage_class] = 1


def _get_page_contents(bucket: str, page: dict) -> list[dict]:
    """Extract object listings from a paginator page, validating key counts."""
    contents = page.get("Contents")
    key_count = page.get("KeyCount")
    if contents is None:
        if key_count not in (None, 0):
            raise RuntimeError(f"list_objects_v2 missing Contents while reporting {key_count} keys" f" for bucket {bucket}")
        return []
    return contents


def _print_progress(stats: _BucketStats):
    size_str = format_bytes(stats.total_size, binary_units=False)
    print(
        f"  Found {stats.file_count:,} files, {size_str}...",
        end="\r",
        flush=True,
    )


def _process_object(state: MigrationStateV2, bucket: str, obj: dict, stats: _BucketStats):
    key = obj["Key"]
    if key.endswith("/"):
        return
    size = obj["Size"]
    etag = obj["ETag"].strip('"')
    storage_class = obj.get("StorageClass")
    if storage_class is None:
        storage_class = "STANDARD"
    last_modified = obj["LastModified"].isoformat()
    metadata = FileMetadata(bucket=bucket, key=key, size=size, etag=etag, storage_class=storage_class, last_modified=last_modified)
    state.add_file(metadata)
    stats.record(size, storage_class)
    if stats.file_count % 10000 == 0:
        _print_progress(stats)


def _save_bucket_stats(state: MigrationStateV2, bucket: str, stats: _BucketStats):
    status = BucketScanStatus(
        bucket=bucket, file_count=stats.file_count, total_size=stats.total_size, storage_classes=stats.storage_classes, scan_complete=True
    )
    state.save_bucket_status(status)
    print(f"  Found {stats.file_count:,} files, " f"{format_bytes(stats.total_size, binary_units=False)}" + " " * 20)


def scan_bucket(s3, state: MigrationStateV2, bucket: str, interrupted: Event):
    """Scan a single bucket"""
    stats = _BucketStats()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        if interrupted.is_set():
            return
        for obj in _get_page_contents(bucket, page):
            _process_object(state, bucket, obj, stats)
    _save_bucket_stats(state, bucket, stats)


def scan_all_buckets(s3, state: MigrationStateV2, interrupted: Event):
    """Scan all S3 buckets and track in database"""
    print("=" * 70)
    print("PHASE 1/4: SCANNING BUCKETS")
    print("=" * 70)
    print()
    response = s3.list_buckets()
    buckets = [b["Name"] for b in response["Buckets"]]
    excluded = EXCLUDED_BUCKETS
    buckets = [b for b in buckets if b not in excluded]
    print(f"Found {len(buckets)} bucket(s)")
    if excluded:
        print(f"Excluded {len(excluded)} bucket(s): {', '.join(excluded)}")
    print()
    for idx, bucket in enumerate(buckets, 1):
        if interrupted.is_set():
            return
        print(f"[{idx}/{len(buckets)}] Scanning: {bucket}")
        scan_bucket(s3, state, bucket, interrupted)
        print()
    state.set_current_phase(Phase.GLACIER_RESTORE)
    print("=" * 70)
    print("✓ PHASE 1 COMPLETE: All Buckets Scanned")
    print("=" * 70)
    print()


def request_restore(s3, state: MigrationStateV2, file_info: dict, idx: int, total: int):
    """Request restore for a single file"""
    bucket = file_info["bucket"]
    key = file_info["key"]
    storage_class = file_info["storage_class"]
    tier = "Bulk" if storage_class == "DEEP_ARCHIVE" else GLACIER_RESTORE_TIER
    try:
        s3.restore_object(
            Bucket=bucket,
            Key=key,
            RestoreRequest={
                "Days": GLACIER_RESTORE_DAYS,
                "GlacierJobParameters": {"Tier": tier},
            },
        )
        state.mark_glacier_restore_requested(bucket, key)
        print(f"  [{idx}/{total}] Requested: {bucket}/{key}")
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "RestoreAlreadyInProgress":
            state.mark_glacier_restore_requested(bucket, key)
        else:
            raise


def request_all_restores(s3, state: MigrationStateV2, interrupted: Event):
    """Request Glacier restore for all archived files"""
    print("=" * 70)
    print("PHASE 2/4: REQUESTING GLACIER RESTORES")
    print("=" * 70)
    print()
    files = state.get_glacier_files_needing_restore()
    if not files:
        print("✓ No Glacier files need restore")
        print()
        state.set_current_phase(Phase.GLACIER_WAIT)
        return
    print(f"Requesting restores for {len(files):,} file(s)")
    print()
    for idx, file in enumerate(files, 1):
        if interrupted.is_set():
            return
        request_restore(s3, state, file, idx, len(files))
    state.set_current_phase(Phase.GLACIER_WAIT)
    print()
    print("=" * 70)
    print("✓ PHASE 2 COMPLETE: All Restores Requested")
    print("=" * 70)
    print()


def _wait_with_interrupt(interrupted: Event, seconds: int):
    """Wait using the event so interrupts are respected without time.sleep."""
    interrupted.wait(seconds)


def check_restore_status(s3, state: MigrationStateV2, file_info: dict) -> bool:
    """Check if restore is complete for a file.

    Raises:
        ClientError: If the S3 API call fails for reasons other than expected restore states.
    """
    response = s3.head_object(Bucket=file_info["bucket"], Key=file_info["key"])
    restore_status = response.get("Restore")
    if restore_status and 'ongoing-request="false"' in restore_status:
        state.mark_glacier_restored(file_info["bucket"], file_info["key"])
        return True
    return False


def wait_for_restores(s3, state: MigrationStateV2, interrupted: Event):
    """Wait for all Glacier restores to complete"""
    print("=" * 70)
    print("PHASE 3/4: WAITING FOR GLACIER RESTORES")
    print("=" * 70)
    print()
    while not interrupted.is_set():
        restoring = state.get_files_restoring()
        if not restoring:
            break
        print(f"Checking {len(restoring):,} file(s) still restoring...")
        for idx, file in enumerate(restoring):
            if interrupted.is_set():
                return
            if check_restore_status(s3, state, file):
                print(f"  [{idx+1}/{len(restoring)}] Restored: {file['bucket']}/{file['key']}")
        print()
        print("Waiting 5 minutes before next check...")
        _wait_with_interrupt(interrupted, 300)
    state.set_current_phase(Phase.SYNCING)
    print("=" * 70)
    print("✓ PHASE 3 COMPLETE: All Restores Complete")
    print("=" * 70)
    print()
