"""
Database loading and caching integration for cleanup_temp_artifacts.

Handles database connection, cache management, and candidate loading orchestration.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .cache import (
    CacheReadError,
    CacheValidationError,
    build_cache_key,
    cache_is_valid,
    load_cache,
    write_cache,
)
from .categories import Category
from .core_scanner import (
    Candidate,
    CandidateLoadError,
    CandidateLoadResult,
    scan_candidates_from_db,
)


@dataclass
class CacheConfig:
    """Configuration for cache operations."""

    enabled: bool
    cache_dir: Path
    refresh_cache: bool
    cache_ttl: int


@dataclass
class DatabaseInfo:
    """Database metadata and statistics."""

    db_path: Path
    db_stat: os.stat_result
    total_files: int
    max_rowid: int


@dataclass
class ScanContext:
    """Context for scanning candidates from database."""

    args: argparse.Namespace
    scan_params: dict[str, object]
    category_map: dict[str, Category]
    cutoff_ts: float | None


def _get_db_file_stats(conn: sqlite3.Connection) -> tuple[int, int]:
    """Get total file count and max rowid from database."""
    try:
        total_files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    except sqlite3.OperationalError as exc:
        raise CandidateLoadError("Migration database missing expected 'files' table") from exc

    try:
        max_rowid_row = conn.execute("SELECT MAX(rowid) FROM files").fetchone()
        max_rowid = max_rowid_row[0] if max_rowid_row and max_rowid_row[0] is not None else 0
    except sqlite3.OperationalError as exc:
        raise CandidateLoadError("Migration database missing expected 'rowid' column") from exc

    return total_files, max_rowid


def _try_load_from_cache(
    cache_config: CacheConfig,
    base_path: Path,
    db_info: DatabaseInfo,
    scan_params: dict[str, object],
    category_map: dict[str, Category],
) -> tuple[Path | None, bool, list[Candidate] | None]:
    """Attempt to load candidates from cache. Returns (cache_path, cache_used, candidates)."""
    if not cache_config.enabled:
        return None, False, None

    cache_key = build_cache_key(base_path, db_info.db_path, scan_params)
    cache_config.cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_config.cache_dir / f"{cache_key}.json"

    if not cache_path.exists() or cache_config.refresh_cache:
        return cache_path, False, None

    try:
        cached_candidates, metadata = load_cache(cache_path, scan_params, category_map)
        is_valid = cache_is_valid(
            metadata,
            ttl_seconds=cache_config.cache_ttl,
            rowcount=db_info.total_files,
            max_rowid=db_info.max_rowid,
            db_mtime_ns=db_info.db_stat.st_mtime_ns,
        )
    except (CacheReadError, CacheValidationError) as exc:
        logging.info("Cache invalid, will rescan: %s", exc)
        return cache_path, False, None

    if not is_valid:
        return cache_path, False, None

    if "generated_at" not in metadata:
        raise CacheValidationError("Cache metadata missing generated_at timestamp")
    generated = metadata["generated_at"]
    print(f"Using cached results from {generated} " f"(files={db_info.total_files:,}). Use --refresh-cache to rescan.\n")
    return cache_path, True, cached_candidates


def _build_cache_and_db_info(
    args: argparse.Namespace,
    db_path: Path,
    db_stat: os.stat_result,
    total_files: int,
    max_rowid: int,
) -> tuple[CacheConfig, DatabaseInfo]:
    """Build cache configuration and database info objects."""
    cache_config = CacheConfig(
        enabled=args.cache_enabled,
        cache_dir=args.cache_dir,
        refresh_cache=args.refresh_cache,
        cache_ttl=args.cache_ttl,
    )
    db_info = DatabaseInfo(db_path=db_path, db_stat=db_stat, total_files=total_files, max_rowid=max_rowid)
    return cache_config, db_info


def _load_or_scan_candidates(
    conn: sqlite3.Connection,
    *,
    cache_config: CacheConfig,
    base_path: Path,
    db_info: DatabaseInfo,
    scan_ctx: ScanContext,
) -> tuple[Path | None, bool, list[Candidate]]:
    """Load candidates from cache or scan database."""
    cache_path, cache_used, candidates = _try_load_from_cache(cache_config, base_path, db_info, scan_ctx.scan_params, scan_ctx.category_map)

    if candidates is None:
        candidates = scan_candidates_from_db(
            conn,
            base_path,
            scan_ctx.args.categories,
            cutoff_ts=scan_ctx.cutoff_ts,
            min_size_bytes=scan_ctx.args.min_size_bytes,
            total_files=db_info.total_files,
        )

    return cache_path, cache_used, candidates


def _create_db_connection(db_path: Path) -> sqlite3.Connection:
    """Create and configure database connection."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:  # pragma: no cover - connection failure
        raise CandidateLoadError(f"Failed to open SQLite database {db_path}") from exc
    return conn


def _perform_scan_operations(
    conn: sqlite3.Connection,
    *,
    args: argparse.Namespace,
    base_path: Path,
    db_path: Path,
    db_stat: os.stat_result,
    cutoff_ts: float | None,
    scan_params: dict[str, object],
) -> CandidateLoadResult:
    """Perform all scanning operations and return results."""
    total_files, max_rowid = _get_db_file_stats(conn)
    cache_config, db_info = _build_cache_and_db_info(args, db_path, db_stat, total_files, max_rowid)
    scan_ctx = ScanContext(
        args=args,
        scan_params=scan_params,
        category_map={cat.name: cat for cat in args.categories},
        cutoff_ts=cutoff_ts,
    )
    cache_path, cache_used, candidates = _load_or_scan_candidates(
        conn, cache_config=cache_config, base_path=base_path, db_info=db_info, scan_ctx=scan_ctx
    )

    return CandidateLoadResult(
        candidates=candidates,
        cache_path=cache_path,
        cache_used=cache_used,
        total_files=total_files,
        max_rowid=max_rowid,
    )


def load_candidates_from_db(
    *,
    args: argparse.Namespace,
    base_path: Path,
    db_path: Path,
    db_stat: os.stat_result,
    cutoff_ts: float | None,
    scan_params: dict[str, object],
) -> CandidateLoadResult:
    """Read candidate directories, honoring cache settings."""
    conn = _create_db_connection(db_path)
    try:
        return _perform_scan_operations(
            conn,
            args=args,
            base_path=base_path,
            db_path=db_path,
            db_stat=db_stat,
            cutoff_ts=cutoff_ts,
            scan_params=scan_params,
        )
    finally:
        conn.close()


class CacheWriteError(RuntimeError):
    """Raised when cache file cannot be written."""


def write_cache_if_needed(
    cache_config: CacheConfig,
    load_result: CandidateLoadResult,
    *,
    cache_path: Path | None,
    cache_used: bool,
    base_path: Path,
    db_info: DatabaseInfo,
    scan_params: dict[str, object],
) -> None:
    """Write cache if enabled and not already used.

    Raises:
        CacheWriteError: If cache file cannot be written
    """
    if not cache_config.enabled or not cache_path or cache_used:
        return

    try:
        write_cache(
            cache_path,
            load_result.candidates,
            scan_params=scan_params,
            base_path=base_path,
            db_info=db_info,
        )
    except OSError as exc:
        raise CacheWriteError(f"Failed to write cache {cache_path}: {exc}") from exc
