"""Duplicate tree detection and analysis logic."""

from __future__ import annotations

import hashlib
import io
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

from cost_toolkit.common.format_utils import format_bytes
from duplicate_tree.core import (
    DirectoryIndex,
    DuplicateCluster,
    find_exact_duplicates,
)
from duplicate_tree_models import (
    FilesTableReadError,
    PathTuple,
    ProgressPrinter,
)

MIN_REPORT_FILES = 2
MIN_REPORT_BYTES = 512 * 1024 * 1024  # 0.5 GiB
MIN_DUPLICATE_NODES = 2

ClusterRow = Dict[str, Any]
NodeRow = Dict[str, Any]


@dataclass(frozen=True)
class ScanFingerprint:
    """Uniquely identifies a DB snapshot by file count + checksum."""

    total_files: int
    checksum: str


def build_directory_index_from_db(db_path: str, progress_label: str = "Scanning files") -> tuple[DirectoryIndex, ScanFingerprint]:
    """Stream the files table and construct the in-memory directory index."""
    index = DirectoryIndex()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        try:
            total_files = conn.execute("SELECT COUNT(*) FROM files WHERE key NOT LIKE '%/'").fetchone()[0]
        except sqlite3.OperationalError as exc:
            raise FilesTableReadError(db_path) from exc
        progress = ProgressPrinter(total_files, progress_label)
        start_time = time.time()
        cursor = conn.execute(
            """
            SELECT bucket, key, size,
                   COALESCE(local_checksum, etag, '') AS checksum
            FROM files
            ORDER BY bucket, key
            """
        )
        processed = 0
        hasher = hashlib.sha256()
        try:
            for processed, row in enumerate(cursor, start=1):
                checksum = row["checksum"] if row["checksum"] else ""
                bucket = row["bucket"]
                key = row["key"]
                size = row["size"]
                index.add_file(bucket, key, size, checksum)
                for value in (bucket, key, str(size), checksum):
                    hasher.update(value.encode("utf-8"))
                    hasher.update(b"\0")
                progress.update(processed)
        except KeyboardInterrupt:
            print("\n\n✗ Scan interrupted by user.")
            raise
        finally:
            elapsed = time.time() - start_time
            progress.finish(f"{progress_label} processed {processed:,}/{total_files:,} files in {elapsed:.1f}s")
    finally:
        conn.close()
    index.finalize()
    fingerprint = ScanFingerprint(total_files=total_files, checksum=hasher.hexdigest())
    return index, fingerprint


def apply_thresholds(clusters: Sequence[DuplicateCluster], min_files: int, min_bytes: int) -> List[DuplicateCluster]:
    """Filter clusters down to nodes meeting file and size thresholds."""
    filtered: List[DuplicateCluster] = []
    for cluster in clusters:
        nodes = [node for node in cluster.nodes if node.total_files > min_files and node.total_size >= min_bytes]
        if len(nodes) >= MIN_DUPLICATE_NODES:
            filtered.append(DuplicateCluster(cluster.signature, nodes))
    return filtered


def cache_key(fingerprint: ScanFingerprint, min_files: int, min_bytes: int) -> str:
    """Build cache key from fingerprint and thresholds."""
    return f"{fingerprint.checksum}|files>{min_files}|bytes>={min_bytes}"


def clusters_to_rows(clusters: Sequence[DuplicateCluster]) -> List[Dict[str, Any]]:
    """Convert cluster objects to serializable row format."""
    rows: List[Dict[str, Any]] = []
    for cluster in clusters:
        if not cluster.nodes:
            continue
        node_rows = [
            {
                "path": list(node.path),
                "total_files": node.total_files,
                "total_size": node.total_size,
            }
            for node in cluster.nodes
        ]
        rows.append(
            {
                "total_files": node_rows[0]["total_files"],
                "total_size": node_rows[0]["total_size"],
                "nodes": node_rows,
            }
        )
    return rows


def render_report_rows(cluster_rows: List[ClusterRow], base_path: Path) -> str:
    """Generate human-readable report from cluster rows."""
    buffer = io.StringIO()
    if not cluster_rows:
        buffer.write("No exact duplicate directories found.\n")
        return buffer.getvalue()
    buffer.write("\n")
    buffer.write("=" * 70 + "\n")
    buffer.write("EXACT DUPLICATE TREES\n")
    buffer.write("=" * 70 + "\n")
    for idx, cluster in enumerate(cluster_rows, start=1):
        size_label = format_bytes(cluster["total_size"])
        buffer.write(f"[{idx}] {cluster['total_files']:,} files, {size_label}\n")
        nodes = sort_node_rows(cluster["nodes"])
        for node in nodes:
            path_tuple = tuple(node["path"])
            buffer.write(f"  - {format_bytes(node['total_size']):>12}  " f"{path_on_disk(base_path, path_tuple)}\n")
        buffer.write("\n")
    return buffer.getvalue()


def sort_node_rows(node_rows: Sequence[NodeRow]) -> List[NodeRow]:
    """Sort node rows by size (desc) then path for deterministic output."""
    return sorted(
        node_rows,
        key=lambda n: (-n["total_size"], tuple(n["path"])),
    )


def path_on_disk(base_path: Path, node_path: PathTuple) -> Path:
    """Construct filesystem path from base path and node path tuple."""
    return base_path.joinpath(*node_path)


def recompute_clusters_for_deletion(index: DirectoryIndex, min_files: int, min_bytes: int) -> List[ClusterRow]:
    """Recompute duplicate clusters when cached data lacks structured rows."""
    clusters = find_exact_duplicates(index)
    clusters = apply_thresholds(clusters, min_files, min_bytes)
    clusters = sorted(
        clusters,
        key=lambda c: c.nodes[0].total_size if c.nodes else 0,
        reverse=True,
    )
    return clusters_to_rows(clusters)
