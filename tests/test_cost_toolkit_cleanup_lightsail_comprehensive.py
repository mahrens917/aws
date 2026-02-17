"""Comprehensive tests for aws_lightsail_cleanup.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.scripts.cleanup.aws_lightsail_cleanup import (
    UnknownBundleError,
    _delete_database,
    _delete_instance,
    _print_summary,
    _process_region,
    delete_lightsail_instances,
    estimate_database_cost,
    estimate_instance_cost,
    main,
    record_cleanup_action,
)
from tests.lightsail_test_utils import build_empty_lightsail_client, build_lightsail_client


class TestDeleteInstance:
    """Tests for _delete_instance function."""

    def test_delete_instance_success(self):
        """Test successful instance deletion."""
        mock_client = MagicMock()
        instance = {
            "name": "test-instance",
            "state": {"name": "running"},
            "bundleId": "nano_2_0",
        }

        with patch("cost_toolkit.scripts.cleanup.aws_lightsail_cleanup._WAIT_EVENT"):
            with patch(
                "cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.estimate_instance_cost",
                return_value=5.0,
            ):
                deleted, cost = _delete_instance(mock_client, instance)

        assert deleted == 1
        assert cost == 5.0
        mock_client.delete_instance.assert_called_once_with(instanceName="test-instance", forceDeleteAddOns=True)

    def test_delete_instance_error(self):
        """Test instance deletion with error."""
        mock_client = MagicMock()
        mock_client.delete_instance.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "delete_instance")
        instance = {
            "name": "test-instance",
            "state": {"name": "running"},
            "bundleId": "nano_2_0",
        }

        with patch(
            "cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.estimate_instance_cost",
            return_value=5.0,
        ):
            deleted, cost = _delete_instance(mock_client, instance)

        assert deleted == 0
        assert cost == 0.0

    def test_delete_instance_no_bundle(self):
        """Test instance deletion when bundle ID is missing."""
        mock_client = MagicMock()
        instance = {
            "name": "test-instance",
            "state": {"name": "stopped"},
        }

        with patch("cost_toolkit.scripts.cleanup.aws_lightsail_cleanup._WAIT_EVENT"):
            with patch(
                "cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.estimate_instance_cost",
                return_value=0.0,
            ):
                deleted, _ = _delete_instance(mock_client, instance)

        assert deleted == 1


class TestDeleteDatabase:
    """Tests for _delete_database function."""

    def test_delete_database_success(self):
        """Test successful database deletion."""
        mock_client = MagicMock()
        database = {
            "name": "test-db",
            "state": "available",
            "relationalDatabaseBundleId": "micro_1_0",
        }

        with patch("cost_toolkit.scripts.cleanup.aws_lightsail_cleanup._WAIT_EVENT"):
            with patch(
                "cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.estimate_database_cost",
                return_value=15.0,
            ):
                deleted, cost = _delete_database(mock_client, database)

        assert deleted == 1
        assert cost == 15.0
        mock_client.delete_relational_database.assert_called_once_with(relationalDatabaseName="test-db", skipFinalSnapshot=True)

    def test_delete_database_error(self):
        """Test database deletion with error."""
        mock_client = MagicMock()
        mock_client.delete_relational_database.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "delete_relational_database")
        database = {
            "name": "test-db",
            "state": "available",
            "relationalDatabaseBundleId": "micro_1_0",
        }

        with patch(
            "cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.estimate_database_cost",
            return_value=15.0,
        ):
            deleted, cost = _delete_database(mock_client, database)

        assert deleted == 0
        assert cost == 0.0


class TestProcessRegion:
    """Tests for _process_region function."""

    def test_process_region_with_resources(self):
        """Test processing region with instances and databases."""
        with patch("boto3.client") as mock_client:
            mock_client.return_value = build_lightsail_client()

            with patch(
                "cost_toolkit.scripts.cleanup.aws_lightsail_cleanup._delete_instance",
                return_value=(1, 5.0),
            ):
                with patch(
                    "cost_toolkit.scripts.cleanup.aws_lightsail_cleanup._delete_database",
                    return_value=(1, 15.0),
                ):
                    instances, databases, savings = _process_region("us-east-1")

        assert instances == 1
        assert databases == 1
        assert savings == 20.0

    def test_process_region_no_resources(self):
        """Test processing region with no resources."""
        with patch("boto3.client") as mock_client:
            mock_client.return_value = build_empty_lightsail_client()

            instances, databases, savings = _process_region("us-east-1")

        assert instances == 0
        assert databases == 0
        assert savings == 0.0

    def test_process_region_not_available(self):
        """Test processing region where Lightsail is not available."""
        with patch("boto3.client") as mock_client:
            mock_ls = MagicMock()
            mock_ls.get_instances.side_effect = ClientError({"Error": {"Code": "InvalidAction"}}, "get_instances")
            mock_client.return_value = mock_ls

            instances, databases, savings = _process_region("us-east-1")

        assert instances == 0
        assert databases == 0
        assert savings == 0.0


class TestPrintSummary:
    """Tests for _print_summary function."""

    def test_print_summary_with_deletions(self, capsys):
        """Test summary printing with deletions."""
        _print_summary(5, 3, 100.50)

        captured = capsys.readouterr()
        assert "LIGHTSAIL CLEANUP COMPLETED" in captured.out
        assert "Instances deleted: 5" in captured.out
        assert "Databases deleted: 3" in captured.out
        assert "$100.50" in captured.out
        assert "IMPORTANT NOTES" in captured.out

    def test_print_summary_no_deletions(self, capsys):
        """Test summary printing with no deletions."""
        _print_summary(0, 0, 0.0)

        captured = capsys.readouterr()
        assert "LIGHTSAIL CLEANUP COMPLETED" in captured.out
        assert "Instances deleted: 0" in captured.out
        assert "IMPORTANT NOTES" not in captured.out


def test_delete_lightsail_instances_delete_lightsail_instances_success(capsys):
    """Test full Lightsail deletion workflow."""
    with patch("cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.setup_aws_credentials"):
        with patch(
            "cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.get_all_aws_regions",
            return_value=["us-east-1"],
        ):
            with patch(
                "cost_toolkit.scripts.cleanup.aws_lightsail_cleanup._process_region",
                return_value=(2, 1, 30.0),
            ):
                with patch("cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.record_cleanup_action"):
                    delete_lightsail_instances()

    captured = capsys.readouterr()
    assert "LIGHTSAIL INSTANCE CLEANUP" in captured.out
    assert "WARNING" in captured.out


class TestEstimateCosts:
    """Tests for cost estimation functions."""

    def test_estimate_instance_cost_known_bundle(self):
        """Test cost estimation for known instance bundle."""
        cost = estimate_instance_cost("nano_2_0")
        assert cost == 3.50

        cost = estimate_instance_cost("small_2_0")
        assert cost == 10.00

        cost = estimate_instance_cost("xlarge_2_0")
        assert cost == 80.00

    def test_estimate_instance_cost_unknown_bundle_raises(self):
        """Test cost estimation raises UnknownBundleError for unknown instance bundle."""
        with pytest.raises(UnknownBundleError) as exc_info:
            estimate_instance_cost("unknown_bundle")

        assert "unknown_bundle" in str(exc_info.value)

    def test_estimate_database_cost_known_bundle(self):
        """Test cost estimation for known database bundle."""
        cost = estimate_database_cost("micro_1_0")
        assert cost == 15.00

        cost = estimate_database_cost("large_1_0")
        assert cost == 115.00

    def test_estimate_database_cost_unknown_bundle_raises(self):
        """Test cost estimation raises UnknownBundleError for unknown database bundle."""
        with pytest.raises(UnknownBundleError) as exc_info:
            estimate_database_cost("unknown_bundle")

        assert "unknown_bundle" in str(exc_info.value)


class TestRecordCleanupAction:
    """Tests for record_cleanup_action function."""

    def test_record_cleanup_action_new_log(self, tmp_path):
        """Test recording cleanup action when log file doesn't exist."""
        test_dir = tmp_path / "cost_toolkit" / "scripts" / "config"
        test_dir.mkdir(parents=True, exist_ok=True)
        log_file = test_dir / "cleanup_log.json"

        with patch("os.path.dirname", return_value=str(test_dir.parent)):
            with patch("os.path.join", return_value=str(log_file)):
                record_cleanup_action("lightsail", 5, 150.50)

        assert log_file.exists()
        with open(log_file, encoding="utf-8") as f:
            data = json.load(f)

        assert "cleanup_actions" in data
        assert len(data["cleanup_actions"]) == 1
        assert data["cleanup_actions"][0]["service"] == "lightsail"
        assert data["cleanup_actions"][0]["resources_deleted"] == 5
        assert data["cleanup_actions"][0]["estimated_monthly_savings"] == 150.50

    def test_record_cleanup_action_existing_log(self, tmp_path):
        """Test recording cleanup action when log file already exists."""
        test_dir = tmp_path / "cost_toolkit" / "scripts" / "config"
        test_dir.mkdir(parents=True, exist_ok=True)
        log_file = test_dir / "cleanup_log.json"

        existing_data = {"cleanup_actions": [{"service": "ec2", "resources_deleted": 3}]}
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(existing_data, f)

        with patch("os.path.dirname", return_value=str(test_dir.parent)):
            with patch("os.path.join", return_value=str(log_file)):
                record_cleanup_action("lightsail", 2, 50.0)

        with open(log_file, encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["cleanup_actions"]) == 2

    def test_record_cleanup_action_error_handling(self, capsys):
        """Test error handling during cleanup action recording."""
        with patch("builtins.open", side_effect=ClientError({"Error": {"Code": "AccessDenied"}}, "open")):
            record_cleanup_action("lightsail", 1, 10.0)

        captured = capsys.readouterr()
        assert "Could not record cleanup action" in captured.out


