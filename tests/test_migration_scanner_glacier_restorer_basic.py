"""Unit tests for glacier restore functions - Basic operations"""

from threading import Event

from migration_scanner import request_all_restores, request_restore
from migration_state_v2 import Phase
from tests.assertions import assert_equal


def test_request_all_restores_no_glacier_files(s3_mock, state_mock, capsys):
    """Test when no Glacier files need restore"""
    state_mock.get_glacier_files_needing_restore.return_value = []

    request_all_restores(s3_mock, state_mock, Event())

    output = capsys.readouterr().out
    assert "No Glacier files need restore" in output
    state_mock.set_current_phase.assert_called_once_with(Phase.GLACIER_WAIT)


def test_request_all_restores_with_files(s3_mock, state_mock):
    """Test requesting restores for Glacier files"""
    state_mock.get_glacier_files_needing_restore.return_value = [{"bucket": "test-bucket", "key": "file.txt", "storage_class": "GLACIER"}]

    request_all_restores(s3_mock, state_mock, Event())

    s3_mock.restore_object.assert_called_once()
    state_mock.mark_glacier_restore_requested.assert_called_once()
    state_mock.set_current_phase.assert_called_once_with(Phase.GLACIER_WAIT)


def test_request_all_restores_multiple_files(s3_mock, state_mock):
    """Test requesting restores for multiple files"""
    state_mock.get_glacier_files_needing_restore.return_value = [
        {"bucket": "bucket1", "key": "file1.txt", "storage_class": "GLACIER"},
        {"bucket": "bucket2", "key": "file2.txt", "storage_class": "GLACIER"},
        {"bucket": "bucket1", "key": "file3.txt", "storage_class": "DEEP_ARCHIVE"},
    ]

    request_all_restores(s3_mock, state_mock, Event())

    assert_equal(s3_mock.restore_object.call_count, 3)
    assert_equal(state_mock.mark_glacier_restore_requested.call_count, 3)


def test_request_all_restores_respects_interrupt(s3_mock, state_mock):
    """Test that request_all_restores stops on interrupt"""
    state_mock.get_glacier_files_needing_restore.return_value = [
        {"bucket": "test-bucket", "key": "file1.txt", "storage_class": "GLACIER"},
        {"bucket": "test-bucket", "key": "file2.txt", "storage_class": "GLACIER"},
    ]

    interrupted = Event()

    def interrupt_on_first_call(*_args, **_kwargs):
        interrupted.set()

    s3_mock.restore_object.side_effect = interrupt_on_first_call

    request_all_restores(s3_mock, state_mock, interrupted)

    # Should only process first file
    assert s3_mock.restore_object.call_count == 1


def test_request_restore_success(s3_mock, state_mock, capsys):
    """Test successful restore request"""
    file_info = {
        "bucket": "test-bucket",
        "key": "file.txt",
        "storage_class": "GLACIER",
    }

    request_restore(s3_mock, state_mock, file_info, 5, 10)

    s3_mock.restore_object.assert_called_once()
    state_mock.mark_glacier_restore_requested.assert_called_once_with("test-bucket", "file.txt")
    output = capsys.readouterr().out
    assert "[5/10]" in output
