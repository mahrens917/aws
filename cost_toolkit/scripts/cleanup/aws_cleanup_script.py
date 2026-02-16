#!/usr/bin/env python3
"""
AWS Cleanup Script
Disables Global Accelerator and stops Lightsail instances to reduce costs.
"""

import sys
from pathlib import Path

from botocore.exceptions import ClientError

from cost_toolkit.common import lightsail_utils
from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.scripts.cleanup import aws_global_accelerator_cleanup as ga_cleanup

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cost_toolkit.scripts import aws_utils


def estimate_instance_cost(bundle_id: str) -> float:
    """Canonical Lightsail instance pricing lookup (fails on unknown bundles)."""
    return lightsail_utils.estimate_instance_cost(bundle_id)


def estimate_database_cost(bundle_id: str) -> float:
    """Canonical Lightsail database pricing lookup (fails on unknown bundles)."""
    return lightsail_utils.estimate_database_cost(bundle_id)


def disable_global_accelerators():
    """Disable all Global Accelerators via the canonical cleanup helpers."""
    aws_utils.setup_aws_credentials()

    print("🔍 Checking Global Accelerators...")
    print("=" * 60)

    accelerators = ga_cleanup.list_accelerators()
    if not accelerators:
        print("✅ No Global Accelerators found.")
        return 0

    disabled = 0
    for accelerator in accelerators:
        accelerator_arn = accelerator["AcceleratorArn"]
        accelerator_name = accelerator.get("Name")
        print(f"📍 Found accelerator: {accelerator_name}")
        print(f"   ARN: {accelerator_arn}")
        if not ga_cleanup.disable_accelerator(accelerator_arn):
            print(f"  ❌ Failed to disable Global Accelerator {accelerator_name}")
            continue
        disabled += 1
        print("-" * 40)
    return disabled


def _stop_instance(lightsail_client, instance):
    """Stop a single Lightsail instance."""
    instance_name = instance["name"]
    state = instance["state"]["name"]
    bundle_id = instance.get("bundleId")

    print(f"📦 Found instance: {instance_name}")
    print(f"   State: {state}")

    if state == "running":
        print(f"🛑 Stopping instance: {instance_name}")
        try:
            lightsail_client.stop_instance(instanceName=instance_name)
            if bundle_id:
                monthly_cost = estimate_instance_cost(bundle_id)
            else:
                monthly_cost = 0.0
            print(f"✅ Stopped instance {instance_name} (est. ${monthly_cost:.2f}/month)")
        except ClientError as exc:
            print(f"❌ Error stopping instance {instance_name}: {exc}")
        else:
            return 1, monthly_cost
    else:
        print(f"ℹ️  Instance {instance_name} is already {state}")

    print("-" * 30)
    return 0, 0.0


def _stop_database(lightsail_client, database):
    """Stop a single Lightsail database."""
    db_name = database["name"]
    db_state = database["state"]
    bundle_id = database.get("relationalDatabaseBundleId") if "relationalDatabaseBundleId" in database else None

    print(f"🗄️  Found database: {db_name}")
    print(f"   State: {db_state}")

    if db_state.lower() == "available":
        print(f"🛑 Stopping database: {db_name}")
        try:
            lightsail_client.stop_relational_database(relationalDatabaseName=db_name)
            monthly_cost = estimate_database_cost(bundle_id) if bundle_id else 0.0
            print(f"✅ Stopped database {db_name} (est. ${monthly_cost:.2f}/month)")
        except ClientError as exc:
            print(f"❌ Error stopping database {db_name}: {exc}")
        else:
            return 1, monthly_cost
    else:
        print(f"ℹ️  Database {db_name} is already {db_state}")

    print("-" * 30)
    return 0, 0.0


def _process_region(region):
    """Process Lightsail resources in a single region."""
    print(f"\n📍 Checking region: {region}")
    lightsail_client = create_client("lightsail", region=region)

    instances, databases = lightsail_utils.load_lightsail_resources(lightsail_client)

    if not instances and not databases:
        print(f"✅ No Lightsail resources found in {region}")
        return 0, 0, 0.0

    instances_stopped = 0
    databases_stopped = 0
    savings = 0.0

    for instance in instances:
        stopped, cost = _stop_instance(lightsail_client, instance)
        instances_stopped += stopped
        savings += cost

    for database in databases:
        stopped, cost = _stop_database(lightsail_client, database)
        databases_stopped += stopped
        savings += cost

    return instances_stopped, databases_stopped, savings


def stop_lightsail_instances():
    """Stop all Lightsail instances"""
    aws_utils.setup_aws_credentials()

    print("\n🔍 Checking Lightsail instances...")
    print("=" * 60)

    regions_to_check = ["eu-central-1", "us-east-1", "us-west-2", "eu-west-1"]
    total_instances_stopped = 0
    total_databases_stopped = 0
    estimated_monthly_savings = 0.0

    for region in regions_to_check:
        try:
            instances, databases, savings = _process_region(region)
            total_instances_stopped += instances
            total_databases_stopped += databases
            estimated_monthly_savings += savings
        except ClientError as exc:
            if "InvalidAction" in str(exc) or "not available" in str(exc):
                print(f"ℹ️  Lightsail not available in {region}")
            else:
                print(f"❌ Error accessing Lightsail in {region}: {exc}")

    return total_instances_stopped, total_databases_stopped, estimated_monthly_savings


def main():
    """Main function to run cleanup operations"""
    print("AWS Cost Optimization Cleanup")
    print("=" * 80)
    print("This script will:")
    print("1. Disable Global Accelerators")
    print("2. Stop Lightsail instances and databases")
    print("=" * 80)

    try:
        disabled_accelerators = disable_global_accelerators()
    except RuntimeError as exc:  # Fail fast on Global Accelerator errors
        print(f"❌ {exc}")
        return 1
    instances, databases, savings = stop_lightsail_instances()

    print("\n" + "=" * 80)
    print("🎉 Cleanup completed!")
    print(f"🛡️  Global Accelerators disabled: {disabled_accelerators}")
    print(f"📦 Lightsail instances stopped: {instances}")
    print(f"🗄️  Lightsail databases stopped: {databases}")
    print(f"💰 Estimated monthly savings from stopped resources: ${savings:.2f}")
    print("⏰ Changes may take a few minutes to take effect.")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    main()
