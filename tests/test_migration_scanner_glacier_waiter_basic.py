"""Unit tests for glacier waiter functions - Basic operations"""

from threading import Event
from unittest import mock

from migration_scanner import check_restore_status, wait_for_restores
from migration_state_v2 import Phase
from tests.assertions import assert_equal


class TestGlacierWaiterBasicWaiting:
    """Test glacier waiter basic waiting operations"""

    def test_wait_for_restores_no_restoring_files(self, s3_mock, state_mock, capsys):
        """Test when no files are restoring"""
        state_mock.get_files_restoring.return_value = []

        wait_for_restores(s3_mock, state_mock, Event())

        output = capsys.readouterr().out
        assert "PHASE 3/4: WAITING FOR GLACIER RESTORES" in output
        assert "PHASE 3 COMPLETE" in output
        state_mock.set_current_phase.assert_called_once_with(Phase.SYNCING)

    def test_wait_for_restores_with_wait_interval(self, s3_mock, state_mock):
        """Test that wait_for_restores waits between checks"""
        state_mock.get_files_restoring.side_effect = [
            [{"bucket": "test-bucket", "key": "file.txt"}],
            [],  # Next check shows no files
        ]

        s3_mock.head_object.return_value = {"Restore": 'ongoing-request="true"'}

        with mock.patch("migration_scanner._wait_with_interrupt") as mock_wait:
            wait_for_restores(s3_mock, state_mock, Event())

            # Should wait 300 seconds (5 minutes) after first check
            mock_wait.assert_called_once()
            assert mock_wait.call_args[0][1] == 300


class TestGlacierWaiterInterruption:
    """Test glacier waiter interruption handling"""

    def test_wait_for_restores_respects_interrupt(self, state_mock):
        """Test that wait_for_restores stops on interrupt"""
        # When interrupted flag is set before entering, loop exits immediately
        interrupted = Event()
        interrupted.set()
        wait_for_restores(mock.Mock(), state_mock, interrupted)

        # Should still transition to SYNCING phase after loop exits
        state_mock.set_current_phase.assert_called_once_with(Phase.SYNCING)

    def test_wait_for_restores_stops_on_interrupt_during_check(self, s3_mock, state_mock):
        """Test interrupt during restore status check"""
        state_mock.get_files_restoring.return_value = [
            {"bucket": "test-bucket", "key": "file1.txt"},
            {"bucket": "test-bucket", "key": "file2.txt"},
        ]

        interrupted = Event()

        def interrupt_on_first_check(*_args, **_kwargs):
            interrupted.set()
            return {"Restore": 'ongoing-request="true"'}

        s3_mock.head_object.side_effect = interrupt_on_first_check

        wait_for_restores(s3_mock, state_mock, interrupted)

        # Should only check first file before interrupt
        assert s3_mock.head_object.call_count == 1


def test_wait_for_restores_loops_until_complete(s3_mock, state_mock):
    """Test that wait_for_restores loops multiple times"""
    s3_mock.head_object.return_value = {"Restore": 'ongoing-request="true"'}

    # Simulate 2 check cycles
    state_mock.get_files_restoring.side_effect = [
        [{"bucket": "test-bucket", "key": "file.txt"}],
        [{"bucket": "test-bucket", "key": "file.txt"}],
        [],  # All done
    ]

    with mock.patch("migration_scanner._wait_with_interrupt"):
        wait_for_restores(s3_mock, state_mock, Event())

    # Should call get_files_restoring 3 times
    assert_equal(state_mock.get_files_restoring.call_count, 3)
