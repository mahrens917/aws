"""Comprehensive tests for route53_helpers.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cost_toolkit.scripts.setup.exceptions import (
    HostedZoneNotFoundError,
    NSRecordsNotFoundError,
)
from cost_toolkit.scripts.setup.route53_helpers import (
    _build_existing_records_map,
    _check_canva_txt_record,
    _check_dns_records,
    _check_root_a_record,
    _check_www_a_record,
    _find_hosted_zone,
    _get_nameserver_records,
    _print_dns_status,
)


class TestFindHostedZone:
    """Tests for _find_hosted_zone function."""

    def test_find_existing_zone(self):
        """Test finding an existing hosted zone."""
        mock_route53 = MagicMock()
        mock_route53.list_hosted_zones.return_value = {
            "HostedZones": [
                {"Name": "example.com.", "Id": "/hostedzone/Z123"},
                {"Name": "other.com.", "Id": "/hostedzone/Z456"},
            ]
        }

        result = _find_hosted_zone(mock_route53, "example.com")

        assert result == {"Name": "example.com.", "Id": "/hostedzone/Z123"}

    def test_find_zone_not_found(self):
        """Test when hosted zone is not found."""
        mock_route53 = MagicMock()
        mock_route53.list_hosted_zones.return_value = {"HostedZones": [{"Name": "other.com.", "Id": "/hostedzone/Z456"}]}

        with pytest.raises(HostedZoneNotFoundError) as exc_info:
            _find_hosted_zone(mock_route53, "example.com")

        assert "example.com" in str(exc_info.value)

    def test_find_zone_empty_list(self):
        """Test with empty hosted zones list."""
        mock_route53 = MagicMock()
        mock_route53.list_hosted_zones.return_value = {"HostedZones": []}

        with pytest.raises(HostedZoneNotFoundError):
            _find_hosted_zone(mock_route53, "example.com")


class TestGetNameserverRecords:
    """Tests for _get_nameserver_records function."""

    def test_get_nameservers_success(self):
        """Test successfully getting nameserver records."""
        mock_route53 = MagicMock()
        mock_route53.list_resource_record_sets.return_value = {
            "ResourceRecordSets": [
                {
                    "Type": "NS",
                    "Name": "example.com.",
                    "ResourceRecords": [
                        {"Value": "ns-1.awsdns-01.com"},
                        {"Value": "ns-2.awsdns-02.net"},
                    ],
                }
            ]
        }

        result = _get_nameserver_records(mock_route53, "/hostedzone/Z123", "example.com")

        assert result == ["ns-1.awsdns-01.com", "ns-2.awsdns-02.net"]

    def test_get_nameservers_not_found(self):
        """Test when nameserver records not found."""
        mock_route53 = MagicMock()
        mock_route53.list_resource_record_sets.return_value = {"ResourceRecordSets": [{"Type": "A", "Name": "example.com."}]}

        with pytest.raises(NSRecordsNotFoundError) as exc_info:
            _get_nameserver_records(mock_route53, "/hostedzone/Z123", "example.com")

        assert "example.com" in str(exc_info.value)

    def test_get_nameservers_wrong_domain(self):
        """Test when NS record exists but for different domain."""
        mock_route53 = MagicMock()
        mock_route53.list_resource_record_sets.return_value = {
            "ResourceRecordSets": [
                {
                    "Type": "NS",
                    "Name": "other.com.",
                    "ResourceRecords": [{"Value": "ns-1.awsdns-01.com"}],
                }
            ]
        }

        with pytest.raises(NSRecordsNotFoundError):
            _get_nameserver_records(mock_route53, "/hostedzone/Z123", "example.com")


class TestCheckRootARecord:
    """Tests for _check_root_a_record function."""

    def test_root_a_record_found(self, capsys):
        """Test finding root domain A record."""
        record = {
            "Type": "A",
            "Name": "example.com.",
            "ResourceRecords": [{"Value": "192.168.1.1"}],
        }

        found, ip = _check_root_a_record(record, "example.com")

        assert found is True
        assert ip == "192.168.1.1"
        captured = capsys.readouterr()
        assert "Root domain A record: 192.168.1.1" in captured.out

    def test_root_a_record_wrong_type(self):
        """Test record with wrong type."""
        record = {"Type": "CNAME", "Name": "example.com."}

        found, ip = _check_root_a_record(record, "example.com")

        assert found is False
        assert ip is None

    def test_root_a_record_wrong_name(self):
        """Test record with wrong name."""
        record = {"Type": "A", "Name": "www.example.com."}

        found, ip = _check_root_a_record(record, "example.com")

        assert found is False
        assert ip is None

    def test_root_a_record_no_resource_records(self):
        """Test A record without ResourceRecords field."""
        record = {"Type": "A", "Name": "example.com."}

        found, ip = _check_root_a_record(record, "example.com")

        assert found is True
        assert ip is None


class TestCheckWwwARecord:
    """Tests for _check_www_a_record function."""

    def test_www_a_record_found(self, capsys):
        """Test finding www subdomain A record."""
        record = {
            "Type": "A",
            "Name": "www.example.com.",
            "ResourceRecords": [{"Value": "192.168.1.2"}],
        }

        found = _check_www_a_record(record, "example.com")

        assert found is True
        captured = capsys.readouterr()
        assert "WWW subdomain A record: 192.168.1.2" in captured.out

    def test_www_a_record_wrong_type(self):
        """Test record with wrong type."""
        record = {"Type": "CNAME", "Name": "www.example.com."}

        found = _check_www_a_record(record, "example.com")

        assert found is False

    def test_www_a_record_wrong_name(self):
        """Test record with wrong name."""
        record = {"Type": "A", "Name": "example.com."}

        found = _check_www_a_record(record, "example.com")

        assert found is False

    def test_www_a_record_no_resource_records(self):
        """Test www A record without ResourceRecords."""
        record = {"Type": "A", "Name": "www.example.com."}

        found = _check_www_a_record(record, "example.com")

        assert found is True


class TestCheckCanvaTxtRecord:
    """Tests for _check_canva_txt_record function."""

    def test_canva_txt_record_found(self, capsys):
        """Test finding Canva verification TXT record."""
        record = {
            "Type": "TXT",
            "Name": "_canva-domain-verify.example.com.",
            "ResourceRecords": [{"Value": "canva-verification-code"}],
        }

        found = _check_canva_txt_record(record)

        assert found is True
        captured = capsys.readouterr()
        assert "Canva verification TXT record" in captured.out

    def test_canva_txt_record_wrong_type(self):
        """Test record with wrong type."""
        record = {"Type": "A", "Name": "_canva-domain-verify.example.com."}

        found = _check_canva_txt_record(record)

        assert found is False

    def test_canva_txt_record_wrong_name(self):
        """Test TXT record without Canva prefix."""
        record = {"Type": "TXT", "Name": "example.com."}

        found = _check_canva_txt_record(record)

        assert found is False

    def test_canva_txt_record_no_resource_records(self):
        """Test Canva TXT record without ResourceRecords."""
        record = {"Type": "TXT", "Name": "_canva-domain-verify.example.com."}

        found = _check_canva_txt_record(record)

        assert found is True


class TestCheckDnsRecords:
    """Tests for _check_dns_records function."""

    def test_check_all_records_present(self):
        """Test when all DNS records are present."""
        records = [
            {
                "Type": "A",
                "Name": "example.com.",
                "ResourceRecords": [{"Value": "192.168.1.1"}],
            },
            {
                "Type": "A",
                "Name": "www.example.com.",
                "ResourceRecords": [{"Value": "192.168.1.2"}],
            },
            {
                "Type": "TXT",
                "Name": "_canva-domain-verify.example.com.",
                "ResourceRecords": [{"Value": "verification-code"}],
            },
        ]

        has_root, has_www, has_canva, canva_ip = _check_dns_records(records, "example.com")

        assert has_root is True
        assert has_www is True
        assert has_canva is True
        assert canva_ip == "192.168.1.1"

    def test_check_only_root_present(self):
        """Test when only root A record present."""
        records = [
            {
                "Type": "A",
                "Name": "example.com.",
                "ResourceRecords": [{"Value": "192.168.1.1"}],
            }
        ]

        has_root, has_www, has_canva, canva_ip = _check_dns_records(records, "example.com")

        assert has_root is True
        assert has_www is False
        assert has_canva is False
        assert canva_ip == "192.168.1.1"

    def test_check_no_records(self):
        """Test when no records present."""
        records = []

        has_root, has_www, has_canva, canva_ip = _check_dns_records(records, "example.com")

        assert has_root is False
        assert has_www is False
        assert has_canva is False
        assert canva_ip is None


class TestPrintDnsStatus:
    """Tests for _print_dns_status function."""

    def test_all_records_present(self, capsys):
        """Test status when all records present."""
        result = _print_dns_status(True, True, True)

        assert result is True
        captured = capsys.readouterr()
        assert "All required DNS records are present" in captured.out

    def test_some_records_missing(self, capsys):
        """Test status when some records missing."""
        result = _print_dns_status(True, False, True)

        assert result is False
        captured = capsys.readouterr()
        assert "Some DNS records are missing" in captured.out

    def test_no_records_present(self, capsys):
        """Test status when no records present."""
        result = _print_dns_status(False, False, False)

        assert result is False
        captured = capsys.readouterr()
        assert "Some DNS records are missing" in captured.out


class TestBuildExistingRecordsMap:
    """Tests for _build_existing_records_map function."""

    def test_build_map_with_records(self):
        """Test building map with multiple records."""
        records = [
            {"Name": "example.com.", "Type": "A"},
            {"Name": "www.example.com.", "Type": "A"},
            {"Name": "example.com.", "Type": "NS"},
        ]

        result = _build_existing_records_map(records)

        assert "example.com.-A" in result
        assert "www.example.com.-A" in result
        assert "example.com.-NS" in result
        assert len(result) == 3

    def test_build_map_empty_records(self):
        """Test building map with empty records."""
        result = _build_existing_records_map([])

        assert not result

    def test_build_map_missing_fields(self):
        """Test building map with records missing Name or Type."""
        records = [{"Name": "example.com."}, {"Type": "A"}]

        result = _build_existing_records_map(records)

        assert "None-A" in result
        assert "example.com.-None" in result
