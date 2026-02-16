"""Unit tests for scan functions from migration_scanner.py - Storage class handling"""

from datetime import datetime
from threading import Event

from migration_scanner import scan_all_buckets, scan_bucket
from tests.assertions import assert_equal


def test_scan_all_buckets_respects_interrupt_signal(s3_mock, state_mock):
    """Test that scan_all_buckets stops on interrupt"""
    s3_mock.list_buckets.return_value = {
        "Buckets": [
            {"Name": "bucket1"},
            {"Name": "bucket2"},
        ]
    }
    s3_mock.get_paginator.return_value.paginate.return_value = []

    interrupted = Event()

    # Interrupt after first bucket
    def interrupt_on_second_call(*_args, **_kwargs):
        interrupted.set()

    state_mock.save_bucket_status.side_effect = interrupt_on_second_call

    scan_all_buckets(s3_mock, state_mock, interrupted)

    # Should only process first bucket
    assert state_mock.save_bucket_status.call_count == 1


def test_scan_bucket_with_mixed_storage_classes(s3_mock, state_mock):
    """Test scanning bucket with multiple storage classes"""
    files = [
        {
            "Key": "standard.txt",
            "Size": 100,
            "ETag": '"etag1"',
            "StorageClass": "STANDARD",
            "LastModified": datetime.now(),
        },
        {
            "Key": "glacier.txt",
            "Size": 200,
            "ETag": '"etag2"',
            "StorageClass": "GLACIER",
            "LastModified": datetime.now(),
        },
        {
            "Key": "deep_archive.txt",
            "Size": 300,
            "ETag": '"etag3"',
            "StorageClass": "DEEP_ARCHIVE",
            "LastModified": datetime.now(),
        },
    ]
    s3_mock.get_paginator.return_value.paginate.return_value = [{"Contents": files}]

    scan_bucket(s3_mock, state_mock, "test-bucket", Event())

    status = state_mock.save_bucket_status.call_args[0][0]
    assert status.storage_classes["STANDARD"] == 1
    assert status.storage_classes["GLACIER"] == 1
    assert status.storage_classes["DEEP_ARCHIVE"] == 1


def test_scan_bucket_handles_missing_storage_class(s3_mock, state_mock):
    """Test handling of objects without StorageClass field"""
    s3_mock.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "file.txt",
                    "Size": 100,
                    "ETag": '"abc123"',
                    "LastModified": datetime.now(),
                    # StorageClass missing - AWS omits this for STANDARD
                }
            ]
        }
    ]

    scan_bucket(s3_mock, state_mock, "test-bucket", Event())

    # Should default to STANDARD
    status = state_mock.save_bucket_status.call_args[0][0]
    assert status.storage_classes["STANDARD"] == 1


def test_scan_bucket_accumulates_size(s3_mock, state_mock):
    """Test that file sizes are accumulated correctly"""
    s3_mock.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "file1.txt",
                    "Size": 1000,
                    "ETag": '"etag1"',
                    "StorageClass": "STANDARD",
                    "LastModified": datetime.now(),
                },
                {
                    "Key": "file2.txt",
                    "Size": 2000,
                    "ETag": '"etag2"',
                    "StorageClass": "STANDARD",
                    "LastModified": datetime.now(),
                },
            ]
        }
    ]

    scan_bucket(s3_mock, state_mock, "test-bucket", Event())

    # Total size should be 3000
    status = state_mock.save_bucket_status.call_args[0][0]
    assert_equal(status.total_size, 3000)
