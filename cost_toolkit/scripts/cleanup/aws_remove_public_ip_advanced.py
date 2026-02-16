#!/usr/bin/env python3
"""Advanced removal of public IP addresses from EC2 instances."""

import sys

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.scripts import aws_utils
from cost_toolkit.scripts.aws_utils import get_instance_info
from cost_toolkit.scripts.cleanup import aws_remove_public_ip as basic_remove
from cost_toolkit.scripts.cleanup.public_ip_common import (
    delay,
    fetch_instance_network_details,
    wait_for_state,
)


def _get_instance_details(_ec2, instance_id, region_name):
    """Get current instance details."""
    print("Step 1: Getting instance details...")
    details = fetch_instance_network_details(instance_id, region_name, instance_fetcher=get_instance_info)
    if not details.current_eni_id:
        raise RuntimeError("Instance has no primary network interface; cannot remove public IP.")

    print(f"  Current state: {details.state}")
    print(f"  Current public IP: {details.public_ip}")
    print(f"  VPC: {details.vpc_id}")
    print(f"  Subnet: {details.subnet_id}")
    print(f"  Security Groups: {details.security_groups}")
    print(f"  Current ENI: {details.current_eni_id}")

    return details


def _stop_instance(ec2, instance_id, current_state):
    """Stop the instance if running."""
    if current_state == "running":
        print(f"Step 2: Stopping instance {instance_id}...")
        ec2.stop_instances(InstanceIds=[instance_id])
        wait_for_state(ec2, instance_id, "instance_stopped")
        print("  ✅ Instance stopped")


def _create_new_eni(ec2, subnet_id, security_groups, instance_id):
    """Create a new network interface without public IP."""
    print("Step 3: Creating new network interface without public IP...")
    try:
        new_eni_response = ec2.create_network_interface(
            SubnetId=subnet_id,
            Groups=security_groups,
            Description=f"Replacement ENI for {instance_id} - no public IP",
        )
        new_eni_id = new_eni_response["NetworkInterface"]["NetworkInterfaceId"]
        print(f"  ✅ Created new ENI: {new_eni_id}")
        delay(5)
    except ClientError as e:
        print(f"  ❌ Error creating new ENI: {e}")
        return None
    return new_eni_id


def _replace_eni(ec2, instance_id, current_eni, new_eni_id):
    """Detach current ENI and attach new one."""
    print("Step 4: Detaching current network interface...")
    try:
        attachment_id = current_eni["Attachment"]["AttachmentId"]
        ec2.detach_network_interface(AttachmentId=attachment_id, Force=True)
        print(f"  ✅ Detached ENI {current_eni['NetworkInterfaceId']}")
        delay(10)
    except ClientError as e:
        print(f"  ❌ Error detaching ENI: {e}")
        return False

    print("Step 5: Attaching new network interface...")
    try:
        ec2.attach_network_interface(NetworkInterfaceId=new_eni_id, InstanceId=instance_id, DeviceIndex=0)
        print(f"  ✅ Attached new ENI {new_eni_id}")
        delay(10)
    except ClientError as e:
        print(f"  ❌ Error attaching new ENI: {e}")
        return False
    return True


def _verify_and_cleanup(ec2, instance_id, current_eni_id, region_name):
    """Verify public IP removal and clean up old ENI."""
    print("Step 7: Verifying public IP removal...")
    delay(10)

    updated_instance = get_instance_info(instance_id, region_name)
    new_public_ip = updated_instance.get("PublicIpAddress")

    if new_public_ip:
        print(f"  ❌ Instance still has public IP: {new_public_ip}")
        return False

    print("  ✅ Public IP successfully removed")
    print("Step 8: Cleaning up old network interface...")
    try:
        ec2.delete_network_interface(NetworkInterfaceId=current_eni_id)
        print(f"  ✅ Deleted old ENI {current_eni_id}")
    except ClientError as e:
        print(f"  ⚠️  Could not delete old ENI {current_eni_id}: {e}")

    return True


