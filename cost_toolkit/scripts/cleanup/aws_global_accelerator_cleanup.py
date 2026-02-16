#!/usr/bin/env python3
"""
AWS Global Accelerator Cleanup Script
Disables and deletes all Global Accelerator resources to eliminate charges.
"""

from threading import Event

import boto3
from botocore.exceptions import ClientError

from ..aws_utils import setup_aws_credentials

MAX_ACCELERATOR_WAIT_SECONDS = 600
_WAIT_EVENT = Event()


def _get_ga_client():
    """Create a Global Accelerator client in us-west-2."""
    return boto3.client("globalaccelerator", region_name="us-west-2")


def list_accelerators():
    """List all Global Accelerators"""
    try:
        client = _get_ga_client()  # Global Accelerator is only in us-west-2
        response = client.list_accelerators()
        accelerators = []
        if "Accelerators" in response:
            accelerators = response["Accelerators"]
    except ClientError as e:
        print(f"❌ Error listing accelerators: {str(e)}")
        return []
    else:
        return accelerators


def disable_accelerator(accelerator_arn):
    """Disable a Global Accelerator"""
    try:
        client = _get_ga_client()

        # Check current status
        response = client.describe_accelerator(AcceleratorArn=accelerator_arn)
        current_status = response["Accelerator"]["Status"]
        current_enabled = response["Accelerator"]["Enabled"]

        print(f"  📊 Current status: {current_status}, Enabled: {current_enabled}")

        if current_enabled:
            print("  🔄 Disabling accelerator...")
            client.update_accelerator(AcceleratorArn=accelerator_arn, Enabled=False)
        else:
            print("  ✅ Accelerator already disabled")

        # Wait for accelerator to be in DEPLOYED state (not IN_PROGRESS)
        print("  ⏳ Waiting for accelerator to reach stable state...")
        max_wait_time = MAX_ACCELERATOR_WAIT_SECONDS  # 10 minutes
        wait_interval = 30  # 30 seconds
        elapsed_time = 0

        while elapsed_time < max_wait_time:
            response = client.describe_accelerator(AcceleratorArn=accelerator_arn)
            status = response["Accelerator"]["Status"]
            enabled = response["Accelerator"]["Enabled"]

            print(f"    Status: {status}, Enabled: {enabled} (waited {elapsed_time}s)")

            if status == "DEPLOYED" and not enabled:
                print("  ✅ Accelerator is disabled and ready for deletion")
                return True

            _WAIT_EVENT.wait(wait_interval)
            elapsed_time += wait_interval

        print("  ⚠️ Timeout waiting for accelerator to reach stable state")

    except ClientError as e:
        print(f"  ❌ Error disabling accelerator: {str(e)}")
        return False

    return False


def delete_listeners(accelerator_arn):
    """Delete all listeners for an accelerator"""
    try:
        client = _get_ga_client()

        # List listeners
        response = client.list_listeners(AcceleratorArn=accelerator_arn)
        listeners = []
        if "Listeners" in response:
            listeners = response["Listeners"]

        for listener in listeners:
            listener_arn = listener["ListenerArn"]
            print(f"  🗑️  Deleting listener: {listener_arn}")

            # First delete endpoint groups
            eg_response = client.list_endpoint_groups(ListenerArn=listener_arn)
            endpoint_groups = []
            if "EndpointGroups" in eg_response:
                endpoint_groups = eg_response["EndpointGroups"]

            for eg in endpoint_groups:
                eg_arn = eg["EndpointGroupArn"]
                print(f"    🗑️  Deleting endpoint group: {eg_arn}")
                client.delete_endpoint_group(EndpointGroupArn=eg_arn)

                # Wait for endpoint group deletion
                _WAIT_EVENT.wait(5)

            # Delete listener
            client.delete_listener(ListenerArn=listener_arn)
            print("  ✅ Deleted listener successfully")

    except ClientError as e:
        print(f"  ❌ Error deleting listeners: {str(e)}")
        return False

    return True


