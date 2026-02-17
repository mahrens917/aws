"""Comprehensive tests for verify_iwannabenewyork_domain.py."""

from __future__ import annotations

import datetime
import socket
from unittest.mock import MagicMock, patch

import pytest

from cost_toolkit.scripts.setup.domain_verification_http import (
    HTTP_STATUS_MOVED_PERMANENTLY,
    HTTP_STATUS_OK,
    HttpRequestError,
    verify_dns_resolution,
    verify_http_connectivity,
    verify_https_connectivity,
)
from cost_toolkit.scripts.setup.domain_verification_ssl import (
    _check_cert_validity,
    _extract_cert_dict,
    _parse_cert_dates,
    _print_cert_info,
)
from cost_toolkit.scripts.setup.exceptions import CertificateInfoError


class TestDnsResolution:
    """Tests for test_dns_resolution function."""

    @patch("cost_toolkit.scripts.setup.domain_verification_http.socket.gethostbyname")
    def test_successful_dns_resolution(self, mock_gethostbyname, capsys):
        """Test successful DNS resolution."""
        mock_gethostbyname.side_effect = ["192.168.1.1", "192.168.1.2"]

        success, ip = verify_dns_resolution("example.com")

        assert success is True
        assert ip == "192.168.1.1"
        captured = capsys.readouterr()
        assert "example.com resolves to: 192.168.1.1" in captured.out
        assert "www.example.com resolves to: 192.168.1.2" in captured.out

    @patch("cost_toolkit.scripts.setup.domain_verification_http.socket.gethostbyname")
    def test_dns_resolution_failure(self, mock_gethostbyname, capsys):
        """Test DNS resolution failure."""
        mock_gethostbyname.side_effect = socket.gaierror("Name or service not known")

        success, ip = verify_dns_resolution("example.com")

        assert success is False
        assert ip is None
        captured = capsys.readouterr()
        assert "DNS resolution failed" in captured.out


class TestHttpConnectivity:
    """Tests for test_http_connectivity function."""

    @patch("cost_toolkit.scripts.setup.domain_verification_http._http_get")
    def test_http_redirects_to_https(self, mock_get, capsys):
        """Test HTTP redirects to HTTPS."""
        mock_response = MagicMock()
        mock_response.status_code = HTTP_STATUS_MOVED_PERMANENTLY
        mock_response.headers = {"Location": "https://example.com"}
        mock_get.return_value = mock_response

        result = verify_http_connectivity("example.com")

        assert result is True
        captured = capsys.readouterr()
        assert "HTTP redirects to HTTPS" in captured.out

    @patch("cost_toolkit.scripts.setup.domain_verification_http._http_get")
    def test_http_no_redirect(self, mock_get, capsys):
        """Test HTTP without redirect."""
        mock_response = MagicMock()
        mock_response.status_code = HTTP_STATUS_OK
        mock_response.headers = {"Location": ""}
        mock_get.return_value = mock_response

        result = verify_http_connectivity("example.com")

        assert result is True
        captured = capsys.readouterr()
        assert f"HTTP response: {HTTP_STATUS_OK}" in captured.out

    @patch("cost_toolkit.scripts.setup.domain_verification_http._http_get")
    def test_http_request_exception(self, mock_get, capsys):
        """Test HTTP request exception."""
        mock_get.side_effect = HttpRequestError("Connection error")

        result = verify_http_connectivity("example.com")

        assert result is False
        captured = capsys.readouterr()
        assert "HTTP test failed" in captured.out


