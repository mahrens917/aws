"""CLI workflow for duplicate tree analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import config as config_module
from cost_toolkit.common.cli_utils import (
    create_migration_cli_parser,
    handle_state_db_reset,
)
from duplicate_tree.analysis import (
    MIN_REPORT_BYTES,
    MIN_REPORT_FILES,
    build_directory_index_from_db,
    recompute_clusters_for_deletion,
)
from duplicate_tree.deletion import delete_duplicate_directories
from duplicate_tree.workflow import (
    DuplicateAnalysisContext,
    load_or_compute_duplicates,
)
from state_db_admin import reseed_state_db_from_local_drive


def _add_module_specific_args(parser: argparse.ArgumentParser) -> None:
    """Add duplicate_tree-specific arguments to the parser."""
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore cached duplicate analysis and recompute from scratch.",
    )
    parser.add_argument(
        "--min-files",
        type=int,
        default=MIN_REPORT_FILES,
        help="Minimum files per directory to include (default: %(default)s).",
    )
    parser.add_argument(
        "--min-size-gb",
        type=float,
        default=MIN_REPORT_BYTES / (1024**3),
        help="Minimum directory size (GiB) to include (default: %(default).2f).",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help=("After reporting duplicates, delete every directory except the first entry " "in each cluster (requires confirmation)."),
    )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments controlling database path, base path, and tolerance."""
    parser = create_migration_cli_parser(
        description=("Detect exact duplicate directory trees on the external drive " "using migrate_v2's SQLite metadata."),
        db_path_default=config_module.STATE_DB_PATH,
        base_path_default=config_module.LOCAL_BASE_PATH,
        add_custom_args=_add_module_specific_args,
    )
    # pylint: enable=no-member
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the duplicate tree report workflow."""
    args = parse_args(argv)
    base_path = Path(args.base_path).expanduser()
    db_path = Path(args.db_path).expanduser()

    db_path = handle_state_db_reset(base_path, db_path, args.reset_state_db, args.yes, reseed_state_db_from_local_drive)

    if not db_path.exists():
        print(f"State DB not found at {db_path}. Run migrate_v2 first.", file=sys.stderr)
        return 1

    min_files = max(0, args.min_files)
    min_bytes = max(0, int(args.min_size_gb * (1024**3)))
    print(f"Using database: {db_path}")
    print(f"Assumed drive root: {base_path}")

    index, fingerprint = build_directory_index_from_db(str(db_path))
    base_path_str = str(base_path)
    can_cache_results = args.min_files == MIN_REPORT_FILES and min_bytes == MIN_REPORT_BYTES
    use_cache = (not args.refresh_cache) and can_cache_results

    context = DuplicateAnalysisContext(
        db_path=str(db_path),
        base_path=base_path,
        base_path_str=base_path_str,
        min_files=min_files,
        min_bytes=min_bytes,
        use_cache=use_cache,
        can_cache_results=can_cache_results,
    )

    cluster_rows, report_text = load_or_compute_duplicates(index, fingerprint, context)

    if report_text:
        print(report_text, end="" if report_text.endswith("\n") else "\n")

    if args.delete:
        if cluster_rows is None:
            print("Cached report lacks structured duplicate data. Recomputing duplicates to prepare deletion plan...")
            cluster_rows = recompute_clusters_for_deletion(index, min_files, min_bytes)
        delete_duplicate_directories(cluster_rows or [], base_path)

    print("Done.")
    return 0