def delete_accelerator(accelerator_arn):
    """Delete a Global Accelerator"""
    try:
        client = _get_ga_client()

        print("  🗑️  Deleting accelerator...")
        client.delete_accelerator(AcceleratorArn=accelerator_arn)

        print("  ✅ Accelerator deletion initiated")
    except ClientError as e:
        print(f"  ❌ Error deleting accelerator: {str(e)}")
        return False

    return True


def process_single_accelerator(accelerator):
    """Process deletion of a single Global Accelerator"""
    accelerator_arn = accelerator["AcceleratorArn"]
    accelerator_name = accelerator.get("Name")
    accelerator_status = accelerator.get("Status")
    accelerator_enabled = accelerator.get("Enabled")

    print(f"\n📋 Processing Accelerator: {accelerator_name}")
    print(f"  ARN: {accelerator_arn}")
    print(f"  Status: {accelerator_status}")
    print(f"  Enabled: {accelerator_enabled}")

    # Calculate estimated cost
    # (Global Accelerator charges $0.025/hour = ~$18/month base + data transfer)
    estimated_monthly_cost = 18.0  # Base cost estimate

    success = True

    # Step 1: Always ensure accelerator is properly disabled and in stable state
    if not disable_accelerator(accelerator_arn):
        success = False
        return success, estimated_monthly_cost

    # Step 2: Delete listeners and endpoint groups
    if not delete_listeners(accelerator_arn):
        success = False
        return success, estimated_monthly_cost

    # Step 3: Delete accelerator
    if not delete_accelerator(accelerator_arn):
        success = False
        return success, estimated_monthly_cost

    if success:
        print(f"  ✅ Successfully deleted accelerator: {accelerator_name}")
    else:
        print(f"  ❌ Failed to delete accelerator: {accelerator_name}")

    return success, estimated_monthly_cost


def print_cleanup_summary(total_processed, total_deleted, monthly_savings):
    """Print cleanup summary with cost savings"""
    print("\n" + "=" * 80)
    print("🎯 CLEANUP SUMMARY")
    print("=" * 80)
    print(f"Total accelerators processed: {total_processed}")
    print(f"Successfully deleted: {total_deleted}")
    print(f"Estimated monthly savings: ${monthly_savings:.2f}")
    print(f"Estimated annual savings: ${monthly_savings * 12:.2f}")

    if total_deleted > 0:
        print("\n✅ SUCCESS: Global Accelerator cleanup completed!")
        print(f"💰 You will save approximately ${monthly_savings:.2f} per month")
        print("\n📋 IMPORTANT NOTES:")
        print("  - All accelerated traffic routing has been stopped")
        print("  - Applications using accelerator endpoints will need updates")
        print("  - Consider using CloudFront or ALB for traffic acceleration needs")
        print("  - Billing charges may take 24-48 hours to stop appearing")
    else:
        print("\n⚠️  No accelerators were successfully deleted")


def main():
    """Main cleanup function"""
    print("AWS Global Accelerator Cleanup")
    print("=" * 80)
    print("⚠️  WARNING: This will permanently delete ALL Global Accelerator resources!")
    print("⚠️  This action cannot be undone and will stop all accelerated traffic!")
    print("=" * 80)

    confirmation = input("Type 'DELETE' to confirm you want to delete all Global Accelerators: ")
    if confirmation != "DELETE":
        print("❌ Cleanup cancelled - confirmation not received")
        return

    # Setup credentials
    setup_aws_credentials()

    # List all accelerators
    print("\n🔍 Discovering Global Accelerators...")
    print("=" * 80)

    accelerators = list_accelerators()

    if not accelerators:
        print("✅ No Global Accelerators found - nothing to clean up")
        return

    total_deleted = 0
    monthly_savings = 0.0

    for accelerator in accelerators:
        success, cost = process_single_accelerator(accelerator)
        monthly_savings += cost
        if success:
            total_deleted += 1

    # Summary
    print_cleanup_summary(len(accelerators), total_deleted, monthly_savings)


if __name__ == "__main__":
    main()
