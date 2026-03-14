"""Extended tests for duplicate_tree analysis module to increase coverage."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from duplicate_tree.analysis import (
    ScanFingerprint,
    apply_thresholds,
    build_directory_index_from_db,
    cache_key,
    clusters_to_rows,
    format_bytes,
    path_on_disk,
    recompute_clusters_for_deletion,
    render_report_rows,
    sort_node_rows,
)
from duplicate_tree.core import DirectoryIndex, DuplicateCluster
from duplicate_tree.models import DirectoryNode, FilesTableReadError


def _create_test_db(tmp_path: Path, include_files_table: bool = True) -> Path:
    """Create a test database with or without files table."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    if include_files_table:
        conn.execute("""
            CREATE TABLE files (
                bucket TEXT NOT NULL,
                key TEXT NOT NULL,
                size INTEGER NOT NULL,
                local_checksum TEXT,
                etag TEXT
            )
            """)
        rows = [
            ("bucket1", "dir1/file1.txt", 1000, "abc123", None),
            ("bucket1", "dir1/file2.txt", 2000, None, "def456"),
            ("bucket1", "dir2/file1.txt", 1000, "abc123", None),
            ("bucket1", "dir2/file2.txt", 2000, None, "def456"),
        ]
        conn.executemany(
            "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    conn.close()
    return db_path


def test_build_directory_index_from_db_missing_table(tmp_path):
    """Test that missing files table raises FilesTableReadError."""
    db_path = _create_test_db(tmp_path, include_files_table=False)
    with pytest.raises(FilesTableReadError):
        build_directory_index_from_db(str(db_path))


def test_build_directory_index_from_db_keyboard_interrupt(tmp_path):
    """Test that KeyboardInterrupt is properly handled during scanning."""
    db_path = _create_test_db(tmp_path)

    with patch("duplicate_tree.analysis.ProgressPrinter.update") as mock_update:
        mock_update.side_effect = KeyboardInterrupt()
        with pytest.raises(KeyboardInterrupt):
            build_directory_index_from_db(str(db_path))


def test_apply_thresholds_filters_correctly():
    """Test that apply_thresholds filters clusters by min_files and min_bytes."""
    node1 = DirectoryNode(path=("bucket", "dir1"), total_files=10, total_size=1000)
    node2 = DirectoryNode(path=("bucket", "dir2"), total_files=10, total_size=1000)
    node3 = DirectoryNode(path=("bucket", "dir3"), total_files=1, total_size=100)

    cluster = DuplicateCluster(signature="sig1", nodes=[node1, node2, node3])
    clusters = [cluster]

    filtered = apply_thresholds(clusters, min_files=5, min_bytes=500)
    assert len(filtered) == 1
    assert len(filtered[0].nodes) == 2


def test_apply_thresholds_removes_single_node_clusters():
    """Test that clusters with only one qualifying node are removed."""
    node1 = DirectoryNode(path=("bucket", "dir1"), total_files=10, total_size=1000)
    node2 = DirectoryNode(path=("bucket", "dir2"), total_files=1, total_size=100)

    cluster = DuplicateCluster(signature="sig1", nodes=[node1, node2])
    clusters = [cluster]

    filtered = apply_thresholds(clusters, min_files=5, min_bytes=500)
    assert len(filtered) == 0


def test_cache_key_format():
    """Test cache key format includes all parameters."""
    fingerprint = ScanFingerprint(total_files=100, checksum="abc123")
    key = cache_key(fingerprint, min_files=5, min_bytes=1000)
    assert "abc123" in key
    assert "files>5" in key
    assert "bytes>=1000" in key


def test_clusters_to_rows_empty_nodes():
    """Test clusters_to_rows skips clusters with no nodes."""
    cluster = DuplicateCluster(signature="sig1", nodes=[])
    rows = clusters_to_rows([cluster])
    assert len(rows) == 0


def test_clusters_to_rows_with_nodes():
    """Test clusters_to_rows converts nodes to row format."""
    node1 = DirectoryNode(path=("bucket", "dir1"), total_files=10, total_size=1000)
    node2 = DirectoryNode(path=("bucket", "dir2"), total_files=10, total_size=1000)
    cluster = DuplicateCluster(signature="sig1", nodes=[node1, node2])

    rows = clusters_to_rows([cluster])
    assert len(rows) == 1
    assert rows[0]["total_files"] == 10
    assert rows[0]["total_size"] == 1000
    assert len(rows[0]["nodes"]) == 2


def test_render_report_rows_empty():
    """Test render_report_rows with empty cluster list."""
    report = render_report_rows([], Path("/tmp"))
    assert "No exact duplicate directories found." in report


def test_render_report_rows_with_clusters(tmp_path):
    """Test render_report_rows generates formatted output."""
    cluster_row = {
        "total_files": 10,
        "total_size": 1000000,
        "nodes": [
            {"path": ["bucket", "dir1"], "total_files": 10, "total_size": 1000000},
            {"path": ["bucket", "dir2"], "total_files": 10, "total_size": 900000},
        ],
    }

    report = render_report_rows([cluster_row], tmp_path)
    assert "EXACT DUPLICATE TREES" in report
    assert "[1]" in report
    assert "10 files" in report


def test_format_bytes_all_units():
    """Test format_bytes for all unit sizes."""
    assert "B" in format_bytes(512)
    assert "KiB" in format_bytes(1024)
    assert "MiB" in format_bytes(1024 * 1024)
    assert "GiB" in format_bytes(1024 * 1024 * 1024)
    assert "TiB" in format_bytes(1024 * 1024 * 1024 * 1024)
    # PiB requires going beyond TiB limit in the loop
    result = format_bytes(1024 * 1024 * 1024 * 1024 * 1024)
    assert "PiB" in result


def test_sort_node_rows():
    """Test sort_node_rows sorts by size descending then path."""
    nodes = [
        {"path": ["bucket", "dir2"], "total_files": 5, "total_size": 1000},
        {"path": ["bucket", "dir1"], "total_files": 5, "total_size": 2000},
        {"path": ["bucket", "dir3"], "total_files": 5, "total_size": 1000},
    ]

    sorted_nodes = sort_node_rows(nodes)
    assert sorted_nodes[0]["total_size"] == 2000
    assert sorted_nodes[0]["path"] == ["bucket", "dir1"]
    assert sorted_nodes[1]["path"] == ["bucket", "dir2"]
    assert sorted_nodes[2]["path"] == ["bucket", "dir3"]


def test_path_on_disk():
    """Test path_on_disk constructs correct filesystem path."""
    base = Path("/mnt/drive")
    node_path = ("bucket1", "dir1", "subdir")
    result = path_on_disk(base, node_path)
    assert result == Path("/mnt/drive/bucket1/dir1/subdir")


def test_recompute_clusters_for_deletion():
    """Test recompute_clusters_for_deletion returns sorted cluster rows."""
    index = DirectoryIndex()
    index.add_file("bucket", "dir1/file1.txt", 1000000, "abc")
    index.add_file("bucket", "dir1/file2.txt", 1000000, "def")
    index.add_file("bucket", "dir2/file1.txt", 1000000, "abc")
    index.add_file("bucket", "dir2/file2.txt", 1000000, "def")
    index.finalize()

    rows = recompute_clusters_for_deletion(index, min_files=0, min_bytes=0)
    assert isinstance(rows, list)
