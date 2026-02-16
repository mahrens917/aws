#!/usr/bin/env python3
"""Clean up Route53 DNS records and hosted zones."""

from threading import Event

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.scripts.aws_utils import wait_for_route53_change

_WAIT_EVENT = Event()


def delete_health_check(health_check_id):
    """Delete a Route 53 health check"""
    print(f"\n🗑️  Deleting Health Check: {health_check_id}")
    print("=" * 80)

    try:
        route53 = create_client("route53")

        # Get health check details first
        try:
            hc_response = route53.get_health_check(HealthCheckId=health_check_id)
            hc_config = hc_response["HealthCheck"]["HealthCheckConfig"]
            hc_type = hc_config.get("Type")

            if hc_type in ["HTTP", "HTTPS"]:
                fqdn = hc_config.get("FullyQualifiedDomainName")
                port = hc_config.get("Port")
                path = hc_config.get("ResourcePath")
                target = f"{hc_type.lower()}://{fqdn}:{port}{path}"
                print(f"  Target: {target}")

            print(f"  Type: {hc_type}")

        except ClientError as e:
            print(f"  Warning: Could not get health check details: {e}")

        # Delete the health check
        route53.delete_health_check(HealthCheckId=health_check_id)
        print(f"  ✅ Health check {health_check_id} deleted successfully")
        print("  💰 Monthly savings: $0.50")

    except ClientError as e:
        print(f"  ❌ Error deleting health check {health_check_id}: {e}")
        return False

    return True


def delete_hosted_zone(zone_name, zone_id):
    """Delete a Route 53 hosted zone"""
    print(f"\n🗑️  Deleting Hosted Zone: {zone_name}")
    print("=" * 80)

    try:
        route53 = create_client("route53")

        print(f"  Zone ID: {zone_id}")
        print(f"  Zone Name: {zone_name}")

        # Step 1: Get all records in the zone
        print("  Step 1: Getting all DNS records...")
        records_response = route53.list_resource_record_sets(HostedZoneId=f"/hostedzone/{zone_id}")
        records = []
        if "ResourceRecordSets" in records_response:
            records = records_response["ResourceRecordSets"]

        # Step 2: Delete all records except NS and SOA (which can't be deleted)
        print("  Step 2: Deleting DNS records...")
        records_to_delete = []

        for record in records:
            record_type = record.get("Type")
            record_name = record.get("Name")

            # Skip NS and SOA records (these are managed by AWS and can't be deleted)
            if record_type in ["NS", "SOA"]:
                print(f"    Skipping {record_type} record: {record_name}")
                continue

            records_to_delete.append(record)
            print(f"    Will delete {record_type} record: {record_name}")

        # Delete records in batches
        if records_to_delete:
            print(f"  Deleting {len(records_to_delete)} DNS records...")

            # Create change batch
            changes = []
            for record in records_to_delete:
                changes.append({"Action": "DELETE", "ResourceRecordSet": record})

            # Submit the change batch
            change_batch = {
                "Comment": "Deleting all records before zone deletion",
                "Changes": changes,
            }

            try:
                change_response = route53.change_resource_record_sets(HostedZoneId=f"/hostedzone/{zone_id}", ChangeBatch=change_batch)

                change_id = change_response["ChangeInfo"]["Id"]
                print(f"    Change submitted: {change_id}")

                # Wait for changes to propagate
                print("    Waiting for DNS changes to propagate...")
                wait_for_route53_change(route53, change_id)
                print("    ✅ DNS records deleted successfully")

            except ClientError as e:
                print(f"    ❌ Error deleting DNS records: {e}")
                return False
        else:
            print("  No custom DNS records to delete")

        # Step 3: Delete the hosted zone
        print("  Step 3: Deleting hosted zone...")
        route53.delete_hosted_zone(Id=f"/hostedzone/{zone_id}")
        print(f"  ✅ Hosted zone {zone_name} deleted successfully")
        print("  💰 Monthly savings: $0.50")

    except ClientError as e:
        print(f"  ❌ Error deleting hosted zone {zone_name}: {e}")
        return False

    return True


