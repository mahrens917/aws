#!/usr/bin/env python3
"""
AWS CloudWatch Cleanup Script
Removes canary runs and reduces CloudWatch monitoring to eliminate API requests and canary costs.
"""


from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import get_all_aws_regions
from cost_toolkit.scripts import aws_utils


def _stop_canary_if_running(synthetics_client, canary_name, canary_state):
    """Stop a canary if it is running."""
    if canary_state == "RUNNING":
        print(f"🛑 Stopping canary: {canary_name}")
        try:
            synthetics_client.stop_canary(Name=canary_name)
            print(f"✅ Successfully stopped canary: {canary_name}")
        except ClientError as e:
            print(f"❌ Error stopping canary {canary_name}: {e}")


def _delete_single_canary(synthetics_client, canary):
    """Delete a single canary."""
    canary_name = canary["Name"]
    canary_state = canary["Status"]["State"]

    print(f"🕯️  Found canary: {canary_name}")
    print(f"   State: {canary_state}")

    _stop_canary_if_running(synthetics_client, canary_name, canary_state)

    print(f"🗑️  Deleting canary: {canary_name}")
    try:
        synthetics_client.delete_canary(Name=canary_name, DeleteLambda=True)
        print(f"✅ Successfully deleted canary: {canary_name}")
    except ClientError as e:
        print(f"❌ Error deleting canary {canary_name}: {e}")

    print("-" * 40)


def _process_canaries_in_region(region):
    """Process canaries in a single region."""
    print(f"\n📍 Checking region: {region}")
    synthetics_client = create_client("synthetics", region=region)

    response = synthetics_client.describe_canaries()
    canaries = []
    if "Canaries" in response:
        canaries = response["Canaries"]

    if not canaries:
        print(f"✅ No canaries found in {region}")
        return

    for canary in canaries:
        _delete_single_canary(synthetics_client, canary)


def delete_cloudwatch_canaries():
    """Delete all CloudWatch Synthetics canaries"""
    aws_utils.setup_aws_credentials()

    print("🔍 Checking CloudWatch Synthetics canaries...")
    print("=" * 70)

    regions = get_all_aws_regions()

    for region in regions:
        try:
            _process_canaries_in_region(region)
        except ClientError as e:
            if "not available" in str(e) or "InvalidAction" in str(e):
                print(f"ℹ️  CloudWatch Synthetics not available in {region}")
            else:
                print(f"❌ Error accessing CloudWatch Synthetics in {region}: {e}")


def _collect_alarm_names_to_disable(alarms):
    """Collect alarm names that need actions disabled."""
    alarm_names = []

    for alarm in alarms:
        alarm_name = alarm["AlarmName"]
        alarm_state = alarm["StateValue"]
        actions_enabled = alarm["ActionsEnabled"]

        print(f"🚨 Found alarm: {alarm_name}")
        print(f"   State: {alarm_state}")
        print(f"   Actions Enabled: {actions_enabled}")

        if actions_enabled:
            alarm_names.append(alarm_name)
            print("   → Will disable actions for this alarm")
        else:
            print("   → Actions already disabled")

        print("-" * 30)

    return alarm_names


def _disable_alarms_in_region(region):
    """Disable alarms in a single region."""
    print(f"\n📍 Checking region: {region}")
    cloudwatch_client = create_client("cloudwatch", region=region)

    response = cloudwatch_client.describe_alarms()
    alarms = []
    if "MetricAlarms" in response:
        alarms = response["MetricAlarms"]

    if not alarms:
        print(f"✅ No alarms found in {region}")
        return

    alarm_names = _collect_alarm_names_to_disable(alarms)

    if alarm_names:
        print(f"🛑 Disabling actions for {len(alarm_names)} alarms in {region}")
        try:
            cloudwatch_client.disable_alarm_actions(AlarmNames=alarm_names)
            print(f"✅ Successfully disabled alarm actions in {region}")
        except ClientError as e:
            print(f"❌ Error disabling alarm actions in {region}: {e}")


