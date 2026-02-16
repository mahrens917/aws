"""Tests for cost_toolkit/scripts/audit/aws_route53_domain_ownership.py - Part 1"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.audit.aws_route53_domain_ownership import (
    _get_domain_annual_cost,
    _process_single_domain,
    check_route53_registered_domains,
)
from tests.assertions import assert_equal


def test_get_domain_annual_cost_com():
    """Test _get_domain_annual_cost returns correct cost for .com domain."""
    result = _get_domain_annual_cost("example.com")
    assert_equal(result, 12.00)


def test_get_domain_annual_cost_org():
    """Test _get_domain_annual_cost returns correct cost for .org domain."""
    result = _get_domain_annual_cost("nonprofit.org")
    assert_equal(result, 12.00)


def test_get_domain_annual_cost_net():
    """Test _get_domain_annual_cost returns correct cost for .net domain."""
    result = _get_domain_annual_cost("network.net")
    assert_equal(result, 12.00)


def test_get_domain_annual_cost_report():
    """Test _get_domain_annual_cost returns correct cost for .report domain."""
    result = _get_domain_annual_cost("annual.report")
    assert_equal(result, 25.00)


def test_get_domain_annual_cost_other_tld():
    """Test _get_domain_annual_cost returns default cost for other TLDs."""
    result = _get_domain_annual_cost("example.io")
    assert_equal(result, 15.00)


def test_get_domain_annual_cost_xyz():
    """Test _get_domain_annual_cost returns default cost for .xyz domain."""
    result = _get_domain_annual_cost("test.xyz")
    assert_equal(result, 15.00)


def test_process_single_domain_success(capsys):
    """Test _process_single_domain with successful domain details retrieval."""
    mock_client = MagicMock()
    expiry_date = datetime(2025, 12, 31, 23, 59, 59)

    domain = {
        "DomainName": "example.com",
        "Expiry": expiry_date,
        "AutoRenew": True,
    }

    mock_client.get_domain_detail.return_value = {
        "RegistrarName": "Amazon Registrar",
        "StatusList": ["clientTransferProhibited", "serverTransferProhibited"],
        "Nameservers": [
            {"Name": "ns-123.awsdns-12.com"},
            {"Name": "ns-456.awsdns-34.net"},
        ],
    }

    result = _process_single_domain(mock_client, domain)

    mock_client.get_domain_detail.assert_called_once_with(DomainName="example.com")

    assert result is not None
    assert_equal(result["domain_name"], "example.com")
    assert_equal(result["expiry"], expiry_date)
    assert_equal(result["auto_renew"], True)
    assert_equal(result["registrar"], "Amazon Registrar")
    assert_equal(len(result["status"]), 2)
    assert_equal(result["status"][0], "clientTransferProhibited")
    assert_equal(len(result["nameservers"]), 2)
    assert_equal(result["annual_cost"], 12.00)

    captured = capsys.readouterr()
    assert "Domain: example.com" in captured.out
    assert "Expiry:" in captured.out
    assert "Auto-renew: True" in captured.out
    assert "Registrar: Amazon Registrar" in captured.out
    assert "ns-123.awsdns-12.com" in captured.out


def test_process_single_domain_missing_fields(capsys):  # pylint: disable=unused-argument
    """Test _process_single_domain handles missing optional fields."""
    mock_client = MagicMock()

    domain = {
        "DomainName": "test.org",
    }

    mock_client.get_domain_detail.return_value = {
        "Nameservers": [],
    }

    result = _process_single_domain(mock_client, domain)

    assert result is not None
    assert_equal(result["domain_name"], "test.org")
    assert_equal(result["expiry"], None)
    assert result["auto_renew"] is None
    assert result["registrar"] is None
    assert_equal(result["status"], [])
    assert_equal(result["nameservers"], [])


def test_process_single_domain_client_error(capsys):
    """Test _process_single_domain handles ClientError gracefully."""
    mock_client = MagicMock()

    domain = {
        "DomainName": "error.com",
        "Expiry": datetime(2026, 1, 1),
        "AutoRenew": False,
    }

    mock_client.get_domain_detail.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
        "GetDomainDetail",
    )

    result = _process_single_domain(mock_client, domain)

    assert result is None

    captured = capsys.readouterr()
    assert "Domain: error.com" in captured.out
    assert "Error getting domain details:" in captured.out


def test_process_single_domain_empty_nameservers(capsys):
    """Test _process_single_domain with empty nameservers list."""
    mock_client = MagicMock()

    domain = {
        "DomainName": "minimal.net",
        "Expiry": datetime(2025, 6, 15),
        "AutoRenew": True,
    }

    mock_client.get_domain_detail.return_value = {
        "RegistrarName": "Test Registrar",
        "StatusList": [],
        "Nameservers": [],
    }

    result = _process_single_domain(mock_client, domain)

    assert result is not None
    assert_equal(len(result["nameservers"]), 0)

    captured = capsys.readouterr()
    assert "Nameservers:" in captured.out


@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.boto3.client")
def test_check_route53_registered_domains_no_domains(mock_boto_client, capsys):
    """Test check_route53_registered_domains with no registered domains."""
    mock_client = MagicMock()
    mock_boto_client.return_value = mock_client
    mock_client.list_domains.return_value = {"Domains": []}

    result = check_route53_registered_domains()

    mock_boto_client.assert_called_once_with("route53domains", region_name="us-east-1")
    mock_client.list_domains.assert_called_once()
    assert_equal(result, [])

    captured = capsys.readouterr()
    assert "Checking Route 53 Registered Domains" in captured.out
    assert "No domains registered through Route 53" in captured.out


@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.boto3.client")
def test_check_route53_registered_domains_with_domains(mock_boto_client, capsys):
    """Test check_route53_registered_domains with multiple domains."""
    mock_client = MagicMock()
    mock_boto_client.return_value = mock_client

    expiry1 = datetime(2025, 12, 31)
    expiry2 = datetime(2026, 6, 15)

    mock_client.list_domains.return_value = {
        "Domains": [
            {
                "DomainName": "example.com",
                "Expiry": expiry1,
                "AutoRenew": True,
            },
            {
                "DomainName": "test.report",
                "Expiry": expiry2,
                "AutoRenew": False,
            },
        ]
    }

    mock_client.get_domain_detail.side_effect = [
        {
            "RegistrarName": "Amazon Registrar",
            "StatusList": ["ok"],
            "Nameservers": [{"Name": "ns-1.example.com"}],
        },
        {
            "RegistrarName": "Amazon Registrar",
            "StatusList": ["ok"],
            "Nameservers": [{"Name": "ns-1.test.com"}],
        },
    ]

    result = check_route53_registered_domains()

    assert_equal(len(result), 2)
    assert_equal(result[0]["domain_name"], "example.com")
    assert_equal(result[0]["annual_cost"], 12.00)
    assert_equal(result[1]["domain_name"], "test.report")
    assert_equal(result[1]["annual_cost"], 25.00)

    captured = capsys.readouterr()
    assert "Domain Registration Summary:" in captured.out
    assert "Total registered domains: 2" in captured.out
    assert "Estimated total annual cost: $37.00" in captured.out


@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.boto3.client")
def test_check_route53_registered_domains_partial_errors(mock_boto_client, capsys):
    """Test check_route53_registered_domains when some domains error."""
    mock_client = MagicMock()
    mock_boto_client.return_value = mock_client

    mock_client.list_domains.return_value = {
        "Domains": [
            {
                "DomainName": "good.com",
                "Expiry": datetime(2025, 12, 31),
                "AutoRenew": True,
            },
            {
                "DomainName": "error.com",
                "Expiry": datetime(2026, 1, 1),
                "AutoRenew": False,
            },
        ]
    }

    def get_domain_detail_side_effect(**kwargs):
        domain_name = kwargs.get("DomainName")
        if domain_name == "error.com":
            raise ClientError(
                {"Error": {"Code": "NotFound", "Message": "Domain not found"}},
                "GetDomainDetail",
            )
        return {
            "RegistrarName": "Amazon Registrar",
            "StatusList": ["ok"],
            "Nameservers": [],
        }

    mock_client.get_domain_detail.side_effect = get_domain_detail_side_effect

    result = check_route53_registered_domains()

    assert_equal(len(result), 1)
    assert_equal(result[0]["domain_name"], "good.com")

    captured = capsys.readouterr()
    assert "Total registered domains: 2" in captured.out
    assert "Error getting domain details:" in captured.out


@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.boto3.client")
def test_check_route53_registered_domains_list_error(mock_boto_client, capsys):
    """Test check_route53_registered_domains handles list_domains error."""
    mock_client = MagicMock()
    mock_boto_client.return_value = mock_client

    mock_client.list_domains.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
        "ListDomains",
    )

    result = check_route53_registered_domains()

    assert_equal(result, [])

    captured = capsys.readouterr()
    assert "Error checking registered domains:" in captured.out
