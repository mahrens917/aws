"""Unit tests for migration_verify.py - Part 3: verify_bucket and delete_bucket functions"""

from unittest import mock

import pytest

from migration_verify_bucket import verify_bucket
from migration_verify_delete import delete_bucket
from tests.assertions import assert_equal


def test_verify_bucket_integration_succeeds(setup_verify_test):
    """Test complete bucket verification workflow"""
    test_env = setup_verify_test({"file1.txt": b"content1"})

    results = verify_bucket(test_env["mock_state"], test_env["tmp_path"], "test-bucket")

    assert_equal(results["verified_count"], 1)
    assert_equal(results["local_file_count"], 1)
    assert_equal(results["checksum_verified"], 1)


def test_verify_bucket_fails_when_local_path_missing(tmp_path):
    """Test verification fails when local path doesn't exist"""
    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {
        "file_count": 1,
        "total_size": 100,
    }

    with pytest.raises(FileNotFoundError):
        verify_bucket(mock_state, tmp_path, "nonexistent-bucket")


def test_verify_bucket_fails_on_missing_files(tmp_path, mock_db_connection):
    """Test verification fails when files are missing"""
    bucket_path = tmp_path / "test-bucket"
    bucket_path.mkdir()
    (bucket_path / "file1.txt").write_bytes(b"content1")

    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {
        "file_count": 2,
        "total_size": 16,
    }

    mock_rows = [
        {"key": "file1.txt", "size": 8, "etag": "abc123"},
        {"key": "file2.txt", "size": 8, "etag": "def456"},  # Missing locally
    ]
    mock_state.db_conn.get_connection.return_value = mock_db_connection(mock_rows)

    with pytest.raises(ValueError) as exc_info:
        verify_bucket(mock_state, tmp_path, "test-bucket")

    assert "File inventory check failed" in str(exc_info.value)


def test_verify_bucket_fails_on_checksum_mismatch(tmp_path, mock_db_connection):
    """Test verification fails on checksum mismatch"""
    bucket_path = tmp_path / "test-bucket"
    bucket_path.mkdir()
    (bucket_path / "file1.txt").write_bytes(b"content1")

    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {
        "file_count": 1,
        "total_size": 8,
    }

    wrong_hash = "0" * 32
    mock_rows = [
        {"key": "file1.txt", "size": 8, "etag": wrong_hash},
    ]
    mock_state.db_conn.get_connection.return_value = mock_db_connection(mock_rows)

    with pytest.raises(ValueError) as exc_info:
        verify_bucket(mock_state, tmp_path, "test-bucket")

    assert "Verification failed" in str(exc_info.value)


def test_delete_bucket_single_page():
    """Test deleting bucket with single page of objects"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {"file_count": 3}

    # Mock paginator with single page (list_object_versions format)
    mock_paginator = mock.Mock()
    mock_paginator.paginate.return_value = [
        {
            "Versions": [
                {"Key": "file1.txt", "VersionId": "v1"},
                {"Key": "file2.txt", "VersionId": "v2"},
                {"Key": "file3.txt", "VersionId": "v3"},
            ]
        }
    ]
    mock_s3.get_paginator.return_value = mock_paginator
    mock_s3.delete_objects.return_value = {}

    delete_bucket(mock_s3, mock_state, "test-bucket")

    # Verify delete_objects was called
    mock_s3.delete_objects.assert_called_once()
    call_args = mock_s3.delete_objects.call_args
    assert call_args[1]["Bucket"] == "test-bucket"
    assert_equal(len(call_args[1]["Delete"]["Objects"]), 3)
    # Verify VersionId is included
    assert all("VersionId" in obj for obj in call_args[1]["Delete"]["Objects"])


def test_delete_bucket_multiple_pages():
    """Test deleting bucket with multiple pages of objects"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {"file_count": 6}

    # Mock paginator with multiple pages (list_object_versions format)
    mock_paginator = mock.Mock()
    mock_paginator.paginate.return_value = [
        {
            "Versions": [
                {"Key": "file1.txt", "VersionId": "v1"},
                {"Key": "file2.txt", "VersionId": "v2"},
            ]
        },
        {
            "Versions": [
                {"Key": "file3.txt", "VersionId": "v3"},
                {"Key": "file4.txt", "VersionId": "v4"},
            ]
        },
        {
            "Versions": [
                {"Key": "file5.txt", "VersionId": "v5"},
                {"Key": "file6.txt", "VersionId": "v6"},
            ]
        },
    ]
    mock_s3.get_paginator.return_value = mock_paginator
    mock_s3.delete_objects.return_value = {}

    delete_bucket(mock_s3, mock_state, "test-bucket")

    # Verify delete_objects was called 3 times (once per page)
    assert_equal(mock_s3.delete_objects.call_count, 3)


