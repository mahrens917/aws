#!/usr/bin/env python3
"""CLI tool to locate and compress large locally downloaded objects."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

try:
    from config import LOCAL_BASE_PATH, STATE_DB_PATH
except ImportError as exc:  # pragma: no cover - failure is fatal for this CLI
    raise SystemExit(f"Unable to import config module: {exc}") from exc

try:
    from cost_toolkit.common.cli_utils import (
        create_migration_cli_parser,
        handle_state_db_reset,
    )
    from cost_toolkit.common.format_utils import parse_size
except ImportError as exc:  # pragma: no cover - failure is fatal for this CLI
    raise SystemExit(f"Unable to import cost_toolkit modules: {exc}") from exc

try:
    from state_db_admin import reseed_state_db_from_local_drive
except ImportError as exc:  # pragma: no cover - failure is fatal for this CLI
    raise SystemExit(f"Unable to import state_db_admin module: {exc}") from exc

from find_compressible.analysis import find_candidates
from find_compressible.reporting import (
    print_compression_summary,
    print_scan_summary,
    report_and_compress_candidates,
)

# Ensure the repository root is importable even when this script is run via an absolute path.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_MIN_SIZE = 512 * 1024 * 1024  # 512 MiB


def _parse_size_argparse(value: str) -> int:
    """Argparse wrapper for canonical parse_size in format_utils."""
    return parse_size(value, for_argparse=True)


def _add_module_specific_args(parser: argparse.ArgumentParser) -> None:
    """Add find_compressible-specific arguments to the parser."""
    parser.add_argument(
        "--min-size",
        type=_parse_size_argparse,
        default=DEFAULT_MIN_SIZE,
        help="Minimum file size to consider (accepts suffixes like 512M, 2G). Default: 512M",
    )
    parser.add_argument(
        "--bucket",
        action="append",
        dest="buckets",
        default=[],
        help="Optional bucket filter. Repeat --bucket for multiple buckets.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after reporting this many candidates (0 means no limit).",
    )
    parser.add_argument(
        "--compress",
        action="store_true",
        help="Compress each reported file in-place using `xz -9e`. Disabled by default.",
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for compression workflow."""
    parser = create_migration_cli_parser(
        description=(
            "Scan the SQLite migration database for large, locally downloaded files that are "
            "likely to compress well with xz -9. Images, videos, and already compressed files "
            "are automatically skipped."
        ),
        db_path_default=STATE_DB_PATH,
        base_path_default=LOCAL_BASE_PATH,
        add_custom_args=_add_module_specific_args,
    )
    return parser.parse_args()


def main() -> None:
    """Execute the compression analysis and optional compression workflow."""
    args = parse_args()
    base_path = Path(args.base_path).expanduser()
    if not base_path.exists():
        raise SystemExit(f"Base path does not exist: {base_path}")

    buckets = sorted(set(args.buckets)) if args.buckets else []
    db_path = Path(args.db_path).expanduser()

    db_path = handle_state_db_reset(base_path, db_path, args.reset_state_db, args.yes, reseed_state_db_from_local_drive)

    if not db_path.exists():
        raise SystemExit(f"State DB not found at {db_path}. Run migrate_v2 first.")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    stats: Counter = Counter()

    try:
        all_candidates = sorted(
            find_candidates(
                conn=conn,
                base_path=base_path,
                min_size=args.min_size,
                buckets=buckets,
                stats=stats,
            ),
            key=lambda item: item.size_bytes,
            reverse=True,
        )
    finally:
        conn.close()

    reported_candidates = all_candidates[: args.limit] if args.limit else all_candidates
    total_reported = len(reported_candidates)
    total_bytes = sum(candidate.size_bytes for candidate in reported_candidates)

    (
        compressed_files,
        compression_failures,
        total_original_space,
        total_compressed_space,
        reported_extensions,
    ) = report_and_compress_candidates(reported_candidates, args.compress, stats)

    print_scan_summary(
        base_path,
        db_path,
        stats,
        total_reported=total_reported,
        total_bytes=total_bytes,
        reported_extensions=reported_extensions,
    )

    if args.compress:
        print_compression_summary(compressed_files, total_original_space, total_compressed_space, compression_failures)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt as exc:  # pragma: no cover - manual abort
        raise SystemExit("\nAborted by user.") from exc
