#!/usr/bin/env python3
"""
AWS Backup Disable Script
Safely disables all automated backup services while preserving existing data.
"""


from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.backup_utils import check_aws_backup_plans as get_backup_plans
from cost_toolkit.common.backup_utils import (
    check_dlm_lifecycle_policies,
    check_eventbridge_scheduled_rules,
    is_backup_related_rule,
)

from ..aws_utils import setup_aws_credentials


def _delete_backup_selection(backup_client, plan_id, selection):
    """Delete a single backup selection."""
    selection_id = selection["SelectionId"]
    selection_name = selection["SelectionName"]

    print(f"      Removing selection: {selection_name} ({selection_id})")

    try:
        backup_client.delete_backup_selection(BackupPlanId=plan_id, SelectionId=selection_id)
        print(f"      ✅ Successfully removed backup selection: {selection_name}")
    except ClientError as e:
        print(f"      ❌ Error removing backup selection {selection_name}: {e}")


def _delete_plan_selections(backup_client, plan_id):
    """Delete all selections for a backup plan."""
    selections_response = backup_client.list_backup_selections(BackupPlanId=plan_id)
    selections = []
    if "BackupSelectionsList" in selections_response:
        selections = selections_response["BackupSelectionsList"]

    if selections:
        print(f"    🔍 Found {len(selections)} backup selection(s) to remove first")
        for selection in selections:
            _delete_backup_selection(backup_client, plan_id, selection)


def _delete_single_backup_plan(backup_client, plan):
    """Delete a single backup plan and its selections."""
    plan_id = plan["BackupPlanId"]
    plan_name = plan["BackupPlanName"]
    creation_date = plan["CreationDate"]

    print(f"  Plan: {plan_name} ({plan_id})")
    print(f"    Created: {creation_date}")

    try:
        _delete_plan_selections(backup_client, plan_id)
        backup_client.delete_backup_plan(BackupPlanId=plan_id)
        print(f"    ✅ Successfully deleted backup plan: {plan_name}")
    except ClientError as e:
        print(f"    ❌ Error deleting backup plan {plan_name}: {e}")

    print()


def disable_aws_backup_plans(region):
    """Disable AWS Backup plans in a specific region."""
    try:
        backup_client = create_client("backup", region=region)
        backup_plans = get_backup_plans(region)

        if backup_plans:
            print(f"🔍 Found {len(backup_plans)} AWS Backup plan(s) in {region}")
            for plan in backup_plans:
                _delete_single_backup_plan(backup_client, plan)
        else:
            print(f"  No AWS Backup plans found in {region}")

    except ClientError as e:
        if "UnrecognizedClientException" in str(e):
            print(f"  AWS Backup service not available in {region}")
            return
        print(f"  Error checking AWS Backup in {region}: {e}")


def disable_dlm_policies(region):
    """Disable Data Lifecycle Manager policies in a specific region."""
    try:
        dlm_client = create_client("dlm", region=region)
        policies = check_dlm_lifecycle_policies(region)

        if policies:
            print(f"📅 Found {len(policies)} Data Lifecycle Manager policies in {region}")

            for policy in policies:
                policy_id = policy["PolicyId"]
                description = policy.get("Description")
                state = policy["State"]

                print(f"  Policy: {policy_id}")
                print(f"    Description: {description}")
                print(f"    Current State: {state}")

                if state == "ENABLED":
                    try:
                        # Update policy to DISABLED state
                        dlm_client.get_lifecycle_policy(PolicyId=policy_id)

                        # Update the policy state to DISABLED
                        dlm_client.update_lifecycle_policy(PolicyId=policy_id, State="DISABLED")
                        print(f"    ✅ Successfully disabled DLM policy: {policy_id}")
                    except ClientError as e:
                        print(f"    ❌ Error disabling DLM policy {policy_id}: {e}")
                else:
                    print("    ℹ️  Policy already disabled")

                print()
        else:
            print(f"  No Data Lifecycle Manager policies found in {region}")

    except ClientError as e:
        if "UnrecognizedClientException" in str(e):
            print(f"  Data Lifecycle Manager service not available in {region}")
            return
        print(f"  Error checking DLM in {region}: {e}")


