"""SSL certificate and Canva verification helpers for domain checks."""

from __future__ import annotations

import datetime
import socket
import ssl
import types
import typing

from botocore.exceptions import ClientError

from cost_toolkit.scripts.setup.exceptions import CertificateInfoError

if typing.TYPE_CHECKING:
    import boto3 as _boto3_type

_boto3: types.ModuleType | None
try:
    import boto3 as _boto3
except ImportError:  # pragma: no cover - optional dependency for tests
    _boto3 = None

BOTO3_AVAILABLE = _boto3 is not None

# Certificate tuple structure indices
CERT_TUPLE_MIN_LENGTH = 2


def _extract_cert_dict(cert_items):
    """Extract dictionary from certificate tuple structure"""
    cert_dict = {}
    if cert_items:
        for item in cert_items:
            if len(item) >= 1 and len(item[0]) >= CERT_TUPLE_MIN_LENGTH:
                cert_dict[item[0][0]] = item[0][1]
    return cert_dict


def _parse_cert_dates(cert):
    """Parse certificate dates"""
    if not cert or "notBefore" not in cert or "notAfter" not in cert:
        raise CertificateInfoError()

    not_before = datetime.datetime.strptime(str(cert["notBefore"]), "%b %d %H:%M:%S %Y %Z")
    not_after = datetime.datetime.strptime(str(cert["notAfter"]), "%b %d %H:%M:%S %Y %Z")
    return not_before, not_after


def _print_cert_info(subject_dict, issuer_dict, not_before, not_after):
    """Print certificate information"""
    common_name = subject_dict.get("commonName")
    org_name = issuer_dict.get("organizationName")
    print(f"  ✅ Certificate Subject: {common_name}")
    print(f"  ✅ Certificate Issuer: {org_name}")
    print(f"  ✅ Valid From: {not_before.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  ✅ Valid Until: {not_after.strftime('%Y-%m-%d %H:%M:%S UTC')}")


def _check_cert_validity(not_before, not_after):
    """Check if certificate is currently valid"""
    now = datetime.datetime.utcnow()
    if not_before <= now <= not_after:
        days_until_expiry = (not_after - now).days
        print(f"  ✅ Certificate is valid ({days_until_expiry} days until expiry)")
        return True
    print("  ❌ Certificate is not valid for current date")
    return False


def check_ssl_certificate(domain):
    """Check SSL certificate details"""
    print(f"\n🛡️  Checking SSL certificate for {domain}")

    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()

                if cert is None:
                    print("  ❌ No certificate received")
                    return False

                cert_subject = cert.get("subject")
                cert_issuer = cert.get("issuer")
                subject_dict = _extract_cert_dict(cert_subject)
                issuer_dict = _extract_cert_dict(cert_issuer)
                not_before, not_after = _parse_cert_dates(cert)

                _print_cert_info(subject_dict, issuer_dict, not_before, not_after)
                return _check_cert_validity(not_before, not_after)

    except ClientError as e:
        print(f"  ❌ SSL certificate check failed: {e}")
        return False


def _is_canva_verification_record(record, domain):
    """Check if a record is the Canva verification TXT record."""
    record_type = record.get("Type")
    if record_type != "TXT":
        return False
    record_name = record.get("Name")
    if not record_name:
        return False
    return record_name.startswith(f"_canva-domain-verify.{domain}.")


def _extract_canva_record_values(record):
    """Extract Canva verification values from a TXT record."""
    resource_records = []
    if "ResourceRecords" in record:
        resource_records = record["ResourceRecords"]
    return [rr.get("Value").replace('"', "") for rr in resource_records]


def _find_hosted_zone_for_domain(route53, domain):
    """Find the Route53 hosted zone for a domain"""
    response = route53.list_hosted_zones()
    hosted_zones = []
    if "HostedZones" in response:
        hosted_zones = response["HostedZones"]

    for zone in hosted_zones:
        if zone["Name"] == f"{domain}.":
            return zone
    return None


def verify_canva_verification(domain):
    """Check if Canva domain verification is in place"""
    print(f"\n🎨 Checking Canva domain verification for {domain}")

    if not BOTO3_AVAILABLE:
        print("  ❌ boto3 not available, cannot verify Canva TXT record")
        return False

    try:
        assert _boto3 is not None
        route53 = _boto3.client("route53")
        hosted_zone = _find_hosted_zone_for_domain(route53, domain)
        if not hosted_zone:
            print(f"  ❌ No Route53 hosted zone found for {domain}")
            return False

        txt_records = route53.list_resource_record_sets(
            HostedZoneId=hosted_zone["Id"],
            StartRecordName=f"_canva-domain-verify.{domain}.",
            StartRecordType="TXT",
            MaxItems="5",
        )
        txt_record_sets = []
        if "ResourceRecordSets" in txt_records:
            txt_record_sets = txt_records["ResourceRecordSets"]

        for record in txt_record_sets:
            if not _is_canva_verification_record(record, domain):
                continue
            values = _extract_canva_record_values(record)
            if values:
                print(f"  ✅ Canva verification TXT record found: {', '.join(values)}")
                return True

    except ClientError as e:
        print(f"  ❌ Canva verification check failed: {e}")
        return False

    print("  ❌ No Canva verification TXT record found")
    return False


if __name__ == "__main__":  # pragma: no cover - script entry point
    pass
