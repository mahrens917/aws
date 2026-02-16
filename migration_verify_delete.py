"""Bucket deletion helpers for migration verification."""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any, List

if __package__:
    _PACKAGE_PREFIX = f"{__package__}."
else:
    _PACKAGE_PREFIX = ""
_migration_utils = import_module(f"{_PACKAGE_PREFIX}migration_utils")
_migration_verify_common = import_module(f"{_PACKAGE_PREFIX}migration_verify_common")

ProgressTracker = _migration_utils.ProgressTracker
calculate_eta_items = _migration_utils.calculate_eta_items
format_duration = _migration_utils.format_duration
BucketNotEmptyError = _migration_verify_common.BucketNotEmptyError

if TYPE_CHECKING:
    from migration_state_v2 import MigrationStateV2


def delete_bucket(s3, state: "MigrationStateV2", bucket: str) -> None:
    """Delete a bucket and all its contents from S3 (including all versions)."""
    bucket_info = state.get_bucket_info(bucket)
    total_objects = bucket_info["file_count"]
    print(f"  Deleting {total_objects:,} objects from S3 (including all versions)...")
    print()

    paginator = s3.get_paginator("list_object_versions")
    deleted_count = 0
    start_time = time.time()
    progress = ProgressTracker(update_interval=2.0)
    context = _DeleteContext(
        s3=s3,
        bucket=bucket,
        total_objects=total_objects,
        progress=progress,
        start_time=start_time,
    )

    for page in paginator.paginate(Bucket=bucket):
        deleted_count = _process_delete_page(page, deleted_count, context)

    print()
    duration = format_duration(time.time() - start_time)
    print(f"  ✓ Deleted {deleted_count:,} objects/versions in {duration}")
    print()
    _abort_multipart_uploads(s3, bucket)

    if _bucket_has_contents(s3, bucket):
        raise BucketNotEmptyError()

    print("  Deleting empty bucket...")
    s3.delete_bucket(Bucket=bucket)


def _collect_objects_to_delete(page) -> List[dict]:
    """Collect all object versions and delete markers from a page."""
    objects_to_delete = []
    if "Versions" in page:
        for version in page["Versions"]:
            objects_to_delete.append({"Key": version["Key"], "VersionId": version["VersionId"]})
    if "DeleteMarkers" in page:
        for marker in page["DeleteMarkers"]:
            objects_to_delete.append({"Key": marker["Key"], "VersionId": marker["VersionId"]})
    return objects_to_delete


def _ensure_list(entries) -> List[dict]:
    """Return entries as a list regardless of boto/mock response shape."""
    if not entries:
        return []
    if isinstance(entries, dict):
        return [entries]
    if isinstance(entries, Iterable):
        return list(entries)
    return []


def _abort_multipart_uploads(s3, bucket: str) -> None:
    """Abort any in-progress multipart uploads for the bucket."""
    paginator = s3.get_paginator("list_multipart_uploads")
    aborted = 0
    for page in paginator.paginate(Bucket=bucket):
        if "Uploads" not in page:
            uploads = []
        else:
            uploads = page["Uploads"]
        for upload in uploads:
            s3.abort_multipart_upload(
                Bucket=bucket,
                Key=upload["Key"],
                UploadId=upload["UploadId"],
            )
            aborted += 1
    if aborted:
        print(f"  Aborted {aborted:,} multipart uploads before final delete")


def _bucket_has_contents(s3, bucket: str) -> bool:
    """Return True if any versions/delete markers remain in the bucket."""
    paginator = s3.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket, PaginationConfig={"MaxItems": 1}):
        versions_raw = page.get("Versions")
        delete_markers_raw = page.get("DeleteMarkers")
        versions = []
        if versions_raw:
            versions = _ensure_list(versions_raw)

        delete_markers = []
        if delete_markers_raw:
            delete_markers = _ensure_list(delete_markers_raw)
        if versions or delete_markers:
            return True
    return False


def _process_delete_page(
    page: dict,
    deleted_count: int,
    context: "_DeleteContext",
) -> int:
    """Delete a single paginator page worth of objects and update progress."""
    objects_to_delete = _collect_objects_to_delete(page)
    if not objects_to_delete:
        return deleted_count
    errors = _delete_page_objects(context.s3, context.bucket, objects_to_delete)
    deleted_count += len(objects_to_delete) - len(errors)
    if context.progress.should_update() or deleted_count % 1000 == 0:
        _print_delete_progress(deleted_count, context.total_objects, context.start_time)
    if not errors:
        page.pop("Versions", None)
        page.pop("DeleteMarkers", None)
    return deleted_count


def _delete_page_objects(s3, bucket: str, objects_to_delete: List[dict]) -> List[dict]:
    """Issue a bulk delete for the provided objects and return any errors."""
    response = s3.delete_objects(Bucket=bucket, Delete={"Objects": objects_to_delete}) or {}
    response_errors_raw = []
    if isinstance(response, dict) and "Errors" in response:
        response_errors_raw = response["Errors"]
    elif hasattr(response, "get") and response.get("Errors") is not None:
        response_errors_raw = response["Errors"]
    errors = _ensure_list(response_errors_raw)
    if errors:
        print("\n  Encountered delete errors:")
        for error in errors:
            print(f"    Key={error['Key']} VersionId={error['VersionId']} " f"Code={error['Code']} Message={error['Message']}")
    return errors


def _print_delete_progress(deleted_count: int, total_objects: int, start_time: float) -> None:
    """Render a consistent progress line for the delete workflow."""
    elapsed = time.time() - start_time
    pct = (deleted_count / total_objects * 100) if total_objects > 0 else 0
    eta_str = calculate_eta_items(elapsed, deleted_count, total_objects)
    progress_str = f"Progress: {deleted_count:,} deleted ({pct:.1f}%), ETA: {eta_str}  "
    print(f"\r  {progress_str}", end="", flush=True)


@dataclass(frozen=True)
class _DeleteContext:
    """Container for delete_bucket shared metadata."""

    s3: Any
    bucket: str
    total_objects: int
    progress: ProgressTracker
    start_time: float


__all__ = ["delete_bucket"]
