"""Comprehensive tests for aws_snapshot_cleanup_final.py - Part 1."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cost_toolkit.common.confirmation_prompts import confirm_snapshot_deletion
from cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final import (
    get_snapshots_to_delete,
    print_deletion_warning,
    process_snapshot_deletions,
)


class TestGetSnapshotsToDelete:
    """Tests for get_snapshots_to_delete function."""

    def test_get_snapshots_returns_list(self):
        """Test that function returns list of snapshots."""
        result = get_snapshots_to_delete()

        assert isinstance(result, list)
        assert len(result) > 0
        for snapshot in result:
            assert "snapshot_id" in snapshot
            assert "region" in snapshot
            assert "size_gb" in snapshot
            assert "description" in snapshot

    def test_get_snapshots_has_expected_snapshots(self):
        """Test that function returns expected snapshots."""
        result = get_snapshots_to_delete()

        snapshot_ids = [s["snapshot_id"] for s in result]
        assert "snap-09e90c64db692f884" in snapshot_ids
        assert "snap-07c0d4017e24b3240" in snapshot_ids

    def test_get_snapshots_regions(self):
        """Test that snapshots have valid regions."""
        result = get_snapshots_to_delete()

        regions = {s["region"] for s in result}
        assert "us-east-1" in regions
        assert "us-east-2" in regions
        assert "eu-west-2" in regions


class TestPrintDeletionWarning:
    """Tests for print_deletion_warning function."""

    def test_print_warning_with_snapshots(self, capsys):
        """Test printing warning with snapshots."""
        snapshots = [
            {
                "snapshot_id": "snap-1",
                "region": "us-east-1",
                "size_gb": 100,
                "description": "Test snapshot 1",
            },
            {
                "snapshot_id": "snap-2",
                "region": "us-west-2",
                "size_gb": 50,
                "description": "Test snapshot 2",
            },
        ]

        print_deletion_warning(snapshots)

        captured = capsys.readouterr()
        assert "AWS Final Snapshot Cleanup Script" in captured.out
        assert "2 freed snapshots" in captured.out
        assert "FINAL WARNING" in captured.out
        assert "$7.50" in captured.out

    def test_print_warning_calculates_savings(self, capsys):
        """Test that warning calculates total savings correctly."""
        snapshots = [
            {"snapshot_id": "snap-1", "region": "us-east-1", "size_gb": 100},
            {"snapshot_id": "snap-2", "region": "us-east-1", "size_gb": 200},
        ]

        print_deletion_warning(snapshots)

        captured = capsys.readouterr()
        assert "$15.00" in captured.out

    def test_print_warning_empty_list(self, capsys):
        """Test warning with empty snapshot list."""
        print_deletion_warning([])

        captured = capsys.readouterr()
        assert "0 freed snapshots" in captured.out
        assert "$0.00" in captured.out


class TestConfirmSnapshotDeletion:
    """Tests for confirm_snapshot_deletion function."""

    def test_confirm_with_correct_input(self):
        """Test confirmation with correct input."""
        with patch("builtins.input", return_value="DELETE FREED SNAPSHOTS"):
            result = confirm_snapshot_deletion()

            assert result is True

    def test_confirm_with_wrong_input(self):
        """Test confirmation with wrong input."""
        with patch("builtins.input", return_value="delete"):
            result = confirm_snapshot_deletion()

            assert result is False

    def test_confirm_with_partial_match(self):
        """Test confirmation with partial match."""
        with patch("builtins.input", return_value="DELETE FREED"):
            result = confirm_snapshot_deletion()

            assert result is False

    def test_confirm_with_case_sensitive(self):
        """Test that confirmation is case-sensitive."""
        with patch("builtins.input", return_value="delete freed snapshots"):
            result = confirm_snapshot_deletion()

            assert result is False


class TestProcessSnapshotDeletions:
    """Tests for process_snapshot_deletions function."""

    def test_process_all_successful(self, capsys):
        """Test processing with all deletions successful."""
        snapshots = [
            {
                "snapshot_id": "snap-1",
                "region": "us-east-1",
                "size_gb": 100,
                "description": "Test 1",
            },
            {
                "snapshot_id": "snap-2",
                "region": "us-west-2",
                "size_gb": 50,
                "description": "Test 2",
            },
        ]
        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2
            with patch("cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final._WAIT_EVENT"):
                with patch(
                    "cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final.delete_snapshot",
                    return_value=True,
                ):
                    successful, failed, savings = process_snapshot_deletions(snapshots, "key", "secret")
        assert successful == 2
        assert failed == 0
        assert savings == 7.5
        captured = capsys.readouterr()
        assert "Processing snap-1" in captured.out
        assert "100 GB" in captured.out

    def test_process_with_failures(self):
        """Test processing with some failures."""
        snapshots = [
            {"snapshot_id": "snap-1", "region": "us-east-1", "size_gb": 100, "description": "1"},
            {"snapshot_id": "snap-2", "region": "us-east-1", "size_gb": 50, "description": "2"},
        ]
        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2
            with patch("cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final._WAIT_EVENT"):
                with patch("cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final.delete_snapshot") as mock_delete:
                    mock_delete.side_effect = [True, False]
                    successful, failed, savings = process_snapshot_deletions(snapshots, "key", "secret")
        assert successful == 1
        assert failed == 1
        assert savings == 5.0

    def test_process_empty_list(self):
        """Test processing empty snapshot list."""
        successful, failed, savings = process_snapshot_deletions([], "key", "secret")
        assert successful == 0
        assert failed == 0
        assert savings == 0
