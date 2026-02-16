#!/usr/bin/env python3
"""Verify iwannabenewyork domain DNS and certificate configuration."""

from __future__ import annotations

import datetime
import sys
import types
import typing

from botocore.exceptions import ClientError

from cost_toolkit.scripts.setup.domain_verification_http import (
    verify_dns_resolution,
    verify_http_connectivity,
    verify_https_connectivity,
)
from cost_toolkit.scripts.setup.domain_verification_ssl import (
    BOTO3_AVAILABLE,
    _find_hosted_zone_for_domain,
    check_ssl_certificate,
    verify_canva_verification,
)

if typing.TYPE_CHECKING:
    import boto3 as _boto3_type

_boto3: types.ModuleType | None
try:
    import boto3 as _boto3
except ImportError:  # pragma: no cover - optional dependency for tests
    _boto3 = None

# Test success thresholds
MIN_TESTS_FOR_MOSTLY_WORKING = 4


def _print_nameservers(route53, zone_id, domain):
    """Print nameservers for the zone"""
    records_response = route53.list_resource_record_sets(HostedZoneId=zone_id)
    records = []
    if "ResourceRecordSets" in records_response:
        records = records_response["ResourceRecordSets"]

    for record in records:
        record_type = record.get("Type")
        record_name = record.get("Name")
        if record_type == "NS" and record_name == f"{domain}.":
            resource_records = []
            if "ResourceRecords" in record:
                resource_records = record["ResourceRecords"]
            nameservers = [rr.get("Value") for rr in resource_records]
            print("  ✅ Nameservers configured:")
            for ns in nameservers:
                print(f"    - {ns}")
            break


def check_route53_configuration(domain):
    """Check Route53 configuration"""
    print(f"\n☁️  Checking Route53 configuration for {domain}")

    if not BOTO3_AVAILABLE:
        print("  ❌ boto3 not available, cannot verify Route53 configuration")
        return False

    try:
        assert _boto3 is not None
        route53 = _boto3.client("route53")

        target_zone = _find_hosted_zone_for_domain(route53, domain)

        if not target_zone:
            print(f"  ❌ No Route53 hosted zone found for {domain}")
            return False

        zone_id = target_zone["Id"].split("/")[-1]
        print(f"  ✅ Route53 hosted zone found: {zone_id}")

        _print_nameservers(route53, target_zone["Id"], domain)

    except ClientError as e:
        print(f"  ❌ Route53 check failed: {e}")
        return False

    return True


def _run_tests(domain):
    """Run all verification tests"""
    tests = [
        ("DNS Resolution", lambda: verify_dns_resolution(domain)),
        ("HTTP Connectivity", lambda: verify_http_connectivity(domain)),
        ("HTTPS Connectivity", lambda: verify_https_connectivity(domain)),
        ("SSL Certificate", lambda: check_ssl_certificate(domain)),
        ("Canva Verification", lambda: verify_canva_verification(domain)),
        ("Route53 Configuration", lambda: check_route53_configuration(domain)),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            if test_name == "DNS Resolution":
                success, _ = test_func()
                results.append((test_name, success))
            else:
                success = test_func()
                results.append((test_name, success))
        except ClientError as e:
            print(f"  ❌ {test_name} failed with error: {e}")
            results.append((test_name, False))

    return results


def _print_summary(results, _domain):
    """Print verification summary"""
    print("\n" + "=" * 80)
    print("🎯 VERIFICATION SUMMARY")
    print("=" * 80)

    passed_tests = [name for name, success in results if success]
    failed_tests = [name for name, success in results if not success]

    print(f"✅ Passed tests: {len(passed_tests)}/{len(results)}")
    for test_name in passed_tests:
        print(f"  ✅ {test_name}")

    if failed_tests:
        print(f"\n❌ Failed tests: {len(failed_tests)}")
        for test_name in failed_tests:
            print(f"  ❌ {test_name}")

    return passed_tests, failed_tests


def _print_overall_status(domain, passed_tests, _failed_tests, total_tests):
    """Print overall verification status"""
    if len(passed_tests) == total_tests:
        print(f"\n🎉 SUCCESS: {domain} is fully configured and working!")
        print(f"🌐 Your Canva website is accessible at: https://{domain}")
        print("🔒 SSL certificate is valid and secure")
        print("☁️  DNS is properly configured through Route53")
    elif len(passed_tests) >= MIN_TESTS_FOR_MOSTLY_WORKING:
        print(f"\n✅ MOSTLY WORKING: {domain} is functional with minor issues")
        print(f"🌐 Your Canva website should be accessible at: https://{domain}")
        print("⚠️  Some non-critical tests failed - check details above")
    else:
        print(f"\n❌ ISSUES DETECTED: {domain} has significant problems")
        print("🔧 Please review the failed tests and fix the issues")


def main():
    """Run domain verification tests and report results."""
    domain = "iwannabenewyork.com"

    print("🚀 Domain Verification for iwannabenewyork.com")
    print("=" * 80)
    print(f"Testing domain: {domain}")
    print("Target: Canva website")
    print(f"Timestamp: {datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 80)

    results = _run_tests(domain)
    passed_tests, failed_tests = _print_summary(results, domain)
    _print_overall_status(domain, passed_tests, failed_tests, len(results))

    print(f"\n💡 To run this verification again: python3 {__file__}")

    return 0 if len(failed_tests) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
