"""Bucket syncing using boto3 (no subprocess)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable, Iterable

from botocore.exceptions import ClientError

from cost_toolkit.common.format_utils import format_bytes
from migration_state_v2 import MigrationStateV2
from migration_utils import ProgressTracker, format_duration


class SyncInterrupted(RuntimeError):
    """Raised when a sync is interrupted."""


@dataclass
class _ProgressState:
    start_time: float
    files_done: int = 0
    bytes_done: int = 0


def _list_objects(s3_client, bucket: str) -> Iterable[dict]:
    """Yield objects in a bucket, failing fast on malformed responses."""
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        contents = page.get("Contents")
        key_count = page.get("KeyCount")
        if contents is None:
            if key_count not in (None, 0):
                raise RuntimeError("list_objects_v2 returned KeyCount without Contents payload")
            continue
        for obj in contents:
            key = obj["Key"]
            if key.endswith("/"):
                continue
            yield obj


def _download_object(
    s3_client,
    bucket: str,
    key: str,
    destination: Path,
    interrupted_check: Callable[[], bool],
    progress_state: _ProgressState,
    progress_tracker: ProgressTracker,
):
    """Stream an object to disk while checking for interrupts."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
        except TypeError:
            response = s3_client.get_object(bucket, key)
    except ClientError as exc:
        raise RuntimeError(f"Failed to fetch {bucket}/{key}: {exc}") from exc

    body = response["Body"]
    bytes_downloaded = 0
    with destination.open("wb") as handle:
        for chunk in body.iter_chunks():
            if interrupted_check():
                raise SyncInterrupted()
            if not chunk:
                continue
            handle.write(chunk)
            bytes_downloaded += len(chunk)
            if progress_tracker.should_update():
                _display_progress(
                    progress_state.start_time,
                    progress_state.files_done,
                    progress_state.bytes_done + bytes_downloaded,
                )

    progress_state.files_done += 1
    progress_state.bytes_done += bytes_downloaded
    return bytes_downloaded


def sync_bucket(s3, state: MigrationStateV2, base_path: Path, bucket: str, interrupted: Event):
    """Sync bucket from S3 to local using boto3 downloads."""
    local_path = base_path / bucket
    local_path.mkdir(parents=True, exist_ok=True)
    print(f"  Syncing s3://{bucket} -> {local_path}/")
    print()

    progress_state = _ProgressState(start_time=time.time())
    tracker = ProgressTracker(update_interval=1.0)

    was_interrupted = False
    try:
        for obj in _list_objects(s3, bucket):
            if interrupted.is_set():
                was_interrupted = True
                break
            key = obj["Key"]
            dest = local_path / key
            _download_object(
                s3,
                bucket,
                key,
                dest,
                interrupted_check=interrupted.is_set,
                progress_state=progress_state,
                progress_tracker=tracker,
            )
        if not was_interrupted:
            _display_progress(progress_state.start_time, progress_state.files_done, progress_state.bytes_done)
            _print_sync_summary(progress_state.start_time, progress_state.files_done, progress_state.bytes_done)
    except ClientError as exc:
        raise RuntimeError(f"Sync failed for bucket {bucket}: {exc}") from exc
    if was_interrupted:
        print("\n✋ Sync interrupted")


def _display_progress(start_time, files_done, bytes_done):
    """Display sync progress."""
    elapsed = 0
    if start_time:
        elapsed = time.time() - start_time
    if elapsed > 0 and bytes_done > 0:
        throughput = bytes_done / elapsed
        progress = (
            f"Progress: {files_done:,} files, {format_bytes(bytes_done, binary_units=False)} "
            f"({format_bytes(throughput, binary_units=False)}/s)  "
        )
        print(f"\r  {progress}", end="", flush=True)


def _print_sync_summary(start_time, files_done, bytes_done):
    """Print sync completion summary."""
    elapsed = 0
    if start_time:
        elapsed = time.time() - start_time
    elapsed = max(elapsed, 0.0001)
    throughput = 0
    if elapsed > 0:
        throughput = bytes_done / elapsed
    print(f"\n✓ Completed in {format_duration(elapsed)}")
    print(f"  Downloaded: {files_done:,} files, {format_bytes(bytes_done, binary_units=False)}")
    print(f"  Throughput: {format_bytes(throughput, binary_units=False)}/s")
    print()
