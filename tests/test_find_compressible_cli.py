"""Tests for find_compressible/cli.py module."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from find_compressible.cli import main, parse_args, parse_size


def test_parse_size_with_kilobytes():
    """Test parse_size with kilobyte suffix."""
    assert parse_size("512k") == 512 * 1024
    assert parse_size("1K") == 1024


def test_parse_size_with_megabytes():
    """Test parse_size with megabyte suffix."""
    assert parse_size("512m") == 512 * 1024 * 1024
    assert parse_size("1M") == 1024 * 1024


def test_parse_size_with_gigabytes():
    """Test parse_size with gigabyte suffix."""
    assert parse_size("2g") == 2 * 1024 * 1024 * 1024
    assert parse_size("1G") == 1024 * 1024 * 1024


def test_parse_size_with_terabytes():
    """Test parse_size with terabyte suffix."""
    assert parse_size("1t") == 1024 * 1024 * 1024 * 1024
    assert parse_size("2T") == 2 * 1024 * 1024 * 1024 * 1024


def test_parse_size_with_raw_bytes():
    """Test parse_size with raw byte value."""
    assert parse_size("1024") == 1024
    assert parse_size("2048") == 2048


def test_parse_size_with_empty_string():
    """Test parse_size with empty string raises error."""
    with pytest.raises(Exception):  # ArgumentTypeError
        parse_size("")


def test_parse_size_with_invalid_number():
    """Test parse_size with invalid number raises error."""
    with pytest.raises(Exception):  # ArgumentTypeError
        parse_size("abcm")


def test_parse_size_with_whitespace():
    """Test parse_size handles whitespace correctly."""
    assert parse_size("  512m  ") == 512 * 1024 * 1024


def test_parse_args_defaults():
    """Test parse_args returns expected defaults."""
    with patch("sys.argv", ["prog"]):
        args = parse_args()
        assert args.min_size == 512 * 1024 * 1024
        assert args.buckets == []
        assert args.limit == 0
        assert args.compress is False


def test_parse_args_with_min_size():
    """Test parse_args with custom min_size."""
    with patch("sys.argv", ["prog", "--min-size", "1G"]):
        args = parse_args()
        assert args.min_size == 1024 * 1024 * 1024


def test_parse_args_with_multiple_buckets():
    """Test parse_args with multiple bucket filters."""
    with patch("sys.argv", ["prog", "--bucket", "b1", "--bucket", "b2"]):
        args = parse_args()
        assert "b1" in args.buckets
        assert "b2" in args.buckets


def test_parse_args_with_limit():
    """Test parse_args with limit option."""
    with patch("sys.argv", ["prog", "--limit", "10"]):
        args = parse_args()
        assert args.limit == 10


def test_parse_args_with_compress():
    """Test parse_args with compress flag."""
    with patch("sys.argv", ["prog", "--compress"]):
        args = parse_args()
        assert args.compress is True


def test_main_with_missing_base_path(tmp_path):
    """Test main exits when base path doesn't exist."""
    missing_path = tmp_path / "missing"
    with patch("sys.argv", ["prog", "--base-path", str(missing_path)]):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert "does not exist" in str(exc_info.value)


def test_main_with_missing_db(tmp_path):
    """Test main exits when database doesn't exist."""
    base_path = tmp_path / "base"
    base_path.mkdir()
    db_path = tmp_path / "missing.db"

    with patch("sys.argv", ["prog", "--base-path", str(base_path), "--db-path", str(db_path)]):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert "not found" in str(exc_info.value)


def _create_test_db(db_path: Path) -> None:
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
        ("bucket1", "file1.txt", 600 * 1024 * 1024, "aaa", None),
        ("bucket2", "file2.log", 700 * 1024 * 1024, "bbb", None),
    ]
    conn.executemany(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_main_with_valid_setup_no_matches(tmp_path, capsys):
    """Test main with valid setup but no matching files on disk."""
    base_path = tmp_path / "base"
    base_path.mkdir()
    db_path = tmp_path / "test.db"
    _create_test_db(db_path)

    with patch("sys.argv", ["prog", "--base-path", str(base_path), "--db-path", str(db_path)]):
        main()

    captured = capsys.readouterr().out
    assert "Scan summary" in captured
    assert "Missing files:" in captured


def test_main_with_bucket_filter(tmp_path, capsys):
    """Test main with bucket filter."""
    base_path = tmp_path / "base"
    base_path.mkdir()
    db_path = tmp_path / "test.db"
    _create_test_db(db_path)

    with patch(
        "sys.argv",
        ["prog", "--base-path", str(base_path), "--db-path", str(db_path), "--bucket", "bucket1"],
    ):
        main()

    captured = capsys.readouterr().out
    assert "Scan summary" in captured


def test_main_with_limit(tmp_path, capsys):
    """Test main with limit option."""
    base_path = tmp_path / "base"
    base_path.mkdir()
    db_path = tmp_path / "test.db"
    _create_test_db(db_path)

    with patch(
        "sys.argv",
        ["prog", "--base-path", str(base_path), "--db-path", str(db_path), "--limit", "1"],
    ):
        main()

    captured = capsys.readouterr().out
    assert "Scan summary" in captured


def test_main_with_compress_flag(tmp_path, capsys):
    """Test main with compress flag (no actual compression without files)."""
    base_path = tmp_path / "base"
    base_path.mkdir()
    db_path = tmp_path / "test.db"
    _create_test_db(db_path)

    with patch(
        "sys.argv",
        ["prog", "--base-path", str(base_path), "--db-path", str(db_path), "--compress"],
    ):
        main()

    captured = capsys.readouterr().out
    assert "Scan summary" in captured
    assert "Compression summary" in captured


def test_main_with_state_db_reset(tmp_path, capsys):
    """Test main with state DB reset option."""
    base_path = tmp_path / "base"
    base_path.mkdir()
    db_path = tmp_path / "test.db"

    mock_reseed = MagicMock(return_value=(db_path, 100, 1024 * 1024))

    with (
        patch("sys.argv", ["prog", "--base-path", str(base_path), "--reset-state-db", "--yes"]),
        patch("find_compressible.cache.reseed_state_db_from_local_drive", mock_reseed),
    ):
        _create_test_db(db_path)
        main()

    captured = capsys.readouterr().out
    assert "Recreated" in captured or "Scan summary" in captured
