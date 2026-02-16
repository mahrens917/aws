"""Comprehensive tests for aws_kms_audit.py - Part 1."""

from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from cost_toolkit.scripts.audit.aws_kms_audit import (
    _print_key_aliases,
    _print_key_grants,
    _print_key_info,
    _process_kms_key,
)
from tests.kms_test_utils import build_kms_client


class TestPrintKeyInfo:
    """Tests for _print_key_info function."""

    def test_print_key_info_enabled(self, capsys):
        """Test printing info for enabled key."""
        key_info = {
            "Description": "Test key",
            "KeyManager": "CUSTOMER",
            "KeyState": "Enabled",
            "CreationDate": "2024-01-01",
        }

        cost = _print_key_info(key_info)

        assert cost == 1
        captured = capsys.readouterr()
        assert "Test key" in captured.out
        assert "CUSTOMER" in captured.out
        assert "Enabled" in captured.out
        assert "$1.00/month" in captured.out

    def test_print_key_info_disabled(self, capsys):
        """Test printing info for disabled key."""
        key_info = {
            "Description": "Disabled key",
            "KeyManager": "CUSTOMER",
            "KeyState": "Disabled",
            "CreationDate": "2024-01-01",
        }

        cost = _print_key_info(key_info)

        assert cost == 1
        captured = capsys.readouterr()
        assert "Disabled" in captured.out

    def test_print_key_info_pending_deletion(self, capsys):
        """Test printing info for key pending deletion."""
        key_info = {
            "Description": "Deleting key",
            "KeyManager": "CUSTOMER",
            "KeyState": "PendingDeletion",
            "CreationDate": "2024-01-01",
        }

        cost = _print_key_info(key_info)

        assert cost == 0
        captured = capsys.readouterr()
        assert "PendingDeletion" in captured.out

    def test_print_key_info_no_description(self, capsys):
        """Test printing info for key without description."""
        key_info = {
            "KeyManager": "AWS",
            "KeyState": "Enabled",
            "CreationDate": "2024-01-01",
        }

        _print_key_info(key_info)

        captured = capsys.readouterr()
        assert "Description: None" in captured.out


class TestPrintKeyAliases:
    """Tests for _print_key_aliases function."""

    def test_print_aliases_with_aliases(self, capsys):
        """Test printing aliases when they exist."""
        mock_kms = MagicMock()
        mock_kms.list_aliases.return_value = {
            "Aliases": [
                {"AliasName": "alias/test-key"},
                {"AliasName": "alias/another-key"},
            ]
        }

        _print_key_aliases(mock_kms, "key-123")

        captured = capsys.readouterr()
        assert "alias/test-key" in captured.out
        assert "alias/another-key" in captured.out

    def test_print_aliases_no_aliases(self, capsys):
        """Test printing aliases when none exist."""
        mock_kms = MagicMock()
        mock_kms.list_aliases.return_value = {"Aliases": []}

        _print_key_aliases(mock_kms, "key-123")

        captured = capsys.readouterr()
        assert "Aliases:" not in captured.out

    def test_print_aliases_error(self, capsys):
        """Test error handling when listing aliases shows error message."""
        mock_kms = MagicMock()
        mock_kms.list_aliases.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "list_aliases")

        _print_key_aliases(mock_kms, "key-123")

        captured = capsys.readouterr()
        assert "unable to retrieve: AccessDenied" in captured.out


class TestPrintKeyGrants:
    """Tests for _print_key_grants function."""

    def test_print_grants_with_grants(self, capsys):
        """Test printing grants when they exist."""
        mock_kms = MagicMock()
        mock_kms.list_grants.return_value = {
            "Grants": [
                {
                    "GranteePrincipal": "arn:aws:iam::123:user/test",
                    "Operations": ["Encrypt", "Decrypt"],
                },
                {
                    "GranteePrincipal": "arn:aws:iam::123:role/service",
                    "Operations": ["GenerateDataKey"],
                },
            ]
        }

        _print_key_grants(mock_kms, "key-123")

        captured = capsys.readouterr()
        assert "Active Grants: 2" in captured.out
        assert "arn:aws:iam::123:user/test" in captured.out
        assert "Encrypt" in captured.out

    def test_print_grants_no_grants(self, capsys):
        """Test printing grants when none exist."""
        mock_kms = MagicMock()
        mock_kms.list_grants.return_value = {"Grants": []}

        _print_key_grants(mock_kms, "key-123")

        captured = capsys.readouterr()
        assert "Active Grants:" not in captured.out


class TestPrintKeyGrantsPart2:
    """Tests for _print_key_grants function - Part 2."""

    def test_print_grants_error(self, capsys):
        """Test error handling when listing grants."""
        mock_kms = MagicMock()
        mock_kms.list_grants.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "list_grants")

        _print_key_grants(mock_kms, "key-123")

        captured = capsys.readouterr()
        assert "Active Grants:" not in captured.out

    def test_print_grants_many_grants(self, capsys):
        """Test printing only first 3 grants when many exist."""
        mock_kms = MagicMock()
        mock_kms.list_grants.return_value = {
            "Grants": [{"GranteePrincipal": f"principal-{i}", "Operations": ["Encrypt"]} for i in range(10)]
        }

        _print_key_grants(mock_kms, "key-123")

        captured = capsys.readouterr()
        assert "Active Grants: 10" in captured.out
        assert "principal-0" in captured.out
        assert "principal-1" in captured.out
        assert "principal-2" in captured.out


class TestProcessKmsKey:
    """Tests for _process_kms_key function."""

    def test_process_customer_managed_key(self, capsys):
        """Test processing customer-managed key."""
        mock_kms = build_kms_client()

        cost, is_customer = _process_kms_key(mock_kms, "key-123")

        assert cost == 1
        assert is_customer is True
        captured = capsys.readouterr()
        assert "Key ID: key-123" in captured.out

    def test_process_aws_managed_key(self):
        """Test processing AWS-managed key."""
        mock_kms = build_kms_client(manager="AWS")

        cost, is_customer = _process_kms_key(mock_kms, "key-123")

        assert cost == 0
        assert is_customer is False


class TestProcessKmsKeyPart2:
    """Tests for _process_kms_key function - Part 2."""

    def test_process_key_access_denied(self, capsys):
        """Test processing key with access denied."""
        mock_kms = MagicMock()
        mock_kms.describe_key.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "describe_key")

        cost, is_customer = _process_kms_key(mock_kms, "key-123")

        assert cost == 0
        assert is_customer is False
        captured = capsys.readouterr()
        assert "Error accessing key" not in captured.out

    def test_process_key_other_error(self, capsys):
        """Test processing key with other errors."""
        mock_kms = MagicMock()
        mock_kms.describe_key.side_effect = ClientError({"Error": {"Code": "InternalError"}}, "describe_key")

        cost, is_customer = _process_kms_key(mock_kms, "key-123")

        assert cost == 0
        assert is_customer is False
        captured = capsys.readouterr()
        assert "Error accessing key" in captured.out
