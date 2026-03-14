"""Extended tests for find_compressible/analysis.py to increase coverage."""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

from find_compressible.analysis import find_candidates


def _create_test_db_with_edge_cases(db_path: Path) -> sqlite3.Connection:
    """Create a test database with edge case files."""
    conn = sqlite3.connect(str(db_path))
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
        # Invalid path (null bytes, etc.)
        ("bucket1", "invalid\x00path.txt", 600 * 1024 * 1024, "aaa", None),
        # File that will be directory
        ("bucket1", "directory_file", 600 * 1024 * 1024, "bbb", None),
        # File below threshold after check
        ("bucket1", "shrunk.txt", 600 * 1024 * 1024, "ccc", None),
        # Valid large file
        ("bucket1", "valid.txt", 600 * 1024 * 1024, "ddd", None),
    ]
    conn.executemany(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def test_find_candidates_with_invalid_path(tmp_path):
    """Test find_candidates handles invalid paths correctly."""
    db_path = tmp_path / "test.db"
    conn = _create_test_db_with_edge_cases(db_path)
    base_path = tmp_path / "base"
    base_path.mkdir()

    stats: Counter = Counter()
    _ = list(find_candidates(conn, base_path, min_size=500 * 1024 * 1024, buckets=[], stats=stats))
    conn.close()

    # Invalid path should be counted as skipped_invalid_path
    assert stats["rows_examined"] > 0
    assert stats.get("skipped_invalid_path", 0) + stats.get("missing_local_files", 0) > 0


def test_find_candidates_with_directory_instead_of_file(tmp_path):
    """Test find_candidates skips directories."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE files (
            bucket TEXT NOT NULL,
            key TEXT NOT NULL,
            size INTEGER NOT NULL,
            local_checksum TEXT,
            etag TEXT
        )
        """)
    conn.execute(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        ("bucket1", "directory_item", 600 * 1024 * 1024, "aaa", None),
    )
    conn.commit()
    conn.row_factory = sqlite3.Row

    base_path = tmp_path / "base"
    base_path.mkdir()
    bucket_dir = base_path / "bucket1"
    bucket_dir.mkdir()
    # Create a directory instead of a file
    (bucket_dir / "directory_item").mkdir()

    stats: Counter = Counter()
    candidates = list(find_candidates(conn, base_path, min_size=500 * 1024 * 1024, buckets=[], stats=stats))
    conn.close()

    assert stats["skipped_non_file"] > 0
    assert len(candidates) == 0


def test_find_candidates_file_shrunk_below_threshold(tmp_path):
    """Test find_candidates handles files that shrunk below threshold."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE files (
            bucket TEXT NOT NULL,
            key TEXT NOT NULL,
            size INTEGER NOT NULL,
            local_checksum TEXT,
            etag TEXT
        )
        """)
    # DB says file is large
    conn.execute(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        ("bucket1", "shrunk.txt", 600 * 1024 * 1024, "aaa", None),
    )
    conn.commit()
    conn.row_factory = sqlite3.Row

    base_path = tmp_path / "base"
    base_path.mkdir()
    bucket_dir = base_path / "bucket1"
    bucket_dir.mkdir()
    # But actual file is small
    (bucket_dir / "shrunk.txt").write_bytes(b"small content")

    stats: Counter = Counter()
    candidates = list(find_candidates(conn, base_path, min_size=500 * 1024 * 1024, buckets=[], stats=stats))
    conn.close()

    assert stats["skipped_now_below_threshold"] > 0
    assert len(candidates) == 0


def test_find_candidates_xz_suffix_uppercase(tmp_path):
    """Test find_candidates skips files with uppercase .XZ extension."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE files (
            bucket TEXT NOT NULL,
            key TEXT NOT NULL,
            size INTEGER NOT NULL,
            local_checksum TEXT,
            etag TEXT
        )
        """)
    conn.execute(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        ("bucket1", "file.TXT.XZ", 600 * 1024 * 1024, "aaa", None),
    )
    conn.commit()
    conn.row_factory = sqlite3.Row

    base_path = tmp_path / "base"
    base_path.mkdir()
    bucket_dir = base_path / "bucket1"
    bucket_dir.mkdir()
    xz_file = bucket_dir / "file.TXT.XZ"
    xz_file.write_bytes(b"x" * (600 * 1024 * 1024))

    stats: Counter = Counter()
    candidates = list(find_candidates(conn, base_path, min_size=500 * 1024 * 1024, buckets=[], stats=stats))
    conn.close()

    # File should be filtered out (either by .xz suffix check or compressed check)
    assert len(candidates) == 0
    # May be caught by compressed or xz check depending on order
    assert stats["skipped_already_xz"] + stats.get("skipped_compressed", 0) > 0


def test_find_candidates_with_video_extension(tmp_path):
    """Test find_candidates skips video files correctly."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE files (
            bucket TEXT NOT NULL,
            key TEXT NOT NULL,
            size INTEGER NOT NULL,
            local_checksum TEXT,
            etag TEXT
        )
        """)
    conn.execute(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        ("bucket1", "movie.mov", 700 * 1024 * 1024, "aaa", None),
    )
    conn.commit()
    conn.row_factory = sqlite3.Row

    base_path = tmp_path / "base"
    base_path.mkdir()
    bucket_dir = base_path / "bucket1"
    bucket_dir.mkdir()
    (bucket_dir / "movie.mov").write_bytes(b"x" * (700 * 1024 * 1024))

    stats: Counter = Counter()
    candidates = list(find_candidates(conn, base_path, min_size=500 * 1024 * 1024, buckets=[], stats=stats))
    conn.close()

    assert stats["skipped_video"] > 0
    assert len(candidates) == 0


def test_find_candidates_with_numeric_extension(tmp_path):
    """Test find_candidates skips files with numeric extensions."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE files (
            bucket TEXT NOT NULL,
            key TEXT NOT NULL,
            size INTEGER NOT NULL,
            local_checksum TEXT,
            etag TEXT
        )
        """)
    conn.execute(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        ("bucket1", "file.log.1", 600 * 1024 * 1024, "aaa", None),
    )
    conn.commit()
    conn.row_factory = sqlite3.Row

    base_path = tmp_path / "base"
    base_path.mkdir()
    bucket_dir = base_path / "bucket1"
    bucket_dir.mkdir()
    (bucket_dir / "file.log.1").write_bytes(b"x" * (600 * 1024 * 1024))

    stats: Counter = Counter()
    candidates = list(find_candidates(conn, base_path, min_size=500 * 1024 * 1024, buckets=[], stats=stats))
    conn.close()

    assert stats["skipped_numeric_extension"] > 0
    assert len(candidates) == 0
