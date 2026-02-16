#!/usr/bin/env python3
"""
AWS Lightsail Cleanup Script
Completely removes all Lightsail instances and databases to eliminate charges.
"""

import json
import os
from datetime import datetime
from threading import Event

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import get_all_aws_regions
from cost_toolkit.common.lightsail_utils import (
    UnknownBundleError,
    estimate_database_cost,
    estimate_instance_cost,
    load_lightsail_resources,
)

from ..aws_utils import setup_aws_credentials

_WAIT_EVENT = Event()


def _delete_instance(lightsail_client, instance):
    """Delete a single Lightsail instance."""
    instance_name = instance["name"]
    instance_state = instance["state"]["name"]
    bundle_id = instance.get("bundleId")

    print(f"\n📦 Found instance: {instance_name}")
    print(f"   State: {instance_state}")
    print(f"   Bundle: {bundle_id}")

    try:
        monthly_cost = estimate_instance_cost(bundle_id)
    except UnknownBundleError as e:
        print(f"⚠️  Unknown bundle for instance {instance_name}: {e}")
        monthly_cost = 0.0

    try:
        print(f"🗑️  Deleting instance: {instance_name}")
        lightsail_client.delete_instance(instanceName=instance_name, forceDeleteAddOns=True)
        print(f"✅ Successfully deleted instance: {instance_name}")
        if monthly_cost > 0:
            print(f"💰 Monthly savings: ${monthly_cost:.2f}")
        _WAIT_EVENT.wait(2)
    except ClientError as e:
        print(f"❌ Error deleting instance {instance_name}: {e}")
        return 0, 0.0
    return 1, monthly_cost


def _delete_database(lightsail_client, database):
    """Delete a single Lightsail database."""
    db_name = database["name"]
    db_state = database["state"]
    db_bundle = database.get("relationalDatabaseBundleId")

    print(f"\n🗄️  Found database: {db_name}")
    print(f"   State: {db_state}")
    print(f"   Bundle: {db_bundle}")

    try:
        monthly_cost = estimate_database_cost(db_bundle)
    except UnknownBundleError as e:
        print(f"⚠️  Unknown bundle for database {db_name}: {e}")
        monthly_cost = 0.0

    try:
        print(f"🗑️  Deleting database: {db_name}")
        lightsail_client.delete_relational_database(relationalDatabaseName=db_name, skipFinalSnapshot=True)
        print(f"✅ Successfully deleted database: {db_name}")
        if monthly_cost > 0:
            print(f"💰 Monthly savings: ${monthly_cost:.2f}")
        _WAIT_EVENT.wait(2)
    except ClientError as e:
        print(f"❌ Error deleting database {db_name}: {e}")
        return 0, 0.0
    return 1, monthly_cost


def _process_region(region):
    """Process Lightsail resources in a single region."""
    try:
        print(f"\n🔍 Checking region: {region}")
        lightsail_client = create_client("lightsail", region=region)

        instances, databases = load_lightsail_resources(lightsail_client)

        if not instances and not databases:
            print(f"✅ No Lightsail resources found in {region}")
            return 0, 0, 0.0

        instances_deleted = 0
        databases_deleted = 0
        region_savings = 0.0

        for instance in instances:
            deleted, cost = _delete_instance(lightsail_client, instance)
            instances_deleted += deleted
            region_savings += cost

        for database in databases:
            deleted, cost = _delete_database(lightsail_client, database)
            databases_deleted += deleted
            region_savings += cost

    except ClientError as e:
        if "InvalidAction" in str(e) or "not available" in str(e):
            print(f"ℹ️  Lightsail not available in {region}")
            return 0, 0, 0.0
        print(f"❌ Error accessing Lightsail in {region}: {e}")
        raise
    return instances_deleted, databases_deleted, region_savings


def _print_summary(total_instances_deleted, total_databases_deleted, total_savings):
    """Print cleanup summary."""
    print("\n" + "=" * 80)
    print("🎉 LIGHTSAIL CLEANUP COMPLETED")
    print("=" * 80)
    print(f"Instances deleted: {total_instances_deleted}")
    print(f"Databases deleted: {total_databases_deleted}")
    print(f"Total estimated monthly savings: ${total_savings:.2f}")

    if total_instances_deleted > 0 or total_databases_deleted > 0:
        print("\n📝 IMPORTANT NOTES:")
        print("• Lightsail resources are being deleted in the background")
        print("• It may take a few minutes for charges to stop")
        print("• Final bills may include partial charges for the current period")
        print("• All data has been permanently deleted")


def delete_lightsail_instances():
    """Delete all Lightsail instances across all regions"""
    setup_aws_credentials()

    print("🔍 LIGHTSAIL INSTANCE CLEANUP")
    print("=" * 80)
    print("⚠️  WARNING: This will DELETE ALL Lightsail instances and databases!")
    print("This action cannot be undone. All data will be lost.")
    print("=" * 80)

    lightsail_regions = get_all_aws_regions()

    total_instances_deleted = 0
    total_databases_deleted = 0
    total_savings = 0.0

    for region in lightsail_regions:
        instances, databases, savings = _process_region(region)
        total_instances_deleted += instances
        total_databases_deleted += databases
        total_savings += savings

    _print_summary(total_instances_deleted, total_databases_deleted, total_savings)

    if total_instances_deleted > 0 or total_databases_deleted > 0:
        record_cleanup_action("lightsail", total_instances_deleted + total_databases_deleted, total_savings)

    return total_instances_deleted, total_databases_deleted, total_savings


def record_cleanup_action(service, resources_deleted, savings):
    """Record cleanup action to prevent future optimization attempts"""
    cleanup_log = {
        "timestamp": datetime.now().isoformat(),
        "service": service,
        "action": "deleted_all_resources",
        "resources_deleted": resources_deleted,
        "estimated_monthly_savings": savings,
        "status": "completed",
    }

    # Create cleanup log file
    log_file = os.path.join(os.path.dirname(__file__), "..", "config", "cleanup_log.json")

    try:
        # Read existing log
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                log_data = json.load(f)
        else:
            log_data = {"cleanup_actions": []}

        # Add new action
        log_data["cleanup_actions"].append(cleanup_log)

        # Write updated log
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)

        print(f"📝 Cleanup action recorded in {log_file}")

    except ClientError as e:
        print(f"⚠️  Could not record cleanup action: {e}")


def main():
    """Main function"""
    print("AWS Lightsail Complete Cleanup")
    print("=" * 80)
    print("This script will DELETE ALL Lightsail instances and databases.")
    print("This will eliminate all Lightsail charges from your AWS account.")
    print("=" * 80)

    # Confirmation prompt
    response = input("\nAre you sure you want to delete ALL Lightsail resources? (type 'DELETE' to confirm): ")

    if response != "DELETE":
        print("❌ Cleanup cancelled. No resources were deleted.")
        return

    # Perform cleanup
    instances, databases, savings = delete_lightsail_instances()

    if instances == 0 and databases == 0:
        print("\n✅ No Lightsail resources found. Your account is already clean!")
    else:
        print(f"\n🎉 Cleanup completed! Estimated monthly savings: ${savings:.2f}")


if __name__ == "__main__":
    main()