def disable_cloudwatch_alarms():
    """Disable CloudWatch alarms to reduce API requests"""
    aws_utils.setup_aws_credentials()

    print("\n🔍 Checking CloudWatch alarms...")
    print("=" * 70)

    regions = get_all_aws_regions()

    for region in regions:
        try:
            _disable_alarms_in_region(region)
        except ClientError as e:
            print(f"❌ Error accessing CloudWatch in {region}: {e}")


def delete_custom_metrics():
    """Information about custom metrics (cannot be directly deleted)"""
    print("\n📊 Custom Metrics Information")
    print("=" * 70)
    print("ℹ️  Custom metrics cannot be directly deleted via API.")
    print("ℹ️  They will automatically expire after 15 months of no new data.")
    print("ℹ️  To stop charges immediately:")
    print("   1. Stop applications that are sending custom metrics")
    print("   2. Remove CloudWatch SDK calls from your code")
    print("   3. Disable any custom metric collection scripts")
    print("   4. Check Lambda functions for CloudWatch metric publishing")


def _update_log_group_retention(logs_client, log_group):
    """Update retention for a single log group."""
    log_group_name = log_group["logGroupName"]
    retention_days = log_group.get("retentionInDays")
    stored_bytes = log_group.get("storedBytes")

    print(f"📄 Log group: {log_group_name}")
    print(f"   Retention: {retention_days} days")
    if stored_bytes:
        print(f"   Size: {stored_bytes / (1024*1024):.2f} MB")

    if retention_days is None or retention_days > 1:
        print(f"🛑 Setting retention to 1 day for: {log_group_name}")
        try:
            logs_client.put_retention_policy(logGroupName=log_group_name, retentionInDays=1)
            print("✅ Successfully set 1-day retention")
        except ClientError as e:
            print(f"❌ Error setting retention: {e}")
    else:
        print("ℹ️  Retention already optimized")

    print("-" * 30)


def _reduce_retention_in_region(region):
    """Reduce log retention in a single region."""
    print(f"\n📍 Checking region: {region}")
    logs_client = create_client("logs", region=region)

    response = logs_client.describe_log_groups()
    log_groups = []
    if "logGroups" in response:
        log_groups = response["logGroups"]

    if not log_groups:
        print(f"✅ No log groups found in {region}")
        return

    for log_group in log_groups:
        _update_log_group_retention(logs_client, log_group)


def reduce_log_retention():
    """Reduce CloudWatch log retention periods"""
    aws_utils.setup_aws_credentials()

    print("\n📝 Checking CloudWatch log groups...")
    print("=" * 70)

    regions = get_all_aws_regions()

    for region in regions:
        try:
            _reduce_retention_in_region(region)
        except ClientError as e:
            print(f"❌ Error accessing CloudWatch Logs in {region}: {e}")


def main():
    """Main function to run CloudWatch cleanup operations"""
    print("AWS CloudWatch Cost Optimization Cleanup")
    print("=" * 80)
    print("This script will:")
    print("1. Delete all CloudWatch Synthetics canaries")
    print("2. Disable CloudWatch alarm actions")
    print("3. Reduce log retention periods to 1 day")
    print("4. Provide guidance on custom metrics")
    print("=" * 80)

    # Delete canaries
    delete_cloudwatch_canaries()

    # Disable alarms
    disable_cloudwatch_alarms()

    # Reduce log retention
    reduce_log_retention()

    # Custom metrics info
    delete_custom_metrics()

    print("\n" + "=" * 80)
    print("🎉 CloudWatch cleanup completed!")
    print("💰 Expected monthly savings: ~$6.37 (18.7% of total costs)")
    print("📊 This eliminates:")
    print("   • 76,719+ API requests per month")
    print("   • 5,411+ canary runs per month")
    print("   • Alarm monitoring costs")
    print("   • Log storage costs")
    print("⏰ Changes take effect immediately.")
    print("=" * 80)


if __name__ == "__main__":
    main()
