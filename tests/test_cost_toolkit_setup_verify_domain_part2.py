"""Comprehensive tests for verify_iwannabenewyork_domain.py - Part 2."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.setup.domain_verification_ssl import (
    _find_hosted_zone_for_domain,
    check_ssl_certificate,
    verify_canva_verification,
)
from cost_toolkit.scripts.setup.verify_iwannabenewyork_domain import (
    _print_nameservers,
    check_route53_configuration,
)


class TestCheckSslCertificate:
    """Tests for check_ssl_certificate function."""

    def test_valid_ssl_certificate(self):
        """Test valid SSL certificate check."""
        module_path = "cost_toolkit.scripts.setup.domain_verification_ssl"
        with (
            patch(f"{module_path}.ssl.create_default_context") as mock_create_ctx,
            patch(f"{module_path}.socket.create_connection") as mock_create_conn,
            patch(f"{module_path}._parse_cert_dates") as mock_parse_dates,
            patch(f"{module_path}._check_cert_validity") as mock_check_validity,
        ):
            mock_cert = {
                "subject": [(("commonName", "example.com"),)],
                "issuer": [(("organizationName", "Let's Encrypt"),)],
            }

            mock_socket = MagicMock()
            mock_ssl_socket = MagicMock()
            mock_ssl_socket.getpeercert.return_value = mock_cert

            mock_context = MagicMock()
            mock_context.wrap_socket.return_value.__enter__ = MagicMock(return_value=mock_ssl_socket)
            mock_context.wrap_socket.return_value.__exit__ = MagicMock(return_value=None)

            mock_create_ctx.return_value = mock_context
            mock_create_conn.return_value.__enter__ = MagicMock(return_value=mock_socket)
            mock_create_conn.return_value.__exit__ = MagicMock(return_value=None)

            mock_parse_dates.return_value = (
                datetime.datetime(2024, 1, 1),
                datetime.datetime(2024, 12, 31),
            )
            mock_check_validity.return_value = True

            result = check_ssl_certificate("example.com")

            assert result is True

    @patch("cost_toolkit.scripts.setup.domain_verification_ssl.ssl.create_default_context")
    @patch("cost_toolkit.scripts.setup.domain_verification_ssl.socket.create_connection")
    def test_no_certificate_received(self, mock_create_conn, mock_create_ctx, capsys):
        """Test when no certificate is received."""
        mock_socket = MagicMock()
        mock_ssl_socket = MagicMock()
        mock_ssl_socket.getpeercert.return_value = None

        mock_context = MagicMock()
        mock_context.wrap_socket.return_value.__enter__ = MagicMock(return_value=mock_ssl_socket)
        mock_context.wrap_socket.return_value.__exit__ = MagicMock(return_value=None)

        mock_create_ctx.return_value = mock_context
        mock_create_conn.return_value.__enter__ = MagicMock(return_value=mock_socket)
        mock_create_conn.return_value.__exit__ = MagicMock(return_value=None)

        result = check_ssl_certificate("example.com")

        assert result is False
        captured = capsys.readouterr()
        assert "No certificate received" in captured.out

    @patch("cost_toolkit.scripts.setup.domain_verification_ssl.socket.create_connection")
    def test_ssl_certificate_client_error(self, mock_create_conn, capsys):
        """Test SSL certificate check with ClientError."""
        mock_create_conn.side_effect = ClientError({"Error": {"Code": "SSLError", "Message": "SSL error"}}, "connect")

        result = check_ssl_certificate("example.com")

        assert result is False
        captured = capsys.readouterr()
        assert "SSL certificate check failed" in captured.out


class TestCanvaVerification:
    """Tests for verify_canva_verification function."""

    @patch("cost_toolkit.scripts.setup.domain_verification_ssl.BOTO3_AVAILABLE", True)
    @patch("cost_toolkit.scripts.setup.domain_verification_ssl._find_hosted_zone_for_domain")
    @patch("cost_toolkit.scripts.setup.domain_verification_ssl._boto3.client")
    def test_verify_canva_verification_found(self, mock_client, mock_find_zone, capsys):
        """Test Canva verification TXT record found."""
        mock_find_zone.return_value = {"Id": "/hostedzone/Z123", "Name": "example.com."}
        mock_client.return_value.list_resource_record_sets.return_value = {
            "ResourceRecordSets": [
                {
                    "Type": "TXT",
                    "Name": "_canva-domain-verify.example.com.",
                    "ResourceRecords": [{"Value": '"canva-verification-code-123"'}],
                }
            ]
        }

        result = verify_canva_verification("example.com")

        assert result is True
        captured = capsys.readouterr()
        assert "Canva verification TXT record found" in captured.out

    @patch("cost_toolkit.scripts.setup.domain_verification_ssl.BOTO3_AVAILABLE", True)
    @patch("cost_toolkit.scripts.setup.domain_verification_ssl._find_hosted_zone_for_domain")
    @patch("cost_toolkit.scripts.setup.domain_verification_ssl._boto3.client")
    def test_verify_canva_verification_not_found_no_output(self, mock_client, mock_find_zone, capsys):
        """Test Canva verification TXT record not found."""
        mock_find_zone.return_value = {"Id": "/hostedzone/Z123", "Name": "example.com."}
        mock_client.return_value.list_resource_record_sets.return_value = {"ResourceRecordSets": []}

        result = verify_canva_verification("example.com")

        assert result is False
        captured = capsys.readouterr()
        assert "No Canva verification TXT record found" in captured.out

    @patch("cost_toolkit.scripts.setup.domain_verification_ssl.BOTO3_AVAILABLE", True)
    @patch("cost_toolkit.scripts.setup.domain_verification_ssl._find_hosted_zone_for_domain")
    @patch("cost_toolkit.scripts.setup.domain_verification_ssl._boto3.client")
    def test_verify_canva_verification_not_found_error(self, mock_client, mock_find_zone):
        """Test Canva verification when hosted zone is missing."""
        mock_find_zone.return_value = None
        mock_client.return_value = MagicMock()

        result = verify_canva_verification("example.com")

        assert result is False

    @patch("cost_toolkit.scripts.setup.domain_verification_ssl.BOTO3_AVAILABLE", True)
    @patch("cost_toolkit.scripts.setup.domain_verification_ssl._find_hosted_zone_for_domain")
    @patch("cost_toolkit.scripts.setup.domain_verification_ssl._boto3.client")
    def test_verify_canva_verification_client_error(self, mock_client, mock_find_zone, capsys):
        """Test Canva verification with ClientError."""
        mock_find_zone.return_value = {"Id": "/hostedzone/Z123", "Name": "example.com."}
        mock_client.return_value.list_resource_record_sets.side_effect = ClientError(
            {"Error": {"Code": "Error", "Message": "DNS error"}}, "ListResourceRecordSets"
        )

        result = verify_canva_verification("example.com")

        assert result is False
        captured = capsys.readouterr()
        assert "Canva verification check failed" in captured.out


class TestFindHostedZoneForDomain:
    """Tests for _find_hosted_zone_for_domain function."""

    def test_find_existing_zone(self):
        """Test finding an existing hosted zone."""
        mock_route53 = MagicMock()
        mock_route53.list_hosted_zones.return_value = {
            "HostedZones": [
                {"Name": "example.com.", "Id": "/hostedzone/Z123"},
                {"Name": "other.com.", "Id": "/hostedzone/Z456"},
            ]
        }

        result = _find_hosted_zone_for_domain(mock_route53, "example.com")

        assert result == {"Name": "example.com.", "Id": "/hostedzone/Z123"}

    def test_find_zone_not_found(self):
        """Test when hosted zone is not found."""
        mock_route53 = MagicMock()
        mock_route53.list_hosted_zones.return_value = {"HostedZones": [{"Name": "other.com.", "Id": "/hostedzone/Z456"}]}

        result = _find_hosted_zone_for_domain(mock_route53, "example.com")

        assert result is None

    def test_find_zone_empty_list(self):
        """Test with empty hosted zones list."""
        mock_route53 = MagicMock()
        mock_route53.list_hosted_zones.return_value = {"HostedZones": []}

        result = _find_hosted_zone_for_domain(mock_route53, "example.com")

        assert result is None


class TestPrintNameservers:
    """Tests for _print_nameservers function."""

    def test_print_nameservers_found(self, capsys):
        """Test printing nameservers when found."""
        mock_route53 = MagicMock()
        mock_route53.list_resource_record_sets.return_value = {
            "ResourceRecordSets": [
                {
                    "Type": "NS",
                    "Name": "example.com.",
                    "ResourceRecords": [
                        {"Value": "ns1.example.com"},
                        {"Value": "ns2.example.com"},
                    ],
                }
            ]
        }

        _print_nameservers(mock_route53, "/hostedzone/Z123", "example.com")

        captured = capsys.readouterr()
        assert "ns1.example.com" in captured.out
        assert "ns2.example.com" in captured.out

    def test_print_nameservers_not_found(self, capsys):
        """Test when nameservers not found."""
        mock_route53 = MagicMock()
        mock_route53.list_resource_record_sets.return_value = {"ResourceRecordSets": [{"Type": "A", "Name": "example.com."}]}

        _print_nameservers(mock_route53, "/hostedzone/Z123", "example.com")

        captured = capsys.readouterr()
        assert "Nameservers configured" not in captured.out


class TestCheckRoute53Configuration:
    """Tests for check_route53_configuration function."""

    @patch("cost_toolkit.scripts.setup.verify_iwannabenewyork_domain.BOTO3_AVAILABLE", True)
    @patch("cost_toolkit.scripts.setup.verify_iwannabenewyork_domain._boto3.client")
    @patch("cost_toolkit.scripts.setup.verify_iwannabenewyork_domain._find_hosted_zone_for_domain")
    @patch("cost_toolkit.scripts.setup.verify_iwannabenewyork_domain._print_nameservers")
    def test_route53_configuration_found(self, _mock_print_ns, mock_find_zone, mock_boto_client, capsys):
        """Test successful Route53 configuration check."""
        mock_route53 = MagicMock()
        mock_boto_client.return_value = mock_route53
        mock_find_zone.return_value = {"Id": "/hostedzone/Z123", "Name": "example.com."}

        result = check_route53_configuration("example.com")

        assert result is True
        captured = capsys.readouterr()
        assert "Route53 hosted zone found: Z123" in captured.out

    @patch("cost_toolkit.scripts.setup.verify_iwannabenewyork_domain.BOTO3_AVAILABLE", True)
    @patch("cost_toolkit.scripts.setup.verify_iwannabenewyork_domain._boto3.client")
    @patch("cost_toolkit.scripts.setup.verify_iwannabenewyork_domain._find_hosted_zone_for_domain")
    def test_route53_configuration_not_found(self, mock_find_zone, mock_boto_client, capsys):
        """Test Route53 configuration when zone not found."""
        mock_route53 = MagicMock()
        mock_boto_client.return_value = mock_route53
        mock_find_zone.return_value = None

        result = check_route53_configuration("example.com")

        assert result is False
        captured = capsys.readouterr()
        assert "No Route53 hosted zone found" in captured.out

    @patch("cost_toolkit.scripts.setup.verify_iwannabenewyork_domain.BOTO3_AVAILABLE", False)
    def test_route53_configuration_boto3_unavailable(self, capsys):
        """Test Route53 check when boto3 is unavailable."""
        result = check_route53_configuration("example.com")

        assert result is False
        captured = capsys.readouterr()
        assert "boto3 not available" in captured.out

    @patch("cost_toolkit.scripts.setup.verify_iwannabenewyork_domain.BOTO3_AVAILABLE", True)
    @patch("cost_toolkit.scripts.setup.verify_iwannabenewyork_domain._boto3.client")
    def test_route53_configuration_client_error(self, mock_boto_client, capsys):
        """Test Route53 check with ClientError."""
        mock_boto_client.side_effect = ClientError({"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "list_hosted_zones")

        result = check_route53_configuration("example.com")

        assert result is False
        captured = capsys.readouterr()
        assert "Route53 check failed" in captured.out
