"""Route53 domain setup helper functions"""

from datetime import datetime, timezone

from cost_toolkit.scripts.aws_utils import wait_for_route53_change
from cost_toolkit.scripts.setup.exceptions import (
    HostedZoneNotFoundError,
    NSRecordsNotFoundError,
)


def _find_hosted_zone(route53, domain_name):
    """Find the hosted zone for the domain"""
    response = route53.list_hosted_zones()
    hosted_zones = response["HostedZones"]

    for zone in hosted_zones:
        if zone["Name"] == f"{domain_name}.":
            return zone

    raise HostedZoneNotFoundError(domain_name)


def _get_nameserver_records(route53, zone_id, domain_name):
    """Get nameserver records for the zone"""
    records_response = route53.list_resource_record_sets(HostedZoneId=zone_id)
    records = records_response["ResourceRecordSets"]

    for record in records:
        record_type = record.get("Type")
        record_name = record.get("Name")
        if record_type == "NS" and record_name == f"{domain_name}.":
            resource_records = []
            if "ResourceRecords" in record:
                resource_records = record["ResourceRecords"]
            return [rr.get("Value") for rr in resource_records]

    raise NSRecordsNotFoundError(domain_name)


def _check_root_a_record(record, domain_name):
    """Check if record is root domain A record and return IP."""
    record_type = record.get("Type")
    record_name = record.get("Name")
    if record_type != "A" or record_name != f"{domain_name}.":
        return False, None

    canva_ip = None
    if "ResourceRecords" in record:
        canva_ip = record["ResourceRecords"][0].get("Value")
        print(f"  ✅ Root domain A record: {canva_ip}")

    return True, canva_ip


def _check_www_a_record(record, domain_name):
    """Check if record is www subdomain A record."""
    record_type = record.get("Type")
    record_name = record.get("Name")
    if record_type != "A" or record_name != f"www.{domain_name}.":
        return False

    if "ResourceRecords" in record:
        www_ip = record["ResourceRecords"][0].get("Value")
        print(f"  ✅ WWW subdomain A record: {www_ip}")

    return True


def _check_canva_txt_record(record):
    """Check if record is Canva verification TXT record."""
    record_type = record.get("Type")
    record_name = record.get("Name")
    if record_type != "TXT" or not record_name or "_canva-domain-verify" not in record_name:
        return False

    if "ResourceRecords" in record:
        txt_value = record["ResourceRecords"][0].get("Value")
        print(f"  ✅ Canva verification TXT record: {txt_value}")

    return True


def _check_dns_records(records, domain_name):
    """Check for required DNS records"""
    has_root_a = False
    has_www_a = False
    has_canva_txt = False
    canva_ip = None

    for record in records:
        root_found, root_ip = _check_root_a_record(record, domain_name)
        if root_found:
            has_root_a = True
            canva_ip = root_ip

        if _check_www_a_record(record, domain_name):
            has_www_a = True

        if _check_canva_txt_record(record):
            has_canva_txt = True

    return has_root_a, has_www_a, has_canva_txt, canva_ip


def _print_dns_status(has_root_a, has_www_a, has_canva_txt):
    """Print DNS setup status summary"""
    print("\n📊 DNS Setup Status:")
    print(f"  Root domain (A record): {'✅' if has_root_a else '❌'}")
    print(f"  WWW subdomain (A record): {'✅' if has_www_a else '❌'}")
    print(f"  Canva verification (TXT): {'✅' if has_canva_txt else '❌'}")

    if has_root_a and has_www_a and has_canva_txt:
        print("  🎉 All required DNS records are present!")
        return True
    print("  ⚠️  Some DNS records are missing")
    return False


def _build_existing_records_map(records):
    """Build a map of existing DNS records for quick lookup"""
    existing_records = {}
    for record in records:
        record_name = record.get("Name")
        record_type = record.get("Type")
        key = f"{record_name}-{record_type}"
        existing_records[key] = record
    return existing_records


def _create_root_domain_change(domain_name, existing_records, canva_ip):
    """Create change for root domain A record if needed"""
    root_key = f"{domain_name}.-A"
    if root_key in existing_records:
        return None

    if not canva_ip:
        print("  ❌ Need Canva IP address to create root domain A record")
        return False

    print(f"  📝 Will create root domain A record: {domain_name} -> {canva_ip}")
    return {
        "Action": "CREATE",
        "ResourceRecordSet": {
            "Name": domain_name,
            "Type": "A",
            "TTL": 300,
            "ResourceRecords": [{"Value": canva_ip}],
        },
    }


def _create_www_subdomain_change(domain_name, existing_records, canva_ip):
    """Create change for www subdomain A record if needed"""
    www_key = f"www.{domain_name}.-A"
    if www_key in existing_records:
        return None

    if not canva_ip:
        print("  ❌ Need Canva IP address to create www subdomain A record")
        return False

    print(f"  📝 Will create www subdomain A record: www.{domain_name} -> {canva_ip}")
    return {
        "Action": "CREATE",
        "ResourceRecordSet": {
            "Name": f"www.{domain_name}",
            "Type": "A",
            "TTL": 300,
            "ResourceRecords": [{"Value": canva_ip}],
        },
    }


def _apply_dns_changes(route53, zone_id, changes):
    """Apply DNS changes and wait for propagation"""
    change_batch = {
        "Comment": (f"Creating missing DNS records for Canva setup - " f"{datetime.now(timezone.utc).isoformat()}"),
        "Changes": changes,
    }

    response = route53.change_resource_record_sets(HostedZoneId=f"/hostedzone/{zone_id}", ChangeBatch=change_batch)

    change_id = response["ChangeInfo"]["Id"]
    print(f"  ✅ DNS changes submitted (Change ID: {change_id})")

    # Wait for changes to propagate
    print("  ⏳ Waiting for DNS changes to propagate...")
    wait_for_route53_change(route53, change_id)
    print("  ✅ DNS changes completed successfully")


if __name__ == "__main__":
    raise SystemExit("This module only provides helpers; run aws_route53_domain_setup.py for the CLI workflow.")