def _print_cleanup_warning():
    """Print warning about what will be deleted."""
    print("\n⚠️  WARNING: This will delete:")
    print("  - 1 health check (monitoring satoshi.report)")
    print("  - 2 hosted zones (lucasahrens.com, iwannabenewyork.com)")
    print("  - All DNS records in those zones")
    print("")
    print("💰 Total monthly savings: $1.50")
    print("")
    print("🚨 IMPORTANT:")
    print("  - lucasahrens.com and iwannabenewyork.com will stop working")
    print("  - You'll need to set up DNS elsewhere if you want to use these domains")
    print("  - satoshi.report will remain fully functional")


def _delete_health_checks(health_check_id):
    """Delete health check and return results."""
    print("\n" + "=" * 80)
    print("DELETING HEALTH CHECK")
    print("=" * 80)
    hc_success = delete_health_check(health_check_id)
    return [("Health Check", hc_success)]


def _delete_zones(zones_to_delete):
    """Delete hosted zones and return results."""
    print("\n" + "=" * 80)
    print("DELETING HOSTED ZONES")
    print("=" * 80)

    results = []
    for zone_name, zone_id in zones_to_delete:
        zone_success = delete_hosted_zone(zone_name, zone_id)
        results.append((zone_name, zone_success))
        if zone_success:
            _WAIT_EVENT.wait(5)

    return results


def _print_successful_deletions(successful_deletions):
    """Print successful deletions."""
    print(f"✅ Successfully deleted: {len(successful_deletions)}")
    for item in successful_deletions:
        print(f"  {item}")


def _print_failed_deletions(failed_deletions):
    """Print failed deletions if any."""
    if not failed_deletions:
        return

    print(f"\n❌ Failed to delete: {len(failed_deletions)}")
    for item in failed_deletions:
        print(f"  {item}")


def _calculate_total_savings(results, zones_to_delete):
    """Calculate total monthly savings from deletions."""
    total_savings = 0

    if ("Health Check", True) in results:
        total_savings += 0.50

    for zone_name, _zone_id in zones_to_delete:
        if (zone_name, True) in results:
            total_savings += 0.50

    return total_savings


def _print_summary(results, zones_to_delete):
    """Print cleanup summary."""
    print("\n" + "=" * 80)
    print("🎯 CLEANUP SUMMARY")
    print("=" * 80)

    successful_deletions = [item for item, success in results if success]
    failed_deletions = [item for item, success in results if not success]

    _print_successful_deletions(successful_deletions)
    _print_failed_deletions(failed_deletions)

    return _calculate_total_savings(results, zones_to_delete)


def main():
    """Clean up Route53 DNS records."""
    print("AWS Route 53 Cleanup")
    print("=" * 80)
    print("Removing health check and specified hosted zones...")

    health_check_id = "ba40de25-4233-4d5c-83ee-2aa058f62fde"
    zones_to_delete = [
        ("lucasahrens.com.", "Z2UJB81SP0DSN5"),
        ("iwannabenewyork.com.", "Z02247451EYLYTZRVX4QB"),
    ]

    _print_cleanup_warning()

    results = []
    results.extend(_delete_health_checks(health_check_id))
    results.extend(_delete_zones(zones_to_delete))

    total_savings = _print_summary(results, zones_to_delete)
    successful_deletions = [item for item, success in results if success]

    print("\n💰 COST SAVINGS:")
    print(f"  Monthly savings: ${total_savings:.2f}")
    print(f"  Annual savings: ${total_savings * 12:.2f}")

    print("\n📊 REMAINING ROUTE 53 COSTS:")
    print("  satoshi.report hosted zone: $0.50/month")
    print("  DNS queries: ~$0.07/month")
    print("  New estimated total: ~$0.57/month (down from $1.57)")

    print("\n🔧 NEXT STEPS:")
    if successful_deletions:
        print("  1. lucasahrens.com and iwannabenewyork.com will stop resolving")
        print("  2. If you need these domains to work, set up DNS elsewhere:")
        print("     - Cloudflare (free)")
        print("     - Your domain registrar's DNS")
        print("     - Other DNS providers")
        print("  3. satoshi.report remains fully functional")


if __name__ == "__main__":
    main()
_WAIT_EVENT = Event()
