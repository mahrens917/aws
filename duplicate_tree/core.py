"""Duplicate tree helpers focused on exact duplicate detection."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Dict, Iterable, List, Set

from migration_verify_common import should_ignore_key

from .models import (
    ChildSignatureMissingError,
    DirectoryNode,
    DuplicateCluster,
    FileEntry,
    PathTuple,
    ProgressPrinter,
)

MIN_DUPLICATE_CLUSTER = 2


class DirectoryIndex:
    """Builds directory nodes from file metadata."""

    def __init__(self):
        self.nodes: Dict[PathTuple, DirectoryNode] = {}

    def add_file(self, bucket: str, key: str, size: int, checksum: str):
        """Add a file entry to the proper directory node hierarchy."""
        if not key or key.endswith("/"):  # Ignore directory placeholders
            return
        if should_ignore_key(key):
            return
        parts = [p for p in key.split("/") if p]
        if not parts:
            return
        filename = parts[-1]
        dir_parts = (bucket,) + tuple(parts[:-1]) if len(parts) > 1 else (bucket,)
        node = self._ensure_node(dir_parts)
        node.files.append(FileEntry(filename, size, checksum))
        node.direct_size += size
        node.direct_files += 1
        # Register intermediate directories
        for depth in range(1, len(dir_parts)):
            parent = dir_parts[:depth]
            child = dir_parts[: depth + 1]
            parent_node = self._ensure_node(parent)
            parent_node.children.add(child)

    def _ensure_node(self, path: PathTuple) -> DirectoryNode:
        if path not in self.nodes:
            self.nodes[path] = DirectoryNode(path=path)
        return self.nodes[path]

    def finalize(self):
        """Compute aggregate stats and signatures bottom-up."""
        for path in sorted(self.nodes, key=len, reverse=True):
            node = self.nodes[path]
            total_size = node.direct_size
            total_files = node.direct_files
            child_signatures: List[tuple[str, str]] = []
            for child_path in sorted(node.children):
                child_node = self.nodes[child_path]
                total_size += child_node.total_size
                total_files += child_node.total_files
                if child_node.signature is None:
                    raise ChildSignatureMissingError(child_path)
                child_name = child_path[-1]
                child_signatures.append((child_name, child_node.signature))
            file_entries = sorted((f.name, f.size, f.checksum) for f in node.files)
            payload = json.dumps(
                {"files": file_entries, "dirs": child_signatures},
                separators=(",", ":"),
            )
            node.signature = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            node.total_size = total_size
            node.total_files = total_files


def find_exact_duplicates(index: DirectoryIndex) -> List[DuplicateCluster]:
    """Group directories by identical signatures."""
    groups: Dict[str, List[DirectoryNode]] = {}
    nodes = list(index.nodes.values())
    total = len(nodes)
    progress = ProgressPrinter(total, "Grouping directories")
    start_time = time.time()
    processed = 0
    try:
        for processed, node in enumerate(nodes, start=1):
            if node.signature is None:
                continue
            if node.signature not in groups:
                groups[node.signature] = []
            groups[node.signature].append(node)
            progress.update(processed)
    except KeyboardInterrupt:
        print("\n\n✗ Duplicate grouping interrupted by user.")
        raise
    finally:
        elapsed = time.time() - start_time
        progress.finish(f"Grouping directories processed {processed:,}/{total:,} entries in {elapsed:.1f}s")
    clusters = []
    for signature, sig_nodes in groups.items():
        collapsed_nodes = _collapse_nested_nodes(sig_nodes)
        if len(collapsed_nodes) < MIN_DUPLICATE_CLUSTER:
            continue
        clusters.append(DuplicateCluster(signature=signature, nodes=collapsed_nodes))
    sorted_clusters = sorted(clusters, key=lambda c: (len(c.nodes[0].path), c.nodes[0].path))
    return _prune_nested_clusters(sorted_clusters)


def _collapse_nested_nodes(nodes: Iterable[DirectoryNode]) -> List[DirectoryNode]:
    """Return only the top-most directories from a duplicate cluster."""
    sorted_nodes = sorted(nodes, key=lambda n: len(n.path))
    collapsed: List[DirectoryNode] = []
    for node in sorted_nodes:
        if any(node.path[: len(parent.path)] == parent.path for parent in collapsed):
            continue
        collapsed.append(node)
    return collapsed


def _has_seen_ancestor(path: PathTuple, seen_paths: Set[PathTuple]) -> bool:
    return any(path[: len(candidate)] == candidate for candidate in seen_paths)


def _prune_nested_clusters(clusters: List[DuplicateCluster]) -> List[DuplicateCluster]:
    """Remove duplicate sets fully contained within already-reported parents."""
    seen_paths: Set[PathTuple] = set()
    pruned: List[DuplicateCluster] = []
    for cluster in clusters:
        node_paths = [node.path for node in cluster.nodes]
        if node_paths and all(_has_seen_ancestor(path, seen_paths) for path in node_paths):
            continue
        pruned.append(cluster)
        seen_paths.update(node_paths)
    return pruned


__all__ = [
    "DirectoryIndex",
    "DuplicateCluster",
    "find_exact_duplicates",
]
