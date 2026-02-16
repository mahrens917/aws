"""Integration and edge case tests for migration_scanner.py

Tests phase transitions, interruption handling, error handling, and edge cases.
"""

from threading import Event
from unittest import mock

import pytest
from botocore.exceptions import ClientError

from migration_scanner import (
    request_all_restores,
    scan_all_buckets,
    wait_for_restores,
)
from migration_state_v2 import MigrationStateV2, Phase


class TestPhaseTransitions:
    """Test phase transitions across functions"""

    def test_scan_all_buckets_transitions_to_glacier_restore(self):
        """Test scan_all_buckets transitions to GLACIER_RESTORE phase"""
        mock_s3 = mock.Mock()
        mock_state = mock.Mock(spec=MigrationStateV2)
        mock_s3.list_buckets.return_value = {"Buckets": []}

        scan_all_buckets(mock_s3, mock_state, Event())

        mock_state.set_current_phase.assert_called_once_with(Phase.GLACIER_RESTORE)

    def test_request_all_restores_transitions_to_glacier_wait(self):
        """Test request_all_restores transitions to GLACIER_WAIT phase"""
        mock_s3 = mock.Mock()
        mock_state = mock.Mock(spec=MigrationStateV2)
        mock_state.get_glacier_files_needing_restore.return_value = []

        request_all_restores(mock_s3, mock_state, Event())

        mock_state.set_current_phase.assert_called_once_with(Phase.GLACIER_WAIT)

    def test_wait_for_restores_transitions_to_syncing(self):
        """Test wait_for_restores transitions to SYNCING phase"""
        mock_s3 = mock.Mock()
        mock_state = mock.Mock(spec=MigrationStateV2)
        mock_state.get_files_restoring.return_value = []

        wait_for_restores(mock_s3, mock_state, Event())

        mock_state.set_current_phase.assert_called_once_with(Phase.SYNCING)


class TestInterruptBehavior:
    """Test interrupt behavior with threading.Event"""

    def test_scan_all_buckets_interrupt_event(self):
        """Test scan_all_buckets respects Event interrupt"""
        mock_s3 = mock.Mock()
        mock_state = mock.Mock(spec=MigrationStateV2)
        interrupted = Event()
        interrupted.set()

        mock_s3.list_buckets.return_value = {"Buckets": [{"Name": "bucket1"}]}
        mock_s3.get_paginator.return_value.paginate.return_value = []

        scan_all_buckets(mock_s3, mock_state, interrupted)

        # Should not process any buckets since interrupted
        mock_state.save_bucket_status.assert_not_called()

    def test_request_all_restores_interrupt_event(self):
        """Test request_all_restores respects Event interrupt"""
        mock_s3 = mock.Mock()
        mock_state = mock.Mock(spec=MigrationStateV2)
        interrupted = Event()
        interrupted.set()

        mock_state.get_glacier_files_needing_restore.return_value = [{"bucket": "b", "key": "k", "storage_class": "GLACIER"}]

        request_all_restores(mock_s3, mock_state, interrupted)

        mock_s3.restore_object.assert_not_called()

    def test_wait_for_restores_interrupt_event(self):
        """Test wait_for_restores respects Event interrupt"""
        mock_s3 = mock.Mock()
        mock_state = mock.Mock(spec=MigrationStateV2)
        interrupted = Event()
        interrupted.set()

        wait_for_restores(mock_s3, mock_state, interrupted)

        # When interrupted before loop, still transitions to SYNCING at end
        mock_state.set_current_phase.assert_called_once_with(Phase.SYNCING)


def test_scan_all_buckets_early_exit_on_interrupt():
    """Test early exit on interrupt in bucket loop"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock(spec=MigrationStateV2)
    mock_s3.list_buckets.return_value = {
        "Buckets": [
            {"Name": "bucket1"},
            {"Name": "bucket2"},
            {"Name": "bucket3"},
        ]
    }
    mock_s3.get_paginator.return_value.paginate.return_value = []

    interrupted = Event()
    call_count = 0

    def count_calls(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            interrupted.set()

    mock_state.save_bucket_status.side_effect = count_calls

    scan_all_buckets(mock_s3, mock_state, interrupted)

    # Should only be called once before interrupt
    assert call_count == 1


def test_request_all_restores_early_exit_on_interrupt():
    """Test early exit on interrupt in restore loop"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock(spec=MigrationStateV2)
    mock_state.get_glacier_files_needing_restore.return_value = [
        {"bucket": "bucket1", "key": "file1.txt", "storage_class": "GLACIER"},
        {"bucket": "bucket2", "key": "file2.txt", "storage_class": "GLACIER"},
        {"bucket": "bucket3", "key": "file3.txt", "storage_class": "GLACIER"},
    ]

    interrupted = Event()
    call_count = 0

    def count_calls(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            interrupted.set()

    mock_s3.restore_object.side_effect = count_calls

    request_all_restores(mock_s3, mock_state, interrupted)

    # Should only be called once before interrupt
    assert call_count == 1


def test_wait_for_restores_early_exit_on_interrupt_during_loop():
    """Test early exit on interrupt in waiter loop"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock(spec=MigrationStateV2)

    interrupted = Event()
    interrupted.set()

    wait_for_restores(mock_s3, mock_state, interrupted)

    # When interrupted before loop, still transitions to SYNCING at end
    mock_state.set_current_phase.assert_called_once_with(Phase.SYNCING)


def test_scan_all_buckets_handles_pagination_error():
    """Test that pagination errors propagate"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock(spec=MigrationStateV2)
    mock_s3.list_buckets.return_value = {"Buckets": [{"Name": "test-bucket"}]}
    mock_s3.get_paginator.return_value.paginate.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
        "ListObjectsV2",
    )

    with pytest.raises(ClientError):
        scan_all_buckets(mock_s3, mock_state, Event())


def test_request_all_restores_handles_non_restore_error():
    """Test that non-RestoreAlreadyInProgress errors propagate"""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock(spec=MigrationStateV2)
    mock_state.get_glacier_files_needing_restore.return_value = [{"bucket": "test-bucket", "key": "file.txt", "storage_class": "GLACIER"}]
    error = ClientError(
        {"Error": {"Code": "NoSuchBucket", "Message": "Bucket does not exist"}},
        "RestoreObject",
    )
    mock_s3.restore_object.side_effect = error

    with pytest.raises(ClientError):
        request_all_restores(mock_s3, mock_state, Event())


def test_wait_for_restores_raises_on_head_object_error():
    """Test that head_object errors are raised (fail-fast)."""
    mock_s3 = mock.Mock()
    mock_state = mock.Mock(spec=MigrationStateV2)
    mock_state.get_files_restoring.return_value = [{"bucket": "test-bucket", "key": "file.txt"}]
    mock_s3.head_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey", "Message": "Not found"}}, "HeadObject")

    with mock.patch("migration_scanner._wait_with_interrupt"):
        with pytest.raises(ClientError):
            wait_for_restores(mock_s3, mock_state, Event())