def test_process_region_other_client_error(capsys):
    """Test process_region with generic client error."""
    with patch("boto3.client") as mock_client:
        mock_ls = MagicMock()
        mock_ls.get_instances.side_effect = ClientError(
            {"Error": {"Code": "UnauthorizedOperation", "Message": "Unauthorized"}},
            "get_instances",
        )
        mock_client.return_value = mock_ls

        with pytest.raises(ClientError):
            _process_region("us-west-2")

    captured = capsys.readouterr()
    assert "Error accessing Lightsail" in captured.out


def test_main_function_user_confirms_deletion(capsys, monkeypatch):
    """Test main function when user confirms deletion."""
    monkeypatch.setattr("builtins.input", lambda _: "DELETE")

    with patch("cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.setup_aws_credentials"):
        with patch(
            "cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.delete_lightsail_instances",
            return_value=(3, 2, 75.0),
        ):
            main()

    captured = capsys.readouterr()
    assert "AWS Lightsail Complete Cleanup" in captured.out
    assert "Cleanup completed" in captured.out
    assert "$75.00" in captured.out


def test_main_function_user_cancels(capsys, monkeypatch):
    """Test main function when user cancels deletion."""
    monkeypatch.setattr("builtins.input", lambda _: "NO")

    with patch("cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.setup_aws_credentials"):
        main()

    captured = capsys.readouterr()
    assert "Cleanup cancelled" in captured.out


def test_main_function_no_resources_found(capsys, monkeypatch):
    """Test main function when no resources are found."""
    monkeypatch.setattr("builtins.input", lambda _: "DELETE")

    with patch("cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.setup_aws_credentials"):
        with patch(
            "cost_toolkit.scripts.cleanup.aws_lightsail_cleanup.delete_lightsail_instances",
            return_value=(0, 0, 0.0),
        ):
            main()

    captured = capsys.readouterr()
    assert "No Lightsail resources found" in captured.out
