"""Comprehensive tests for aws_lambda_cleanup.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_test_constants import DEFAULT_TEST_REGIONS
from cost_toolkit.scripts.cleanup.aws_lambda_cleanup import delete_lambda_functions
from tests.conftest_test_values import TEST_LAMBDA_CALL_COUNT


@patch("cost_toolkit.scripts.cleanup.aws_lambda_cleanup.aws_utils.setup_aws_credentials")
def test_delete_lambda_functions_calls_shared_setup(mock_setup):
    """delete_lambda_functions should load credentials before scanning regions."""
    with patch("boto3.client") as mock_client:
        mock_lambda = MagicMock()
        mock_lambda.list_functions.return_value = {"Functions": []}
        mock_client.return_value = mock_lambda
        delete_lambda_functions()
    mock_setup.assert_called_once()


def test_delete_lambda_functions_removes_all(capsys):
    """Test deleting Lambda functions (single and multiple)."""
    with patch("cost_toolkit.scripts.cleanup.aws_lambda_cleanup._WAIT_EVENT"):
        with patch("cost_toolkit.scripts.cleanup.aws_lambda_cleanup.aws_utils.setup_aws_credentials"):
            with patch("boto3.client") as mock_client:
                mock_lambda = MagicMock()
                mock_lambda.list_functions.return_value = {
                    "Functions": [
                        {"FunctionName": "function-1"},
                        {"FunctionName": "function-2"},
                        {"FunctionName": "function-3"},
                    ]
                }
                mock_client.return_value = mock_lambda
                delete_lambda_functions()
    assert mock_lambda.delete_function.call_count == 9
    captured = capsys.readouterr()
    functions_per_region = len(mock_lambda.list_functions.return_value["Functions"])
    expected_total = len(DEFAULT_TEST_REGIONS) * functions_per_region
    assert f"Total Lambda functions deleted: {expected_total}" in captured.out


def test_delete_lambda_functions_handles_empty_account(capsys):
    """Test when no Lambda functions exist."""
    with patch("cost_toolkit.scripts.cleanup.aws_lambda_cleanup.aws_utils.setup_aws_credentials"):
        with patch("boto3.client") as mock_client:
            mock_lambda = MagicMock()
            mock_lambda.list_functions.return_value = {"Functions": []}
            mock_client.return_value = mock_lambda
            delete_lambda_functions()
    captured = capsys.readouterr()
    assert "No Lambda functions found" in captured.out
    assert "No Lambda functions were deleted" in captured.out


def test_delete_lambda_functions_handles_delete_error(capsys):
    """Test handling error when deleting function."""
    with patch("cost_toolkit.scripts.cleanup.aws_lambda_cleanup._WAIT_EVENT"):
        with patch("cost_toolkit.scripts.cleanup.aws_lambda_cleanup.aws_utils.setup_aws_credentials"):
            with patch("boto3.client") as mock_client:
                mock_lambda = MagicMock()
                mock_lambda.list_functions.return_value = {"Functions": [{"FunctionName": "test"}]}
                mock_lambda.delete_function.side_effect = ClientError({"Error": {"Code": "ServiceError"}}, "delete_function")
                mock_client.return_value = mock_lambda
                delete_lambda_functions()
    captured = capsys.readouterr()
    assert "Failed to delete" in captured.out


def test_delete_lambda_functions_handles_listing_error(capsys):
    """Test handling error when listing functions."""
    with patch("cost_toolkit.scripts.cleanup.aws_lambda_cleanup.aws_utils.setup_aws_credentials"):
        with patch("boto3.client") as mock_client:
            mock_lambda = MagicMock()
            mock_lambda.list_functions.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "list_functions")
            mock_client.return_value = mock_lambda
            delete_lambda_functions()
    captured = capsys.readouterr()
    assert "Error accessing Lambda" in captured.out


def test_delete_lambda_functions_iterates_regions(capsys):
    """Test processing multiple regions."""
    with patch("cost_toolkit.scripts.cleanup.aws_lambda_cleanup._WAIT_EVENT"):
        with patch("cost_toolkit.scripts.cleanup.aws_lambda_cleanup.aws_utils.setup_aws_credentials"):
            with patch("boto3.client") as mock_client:
                call_count = 0

                def list_functions_side_effect():
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return {"Functions": [{"FunctionName": "func-us-east-1"}]}
                    if call_count == TEST_LAMBDA_CALL_COUNT:
                        return {"Functions": [{"FunctionName": "func-us-east-2"}]}
                    return {"Functions": [{"FunctionName": "func-us-west-2"}]}

                mock_lambda = MagicMock()
                mock_lambda.list_functions.side_effect = list_functions_side_effect
                mock_client.return_value = mock_lambda
                delete_lambda_functions()
    captured = capsys.readouterr()
    assert "us-east-1" in captured.out
    assert "us-east-2" in captured.out
    assert "us-west-2" in captured.out


def test_delete_lambda_functions_always_prints_summary(capsys):
    """Test that summary is always printed."""
    with patch("cost_toolkit.scripts.cleanup.aws_lambda_cleanup.aws_utils.setup_aws_credentials"):
        with patch("boto3.client") as mock_client:
            mock_lambda = MagicMock()
            mock_lambda.list_functions.return_value = {"Functions": []}
            mock_client.return_value = mock_lambda
            delete_lambda_functions()
    captured = capsys.readouterr()
    assert "Lambda Cleanup Summary" in captured.out
    assert "Total Lambda functions deleted" in captured.out
