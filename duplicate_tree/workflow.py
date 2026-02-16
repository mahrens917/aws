"""Workflow orchestration for duplicate analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from duplicate_tree.analysis import (
    ClusterRow,
    ScanFingerprint,
    apply_thresholds,
    clusters_to_rows,
    render_report_rows,
)
from duplicate_tree.cache import CacheLocation, load_cached_report, store_cached_report
from duplicate_tree.core import (
    DirectoryIndex,
    find_exact_duplicates,
)


@dataclass(frozen=True)
class DuplicateAnalysisContext:
    """Context for duplicate analysis operations."""

    db_path: str
    base_path: Path
    base_path_str: str
    min_files: int
    min_bytes: int
    use_cache: bool
    can_cache_results: bool


def load_cached_duplicates(
    context: DuplicateAnalysisContext,
    fingerprint: ScanFingerprint,
) -> Optional[tuple[Optional[List[ClusterRow]], str]]:
    """Attempt to load cached duplicate analysis."""
    if not context.use_cache:
        return None
    location = CacheLocation(
        db_path=context.db_path,
        fingerprint=fingerprint,
        base_path=context.base_path_str,
        min_files=context.min_files,
        min_bytes=context.min_bytes,
    )
    cached_report = load_cached_report(location)
    if not cached_report:
        return None

    print("Using cached duplicate analysis from " f"{cached_report['generated_at']} " f"({int(cached_report['total_files']):,} files).")
    if "rows" in cached_report:
        cluster_rows: Optional[List[ClusterRow]] = cached_report["rows"]
        report_text = render_report_rows(cluster_rows, context.base_path)
    else:
        cluster_rows = None
        report_text: str = cached_report["report"]
    return cluster_rows, report_text


def compute_fresh_duplicates(
    index: DirectoryIndex,
    context: DuplicateAnalysisContext,
    fingerprint: ScanFingerprint,
) -> tuple[List[ClusterRow], str]:
    """Compute fresh duplicate analysis from index."""
    clusters = find_exact_duplicates(index)
    clusters = apply_thresholds(clusters, context.min_files, context.min_bytes)
    clusters = sorted(clusters, key=lambda c: c.nodes[0].total_size if c.nodes else 0, reverse=True)
    cluster_rows = clusters_to_rows(clusters)
    report_text = render_report_rows(cluster_rows, context.base_path)
    if context.can_cache_results:
        location = CacheLocation(
            db_path=context.db_path,
            fingerprint=fingerprint,
            base_path=context.base_path_str,
            min_files=context.min_files,
            min_bytes=context.min_bytes,
        )
        store_cached_report(location, clusters)
    return cluster_rows, report_text


def load_or_compute_duplicates(
    index: DirectoryIndex,
    fingerprint: ScanFingerprint,
    context: DuplicateAnalysisContext,
) -> tuple[Optional[List[ClusterRow]], str]:
    """Load cached duplicates or compute fresh analysis."""
    cached_result = load_cached_duplicates(context, fingerprint)
    if cached_result is not None:
        return cached_result
    return compute_fresh_duplicates(index, context, fingerprint)


def run_public_report() -> int:
    """Shim for public duplicate report CLI."""
    return 42
