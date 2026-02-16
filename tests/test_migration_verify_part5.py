"""Unit tests for migration_verify.py - Part 5: Edge Cases (Part 2) and Integration Tests"""

import time
from unittest import mock

import pytest

from migration_utils import ProgressTracker
from migration_verify_bucket import verify_bucket
from migration_verify_checksums import update_verification_progress
from migration_verify_delete import _bucket_has_contents, _ensure_list, delete_bucket
from migration_verify_inventory import scan_local_files
from tests.assertions import assert_equal


def test_update_progress_with_large_file_counts(capsys):
    """Test progress update with large file counts"""
    progress = ProgressTracker(update_interval=2.0)
    start_time = time.time() - 10

    # Test with 1 million files
    update_verification_progress(
        progress=progress,
        start_time=start_time,
        verified_count=500000,
        total_bytes_verified=1024 * 1024 * 1024,  # 1 GB
        expected_files=1000000,
        expected_size=2048 * 1024 * 1024,  # 2 GB
    )

    captured = capsys.readouterr()
    # Should display progress with large counts
    assert "Progress:" in captured.out


def test_verify_files_all_file_count_milestone_updates(capsys):
    """Test progress updates at every 100-file milestone"""
    progress = ProgressTracker(update_interval=2.0)
    current_time = time.time()

    # Verify that exactly 100 files triggers an update
    update_verification_progress(
        progress=progress,
        start_time=current_time,
        verified_count=100,
        total_bytes_verified=1024,
        expected_files=1000,
        expected_size=10240,
    )

    captured = capsys.readouterr()
    # Should have updated due to file count milestone
    assert "Progress:" in captured.out


def test_delete_bucket_with_zero_objects():
    """Test deleting bucket with no objects"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {"file_count": 0}

    mock_paginator = mock.Mock()
    mock_paginator.paginate.return_value = []
    mock_s3.get_paginator.return_value = mock_paginator

    delete_bucket(mock_s3, mock_state, "empty-bucket")

    # Should still call delete_bucket to remove the empty bucket
    mock_s3.delete_bucket.assert_called_once_with(Bucket="empty-bucket")


def test_scan_large_number_of_files_with_progress_output(tmp_path):
    """Test scanning with many files to trigger progress output"""
    bucket_path = tmp_path / "test-bucket"
    bucket_path.mkdir()

    # Create 10100 files to trigger progress output (>10000)
    for i in range(10100):
        subdir = bucket_path / f"dir{i // 100}"
        subdir.mkdir(exist_ok=True)
        (subdir / f"file{i}.txt").write_text(f"content{i}")

    local_files = scan_local_files(tmp_path, "test-bucket", 10100)

    assert_equal(len(local_files), 10100)


def test_delete_bucket_with_pagination_triggers_progress():
    """Test delete progress update at 1000 object intervals"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {"file_count": 2500}

    # Create 3 pages with 1000, 1000, 500 objects (list_object_versions format)
    mock_paginator = mock.Mock()
    mock_paginator.paginate.return_value = [
        {"Versions": [{"Key": f"file{i}.txt", "VersionId": f"v{i}"} for i in range(1000)]},
        {"Versions": [{"Key": f"file{i}.txt", "VersionId": f"v{i}"} for i in range(1000, 2000)]},
        {"Versions": [{"Key": f"file{i}.txt", "VersionId": f"v{i}"} for i in range(2000, 2500)]},
    ]
    mock_s3.get_paginator.return_value = mock_paginator
    # Mock delete_objects to return a response without errors
    mock_s3.delete_objects.return_value = {"Deleted": []}

    delete_bucket(mock_s3, mock_state, "test-bucket")

    # Should be called 3 times (one per page)
    assert_equal(mock_s3.delete_objects.call_count, 3)


def test_full_verification_workflow(setup_verify_test):
    """Test complete verification workflow from inventory to checksums"""
    test_env = setup_verify_test({"file1.txt": b"content", "file2.txt": b"data"})

    results = verify_bucket(test_env["mock_state"], test_env["tmp_path"], "test-bucket")

    assert_equal(results["verified_count"], 2)
    assert_equal(results["checksum_verified"], 2)
    assert_equal(results["local_file_count"], 2)


def test_error_handling_across_components(tmp_path, mock_db_connection):
    """Test error handling flows through components"""
    bucket_path = tmp_path / "test-bucket"
    bucket_path.mkdir()
    (bucket_path / "file1.txt").write_bytes(b"content")

    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {
        "file_count": 1,
        "total_size": 100,
    }

    mock_rows = [
        {"key": "file1.txt", "size": 100, "etag": "abc123"},  # Wrong size
    ]
    mock_state.db_conn.get_connection.return_value = mock_db_connection(mock_rows)

    with pytest.raises(ValueError):
        verify_bucket(mock_state, tmp_path, "test-bucket")


# Edge case tests for _ensure_list() function
def test_ensure_list_with_empty_input():
    """Test _ensure_list with empty/None inputs"""
    assert_equal(_ensure_list(None), [])
    assert_equal(_ensure_list([]), [])
    assert_equal(_ensure_list(""), [])


def test_ensure_list_with_dict_input():
    """Test _ensure_list converts dict to single-element list"""
    test_dict = {"Key": "file.txt", "VersionId": "v1"}
    result = _ensure_list(test_dict)
    assert_equal(len(result), 1)
    assert_equal(result[0], test_dict)


def test_ensure_list_with_list_input():
    """Test _ensure_list returns list as-is"""
    test_list = [{"Key": "file1.txt"}, {"Key": "file2.txt"}]
    result = _ensure_list(test_list)
    assert_equal(result, test_list)


# Edge case tests for _bucket_has_contents() function
def test_bucket_has_contents_empty():
    """Test bucket with no content returns False"""
    mock_s3 = mock.Mock()
    mock_paginator = mock.Mock()
    mock_paginator.paginate.return_value = [{}]  # Empty page
    mock_s3.get_paginator.return_value = mock_paginator

    result = _bucket_has_contents(mock_s3, "empty-bucket")
    assert result is False


def test_bucket_has_contents_with_versions():
    """Test bucket with versions returns True"""
    mock_s3 = mock.Mock()
    mock_paginator = mock.Mock()
    mock_paginator.paginate.return_value = [{"Versions": [{"Key": "file.txt", "VersionId": "v1"}]}]
    mock_s3.get_paginator.return_value = mock_paginator

    result = _bucket_has_contents(mock_s3, "bucket-with-versions")
    assert result is True


def test_bucket_has_contents_with_delete_markers():
    """Test bucket with delete markers returns True"""
    mock_s3 = mock.Mock()
    mock_paginator = mock.Mock()
    mock_paginator.paginate.return_value = [{"DeleteMarkers": [{"Key": "file.txt", "VersionId": "d1"}]}]
    mock_s3.get_paginator.return_value = mock_paginator

    result = _bucket_has_contents(mock_s3, "bucket-with-delete-markers")
    assert result is True
