"""Unit tests for migration_verify.py - Part 4: Edge Cases (Part 1)"""

import hashlib
from unittest import mock

import pytest

from migration_verify_bucket import verify_bucket
from migration_verify_checksums import verify_files, verify_multipart_file
from migration_verify_delete import delete_bucket
from migration_verify_inventory import check_inventory, scan_local_files
from tests.assertions import assert_equal


def test_check_inventory_shows_many_missing_files():
    """Test inventory check shows summary when >10 missing files"""
    expected_keys = {f"file{i}.txt" for i in range(20)}
    local_keys = {"file0.txt", "file1.txt"}

    with pytest.raises(ValueError) as exc_info:
        check_inventory(expected_keys, local_keys)

    assert "18 missing" in str(exc_info.value)


def test_check_inventory_shows_many_extra_files():
    """Test inventory check shows summary when >10 extra files"""
    expected_keys = {"file0.txt", "file1.txt"}
    local_keys = {f"file{i}.txt" for i in range(20)}

    with pytest.raises(ValueError) as exc_info:
        check_inventory(expected_keys, local_keys)

    assert "18 extra" in str(exc_info.value)


def test_verify_files_shows_many_verification_errors(tmp_path):
    """Test verify_files shows summary when >10 verification errors"""
    # Create files with size mismatches
    files = {}
    expected_map = {}
    for i in range(15):
        file_path = tmp_path / f"file{i}.txt"
        file_path.write_bytes(b"content")
        files[f"file{i}.txt"] = file_path
        expected_map[f"file{i}.txt"] = {"size": 999, "etag": "abc123"}

    with pytest.raises(ValueError) as exc_info:
        verify_files(
            local_files=files,
            expected_file_map=expected_map,
            expected_files=15,
            expected_size=15 * 999,
        )

    assert "15 file(s) with issues" in str(exc_info.value)


def test_scan_local_files_with_no_progress_needed(tmp_path):
    """Test scanning <10000 files doesn't show progress"""
    bucket_path = tmp_path / "test-bucket"
    bucket_path.mkdir()
    # Create 5 files (less than 10000)
    for i in range(5):
        (bucket_path / f"file{i}.txt").write_text(f"content{i}")

    local_files = scan_local_files(tmp_path, "test-bucket", 5)

    assert_equal(len(local_files), 5)


def test_scan_files_with_equal_expected_files(tmp_path):
    """Test scanning when actual files equal expected files"""
    bucket_path = tmp_path / "test-bucket"
    bucket_path.mkdir()

    # Create exactly 100 files
    for i in range(100):
        (bucket_path / f"file{i}.txt").write_text(f"content{i}")

    # Tell it to expect exactly 100 files
    local_files = scan_local_files(tmp_path, "test-bucket", 100)

    assert_equal(len(local_files), 100)


def test_verify_files_count_mismatch_in_verify_bucket(tmp_path, mock_db_connection):
    """Test that verify_bucket detects verified count mismatch"""
    bucket_path = tmp_path / "test-bucket"
    bucket_path.mkdir()
    (bucket_path / "file1.txt").write_bytes(b"content1")

    md5_1 = hashlib.md5(b"content1", usedforsecurity=False).hexdigest()

    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {
        "file_count": 2,  # Says 2 files but only has 1
        "total_size": 16,
    }

    mock_rows = [
        {"key": "file1.txt", "size": 8, "etag": md5_1},
        {"key": "file2.txt", "size": 8, "etag": "def456"},  # Missing
    ]
    mock_state.db_conn.get_connection.return_value = mock_db_connection(mock_rows)

    # Should fail at inventory check because file2.txt is missing
    with pytest.raises(ValueError):
        verify_bucket(mock_state, tmp_path, "test-bucket")


def test_verify_multipart_file_verifies_checksum(tmp_path, empty_verify_stats):
    """Test multipart file verification updates stats correctly"""
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"multipart content here")

    stats = empty_verify_stats.copy()
    stats["size_verified"] = 1

    verify_multipart_file("file1.txt", file1, stats)

    assert_equal(stats["verified_count"], 1)
    assert_equal(stats["checksum_verified"], 1)


def test_compute_etag_with_empty_file(tmp_path):
    """Test ETag computation for empty file"""
    from migration_verify_checksums import compute_etag

    file1 = tmp_path / "empty.txt"
    file1.write_bytes(b"")

    md5_hash = hashlib.md5(b"", usedforsecurity=False).hexdigest()

    computed, is_match = compute_etag(file1, md5_hash)

    assert is_match is True
    assert computed == md5_hash


def test_verify_files_with_mixed_single_and_multipart(tmp_path):
    """Test verification of files with mixed part types"""
    # Create single-part file
    file1 = tmp_path / "singlepart.txt"
    file1.write_bytes(b"single")

    # Create multipart file
    file2 = tmp_path / "multipart.txt"
    file2.write_bytes(b"multipart")

    md5_1 = hashlib.md5(b"single", usedforsecurity=False).hexdigest()

    local_files = {
        "singlepart.txt": file1,
        "multipart.txt": file2,
    }
    expected_file_map = {
        "singlepart.txt": {"size": 6, "etag": md5_1},
        "multipart.txt": {"size": 9, "etag": "def456-2"},  # Multipart (has hyphen)
    }

    results = verify_files(
        local_files=local_files,
        expected_file_map=expected_file_map,
        expected_files=2,
        expected_size=15,
    )

    assert_equal(results["verified_count"], 2)
    assert_equal(results["checksum_verified"], 2)


def test_delete_bucket_large_batch():
    """Test deleting bucket with large batch of objects"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {"file_count": 1500}

    # Create mock paginator with large batch (list_object_versions format)
    large_batch = {"Versions": [{"Key": f"file{i}.txt", "VersionId": f"v{i}"} for i in range(1500)]}
    mock_paginator = mock.Mock()
    mock_paginator.paginate.return_value = [large_batch]
    mock_s3.get_paginator.return_value = mock_paginator
    mock_s3.delete_objects.return_value = {}

    delete_bucket(mock_s3, mock_state, "test-bucket")

    # Verify delete_objects was called with all objects
    call_args = mock_s3.delete_objects.call_args
    assert_equal(len(call_args[1]["Delete"]["Objects"]), 1500)


def test_delete_bucket_updates_progress():
    """Test that delete progress is displayed"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {"file_count": 5}

    # Create multiple pages to trigger progress updates (list_object_versions format)
    mock_paginator = mock.Mock()
    pages = [{"Versions": [{"Key": f"file{i}.txt", "VersionId": f"v{i}"} for i in range(j * 1000, (j + 1) * 1000)]} for j in range(5)]
    mock_paginator.paginate.return_value = pages
    mock_s3.get_paginator.return_value = mock_paginator
    mock_s3.delete_objects.return_value = {}

    # Should not raise an error
    delete_bucket(mock_s3, mock_state, "test-bucket")

    # Should have called delete_objects for each page
    assert_equal(mock_s3.delete_objects.call_count, 5)
