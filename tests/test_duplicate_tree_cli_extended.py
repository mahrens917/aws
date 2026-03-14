"""Extended tests for duplicate_tree/cli.py to improve coverage."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

from cost_toolkit.common.cli_utils import confirm_reset_state_db
from duplicate_tree.cli import (
    handle_state_db_reset,
    main,
    parse_args,
)
from tests.assertions import assert_equal
from tests.state_db_reset_test_utils import build_reset_context


def _write_sample_db(tmp_path: Path) -> Path:
    """Create a sample database with duplicate directories."""
    db_path = tmp_path / "state.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE files (
            bucket TEXT NOT NULL,
            key TEXT NOT NULL,
            size INTEGER NOT NULL,
            local_checksum TEXT,
            etag TEXT
        )
        """)
    large = 600 * 1024 * 1024  # 0.56 GiB
    rows = [
        ("bucket", "dirA/file1.txt", large, "aaa", None),
        ("bucket", "dirA/sub/file2.txt", large, "bbb", None),
        ("bucket", "dirB/file1.txt", large, "aaa", None),
        ("bucket", "dirB/sub/file2.txt", large, "bbb", None),
    ]
    conn.executemany(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


def test_parse_args_with_delete():
    """Test parse_args with delete flag."""
    args = parse_args(["--delete"])
    assert args.delete is True


def test_parse_args_with_min_files():
    """Test parse_args with min_files option."""
    args = parse_args(["--min-files", "10"])
    assert_equal(args.min_files, 10)


def test_parse_args_with_min_size_gb():
    """Test parse_args with min_size_gb option."""
    args = parse_args(["--min-size-gb", "2.5"])
    assert_equal(args.min_size_gb, 2.5)


def test_parse_args_with_refresh_cache():
    """Test parse_args with refresh_cache flag."""
    args = parse_args(["--refresh-cache"])
    assert args.refresh_cache is True


def test_parse_args_with_reset_state_db():
    """Test parse_args with reset_state_db flag."""
    args = parse_args(["--reset-state-db", "--yes"])
    assert args.reset_state_db is True
    assert args.yes is True


def test_confirm_state_db_reset_with_skip_prompt():
    """Test confirm_reset_state_db when skip_prompt is True."""
    db_path = Path("/tmp/test.db")
    result = confirm_reset_state_db(str(db_path), skip_prompt=True)
    assert result is True


def test_handle_state_db_reset_no_reset():
    """Test handle_state_db_reset when should_reset is False."""
    base_path, db_path, mock_reseed = build_reset_context()

    result = handle_state_db_reset(base_path, db_path, should_reset=False, skip_prompt=False, reseed_function=mock_reseed)
    assert_equal(result, db_path)


def test_handle_state_db_reset_cancelled(tmp_path, capsys):
    """Test handle_state_db_reset when user cancels."""
    db_path = tmp_path / "test.db"
    base_path = tmp_path / "base"
    base_path.mkdir()

    def mock_reseed(_bp, dp):
        return dp, 100, 1000

    with patch("builtins.input", return_value="n"):
        result = handle_state_db_reset(base_path, db_path, should_reset=True, skip_prompt=False, reseed_function=mock_reseed)
        assert_equal(result, db_path)
        captured = capsys.readouterr().out
        assert "cancelled" in captured


def test_main_with_missing_db(tmp_path, capsys):
    """Test main with missing database file."""
    db_path = tmp_path / "missing.db"
    base_path = tmp_path / "base"
    base_path.mkdir()
    exit_code = main(["--db-path", str(db_path), "--base-path", str(base_path)])
    assert_equal(exit_code, 1)
    captured = capsys.readouterr().err
    assert "not found" in captured


def test_main_with_delete_no_clusters(tmp_path, capsys):
    """Test main with delete flag but no duplicate clusters found."""
    db_path = tmp_path / "small.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE files (
            bucket TEXT NOT NULL,
            key TEXT NOT NULL,
            size INTEGER NOT NULL,
            local_checksum TEXT,
            etag TEXT
        )
        """)
    # Small files that won't meet threshold
    rows = [
        ("bucket", "fileA.txt", 100, "aaa", None),
        ("bucket", "fileB.txt", 100, "bbb", None),
    ]
    conn.executemany(
        "INSERT INTO files (bucket, key, size, local_checksum, etag) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()

    base_path = tmp_path / "base"
    base_path.mkdir()

    with patch("builtins.input", return_value="n"):
        exit_code = main(
            [
                "--db-path",
                str(db_path),
                "--base-path",
                str(base_path),
                "--delete",
                "--refresh-cache",
            ]
        )
    assert_equal(exit_code, 0)
    captured = capsys.readouterr().out
    assert "No exact duplicate directories found" in captured


def test_main_with_custom_thresholds(tmp_path, capsys):
    """Test main with custom min_files and min_size_gb."""
    db_path = _write_sample_db(tmp_path)
    base_path = tmp_path / "base"
    base_path.mkdir()

    exit_code = main(
        [
            "--db-path",
            str(db_path),
            "--base-path",
            str(base_path),
            "--min-files",
            "1",
            "--min-size-gb",
            "0.5",
            "--refresh-cache",
        ]
    )
    assert_equal(exit_code, 0)
    captured = capsys.readouterr().out
    assert "Using database:" in captured


def test_main_with_negative_min_files(tmp_path):
    """Test main with negative min_files (should be clamped to 0)."""
    db_path = _write_sample_db(tmp_path)
    base_path = tmp_path / "base"
    base_path.mkdir()

    exit_code = main(
        [
            "--db-path",
            str(db_path),
            "--base-path",
            str(base_path),
            "--min-files",
            "-5",
            "--refresh-cache",
        ]
    )
    assert_equal(exit_code, 0)


def test_main_with_delete_and_cached_report(tmp_path, capsys):
    """Test main with delete flag and cached report (should recompute)."""
    db_path = _write_sample_db(tmp_path)
    base_path = tmp_path / "base"
    base_path.mkdir()

    # First run to cache results
    exit_code = main(
        [
            "--db-path",
            str(db_path),
            "--base-path",
            str(base_path),
        ]
    )
    assert_equal(exit_code, 0)

    # Second run with delete
    with patch("builtins.input", return_value="n"):
        exit_code = main(
            [
                "--db-path",
                str(db_path),
                "--base-path",
                str(base_path),
                "--delete",
            ]
        )
    assert_equal(exit_code, 0)
    captured = capsys.readouterr().out
    # Should show some output about duplicates or deletion
    assert "Done" in captured
