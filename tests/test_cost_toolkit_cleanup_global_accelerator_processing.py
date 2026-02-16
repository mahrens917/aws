"""Comprehensive tests for aws_global_accelerator_cleanup.py - Processing and integration."""

from __future__ import annotations

from unittest.mock import patch

from cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup import (
    main,
    print_cleanup_summary,
    process_single_accelerator,
)


class TestProcessSingleAccelerator:
    """Tests for process_single_accelerator function."""

    def test_process_accelerator_success(self, capsys):
        """Test successful processing of single accelerator."""
        accelerator = {
            "AcceleratorArn": "arn:aws:accelerator/abc",
            "Name": "test-accelerator",
            "Status": "DEPLOYED",
            "Enabled": True,
        }

        with patch(
            "cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.disable_accelerator",
            return_value=True,
        ):
            with patch(
                "cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.delete_listeners",
                return_value=True,
            ):
                with patch(
                    "cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.delete_accelerator",
                    return_value=True,
                ):
                    success, cost = process_single_accelerator(accelerator)

        assert success is True
        assert cost == 18.0
        captured = capsys.readouterr()
        assert "Successfully deleted" in captured.out

    def test_process_accelerator_disable_fails(self):
        """Test when disabling accelerator fails."""
        accelerator = {
            "AcceleratorArn": "arn:aws:accelerator/abc",
            "Name": "test-accelerator",
            "Status": "DEPLOYED",
            "Enabled": True,
        }

        with patch(
            "cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.disable_accelerator",
            return_value=False,
        ):
            success, cost = process_single_accelerator(accelerator)

        assert success is False
        assert cost == 18.0

    def test_process_accelerator_delete_listeners_fails(self):
        """Test when deleting listeners fails."""
        accelerator = {
            "AcceleratorArn": "arn:aws:accelerator/abc",
            "Name": "test-accelerator",
            "Status": "DEPLOYED",
            "Enabled": True,
        }

        with patch(
            "cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.disable_accelerator",
            return_value=True,
        ):
            with patch(
                "cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.delete_listeners",
                return_value=False,
            ):
                success, _ = process_single_accelerator(accelerator)

        assert success is False

    def test_process_accelerator_unnamed(self, capsys):
        """Test processing accelerator without name."""
        accelerator = {
            "AcceleratorArn": "arn:aws:accelerator/abc",
            "Status": "DEPLOYED",
            "Enabled": False,
        }

        with patch(
            "cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.disable_accelerator",
            return_value=True,
        ):
            with patch(
                "cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.delete_listeners",
                return_value=True,
            ):
                with patch(
                    "cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.delete_accelerator",
                    return_value=True,
                ):
                    _, _ = process_single_accelerator(accelerator)

        captured = capsys.readouterr()
        assert "Processing Accelerator: None" in captured.out


class TestPrintCleanupSummary:
    """Tests for print_cleanup_summary function."""

    def test_print_summary_with_deletions(self, capsys):
        """Test summary with successful deletions."""
        print_cleanup_summary(5, 4, 72.0)

        captured = capsys.readouterr()
        assert "CLEANUP SUMMARY" in captured.out
        assert "Total accelerators processed: 5" in captured.out
        assert "Successfully deleted: 4" in captured.out
        assert "$72.00" in captured.out
        assert "IMPORTANT NOTES" in captured.out

    def test_print_summary_no_deletions(self, capsys):
        """Test summary with no deletions."""
        print_cleanup_summary(2, 0, 0.0)

        captured = capsys.readouterr()
        assert "CLEANUP SUMMARY" in captured.out
        assert "No accelerators were successfully deleted" in captured.out

    def test_print_summary_partial_success(self, capsys):
        """Test summary with partial success."""
        print_cleanup_summary(3, 2, 36.0)

        captured = capsys.readouterr()
        assert "Total accelerators processed: 3" in captured.out
        assert "Successfully deleted: 2" in captured.out
        assert "$36.00" in captured.out


class TestMain:
    """Tests for main function."""

    def test_main_cancelled_by_user(self, capsys):
        """Test main function when user cancels."""
        with patch("builtins.input", return_value="NO"):
            main()

        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "cancelled" in captured.out

    def test_main_no_accelerators(self, capsys):
        """Test main when no accelerators found."""
        with patch("builtins.input", return_value="DELETE"):
            with patch("cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.setup_aws_credentials"):
                with patch(
                    "cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.list_accelerators",
                    return_value=[],
                ):
                    main()

        captured = capsys.readouterr()
        assert "No Global Accelerators found" in captured.out

    def test_main_with_accelerators(self, capsys):
        """Test main with accelerators to delete."""
        accelerator = {
            "AcceleratorArn": "arn:test",
            "Name": "test",
            "Status": "DEPLOYED",
            "Enabled": True,
        }

        with patch("builtins.input", return_value="DELETE"):
            with patch("cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.setup_aws_credentials"):
                with patch(
                    "cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.list_accelerators",
                    return_value=[accelerator],
                ):
                    with patch(
                        "cost_toolkit.scripts.cleanup.aws_global_accelerator_cleanup.process_single_accelerator",
                        return_value=(True, 18.0),
                    ):
                        main()

        captured = capsys.readouterr()
        assert "CLEANUP SUMMARY" in captured.out
