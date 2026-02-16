"""Unit tests for show_migration_status function from migration_orchestrator.py

Tests cover:
- Status display for all migration phases (scanning, glacier_restore, syncing, complete)
- Overall summary and bucket progress reporting
- Individual bucket details display
"""

from unittest import mock

from migration_orchestrator import show_migration_status
from migration_state_v2 import Phase


def test_show_status_scanning_phase():
    """Test show_migration_status for SCANNING phase"""
    state_mock = mock.Mock()
    state_mock.get_current_phase.return_value = Phase.SCANNING
    state_mock.get_all_buckets.return_value = []
    state_mock.get_scan_summary.return_value = {
        "bucket_count": 0,
        "total_files": 0,
        "total_size": 0,
    }

    with mock.patch("builtins.print") as mock_print:
        show_migration_status(state_mock)

    printed_text = " ".join([str(call) for call in mock_print.call_args_list])
    assert "MIGRATION STATUS" in printed_text
    assert "scanning" in printed_text.lower()


def test_show_status_no_buckets():
    """Test show_migration_status when no buckets exist"""
    state_mock = mock.Mock()
    state_mock.get_current_phase.return_value = Phase.SCANNING
    state_mock.get_all_buckets.return_value = []
    state_mock.get_scan_summary.return_value = {
        "bucket_count": 0,
        "total_files": 0,
        "total_size": 0,
    }

    with mock.patch("builtins.print") as mock_print:
        show_migration_status(state_mock)

    printed_text = " ".join([str(call) for call in mock_print.call_args_list])
    assert "MIGRATION STATUS" in printed_text


def test_show_status_glacier_restore_phase_shows_summary():
    """Test show_migration_status for GLACIER_RESTORE phase shows scan summary"""
    state_mock = mock.Mock()
    state_mock.get_current_phase.return_value = Phase.GLACIER_RESTORE
    state_mock.get_all_buckets.return_value = ["bucket-1", "bucket-2"]
    state_mock.get_scan_summary.return_value = {
        "bucket_count": 2,
        "total_files": 1000,
        "total_size": 10737418240,
    }
    state_mock.get_completed_buckets_for_phase.return_value = []

    bucket_infos = [
        mock.Mock(
            file_count=500,
            total_size=5368709120,
            sync_complete=False,
            verify_complete=False,
            delete_complete=False,
        ),
        mock.Mock(
            file_count=500,
            total_size=5368709120,
            sync_complete=False,
            verify_complete=False,
            delete_complete=False,
        ),
    ]
    state_mock.get_bucket_status.side_effect = bucket_infos

    with mock.patch("builtins.print") as mock_print:
        show_migration_status(state_mock)

    printed_text = " ".join([str(call) for call in mock_print.call_args_list])
    assert "Overall Summary" in printed_text
    assert "Total Buckets: 2" in printed_text
    assert "Total Files: 1,000" in printed_text


def test_show_status_shows_bucket_progress():
    """Test show_migration_status displays bucket progress"""
    state_mock = mock.Mock()
    state_mock.get_current_phase.return_value = Phase.SYNCING
    state_mock.get_all_buckets.return_value = ["bucket-1", "bucket-2", "bucket-3"]
    state_mock.get_scan_summary.return_value = {
        "bucket_count": 3,
        "total_files": 1500,
        "total_size": 15000000000,
    }
    state_mock.get_completed_buckets_for_phase.return_value = ["bucket-1"]

    bucket_infos = [
        mock.Mock(
            file_count=500,
            total_size=5000000000,
            sync_complete=True,
            verify_complete=True,
            delete_complete=True,
        ),
        mock.Mock(
            file_count=500,
            total_size=5000000000,
            sync_complete=False,
            verify_complete=False,
            delete_complete=False,
        ),
        mock.Mock(
            file_count=500,
            total_size=5000000000,
            sync_complete=False,
            verify_complete=False,
            delete_complete=False,
        ),
    ]
    state_mock.get_bucket_status.side_effect = bucket_infos

    with mock.patch("builtins.print") as mock_print:
        show_migration_status(state_mock)

    printed_text = " ".join([str(call) for call in mock_print.call_args_list])
    assert "Bucket Progress" in printed_text
    assert "Completed: 1/3" in printed_text


def test_show_status_displays_bucket_details():
    """Test show_migration_status shows individual bucket details"""
    state_mock = mock.Mock()
    state_mock.get_current_phase.return_value = Phase.SYNCING
    state_mock.get_all_buckets.return_value = ["bucket-1"]
    state_mock.get_scan_summary.return_value = {
        "bucket_count": 1,
        "total_files": 100,
        "total_size": 1000000,
    }
    state_mock.get_completed_buckets_for_phase.return_value = []

    state_mock.get_bucket_status.return_value = mock.Mock(
        file_count=100,
        total_size=1000000,
        sync_complete=True,
        verify_complete=False,
        delete_complete=False,
    )

    with mock.patch("builtins.print") as mock_print:
        show_migration_status(state_mock)

    printed_text = " ".join([str(call) for call in mock_print.call_args_list])
    assert "bucket-1" in printed_text
    assert "100" in printed_text


def test_show_status_complete_phase():
    """Test show_migration_status for COMPLETE phase"""
    state_mock = mock.Mock()
    state_mock.get_current_phase.return_value = Phase.COMPLETE
    state_mock.get_all_buckets.return_value = ["bucket-1"]
    state_mock.get_scan_summary.return_value = {
        "bucket_count": 1,
        "total_files": 100,
        "total_size": 1000000,
    }
    state_mock.get_completed_buckets_for_phase.return_value = ["bucket-1"]
    state_mock.get_bucket_status.return_value = mock.Mock(
        file_count=100,
        total_size=1000000,
        sync_complete=True,
        verify_complete=True,
        delete_complete=True,
    )

    with mock.patch("builtins.print") as mock_print:
        show_migration_status(state_mock)

    printed_text = " ".join([str(call) for call in mock_print.call_args_list])
    assert "MIGRATION STATUS" in printed_text
