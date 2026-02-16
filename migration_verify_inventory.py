"""Local inventory helpers for migration verification."""

from __future__ import annotations

import os
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Set, Tuple

_PACKAGE_PREFIX = f"{__package__}." if __package__ else ""
_migration_utils = import_module(f"{_PACKAGE_PREFIX}migration_utils")
_migration_verify_common = import_module(f"{_PACKAGE_PREFIX}migration_verify_common")

ProgressTracker = _migration_utils.ProgressTracker
MAX_ERROR_DISPLAY = _migration_verify_common.MAX_ERROR_DISPLAY
should_ignore_key = _migration_verify_common.should_ignore_key

if TYPE_CHECKING:
    from migration_state_v2 import MigrationStateV2


def _load_expected_file_map(state: "MigrationStateV2", bucket: str) -> Dict[str, Dict]:
    print("  Loading file metadata from database...")
    expected_file_map: Dict[str, Dict] = {}
    with state.db_conn.get_connection() as conn:
        cursor = conn.execute("SELECT key, size, etag FROM files WHERE bucket = ?", (bucket,))
        for row in cursor:
            normalized_key = row["key"].replace("\\", "/")
            expected_file_map[normalized_key] = {"size": row["size"], "etag": row["etag"]}
    print(f"  Loaded {len(expected_file_map):,} file records")
    print()
    return expected_file_map


def _scan_local_directory(base_path: Path, bucket: str, expected_files: int) -> Dict[str, Path]:
    print("  Scanning local files...")
    local_path = base_path / bucket
    local_files: Dict[str, Path] = {}
    scan_count = 0
    progress = ProgressTracker(update_interval=2.0)
    base_str = str(local_path)
    for root, _, files in os.walk(base_str):
        for file_name in files:
            file_path = Path(root) / file_name
            s3_key = os.path.relpath(file_path, base_str).replace("\\", "/")
            local_files[s3_key] = file_path
            scan_count += 1
            if progress.should_update() or scan_count % 10000 == 0:
                percentage = (scan_count / expected_files * 100) if expected_files > 0 else 0
                print(
                    f"\r  Scanned: {scan_count:,} files ({percentage:.1f}%)  ",
                    end="",
                    flush=True,
                )
    print(f"\r  Found {len(local_files):,} local files" + " " * 30)
    print()
    return local_files


def _partition_inventory(expected_keys: Set[str], local_keys: Set[str]) -> Tuple[Set[str], Set[str], int]:
    missing_files = expected_keys - local_keys
    extra_files_raw = local_keys - expected_keys
    extra_files = {key for key in extra_files_raw if not should_ignore_key(key)}
    ignored_count = len(extra_files_raw) - len(extra_files)
    return missing_files, extra_files, ignored_count


def _inventory_error_messages(missing_files: Set[str], extra_files: Set[str]) -> List[str]:
    errors: List[str] = []
    for key in list(missing_files)[:MAX_ERROR_DISPLAY]:
        errors.append(f"Missing file: {key}")
    if len(missing_files) > MAX_ERROR_DISPLAY:
        errors.append(f"... and {len(missing_files) - MAX_ERROR_DISPLAY} more missing files")
    for key in list(extra_files)[:MAX_ERROR_DISPLAY]:
        errors.append(f"Extra file (not in S3): {key}")
    if len(extra_files) > MAX_ERROR_DISPLAY:
        errors.append(f"... and {len(extra_files) - MAX_ERROR_DISPLAY} more extra files")
    return errors


def _validate_inventory(expected_keys: Set[str], local_keys: Set[str]) -> List[str]:
    print("  Checking file inventory...")
    missing_files, extra_files, ignored_count = _partition_inventory(expected_keys, local_keys)
    if ignored_count > 0:
        print(f"  ℹ Ignoring {ignored_count} system metadata file(s) (.DS_Store, Thumbs.db, etc.)")
    errors = _inventory_error_messages(missing_files, extra_files)
    if errors:
        print("  ✗ File inventory mismatch:")
        for error in errors:
            print(f"    - {error}")
        print()
        msg = f"File inventory check failed: {len(missing_files)} missing, {len(extra_files)} extra"
        raise ValueError(msg)
    return errors


def load_expected_files(state: "MigrationStateV2", bucket: str) -> Dict[str, Dict]:
    """Load expected file metadata for the requested bucket."""
    return _load_expected_file_map(state, bucket)


def scan_local_files(base_path: Path, bucket: str, expected_files: int) -> Dict[str, Path]:
    """Scan the on-disk directory for the bucket and return discovered files."""
    return _scan_local_directory(base_path, bucket, expected_files)


def check_inventory(expected_keys: Set[str], local_keys: Set[str]) -> List[str]:
    """Compare inventory results and raise when they differ."""
    return _validate_inventory(expected_keys, local_keys)


__all__ = ["check_inventory", "load_expected_files", "scan_local_files"]
