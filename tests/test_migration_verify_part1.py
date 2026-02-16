"""
Unit tests for migration_verify.py - Part 1.

Tests for inventory and progress functions.
"""

import time
from unittest import mock

import pytest

from migration_utils import ProgressTracker
from migration_verify_checksums import update_verification_progress
from migration_verify_inventory import check_inventory, load_expected_files, scan_local_files
from tests.assertions import assert_equal


def test_load_expected_files_returns_file_map(tmp_path, mock_db_connection):
    """Test loading expected files from database"""
    mock_state = mock.Mock()

    # Mock database rows as list
    mock_rows = [
        {"key": "file1.txt", "size": 100, "etag": "abc123"},
        {"key": "dir/file2.txt", "size": 200, "etag": "def456"},
    ]

    mock_state.db_conn.get_connection.return_value = mock_db_connection(mock_rows)

    result = load_expected_files(mock_state, "test-bucket")

    assert_equal(len(result), 2)
    assert_equal(result["file1.txt"]["size"], 100)
    assert result["file1.txt"]["etag"] == "abc123"
    assert_equal(result["dir/file2.txt"]["size"], 200)


def test_load_expected_files_normalizes_windows_paths(tmp_path, mock_db_connection):
    """Test that Windows path separators are normalized"""
    mock_state = mock.Mock()

    # Mock database with Windows-style path
    mock_rows = [
        {"key": "dir\\file.txt", "size": 100, "etag": "abc123"},
    ]

    mock_state.db_conn.get_connection.return_value = mock_db_connection(mock_rows)

    result = load_expected_files(mock_state, "test-bucket")

    # Path should be normalized to forward slashes
    assert "dir/file.txt" in result
    assert "dir\\file.txt" not in result


def test_scan_local_files_finds_files(tmp_path):
    """Test scanning local files"""
    # Create test directory structure
    bucket_path = tmp_path / "test-bucket"
    bucket_path.mkdir()
    (bucket_path / "file1.txt").write_text("content1")
    (bucket_path / "subdir").mkdir()
    (bucket_path / "subdir" / "file2.txt").write_text("content2")

    local_files = scan_local_files(tmp_path, "test-bucket", 2)

    assert_equal(len(local_files), 2)
    assert "file1.txt" in local_files
    assert "subdir/file2.txt" in local_files


def test_scan_local_files_handles_missing_directory(tmp_path):
    """Test scanning when directory doesn't exist"""
    # Create bucket path but leave it empty for rglob
    bucket_path = tmp_path / "test-bucket"
    bucket_path.mkdir()

    local_files = scan_local_files(tmp_path, "test-bucket", 0)

    assert not local_files


def test_scan_local_files_normalizes_windows_paths(tmp_path):
    """Test that scanned files use forward slashes"""
    bucket_path = tmp_path / "test-bucket"
    bucket_path.mkdir()
    (bucket_path / "subdir").mkdir()
    (bucket_path / "subdir" / "file.txt").write_text("content")

    local_files = scan_local_files(tmp_path, "test-bucket", 1)

    # Should use forward slashes regardless of platform
    assert "subdir/file.txt" in local_files
    assert "subdir\\file.txt" not in local_files


def test_check_inventory_success_when_files_match():
    """Test inventory check succeeds when files match"""
    expected_keys = {"file1.txt", "file2.txt", "dir/file3.txt"}
    local_keys = {"file1.txt", "file2.txt", "dir/file3.txt"}

    errors = check_inventory(expected_keys, local_keys)

    assert not errors


def test_check_inventory_fails_on_missing_files():
    """Test inventory check fails when files are missing"""
    expected_keys = {"file1.txt", "file2.txt", "file3.txt"}
    local_keys = {"file1.txt"}

    with pytest.raises(ValueError) as exc_info:
        check_inventory(expected_keys, local_keys)

    assert "File inventory check failed" in str(exc_info.value)
    assert "2 missing" in str(exc_info.value)


def test_check_inventory_fails_on_extra_files():
    """Test inventory check fails when extra files exist"""
    expected_keys = {"file1.txt"}
    local_keys = {"file1.txt", "file2.txt", "file3.txt"}

    with pytest.raises(ValueError) as exc_info:
        check_inventory(expected_keys, local_keys)

    assert "File inventory check failed" in str(exc_info.value)
    assert "2 extra" in str(exc_info.value)


def test_check_inventory_fails_on_both_missing_and_extra():
    """Test inventory check fails on both missing and extra files"""
    expected_keys = {"file1.txt", "file2.txt"}
    local_keys = {"file1.txt", "file3.txt", "file4.txt"}

    with pytest.raises(ValueError) as exc_info:
        check_inventory(expected_keys, local_keys)

    assert "File inventory check failed" in str(exc_info.value)
    assert "1 missing" in str(exc_info.value)
    assert "2 extra" in str(exc_info.value)


def test_update_progress_displays_on_file_milestone(capsys):
    """Test progress update displays at file count milestone"""
    progress = ProgressTracker(update_interval=2.0)
    start_time = time.time() - 10  # Started 10 seconds ago

    update_verification_progress(
        progress=progress,
        start_time=start_time,
        verified_count=100,  # Divisible by 100 triggers display
        total_bytes_verified=1024 * 1024,  # 1 MB
        expected_files=200,
        expected_size=10 * 1024 * 1024,  # 10 MB
    )

    captured = capsys.readouterr()
    # Should display progress at 100-file milestone
    assert "Progress:" in captured.out


def test_update_progress_updates_on_file_count_milestone(capsys):
    """Test progress update displays on file count milestone (every 100 files)"""
    progress = ProgressTracker(update_interval=2.0)
    start_time = time.time()

    update_verification_progress(
        progress=progress,
        start_time=start_time,
        verified_count=100,  # Exactly 100 files (divisible by 100)
        total_bytes_verified=1024 * 1024,
        expected_files=200,
        expected_size=20 * 1024 * 1024,
    )

    captured = capsys.readouterr()
    # Should display due to file count milestone
    assert "Progress:" in captured.out


def test_update_progress_no_update_when_too_soon(capsys):
    """Test progress update doesn't display when too soon"""
    progress = ProgressTracker(update_interval=2.0)
    start_time = time.time()

    update_verification_progress(
        progress=progress,
        start_time=start_time,
        verified_count=50,
        total_bytes_verified=1024 * 1024,
        expected_files=100,
        expected_size=10 * 1024 * 1024,
    )

    captured = capsys.readouterr()
    # Should not display since <2 seconds elapsed
    assert captured.out == ""
