"""Extended tests for duplicate_tree cache module to increase coverage."""

from __future__ import annotations

import json
import sqlite3

from duplicate_tree.analysis import (
    MIN_REPORT_BYTES,
    MIN_REPORT_FILES,
    ScanFingerprint,
    cache_key,
)
from duplicate_tree.cache import (
    EXACT_TOLERANCE,
    CacheLocation,
    ensure_cache_table,
    load_cached_report,
    store_cached_report,
)
from duplicate_tree.core import DuplicateCluster
from duplicate_tree_models import DirectoryNode


def test_ensure_cache_table_idempotent(tmp_path):
    """Test that ensure_cache_table can be called multiple times safely."""
    db_path = tmp_path / "cache.db"
    conn = sqlite3.connect(str(db_path))

    ensure_cache_table(conn)
    ensure_cache_table(conn)

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='duplicate_tree_cache'")
    result = cursor.fetchone()
    assert result is not None
    conn.close()


def test_load_cached_report_no_match(tmp_path):
    """Test load_cached_report returns None when no match exists."""
    db_path = tmp_path / "cache.db"
    fingerprint = ScanFingerprint(total_files=10, checksum="nonexistent")

    result = load_cached_report(CacheLocation(db_path=str(db_path), fingerprint=fingerprint, base_path="/base/path"))
    assert result is None


def test_load_cached_report_file_count_mismatch(tmp_path):
    """Test load_cached_report returns None when file count doesn't match."""
    db_path = tmp_path / "cache.db"
    conn = sqlite3.connect(str(db_path))
    ensure_cache_table(conn)

    fingerprint = ScanFingerprint(total_files=10, checksum="abc123")
    key = cache_key(fingerprint, min_files=2, min_bytes=512 * 1024 * 1024)

    conn.execute(
        """
        INSERT INTO duplicate_tree_cache (
            fingerprint, tolerance, base_path, total_files, generated_at, report
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (key, EXACT_TOLERANCE, "/base/path", 99, "2024-01-01T00:00:00", "[]"),
    )
    conn.commit()
    conn.close()

    result = load_cached_report(CacheLocation(db_path=str(db_path), fingerprint=fingerprint, base_path="/base/path"))
    assert result is None


def test_load_cached_report_invalid_json(tmp_path):
    """Test load_cached_report handles invalid JSON gracefully."""
    db_path = tmp_path / "cache.db"
    conn = sqlite3.connect(str(db_path))
    ensure_cache_table(conn)

    fingerprint = ScanFingerprint(total_files=10, checksum="abc123")
    key = cache_key(fingerprint, min_files=2, min_bytes=512 * 1024 * 1024)

    conn.execute(
        """
        INSERT INTO duplicate_tree_cache (
            fingerprint, tolerance, base_path, total_files, generated_at, report
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (key, EXACT_TOLERANCE, "/base/path", 10, "2024-01-01T00:00:00", "INVALID JSON"),
    )
    conn.commit()
    conn.close()

    result = load_cached_report(CacheLocation(db_path=str(db_path), fingerprint=fingerprint, base_path="/base/path"))
    assert result is not None
    assert "report" in result
    assert result["report"] == "INVALID JSON"


def test_load_cached_report_valid_payload(tmp_path):
    """Test load_cached_report returns parsed rows on valid payload."""
    db_path = tmp_path / "cache.db"
    conn = sqlite3.connect(str(db_path))
    ensure_cache_table(conn)

    fingerprint = ScanFingerprint(total_files=2, checksum="good")
    key = cache_key(fingerprint, min_files=MIN_REPORT_FILES, min_bytes=MIN_REPORT_BYTES)
    payload = '[{"total_files": 2, "total_size": 10, "nodes": []}]'

    conn.execute(
        """
        INSERT INTO duplicate_tree_cache (
            fingerprint, tolerance, base_path, total_files, generated_at, report
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (key, EXACT_TOLERANCE, "/base/path", 2, "2024-01-02T00:00:00", payload),
    )
    conn.commit()
    conn.close()

    result = load_cached_report(CacheLocation(db_path=str(db_path), fingerprint=fingerprint, base_path="/base/path"))

    assert result is not None
    assert result["rows"] == [{"total_files": 2, "total_size": 10, "nodes": []}]
    assert result["total_files"] == "2"


def test_store_cached_report_with_clusters(tmp_path):
    """Test store_cached_report persists cluster data correctly."""
    db_path = tmp_path / "cache.db"
    fingerprint = ScanFingerprint(total_files=10, checksum="abc123")

    node1 = DirectoryNode(path=("bucket", "dir1"), total_files=5, total_size=1000)
    node2 = DirectoryNode(path=("bucket", "dir2"), total_files=5, total_size=1000)
    cluster = DuplicateCluster(signature="sig1", nodes=[node1, node2])

    store_cached_report(CacheLocation(db_path=str(db_path), fingerprint=fingerprint, base_path="/base/path"), [cluster])

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM duplicate_tree_cache").fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0]["total_files"] == 10

    report_data = json.loads(rows[0]["report"])
    assert len(report_data) == 1
    assert report_data[0]["total_files"] == 5


def test_store_cached_report_replaces_existing(tmp_path):
    """Test store_cached_report replaces existing entries."""
    db_path = tmp_path / "cache.db"
    fingerprint = ScanFingerprint(total_files=10, checksum="abc123")

    store_cached_report(CacheLocation(db_path=str(db_path), fingerprint=fingerprint, base_path="/base/path"), [])
    store_cached_report(CacheLocation(db_path=str(db_path), fingerprint=fingerprint, base_path="/base/path"), [])

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM duplicate_tree_cache").fetchone()[0]
    conn.close()

    assert count == 1