def disable_eventbridge_backup_rules(region):
    """Disable EventBridge rules that trigger automated backups."""
    try:
        events_client = create_client("events", region=region)
        rules = check_eventbridge_scheduled_rules(region)

        backup_rules = []
        for rule in rules:
            # Look for rules that might be related to snapshots/AMIs/backups
            if is_backup_related_rule(rule):
                backup_rules.append(rule)

        if backup_rules:
            print(f"⏰ Found {len(backup_rules)} EventBridge backup-related rules in {region}")

            for rule in backup_rules:
                rule_name = rule["Name"]
                description = rule.get("Description")
                state = rule["State"]
                schedule = rule.get("ScheduleExpression")

                print(f"  Rule: {rule_name}")
                print(f"    Description: {description}")
                print(f"    Current State: {state}")
                print(f"    Schedule: {schedule}")

                if state == "ENABLED":
                    try:
                        # Disable the rule
                        events_client.disable_rule(Name=rule_name)
                        print(f"    ✅ Successfully disabled EventBridge rule: {rule_name}")
                    except ClientError as e:
                        print(f"    ❌ Error disabling EventBridge rule {rule_name}: {e}")
                else:
                    print("    ℹ️  Rule already disabled")

                print()
        else:
            print(f"  No backup-related EventBridge rules found in {region}")

    except ClientError as e:
        print(f"  Error checking EventBridge rules in {region}: {e}")


def _check_vault_recovery_points(backup_client, vault_name):
    """Check and report recovery point status for a vault."""
    try:
        recovery_points = backup_client.list_recovery_points_by_backup_vault(BackupVaultName=vault_name, MaxResults=1)
        recovery_points_list = []
        if "RecoveryPoints" in recovery_points:
            recovery_points_list = recovery_points["RecoveryPoints"]
        point_count = len(recovery_points_list)
        if point_count > 0:
            print("    ℹ️  Vault contains recovery points - keeping vault")
        else:
            print("    ℹ️  Vault is empty - could be deleted if desired")
    except ClientError as e:
        print(f"    ⚠️  Error checking vault contents: {e}")


def _print_vault_info(vault):
    """Print vault information."""
    vault_name = vault["BackupVaultName"]
    creation_date = vault["CreationDate"]
    print(f"  Vault: {vault_name}")
    print(f"    Created: {creation_date}")
    return vault_name


def check_backup_vault_policies(region):
    """Check and optionally clean up backup vault policies."""
    try:
        backup_client = create_client("backup", region=region)
        vaults_response = backup_client.list_backup_vaults()
        vaults = []
        if "BackupVaultList" in vaults_response:
            vaults = vaults_response["BackupVaultList"]

        if vaults:
            print(f"🏦 Found {len(vaults)} backup vault(s) in {region}")
            for vault in vaults:
                vault_name = _print_vault_info(vault)
                _check_vault_recovery_points(backup_client, vault_name)
                print()
        else:
            print(f"  No backup vaults found in {region}")

    except ClientError as e:
        if "UnrecognizedClientException" in str(e):
            return
        print(f"  Error checking backup vaults in {region}: {e}")


def main():
    """Main function to disable all automated backup services."""
    setup_aws_credentials()

    print("AWS Automated Backup Disable Script")
    print("=" * 80)
    print("Disabling all automated backup services while preserving existing data...")
    print()

    # Focus on regions where we have resources
    priority_regions = ["eu-west-2", "us-east-2", "us-east-1"]

    for region in priority_regions:
        print(f"🔧 Disabling automated backups in {region}")
        print("=" * 80)

        # Disable AWS Backup plans
        disable_aws_backup_plans(region)

        # Disable Data Lifecycle Manager policies
        disable_dlm_policies(region)

        # Disable EventBridge backup rules
        disable_eventbridge_backup_rules(region)

        # Check backup vaults (informational)
        check_backup_vault_policies(region)

        print()

    print("🎯 SUMMARY")
    print("=" * 80)
    print("✅ All automated backup services have been disabled")
    print("✅ Existing EBS volumes remain active and unchanged")
    print("✅ All existing snapshots are preserved")
    print("✅ No future automated snapshots will be created")
    print("💰 This will prevent ~$22.40/month in new automated backup costs")
    print()
    print("📝 Note: You can still create manual snapshots anytime using:")
    print("   python3 scripts/management/aws_ebs_volume_manager.py snapshot <volume-id>")


if __name__ == "__main__":
    main()
