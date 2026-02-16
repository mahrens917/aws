"""Unit tests for scan functions from migration_scanner.py - ETag handling"""

from datetime import datetime
from threading import Event

import pytest

from migration_scanner import scan_bucket


def test_scan_bucket_raises_on_missing_etag(s3_mock, state_mock):
    """Test that missing ETag field raises KeyError (fail-fast)"""
    s3_mock.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "file.txt",
                    "Size": 100,
                    "StorageClass": "STANDARD",
                    "LastModified": datetime.now(),
                    # ETag missing - AWS always provides this, so missing indicates bad data
                }
            ]
        }
    ]

    with pytest.raises(KeyError, match="ETag"):
        scan_bucket(s3_mock, state_mock, "test-bucket", Event())

    # Should not have called add_file since we raised before that
    state_mock.add_file.assert_not_called()


def test_scan_bucket_strips_etag_quotes(s3_mock, state_mock):
    """Test that ETags are stripped of quotes"""
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

    scan_bucket(s3_mock, state_mock, "test-bucket", Event())

    # ETag should be stripped of quotes
    call_args = state_mock.add_file.call_args
    metadata = call_args[0][0]
    assert metadata.etag == "abc123"
