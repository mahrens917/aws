"""Tests for cost_toolkit/scripts/audit/aws_route53_domain_ownership.py - Part 2"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.audit.aws_route53_domain_ownership import (
    _print_cost_breakdown,
    _print_ownership_analysis,
    _print_recommendations,
    check_current_hosted_zones,
    main,
)
from tests.assertions import assert_equal


@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.boto3.client")
def test_check_current_hosted_zones_no_zones(mock_boto_client, capsys):
    """Test check_current_hosted_zones with no hosted zones."""
    mock_client = MagicMock()
    mock_boto_client.return_value = mock_client
    mock_client.list_hosted_zones.return_value = {"HostedZones": []}

    result = check_current_hosted_zones()

    mock_boto_client.assert_called_once_with("route53")
    mock_client.list_hosted_zones.assert_called_once()
    assert_equal(result, [])

    captured = capsys.readouterr()
    assert "Current Route 53 Hosted Zones" in captured.out
    assert "No hosted zones found" in captured.out


@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.boto3.client")
def test_check_current_hosted_zones_with_zones(mock_boto_client, capsys):
    """Test check_current_hosted_zones with multiple zones."""
    mock_client = MagicMock()
    mock_boto_client.return_value = mock_client

    mock_client.list_hosted_zones.return_value = {
        "HostedZones": [
            {
                "Id": "/hostedzone/Z1234567890ABC",
                "Name": "example.com.",
                "Config": {"PrivateZone": False},
                "ResourceRecordSetCount": 10,
            },
            {
                "Id": "/hostedzone/Z0987654321XYZ",
                "Name": "internal.local.",
                "Config": {"PrivateZone": True},
                "ResourceRecordSetCount": 5,
            },
        ]
    }

    result = check_current_hosted_zones()

    assert_equal(len(result), 2)
    assert_equal(result[0]["zone_name"], "example.com.")
    assert_equal(result[0]["zone_id"], "Z1234567890ABC")
    assert_equal(result[0]["is_private"], False)
    assert_equal(result[0]["record_count"], 10)
    assert_equal(result[1]["zone_name"], "internal.local.")
    assert_equal(result[1]["zone_id"], "Z0987654321XYZ")
    assert_equal(result[1]["is_private"], True)
    assert_equal(result[1]["record_count"], 5)

    captured = capsys.readouterr()
    assert "Hosted Zone: example.com." in captured.out
    assert "Zone ID: Z1234567890ABC" in captured.out
    assert "Type: Public" in captured.out
    assert "Type: Private" in captured.out
    assert "Hosted Zones Summary:" in captured.out
    assert "Total zones: 2" in captured.out
    assert "Monthly cost: $1.00" in captured.out


@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.boto3.client")
def test_check_current_hosted_zones_missing_config(mock_boto_client, capsys):  # pylint: disable=unused-argument
    """Test check_current_hosted_zones handles missing Config field."""
    mock_client = MagicMock()
    mock_boto_client.return_value = mock_client

    mock_client.list_hosted_zones.return_value = {
        "HostedZones": [
            {
                "Id": "/hostedzone/ZTEST123456",
                "Name": "test.com.",
            }
        ]
    }

    result = check_current_hosted_zones()

    assert_equal(len(result), 1)
    assert result[0]["is_private"] is None
    assert result[0]["record_count"] is None


@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.boto3.client")
def test_check_current_hosted_zones_client_error(mock_boto_client, capsys):
    """Test check_current_hosted_zones handles ClientError."""
    mock_client = MagicMock()
    mock_boto_client.return_value = mock_client

    mock_client.list_hosted_zones.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
        "ListHostedZones",
    )

    result = check_current_hosted_zones()

    assert_equal(result, [])

    captured = capsys.readouterr()
    assert "Error checking hosted zones:" in captured.out


def test_print_ownership_analysis_with_domains_and_zones(capsys):
    """Test _print_ownership_analysis with both domains and zones."""
    registered_domains = [
        {
            "domain_name": "example.com",
            "expiry": datetime(2025, 12, 31),
            "annual_cost": 12.00,
        },
        {
            "domain_name": "test.org",
            "expiry": datetime(2026, 6, 15),
            "annual_cost": 12.00,
        },
    ]

    hosted_zones = [
        {
            "zone_name": "example.com.",
            "zone_id": "Z123456",
        },
    ]

    _print_ownership_analysis(registered_domains, hosted_zones)

    captured = capsys.readouterr()
    assert "DOMAIN OWNERSHIP ANALYSIS" in captured.out
    assert "You OWN these domains through Route 53:" in captured.out
    assert "example.com" in captured.out
    assert "test.org" in captured.out
    assert "You have DNS hosting for:" in captured.out
    assert "example.com." in captured.out


def test_print_ownership_analysis_no_domains(capsys):
    """Test _print_ownership_analysis with no registered domains."""
    registered_domains = []
    hosted_zones = [
        {
            "zone_name": "external.com.",
            "zone_id": "Z789012",
        }
    ]

    _print_ownership_analysis(registered_domains, hosted_zones)

    captured = capsys.readouterr()
    assert "No domains registered through Route 53" in captured.out
    assert "Your domains may be registered elsewhere" in captured.out
    assert "You have DNS hosting for:" in captured.out


def test_print_ownership_analysis_no_zones(capsys):
    """Test _print_ownership_analysis with no hosted zones."""
    registered_domains = [
        {
            "domain_name": "example.com",
            "expiry": datetime(2025, 12, 31),
            "annual_cost": 12.00,
        }
    ]
    hosted_zones = []

    _print_ownership_analysis(registered_domains, hosted_zones)

    captured = capsys.readouterr()
    assert "You OWN these domains through Route 53:" in captured.out
    assert "example.com" in captured.out
    assert "You have DNS hosting for:" not in captured.out


def test_print_ownership_analysis_empty(capsys):
    """Test _print_ownership_analysis with no domains or zones."""
    _print_ownership_analysis([], [])

    captured = capsys.readouterr()
    assert "No domains registered through Route 53" in captured.out


def test_print_cost_breakdown_with_domains_and_zones(capsys):
    """Test _print_cost_breakdown with domains and zones."""
    registered_domains = [
        {"annual_cost": 12.00},
        {"annual_cost": 25.00},
    ]

    hosted_zones = [{}, {}, {}]  # 3 zones

    _print_cost_breakdown(registered_domains, hosted_zones)

    captured = capsys.readouterr()
    assert "COST BREAKDOWN:" in captured.out
    assert "Domain registration: $37.00/year" in captured.out
    assert "DNS hosting: $1.50/month ($18.00/year)" in captured.out


def test_print_cost_breakdown_no_domains(capsys):
    """Test _print_cost_breakdown with no registered domains."""
    registered_domains = []
    hosted_zones = [{}]

    _print_cost_breakdown(registered_domains, hosted_zones)

    captured = capsys.readouterr()
    assert "Domain registration: $0/year (registered elsewhere)" in captured.out
    assert "DNS hosting: $0.50/month ($6.00/year)" in captured.out


def test_print_cost_breakdown_no_zones(capsys):
    """Test _print_cost_breakdown with no hosted zones."""
    registered_domains = [{"annual_cost": 15.00}]
    hosted_zones = []

    _print_cost_breakdown(registered_domains, hosted_zones)

    captured = capsys.readouterr()
    assert "Domain registration: $15.00/year" in captured.out
    assert "DNS hosting: $0/month" in captured.out


def test_print_cost_breakdown_empty(capsys):
    """Test _print_cost_breakdown with no domains or zones."""
    _print_cost_breakdown([], [])

    captured = capsys.readouterr()
    assert "Domain registration: $0/year (registered elsewhere)" in captured.out
    assert "DNS hosting: $0/month" in captured.out


def test_print_recommendations_domains_elsewhere(capsys):
    """Test _print_recommendations when domains registered elsewhere."""
    registered_domains = []
    hosted_zones = [{"zone_name": "external.com."}]

    _print_recommendations(registered_domains, hosted_zones)

    captured = capsys.readouterr()
    assert "RECOMMENDATIONS:" in captured.out
    assert "Your domains are likely registered elsewhere" in captured.out
    assert "You can keep using Route 53 for DNS" in captured.out
    assert "Consider moving DNS to free providers like Cloudflare" in captured.out


def test_print_recommendations_with_registered_domains(capsys):
    """Test _print_recommendations with registered domains."""
    registered_domains = [{"domain_name": "example.com"}, {"domain_name": "test.org"}]
    hosted_zones = []

    _print_recommendations(registered_domains, hosted_zones)

    captured = capsys.readouterr()
    assert "You own 2 domain(s) through Route 53" in captured.out
    assert "These will auto-renew unless you disable it" in captured.out
    assert "You can transfer DNS hosting elsewhere" in captured.out


def test_print_recommendations_single_domain(capsys):
    """Test _print_recommendations with single registered domain."""
    registered_domains = [{"domain_name": "single.com"}]
    hosted_zones = []

    _print_recommendations(registered_domains, hosted_zones)

    captured = capsys.readouterr()
    assert "You own 1 domain(s) through Route 53" in captured.out


def test_print_recommendations_both(capsys):
    """Test _print_recommendations with domains and zones."""
    registered_domains = [{"domain_name": "example.com"}]
    hosted_zones = [{"zone_name": "example.com."}]

    _print_recommendations(registered_domains, hosted_zones)

    captured = capsys.readouterr()
    assert "You own 1 domain(s) through Route 53" in captured.out


@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.check_current_hosted_zones")
@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.check_route53_registered_domains")
def test_main_with_data(mock_check_domains, mock_check_zones, capsys):
    """Test main function with domains and zones."""
    mock_check_domains.return_value = [
        {
            "domain_name": "example.com",
            "expiry": datetime(2025, 12, 31),
            "annual_cost": 12.00,
        }
    ]

    mock_check_zones.return_value = [
        {
            "zone_name": "example.com.",
            "zone_id": "Z123456",
        }
    ]

    main()

    mock_check_domains.assert_called_once()
    mock_check_zones.assert_called_once()

    captured = capsys.readouterr()
    assert "AWS Route 53 Domain Ownership Analysis" in captured.out
    assert "Checking domain registration vs DNS hosting..." in captured.out
    assert "DOMAIN OWNERSHIP ANALYSIS" in captured.out
    assert "COST BREAKDOWN:" in captured.out
    assert "RECOMMENDATIONS:" in captured.out


@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.check_current_hosted_zones")
@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.check_route53_registered_domains")
def test_main_empty(mock_check_domains, mock_check_zones, capsys):
    """Test main function with no domains or zones."""
    mock_check_domains.return_value = []
    mock_check_zones.return_value = []

    main()

    mock_check_domains.assert_called_once()
    mock_check_zones.assert_called_once()

    captured = capsys.readouterr()
    assert "AWS Route 53 Domain Ownership Analysis" in captured.out
    assert "No domains registered through Route 53" in captured.out


@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.check_current_hosted_zones")
@patch("cost_toolkit.scripts.audit.aws_route53_domain_ownership.check_route53_registered_domains")
def test_main_zones_only(mock_check_domains, mock_check_zones, capsys):
    """Test main function with only hosted zones."""
    mock_check_domains.return_value = []
    mock_check_zones.return_value = [
        {
            "zone_name": "external.com.",
            "zone_id": "Z789012",
        }
    ]

    main()

    captured = capsys.readouterr()
    assert "Your domains are likely registered elsewhere" in captured.out
    assert "Consider moving DNS to free providers" in captured.out
