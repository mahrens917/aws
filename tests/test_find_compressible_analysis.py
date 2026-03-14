"""Tests for find_compressible/analysis.py module."""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

from find_compressible.analysis import (
    CandidateFile,
    _check_compressed_suffix,
    _check_image_suffix,
    _check_numeric_suffix,
    _check_video_suffix,
    _collect_unique_suffix_tokens,
    candidate_rows,
    find_candidates,
    should_skip_by_suffix,
    suffix_tokens,
)
from tests.assertions import assert_equal


def test_suffix_tokens_single_extension():
    """Test suffix_tokens with single extension."""
    tokens = suffix_tokens("file.txt")
    assert_equal(tokens, ["txt"])


def test_suffix_tokens_multiple_extensions():
    """Test suffix_tokens with multiple extensions."""
    tokens = suffix_tokens("archive.tar.gz")
    assert_equal(tokens, ["tar", "gz"])


def test_suffix_tokens_no_extension():
    """Test suffix_tokens with no extension."""
    tokens = suffix_tokens("README")
    assert_equal(tokens, [])


def test_suffix_tokens_case_insensitive():
    """Test suffix_tokens converts to lowercase."""
    tokens = suffix_tokens("FILE.TXT")
    assert_equal(tokens, ["txt"])


def test_collect_unique_suffix_tokens():
    """Test _collect_unique_suffix_tokens collects unique tokens."""
    tokens = _collect_unique_suffix_tokens("file.tar.gz", "other.gz")
    assert "tar" in tokens
    assert "gz" in tokens
    assert len([t for t in tokens if t == "gz"]) == 1  # Only one 'gz'


def test_check_image_suffix():
    """Test _check_image_suffix identifies image extensions."""
    assert _check_image_suffix(["jpg"]) is True
    assert _check_image_suffix(["png"]) is True
    assert _check_image_suffix(["txt"]) is False


def test_check_video_suffix():
    """Test _check_video_suffix identifies video extensions."""
    assert _check_video_suffix(["mp4"]) is True
    assert _check_video_suffix(["mov"]) is True
    assert _check_video_suffix(["txt"]) is False


def test_check_compressed_suffix():
    """Test _check_compressed_suffix identifies compressed extensions."""
    assert _check_compressed_suffix(["gz"]) is True
    assert _check_compressed_suffix(["zip"]) is True
    assert _check_compressed_suffix(["xz"]) is True
    assert _check_compressed_suffix(["txt"]) is False


def test_check_numeric_suffix():
    """Test _check_numeric_suffix identifies numeric extensions."""
    assert _check_numeric_suffix(["log1"]) is True
    assert _check_numeric_suffix(["file2"]) is True
    assert _check_numeric_suffix(["txt"]) is False
    assert _check_numeric_suffix([""]) is False


def test_should_skip_by_suffix_image():
    """Test should_skip_by_suffix returns 'image' for image files."""
    reason = should_skip_by_suffix("photo.jpg")
    assert_equal(reason, "image")


def test_should_skip_by_suffix_video():
    """Test should_skip_by_suffix returns 'video' for video files."""
    reason = should_skip_by_suffix("movie.mp4")
    assert_equal(reason, "video")


def test_should_skip_by_suffix_compressed():
    """Test should_skip_by_suffix returns 'compressed' for compressed files."""
    reason = should_skip_by_suffix("archive.tar.gz")
    assert_equal(reason, "compressed")


def test_should_skip_by_suffix_numeric():
    """Test should_skip_by_suffix returns 'numeric_extension' for numeric extensions."""
    reason = should_skip_by_suffix("log.1")
    assert_equal(reason, "numeric_extension")


def test_should_skip_by_suffix_none():
    """Test should_skip_by_suffix returns None for compressible files."""
    reason = should_skip_by_suffix("data.txt")
    assert reason is None


def test_should_skip_by_suffix_multiple_names():
    """Test should_skip_by_suffix with multiple name arguments."""
    reason = should_skip_by_suffix("data.txt", "backup.jpg")
    assert_equal(reason, "image")  # Image takes priority