def remove_public_ip_by_network_interface_replacement(instance_id, region_name):
    """Remove public IP by creating a new network interface without public IP"""
    print(f"\n🔧 Advanced method: Replacing network interface for {instance_id}")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)
        details = _get_instance_details(ec2, instance_id, region_name)

        if not details.public_ip:
            print(f"✅ Instance {instance_id} already has no public IP")
            return True

        _stop_instance(ec2, instance_id, details.state)

        new_eni_id = _create_new_eni(ec2, details.subnet_id, details.security_groups, instance_id)
        if not new_eni_id:
            return False

        if not _replace_eni(ec2, instance_id, details.current_eni, new_eni_id):
            try:
                ec2.delete_network_interface(NetworkInterfaceId=new_eni_id)
            except ClientError as e:
                print(f"  ⚠️  Failed to clean up ENI {new_eni_id}: {e}")
            return False

        print("Step 6: Starting instance...")
        try:
            ec2.start_instances(InstanceIds=[instance_id])
            wait_for_state(ec2, instance_id, "instance_running")
            print("  ✅ Instance started")
        except ClientError as e:
            print(f"  ❌ Error starting instance: {e}")
            return False

        return _verify_and_cleanup(ec2, instance_id, details.current_eni_id, region_name)

    except ClientError as e:
        print(f"❌ Error in advanced public IP removal: {e}")
        return False


def simple_stop_start_without_public_ip(instance_id, region_name):
    """Simple approach: just stop instance and start in private subnet mode"""
    print("\n🔧 Simple method: Stop/start with private-only configuration")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)

        # Get instance details
        instance = get_instance_info(instance_id, region_name)
        subnet_id = instance["SubnetId"]

        print("Step 1: Ensuring subnet doesn't auto-assign public IPs...")

        # Make sure subnet doesn't auto-assign public IPs
        ec2.modify_subnet_attribute(SubnetId=subnet_id, MapPublicIpOnLaunch={"Value": False})
        print(f"  ✅ Subnet {subnet_id} set to not auto-assign public IPs")

        print("Step 2: Stopping instance...")
        ec2.stop_instances(InstanceIds=[instance_id])

        wait_for_state(ec2, instance_id, "instance_stopped")
        print("  ✅ Instance stopped")

        print("Step 3: Starting instance (should get no public IP)...")
        ec2.start_instances(InstanceIds=[instance_id])

        wait_for_state(ec2, instance_id, "instance_running")
        print("  ✅ Instance started")

        # Verify
        delay(10)
        updated_instance = get_instance_info(instance_id, region_name)
        new_public_ip = updated_instance.get("PublicIpAddress")

        if new_public_ip:
            print(f"  ❌ Instance still has public IP: {new_public_ip}")
            return False

    except ClientError as e:
        print(f"❌ Error in simple public IP removal: {e}")
        return False

    print("  ✅ Public IP successfully removed")
    return True


def main():
    """Remove public IP addresses using advanced techniques."""
    print("AWS Advanced Public IP Removal")
    print("=" * 80)

    instance_id, region_name, using_default = basic_remove.parse_args()  # Reuse standard CLI
    if using_default:
        print("⚠️  Using defaults from config/public_ip_defaults.json; provide --instance-id/--region to override.")

    aws_utils.setup_aws_credentials()

    print("\n" + "=" * 80)
    print("ATTEMPTING STANDARD METHOD")
    print("=" * 80)
    success = basic_remove.remove_public_ip_from_instance(instance_id, region_name)

    if not success:
        print("\n" + "=" * 80)
        print("ATTEMPTING SIMPLE STOP/START METHOD")
        print("=" * 80)
        success = simple_stop_start_without_public_ip(instance_id, region_name)

    if not success:
        print("\n" + "=" * 80)
        print("ATTEMPTING ADVANCED METHOD")
        print("=" * 80)
        success = remove_public_ip_by_network_interface_replacement(instance_id, region_name)

    # Final summary
    print("\n" + "=" * 80)
    print("🎯 FINAL RESULT")
    print("=" * 80)

    if success:
        print(f"✅ Successfully removed public IP from {instance_id}")
        print("💰 Monthly savings: $3.60")
        print("🔧 Connection method: AWS Systems Manager")
        print(f"   Command: aws ssm start-session --target {instance_id} --region {region_name}")
        print("📍 Instance now has private IP only")
    else:
        print(f"❌ Failed to remove public IP from {instance_id}")
        print("💡 The instance may need manual intervention via AWS Console")
        print("   1. Stop the instance")
        print("   2. Actions -> Networking -> Change subnet (to a private subnet)")
        print("   3. Start the instance")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