def test_delete_bucket_handles_empty_pages():
    """Test deleting bucket handles pages with no Versions"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {"file_count": 2}

    # Mock paginator with mixed pages (list_object_versions format)
    mock_paginator = mock.Mock()
    mock_paginator.paginate.return_value = [
        {"Versions": [{"Key": "file1.txt", "VersionId": "v1"}]},
        {},  # Empty page (no Versions key)
        {"Versions": [{"Key": "file2.txt", "VersionId": "v2"}]},
    ]
    mock_s3.get_paginator.return_value = mock_paginator
    mock_s3.delete_objects.return_value = {}

    delete_bucket(mock_s3, mock_state, "test-bucket")

    # Should only call delete_objects twice (skipping empty page)
    assert_equal(mock_s3.delete_objects.call_count, 2)


def test_delete_bucket_calls_delete_bucket_method():
    """Test that delete_bucket is called to remove empty bucket"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {"file_count": 1}

    mock_paginator = mock.Mock()
    mock_paginator.paginate.return_value = [{"Versions": [{"Key": "file1.txt", "VersionId": "v1"}]}]
    mock_s3.get_paginator.return_value = mock_paginator
    mock_s3.delete_objects.return_value = {}

    delete_bucket(mock_s3, mock_state, "test-bucket")

    # Verify delete_bucket was called
    mock_s3.delete_bucket.assert_called_once_with(Bucket="test-bucket")


def test_delete_bucket_formats_object_keys_correctly():
    """Test that object keys are formatted correctly for deletion"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock()
    mock_state.get_bucket_info.return_value = {"file_count": 2}

    mock_paginator = mock.Mock()
    mock_paginator.paginate.return_value = [
        {
            "Versions": [
                {"Key": "path/to/file1.txt", "VersionId": "v1"},
                {"Key": "path/to/file2.txt", "VersionId": "v2"},
            ]
        }
    ]
    mock_s3.get_paginator.return_value = mock_paginator
    mock_s3.delete_objects.return_value = {}

    delete_bucket(mock_s3, mock_state, "test-bucket")

    # Verify keys and version IDs are in correct format
    call_args = mock_s3.delete_objects.call_args
    objects = call_args[1]["Delete"]["Objects"]
    assert objects[0]["Key"] == "path/to/file1.txt"
    assert objects[0]["VersionId"] == "v1"
    assert objects[1]["Key"] == "path/to/file2.txt"
    assert objects[1]["VersionId"] == "v2"


class TestBucketDeleterMultipartCleanup:
    """Tests for delete_bucket multipart upload and final cleanup handling"""

    def test_delete_bucket_aborts_multipart_uploads_before_final_delete(self):
        """delete_bucket should abort uploads prior to deleting the bucket"""
        mock_s3 = mock.Mock()
        mock_state = mock.Mock()
        mock_state.get_bucket_info.return_value = {"file_count": 0}

        version_paginator = mock.Mock()
        version_paginator.paginate.return_value = []

        uploads_paginator = mock.Mock()
        uploads_paginator.paginate.return_value = [{"Uploads": [{"Key": "file1.txt", "UploadId": "upload-1"}]}]

        final_check_paginator = mock.Mock()
        final_check_paginator.paginate.return_value = [{}]

        mock_s3.get_paginator.side_effect = [
            version_paginator,
            uploads_paginator,
            final_check_paginator,
        ]

        delete_bucket(mock_s3, mock_state, "test-bucket")

        mock_s3.abort_multipart_upload.assert_called_once_with(Bucket="test-bucket", Key="file1.txt", UploadId="upload-1")
        mock_s3.delete_bucket.assert_called_once_with(Bucket="test-bucket")

    def test_delete_bucket_raises_when_objects_remain(self):
        """delete_bucket should raise if objects remain after deletion pass"""
        mock_s3 = mock.Mock()
        mock_state = mock.Mock()
        mock_state.get_bucket_info.return_value = {"file_count": 1}

        version_paginator = mock.Mock()
        version_paginator.paginate.return_value = []

        uploads_paginator = mock.Mock()
        uploads_paginator.paginate.return_value = []

        leftover_paginator = mock.Mock()
        leftover_paginator.paginate.return_value = [{"Versions": [{"Key": "file1.txt", "VersionId": "v1"}]}]

        mock_s3.get_paginator.side_effect = [
            version_paginator,
            uploads_paginator,
            leftover_paginator,
        ]

        with pytest.raises(RuntimeError) as exc_info:
            delete_bucket(mock_s3, mock_state, "test-bucket")

        assert "Bucket still contains objects" in str(exc_info.value)
        mock_s3.delete_bucket.assert_not_called()
