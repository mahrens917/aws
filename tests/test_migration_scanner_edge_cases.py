"""Edge case and large-scale tests for migration_scanner.py functions"""

import io
import sys
from datetime import datetime
from threading import Event
from unittest import mock

from migration_scanner import check_restore_status, scan_all_buckets, scan_bucket, wait_for_restores
from migration_state_v2 import MigrationStateV2
from tests.assertions import assert_equal


def test_scan_bucket_respects_pagination_interrupt():
    """Test interrupt during pagination"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock(spec=MigrationStateV2)

    interrupted = Event()
    page_count = 0

    def paginate_with_interrupt(*_args, **_kwargs):
        nonlocal page_count
        page_count += 1
        interrupted.set()
        return [
            {
                "Contents": [
                    {
                        "Key": f"file{page_count}.txt",
                        "Size": 100,
                        "ETag": '"abc123"',
                        "StorageClass": "STANDARD",
                        "LastModified": datetime.now(),
                    }
                ]
            }
        ]

    mock_s3.get_paginator.return_value.paginate = paginate_with_interrupt

    scan_bucket(mock_s3, mock_state, "test-bucket", interrupted)

    # Should only process first page before interrupt
    mock_state.save_bucket_status.assert_not_called()


def test_scan_bucket_progress_output():
    """Test progress output for large number of files"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock(spec=MigrationStateV2)

    files = []
    for i in range(20001):
        files.append(
            {
                "Key": f"file{i}.txt",
                "Size": 100,
                "ETag": f'"etag{i}"',
                "StorageClass": "STANDARD",
                "LastModified": datetime.now(),
            }
        )

    mock_s3.get_paginator.return_value.paginate.return_value = [{"Contents": files}]

    captured_output = io.StringIO()
    sys.stdout = captured_output

    scan_bucket(mock_s3, mock_state, "test-bucket", Event())

    sys.stdout = sys.__stdout__
    output = captured_output.getvalue()
    # Should show progress at 10000 mark
    assert "20001" in output or "20,001" in output


def test_scan_all_buckets_handles_very_large_bucket():
    """Test scanning a bucket with many files"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock(spec=MigrationStateV2)
    mock_s3.list_buckets.return_value = {"Buckets": [{"Name": "large-bucket"}]}

    # Create a large number of files
    files = [
        {
            "Key": f"file{i}.txt",
            "Size": 1000000,
            "ETag": f'"etag{i}"',
            "StorageClass": "STANDARD",
            "LastModified": datetime.now(),
        }
        for i in range(50000)
    ]

    mock_s3.get_paginator.return_value.paginate.return_value = [{"Contents": files}]

    scan_all_buckets(mock_s3, mock_state, Event())

    # Should have added all files
    assert_equal(mock_state.add_file.call_count, 50000)


def test_scan_all_buckets_handles_zero_size_files():
    """Test scanning bucket with zero-size files"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock(spec=MigrationStateV2)
    mock_s3.list_buckets.return_value = {"Buckets": [{"Name": "test-bucket"}]}

    mock_s3.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "zero.txt",
                    "Size": 0,
                    "ETag": '"abc123"',
                    "StorageClass": "STANDARD",
                    "LastModified": datetime.now(),
                }
            ]
        }
    ]

    scan_all_buckets(mock_s3, mock_state, Event())

    status = mock_state.save_bucket_status.call_args[0][0]
    assert status.total_size == 0  # Total size should be 0


def test_check_restore_status_handles_restore_string_variations():
    """Test various restore string formats"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock(spec=MigrationStateV2)

    test_cases = [
        ('ongoing-request="false"', True),
        ('ongoing-request="true"', False),
        ('ongoing-request="false", expiry-date="..."', True),
        ("", False),
    ]

    for restore_string, expected in test_cases:
        mock_s3.head_object.return_value = {"Restore": restore_string} if restore_string else {}

        result = check_restore_status(mock_s3, mock_state, {"bucket": "b", "key": "k"})
        assert result == expected


def test_check_restore_status_partial_restore_string(s3_mock, state_mock):
    """Test restore status with various Restore header formats"""
    # AWS includes timestamp and expiry in the Restore header
    s3_mock.head_object.return_value = {
        "Restore": 'ongoing-request="false", expiry-date="Tue, 25 Oct 2022 00:00:00 GMT"',
    }

    file_info = {"bucket": "test-bucket", "key": "file.txt"}
    result = check_restore_status(s3_mock, state_mock, file_info)

    assert result is True
    state_mock.mark_glacier_restored.assert_called_once()


def test_wait_for_restores_prints_restored_files(s3_mock, state_mock, capsys):
    """Test output shows restored files"""
    s3_mock.head_object.return_value = {"Restore": 'ongoing-request="false"'}

    state_mock.get_files_restoring.side_effect = [
        [
            {"bucket": "test-bucket", "key": "file1.txt"},
            {"bucket": "test-bucket", "key": "file2.txt"},
        ],
        [],
    ]

    with mock.patch("migration_scanner._wait_with_interrupt"):
        wait_for_restores(s3_mock, state_mock, Event())

    output = capsys.readouterr().out
    assert "Restored: test-bucket/file1.txt" in output
    assert "Restored: test-bucket/file2.txt" in output


def test_check_restore_status_with_multiple_files(s3_mock, state_mock):
    """Test checking multiple files"""
    files = [
        {"bucket": "bucket1", "key": "file1.txt"},
        {"bucket": "bucket2", "key": "file2.txt"},
        {"bucket": "bucket1", "key": "file3.txt"},
    ]

    # First file complete, others still restoring
    s3_mock.head_object.side_effect = [
        {"Restore": 'ongoing-request="false"'},
        {"Restore": 'ongoing-request="true"'},
        {"Restore": 'ongoing-request="true"'},
    ]

    results = [check_restore_status(s3_mock, state_mock, f) for f in files]

    assert results == [True, False, False]
    assert state_mock.mark_glacier_restored.call_count == 1