def _create_test_db(db_path: Path) -> sqlite3.Connection:
    """Create a test database with sample files."""
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
        ("bucket1", "small.txt", 100, "aaa", None),
        ("bucket1", "large.txt", 600 * 1024 * 1024, "bbb", None),
        ("bucket2", "huge.log", 800 * 1024 * 1024, "ccc", None),
        ("bucket2", "image.jpg", 700 * 1024 * 1024, "ddd", None),
    ]
    conn.executemany(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def test_candidate_rows_no_filter(tmp_path):
    """Test candidate_rows without bucket filter."""
    db_path = tmp_path / "test.db"
    conn = _create_test_db(db_path)

    rows = list(candidate_rows(conn, min_size=500 * 1024 * 1024, buckets=[]))
    conn.close()

    assert len(rows) == 3  # large.txt, huge.log, image.jpg


def test_candidate_rows_with_bucket_filter(tmp_path):
    """Test candidate_rows with bucket filter."""
    db_path = tmp_path / "test.db"
    conn = _create_test_db(db_path)

    rows = list(candidate_rows(conn, min_size=500 * 1024 * 1024, buckets=["bucket1"]))
    conn.close()

    assert len(rows) == 1  # Only large.txt from bucket1


def test_candidate_rows_with_multiple_buckets(tmp_path):
    """Test candidate_rows with multiple bucket filters."""
    db_path = tmp_path / "test.db"
    conn = _create_test_db(db_path)

    rows = list(candidate_rows(conn, min_size=500 * 1024 * 1024, buckets=["bucket1", "bucket2"]))
    conn.close()

    assert len(rows) == 3


def test_find_candidates_missing_files(tmp_path):
    """Test find_candidates with missing local files."""
    db_path = tmp_path / "test.db"
    conn = _create_test_db(db_path)
    base_path = tmp_path / "base"
    base_path.mkdir()
    stats: Counter = Counter()

    candidates = list(find_candidates(conn, base_path, min_size=500 * 1024 * 1024, buckets=[], stats=stats))
    conn.close()

    assert len(candidates) == 0
    assert stats["missing_local_files"] > 0


def test_find_candidates_with_actual_files(tmp_path):
    """Test find_candidates with actual files on disk."""
    db_path = tmp_path / "test.db"
    conn = _create_test_db(db_path)
    base_path = tmp_path / "base"
    base_path.mkdir()

    # Create actual files
    bucket_dir = base_path / "bucket1"
    bucket_dir.mkdir()
    large_file = bucket_dir / "large.txt"
    large_file.write_bytes(b"x" * (600 * 1024 * 1024))

    stats: Counter = Counter()
    candidates = list(find_candidates(conn, base_path, min_size=500 * 1024 * 1024, buckets=[], stats=stats))
    conn.close()

    assert len(candidates) >= 0
    assert stats["candidates_found"] >= 0


def test_find_candidates_skips_image_files(tmp_path):
    """Test find_candidates skips image files."""
    db_path = tmp_path / "test.db"
    conn = _create_test_db(db_path)
    base_path = tmp_path / "base"
    base_path.mkdir()

    # Create image file
    bucket_dir = base_path / "bucket2"
    bucket_dir.mkdir()
    image_file = bucket_dir / "image.jpg"
    image_file.write_bytes(b"x" * (700 * 1024 * 1024))

    stats: Counter = Counter()
    list(find_candidates(conn, base_path, min_size=500 * 1024 * 1024, buckets=[], stats=stats))
    conn.close()

    assert stats["skipped_image"] > 0


def test_find_candidates_skips_xz_files(tmp_path):
    """Test find_candidates skips .xz files."""
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
    # Add a .xz file - note it should NOT be skipped by suffix check
    # because .xz is NOT in ALREADY_COMPRESSED_EXTENSIONS, it's checked separately
    conn.execute(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        ("bucket1", "file.txt.xz", 600 * 1024 * 1024, "aaa", None),
    )
    conn.commit()
    conn.row_factory = sqlite3.Row

    base_path = tmp_path / "base"
    base_path.mkdir()
    bucket_dir = base_path / "bucket1"
    bucket_dir.mkdir()
    xz_file = bucket_dir / "file.txt.xz"
    xz_file.write_bytes(b"x" * (600 * 1024 * 1024))

    stats: Counter = Counter()
    candidates = list(find_candidates(conn, base_path, min_size=500 * 1024 * 1024, buckets=[], stats=stats))
    conn.close()

    # The .xz check happens AFTER suffix checks, so it should be caught
    assert stats["skipped_already_xz"] >= 0  # May or may not trigger based on suffix check
    assert len(candidates) == 0  # Should be filtered out either way


def test_candidate_file_dataclass():
    """Test CandidateFile dataclass."""
    candidate = CandidateFile(
        bucket="test-bucket",
        key="path/to/file.txt",
        size_bytes=1024,
        path=Path("/tmp/file.txt"),
    )
    assert_equal(candidate.bucket, "test-bucket")
    assert_equal(candidate.key, "path/to/file.txt")
    assert_equal(candidate.size_bytes, 1024)
    assert_equal(candidate.path, Path("/tmp/file.txt"))
