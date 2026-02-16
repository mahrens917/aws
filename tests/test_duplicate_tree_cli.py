"""Tests for the duplicate_tree_cli helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from duplicate_tree.analysis import ScanFingerprint, build_directory_index_from_db
from duplicate_tree.cache import CacheLocation, load_cached_report, store_cached_report
from duplicate_tree.cli import main
from tests.assertions import assert_equal

MIN_DUPLICATE_DIRECTORIES = 2


def _write_sample_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE files (
            bucket TEXT NOT NULL,
            key TEXT NOT NULL,
            size INTEGER NOT NULL,
            local_checksum TEXT,
            etag TEXT
        )
        """
    )
    large = 600 * 1024 * 1024  # 0.56 GiB
    rows = [
        ("bucket", "dirA/file1.txt", large, "aaa", None),
        ("bucket", "dirA/sub/file2.txt", large, "bbb", None),
        ("bucket", "dirA/extra/file3.bin", large, "ccc", None),
        ("bucket", "dirB/file1.txt", large, "aaa", None),
        ("bucket", "dirB/sub/file2.txt", large, "bbb", None),
        ("bucket", "dirB/extra/file3.bin", large, "ccc", None),
    ]
    conn.executemany(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


def test_build_directory_index_from_db(tmp_path):
    """Test building directory index from database."""
    db_path = _write_sample_db(tmp_path)
    index, fingerprint = build_directory_index_from_db(str(db_path))
    assert_equal(fingerprint.total_files, 6)
    assert len(index.nodes) >= MIN_DUPLICATE_DIRECTORIES


def test_cache_round_trip(tmp_path):
    """Test caching and loading report."""
    db_path = tmp_path / "cache.db"
    fingerprint = ScanFingerprint(total_files=4, checksum="abc123")
    store_cached_report(
        CacheLocation(db_path=str(db_path), fingerprint=fingerprint, base_path="/drive"),
        clusters=[],
    )
    cached = load_cached_report(CacheLocation(db_path=str(db_path), fingerprint=fingerprint, base_path="/drive"))
    assert cached is not None
    assert "rows" in cached


def test_cli_main_end_to_end(tmp_path, capsys):
    """Test CLI main function end-to-end with caching."""
    db_path = _write_sample_db(tmp_path)
    base_path = tmp_path / "drive"
    base_path.mkdir()
    exit_code = main(
        [
            "--db-path",
            str(db_path),
            "--base-path",
            str(base_path),
            "--refresh-cache",
        ]
    )
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "EXACT DUPLICATE TREES" in captured
    assert "NEAR DUPLICATES" not in captured
    assert "dirA/sub" not in captured
    assert "GiB" in captured

    exit_code_cached = main(
        [
            "--db-path",
            str(db_path),
            "--base-path",
            str(base_path),
        ]
    )
    cached_output = capsys.readouterr().out
    assert exit_code_cached == 0
    assert "cached duplicate analysis" in cached_output


def test_threshold_filters_small_clusters(tmp_path, capsys):
    """Test that threshold filters out small clusters."""
    db_path = tmp_path / "small.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE files (
            bucket TEXT NOT NULL,
            key TEXT NOT NULL,
            size INTEGER NOT NULL,
            local_checksum TEXT,
            etag TEXT
        )
        """
    )
    rows = [
        ("bucket", "tinyA/file1.txt", 10, "aaa", None),
        ("bucket", "tinyB/file1.txt", 10, "aaa", None),
    ]
    conn.executemany(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    base_path = tmp_path / "drive_small"
    base_path.mkdir()
    exit_code = main(
        [
            "--db-path",
            str(db_path),
            "--base-path",
            str(base_path),
            "--refresh-cache",
        ]
    )
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "No exact duplicate directories found." in captured
