"""Unit tests for scan functions from migration_scanner.py - Basic operations"""

from datetime import datetime
from unittest import mock

from migration_scanner import scan_all_buckets, scan_bucket
from migration_state_v2 import Phase
from tests.assertions import assert_equal


def test_scan_all_buckets_with_no_buckets(s3_mock, state_mock, interrupted, capsys):
    """Test scanning when no buckets exist"""
    s3_mock.list_buckets.return_value = {"Buckets": []}

    scan_all_buckets(s3_mock, state_mock, interrupted)

    assert capsys.readouterr().out.count("PHASE 1/4: SCANNING BUCKETS") == 1
    state_mock.set_current_phase.assert_called_once_with(Phase.GLACIER_RESTORE)


def test_scan_all_buckets_with_single_bucket(s3_mock, state_mock, interrupted):
    """Test scanning with single bucket"""
    s3_mock.list_buckets.return_value = {"Buckets": [{"Name": "test-bucket"}]}
    s3_mock.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "file.txt",
                    "Size": 100,
                    "ETag": '"abc123"',
                    "StorageClass": "STANDARD",
                    "LastModified": datetime.now(),
                }
            ]
        }
    ]

    scan_all_buckets(s3_mock, state_mock, interrupted)

    state_mock.add_file.assert_called_once()
    state_mock.save_bucket_status.assert_called_once()
    state_mock.set_current_phase.assert_called_once_with(Phase.GLACIER_RESTORE)


def test_scan_all_buckets_handles_empty_bucket(s3_mock, state_mock, interrupted):
    """Test scanning empty bucket"""
    s3_mock.list_buckets.return_value = {"Buckets": [{"Name": "empty-bucket"}]}
    s3_mock.get_paginator.return_value.paginate.return_value = [{}]

    scan_all_buckets(s3_mock, state_mock, interrupted)

    state_mock.add_file.assert_not_called()
    state_mock.save_bucket_status.assert_called_once()
    status = state_mock.save_bucket_status.call_args[0][0]
    assert status.bucket == "empty-bucket"
    assert status.file_count == 0
    assert status.total_size == 0
    assert status.storage_classes == {}
    assert status.scan_complete is True


def test_scan_all_buckets_filters_excluded_buckets(s3_mock, state_mock, interrupted, capsys):
    """Test that excluded buckets are filtered out"""
    with mock.patch("migration_scanner.EXCLUDED_BUCKETS", ["excluded-bucket"]):
        s3_mock.list_buckets.return_value = {
            "Buckets": [
                {"Name": "test-bucket"},
                {"Name": "excluded-bucket"},
            ]
        }
        s3_mock.get_paginator.return_value.paginate.return_value = []

        scan_all_buckets(s3_mock, state_mock, interrupted)

        output = capsys.readouterr().out
        assert "Found 1 bucket(s)" in output
        assert "Excluded 1 bucket(s)" in output


def test_scan_all_buckets_with_multiple_pages(s3_mock, state_mock, interrupted):
    """Test scanning bucket with pagination"""
    s3_mock.list_buckets.return_value = {"Buckets": [{"Name": "test-bucket"}]}
    s3_mock.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "file1.txt",
                    "Size": 100,
                    "ETag": '"abc123"',
                    "StorageClass": "STANDARD",
                    "LastModified": datetime.now(),
                }
            ]
        },
        {
            "Contents": [
                {
                    "Key": "file2.txt",
                    "ETag": '"def456"',
                    "Size": 200,
                    "StorageClass": "GLACIER",
                    "LastModified": datetime.now(),
                }
            ]
        },
    ]

    scan_all_buckets(s3_mock, state_mock, interrupted)

    assert_equal(state_mock.add_file.call_count, 2)
