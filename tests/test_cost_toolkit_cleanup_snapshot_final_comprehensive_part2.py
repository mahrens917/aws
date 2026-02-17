"""Comprehensive tests for aws_snapshot_cleanup_final.py - Part 2."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final import (
    delete_freed_snapshots,
    main,
    print_cleanup_summary,
    process_snapshot_deletions,
)


class TestProcessSnapshotDeletionsConfiguration:
    """Configuration and multi-region tests for process_snapshot_deletions."""

    def test_process_creates_clients_with_credentials(self):
        """Test that process creates EC2 clients with correct credentials."""
        snapshots = [{"snapshot_id": "snap-1", "region": "us-east-1", "size_gb": 10, "description": "1"}]
        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2
            with patch("cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final._WAIT_EVENT"):
                with patch(
                    "cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final.delete_snapshot",
                    return_value=True,
                ):
                    process_snapshot_deletions(snapshots, "test-key", "test-secret")
            mock_boto3.assert_called_with(
                "ec2",
                region_name="us-east-1",
                aws_access_key_id="test-key",
                aws_secret_access_key="test-secret",
            )

    def test_process_handles_multiple_regions(self):
        """Test processing snapshots from multiple regions."""
        snapshots = [
            {"snapshot_id": "snap-1", "region": "us-east-1", "size_gb": 10, "description": "1"},
            {"snapshot_id": "snap-2", "region": "us-west-2", "size_gb": 20, "description": "2"},
            {"snapshot_id": "snap-3", "region": "eu-west-2", "size_gb": 30, "description": "3"},
        ]
        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2
            with patch("cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final._WAIT_EVENT"):
                with patch(
                    "cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final.delete_snapshot",
                    return_value=True,
                ):
                    process_snapshot_deletions(snapshots, "key", "secret")
            assert mock_boto3.call_count == 3


class TestPrintCleanupSummary:
    """Tests for print_cleanup_summary function."""

    def test_print_summary_all_successful(self, capsys):
        """Test summary with all successful deletions."""
        print_cleanup_summary(3, 0, 15.0)

        captured = capsys.readouterr()
        assert "Successfully deleted: 3 snapshots" in captured.out
        assert "Failed to delete: 0 snapshots" in captured.out
        assert "$15.00" in captured.out
        assert "$180.00" in captured.out
        assert "cleanup completed successfully" in captured.out

    def test_print_summary_with_failures(self, capsys):
        """Test summary with some failures."""
        print_cleanup_summary(2, 1, 10.0)

        captured = capsys.readouterr()
        assert "Successfully deleted: 2 snapshots" in captured.out
        assert "Failed to delete: 1 snapshots" in captured.out
        assert "$10.00" in captured.out

    def test_print_summary_all_failed(self, capsys):
        """Test summary with all deletions failed."""
        print_cleanup_summary(0, 3, 0.0)

        captured = capsys.readouterr()
        assert "Successfully deleted: 0 snapshots" in captured.out
        assert "Failed to delete: 3 snapshots" in captured.out
        assert "No snapshots were successfully deleted" in captured.out
        assert "Try again in a few minutes" in captured.out

    def test_print_summary_includes_verification_command(self, capsys):
        """Test that summary includes verification command."""
        print_cleanup_summary(1, 0, 5.0)

        captured = capsys.readouterr()
        assert "aws_ebs_audit.py" in captured.out


class TestDeleteFreedSnapshots:
    """Tests for delete_freed_snapshots function."""

    def test_delete_with_confirmation(self, capsys):
        """Test deletion with user confirmation."""
        mod = "cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final"
        with (
            patch(f"{mod}.setup_aws_credentials") as mock_creds,
            patch(f"{mod}.confirm_snapshot_deletion") as mock_confirm,
            patch(f"{mod}.process_snapshot_deletions") as mock_process,
        ):
            mock_creds.return_value = ("key", "secret")
            mock_confirm.return_value = True
            mock_process.return_value = (2, 0, 10.0)

            delete_freed_snapshots()

            mock_process.assert_called_once()
            captured = capsys.readouterr()
            assert "Proceeding with freed snapshot deletion" in captured.out

    def test_delete_without_confirmation(self, capsys):
        """Test deletion cancelled by user."""
        mod = "cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final"
        with (
            patch(f"{mod}.setup_aws_credentials") as mock_creds,
            patch(f"{mod}.confirm_snapshot_deletion") as mock_confirm,
            patch(f"{mod}.process_snapshot_deletions") as mock_process,
        ):
            mock_creds.return_value = ("key", "secret")
            mock_confirm.return_value = False

            delete_freed_snapshots()

            mock_process.assert_not_called()
            captured = capsys.readouterr()
            assert "Operation cancelled by user" in captured.out

    def test_delete_passes_credentials(self):
        """Test that credentials are passed to process function."""
        mod = "cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final"
        with (
            patch(f"{mod}.setup_aws_credentials") as mock_creds,
            patch(f"{mod}.confirm_snapshot_deletion") as mock_confirm,
            patch(f"{mod}.process_snapshot_deletions") as mock_process,
        ):
            mock_creds.return_value = ("test-key", "test-secret")
            mock_confirm.return_value = True
            mock_process.return_value = (0, 0, 0.0)

            delete_freed_snapshots()

            args = mock_process.call_args[0]
            assert args[1] == "test-key"
            assert args[2] == "test-secret"


class TestMain:
    """Tests for main function."""

    def test_main_success(self):
        """Test successful main execution."""
        with patch("cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final.delete_freed_snapshots") as mock_delete:
            main()

            mock_delete.assert_called_once()

    def test_main_with_client_error(self, capsys):
        """Test main with client error."""
        with patch("cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final.delete_freed_snapshots") as mock_delete:
            mock_delete.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "operation")

            with patch("sys.exit") as mock_exit:
                main()

                mock_exit.assert_called_once_with(1)
                captured = capsys.readouterr()
                assert "Script failed" in captured.out

    def test_main_without_error(self):
        """Test main completes without error when no exception."""
        with patch("cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final.delete_freed_snapshots"):
            with patch("sys.exit") as mock_exit:
                main()

                mock_exit.assert_not_called()


class TestIntegrationScenarios:
    """Integration tests for common scenarios."""

    def test_full_deletion_workflow(self, capsys):
        """Test complete deletion workflow."""
        with patch("cost_toolkit.common.credential_utils.setup_aws_credentials") as mock_creds:
            with patch("builtins.input", return_value="DELETE FREED SNAPSHOTS"):
                with patch("boto3.client") as mock_boto3:
                    mock_ec2 = MagicMock()
                    mock_boto3.return_value = mock_ec2
                    mock_creds.return_value = ("key", "secret")

                    with patch("cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final._WAIT_EVENT"):
                        delete_freed_snapshots()

            captured = capsys.readouterr()
            assert "AWS Final Snapshot Cleanup Script" in captured.out
            assert "FINAL CLEANUP SUMMARY" in captured.out

    def test_large_snapshot_deletion(self):
        """Test deletion of large snapshot."""
        snapshots = [
            {
                "snapshot_id": "snap-large",
                "region": "eu-west-2",
                "size_gb": 1024,
                "description": "Large snapshot",
            }
        ]

        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2
            with patch("cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final._WAIT_EVENT"):
                with patch(
                    "cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final.delete_snapshot",
                    return_value=True,
                ):
                    successful, _, savings = process_snapshot_deletions(snapshots, "key", "secret")

        assert successful == 1
        assert savings == 51.2

    def test_mixed_success_failure_workflow(self):
        """Test workflow with mixed success and failures."""
        snapshots = [
            {"snapshot_id": "snap-1", "region": "us-east-1", "size_gb": 10, "description": "1"},
            {"snapshot_id": "snap-2", "region": "us-east-1", "size_gb": 20, "description": "2"},
            {"snapshot_id": "snap-3", "region": "us-east-1", "size_gb": 30, "description": "3"},
        ]

        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2
            with patch("cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final._WAIT_EVENT"):
                with patch("cost_toolkit.scripts.cleanup.aws_snapshot_cleanup_final.delete_snapshot") as mock_delete:
                    mock_delete.side_effect = [True, False, True]

                    successful, failed, savings = process_snapshot_deletions(snapshots, "key", "secret")

        assert successful == 2
        assert failed == 1
        assert savings == 2.0
