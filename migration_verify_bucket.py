"""Bucket-level verification orchestration."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Dict

_PACKAGE_PREFIX = f"{__package__}." if __package__ else ""
_migration_utils = import_module(f"{_PACKAGE_PREFIX}migration_utils")
_migration_verify_checksums = import_module(f"{_PACKAGE_PREFIX}migration_verify_checksums")
_migration_verify_common = import_module(f"{_PACKAGE_PREFIX}migration_verify_common")
_migration_verify_inventory = import_module(f"{_PACKAGE_PREFIX}migration_verify_inventory")
_format_utils = import_module("cost_toolkit.common.format_utils")

format_bytes = _format_utils.format_bytes
print_verification_success_messages = _migration_utils.print_verification_success_messages
verify_files = _migration_verify_checksums.verify_files
LocalPathMissingError = _migration_verify_common.LocalPathMissingError
VerificationCountMismatchError = _migration_verify_common.VerificationCountMismatchError
load_expected_files = _migration_verify_inventory.load_expected_files
scan_local_files = _migration_verify_inventory.scan_local_files
check_inventory = _migration_verify_inventory.check_inventory

if TYPE_CHECKING:
    from migration_state_v2 import MigrationStateV2


def verify_bucket(state: "MigrationStateV2", base_path: Path, bucket: str) -> Dict[str, int]:
    """Verify a bucket's files locally with complete integrity checking."""
    bucket_info = state.get_bucket_info(bucket)
    expected_files = bucket_info["file_count"]
    expected_size = bucket_info["total_size"]
    local_path = base_path / bucket
    if not local_path.exists():
        raise LocalPathMissingError(local_path)
    expected_size_str = format_bytes(expected_size, binary_units=False)
    print(f"  Expected: {expected_files:,} files, {expected_size_str}")
    print()
    expected_file_map = load_expected_files(state, bucket)
    local_files = scan_local_files(base_path, bucket, expected_files)
    expected_keys = set(expected_file_map.keys())
    local_keys = set(local_files.keys())
    check_inventory(expected_keys, local_keys)
    print(f"  ✓ All {expected_files:,} files present (no missing or extra files)")
    print()
    verify_results = verify_files(local_files, expected_file_map, expected_files, expected_size)
    verified_count = verify_results["verified_count"]
    size_verified = verify_results["size_verified"]
    checksum_verified = verify_results["checksum_verified"]
    total_bytes_verified = verify_results["total_bytes_verified"]

    # Calculate ignored system files
    ignored_count = len(local_files) - expected_files

    print(f"  S3 files:             {expected_files:,}")
    print(f"  Verified files:       {verified_count:,}")
    print(f"  - Size verified:      {size_verified:,}")
    print(f"  - Checksum verified:  {checksum_verified:,}")
    if ignored_count > 0:
        print()
        print(f"  (Ignored {ignored_count:,} system metadata files: .DS_Store, etc.)")
    print()
    if verified_count != expected_files:
        raise VerificationCountMismatchError(verified_count, expected_files)
    print(f"  ✓ All {verified_count:,} files verified successfully")
    print_verification_success_messages()
    print(f"  ✓ Total size: {format_bytes(bucket_info['total_size'], binary_units=False)}")
    print()
    return {
        "verified_count": verified_count,
        "size_verified": size_verified,
        "checksum_verified": checksum_verified,
        "total_bytes_verified": total_bytes_verified,
        "local_file_count": len(local_files),
    }


__all__ = ["verify_bucket"]