class TestHttpsConnectivity:
    """Tests for test_https_connectivity function."""

    @patch("cost_toolkit.scripts.setup.domain_verification_http._http_get")
    def test_https_success_with_cloudflare(self, mock_get, capsys):
        """Test successful HTTPS with Cloudflare."""
        mock_response = MagicMock()
        mock_response.status_code = HTTP_STATUS_OK
        mock_response.headers = {"Content-Type": "text/html", "Server": "cloudflare"}
        mock_get.return_value = mock_response

        result = verify_https_connectivity("example.com")

        assert result is True
        captured = capsys.readouterr()
        assert "HTTPS connection successful" in captured.out
        assert "Served by Cloudflare" in captured.out

    @patch("cost_toolkit.scripts.setup.domain_verification_http._http_get")
    def test_https_success_without_cloudflare(self, mock_get, capsys):
        """Test successful HTTPS without Cloudflare."""
        mock_response = MagicMock()
        mock_response.status_code = HTTP_STATUS_OK
        mock_response.headers = {"Content-Type": "text/html", "Server": "nginx"}
        mock_get.return_value = mock_response

        result = verify_https_connectivity("example.com")

        assert result is True
        captured = capsys.readouterr()
        assert "HTTPS connection successful" in captured.out
        assert "Served by Cloudflare" not in captured.out

    @patch("cost_toolkit.scripts.setup.domain_verification_http._http_get")
    def test_https_non_ok_status(self, mock_get, capsys):
        """Test HTTPS with non-OK status."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = verify_https_connectivity("example.com")

        assert result is False
        captured = capsys.readouterr()
        assert "HTTPS response: 404" in captured.out

    @patch("cost_toolkit.scripts.setup.domain_verification_http._http_get")
    def test_https_request_exception(self, mock_get, capsys):
        """Test HTTPS request exception."""
        mock_get.side_effect = HttpRequestError("SSL error")

        result = verify_https_connectivity("example.com")

        assert result is False
        captured = capsys.readouterr()
        assert "HTTPS test failed" in captured.out


class TestExtractCertDict:
    """Tests for _extract_cert_dict function."""

    def test_extract_valid_cert_items(self):
        """Test extracting valid certificate items."""
        cert_items = [(("commonName", "example.com"),), (("organizationName", "Acme Inc"),)]

        result = _extract_cert_dict(cert_items)

        assert result == {"commonName": "example.com", "organizationName": "Acme Inc"}

    def test_extract_empty_cert_items(self):
        """Test extracting empty certificate items."""
        result = _extract_cert_dict([])

        assert not result

    def test_extract_malformed_cert_items(self):
        """Test extracting malformed certificate items."""
        cert_items = [((),), (("key",),)]

        result = _extract_cert_dict(cert_items)

        assert not result


class TestParseCertDates:
    """Tests for _parse_cert_dates function."""

    def test_parse_valid_dates(self):
        """Test parsing valid certificate dates."""
        cert = {"notBefore": "Jan 1 00:00:00 2024 GMT", "notAfter": "Dec 31 23:59:59 2024 GMT"}

        not_before, not_after = _parse_cert_dates(cert)

        assert not_before == datetime.datetime(2024, 1, 1, 0, 0, 0)
        assert not_after == datetime.datetime(2024, 12, 31, 23, 59, 59)

    def test_parse_missing_notbefore(self):
        """Test parsing certificate without notBefore."""
        cert = {"notAfter": "Dec 31 23:59:59 2024 GMT"}

        with pytest.raises(CertificateInfoError):
            _parse_cert_dates(cert)

    def test_parse_missing_notafter(self):
        """Test parsing certificate without notAfter."""
        cert = {"notBefore": "Jan 1 00:00:00 2024 GMT"}

        with pytest.raises(CertificateInfoError):
            _parse_cert_dates(cert)

    def test_parse_none_cert(self):
        """Test parsing None certificate."""
        with pytest.raises(CertificateInfoError):
            _parse_cert_dates(None)


class TestPrintCertInfo:
    """Tests for _print_cert_info function."""

    def test_print_cert_info(self, capsys):
        """Test printing certificate information."""
        subject_dict = {"commonName": "example.com"}
        issuer_dict = {"organizationName": "Let's Encrypt"}
        not_before = datetime.datetime(2024, 1, 1, 0, 0, 0)
        not_after = datetime.datetime(2024, 12, 31, 23, 59, 59)

        _print_cert_info(subject_dict, issuer_dict, not_before, not_after)

        captured = capsys.readouterr()
        assert "Certificate Subject: example.com" in captured.out
        assert "Certificate Issuer: Let's Encrypt" in captured.out
        assert "Valid From: 2024-01-01 00:00:00 UTC" in captured.out
        assert "Valid Until: 2024-12-31 23:59:59 UTC" in captured.out

    def test_print_cert_info_unknown_fields(self, capsys):
        """Test printing certificate info with unknown fields."""
        subject_dict = {}
        issuer_dict = {}
        not_before = datetime.datetime(2024, 1, 1, 0, 0, 0)
        not_after = datetime.datetime(2024, 12, 31, 23, 59, 59)

        _print_cert_info(subject_dict, issuer_dict, not_before, not_after)

        captured = capsys.readouterr()
        assert "Certificate Subject: None" in captured.out
        assert "Certificate Issuer: None" in captured.out


class TestCheckCertValidity:
    """Tests for _check_cert_validity function."""

    @patch("cost_toolkit.scripts.setup.domain_verification_ssl.datetime")
    def test_cert_is_valid(self, mock_datetime, capsys):
        """Test valid certificate."""
        mock_datetime.datetime.now.return_value = datetime.datetime(2024, 6, 15, 0, 0, 0, tzinfo=datetime.timezone.utc)
        not_before = datetime.datetime(2024, 1, 1, 0, 0, 0)
        not_after = datetime.datetime(2024, 12, 31, 23, 59, 59)

        result = _check_cert_validity(not_before, not_after)

        assert result is True
        captured = capsys.readouterr()
        assert "Certificate is valid" in captured.out
        assert "199 days until expiry" in captured.out

    @patch("cost_toolkit.scripts.setup.domain_verification_ssl.datetime")
    def test_cert_is_expired(self, mock_datetime, capsys):
        """Test expired certificate."""
        mock_datetime.datetime.now.return_value = datetime.datetime(2025, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
        not_before = datetime.datetime(2024, 1, 1, 0, 0, 0)
        not_after = datetime.datetime(2024, 12, 31, 23, 59, 59)

        result = _check_cert_validity(not_before, not_after)

        assert result is False
        captured = capsys.readouterr()
        assert "Certificate is not valid for current date" in captured.out

    @patch("cost_toolkit.scripts.setup.domain_verification_ssl.datetime")
    def test_cert_not_yet_valid(self, mock_datetime, capsys):
        """Test not yet valid certificate."""
        mock_datetime.datetime.now.return_value = datetime.datetime(2023, 12, 31, 0, 0, 0, tzinfo=datetime.timezone.utc)
        not_before = datetime.datetime(2024, 1, 1, 0, 0, 0)
        not_after = datetime.datetime(2024, 12, 31, 23, 59, 59)

        result = _check_cert_validity(not_before, not_after)

        assert result is False
        captured = capsys.readouterr()
        assert "Certificate is not valid for current date" in captured.out
