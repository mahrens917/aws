#!/usr/bin/env python3
"""
AWS Network Interface Deep Audit Script
Investigates network interfaces that appear to be orphaned or attached to non-existent instances.
"""

import boto3
from botocore.exceptions import ClientError

from cost_toolkit.common.credential_utils import setup_aws_credentials


def _print_basic_eni_info(eni):
    """Print basic ENI information."""
    status = eni["Status"]
    interface_type = eni.get("InterfaceType")
    description = eni.get("Description")
    vpc_id = eni.get("VpcId")
    subnet_id = eni.get("SubnetId")

    print(f"   Status: {status}")
    print(f"   Type: {interface_type}")
    print(f"   Description: {description}")
    print(f"   VPC: {vpc_id}")
    print(f"   Subnet: {subnet_id}")


def _check_instance_attachment(ec2, attachment):
    """Check if attached instance exists and is valid."""
    instance_id = attachment.get("InstanceId")
    attachment_status = attachment.get("Status")
    attach_time = attachment.get("AttachTime")

    print(f"   Attachment Status: {attachment_status}")
    print(f"   Attached Instance: {instance_id}")
    print(f"   Attach Time: {attach_time}")

    if not instance_id:
        return None

    try:
        instance_response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = instance_response["Reservations"][0]["Instances"][0]
        instance_state = instance["State"]["Name"]
        instance_type = instance.get("InstanceType")

        print(f"   ✅ Instance exists: {instance_id}")
        print(f"   Instance State: {instance_state}")
        print(f"   Instance Type: {instance_type}")

        if instance_state in ["terminated", "shutting-down"]:
            print(f"   ⚠️  Instance is {instance_state} - ENI may be orphaned")
            return "orphaned"
        if instance_state in ["stopped", "stopping"]:
            print(f"   ⚠️  Instance is {instance_state} - ENI attached to stopped instance")
            return "attached_stopped"

    except ec2.exceptions.ClientError as e:
        if "InvalidInstanceID.NotFound" in str(e):
            print(f"   ❌ Instance {instance_id} does not exist - ENI is orphaned!")
            return "orphaned"
        print(f"   ❌ Error checking instance: {str(e)}")
        return "error"

    print("   ✅ Instance is active")
    return "active"


def _check_detached_eni(eni):
    """Check status of a detached ENI."""
    print("   ⚠️  No attachment information - likely detached")

    interface_type = eni.get("InterfaceType")
    if interface_type != "interface":
        print(f"   ℹ️  Special interface type: {interface_type}")
        return "aws_service"

    association = eni.get("Association")
    if association:
        public_ip = association.get("PublicIp")
        allocation_id = association.get("AllocationId")
        print(f"   🌐 Public IP: {public_ip}")
        print(f"   🏷️  EIP Allocation: {allocation_id}")
        return "eip_attached"

    return "detached"


def investigate_network_interface(region_name, interface_id, aws_access_key_id, aws_secret_access_key):
    """Deep investigation of a specific network interface"""
    try:
        ec2 = boto3.client(
            "ec2",
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        response = ec2.describe_network_interfaces(NetworkInterfaceIds=[interface_id])
        eni = response["NetworkInterfaces"][0]

        print(f"\n🔍 Deep Analysis: {interface_id}")
        print("-" * 50)

        _print_basic_eni_info(eni)

        attachment = eni.get("Attachment")
        if attachment:
            return _check_instance_attachment(ec2, attachment)
        return _check_detached_eni(eni)

    except ClientError as e:
        print(f"❌ Error investigating {interface_id}: {str(e)}")
        return "error"


def main():
    """Main execution function"""
    print("AWS Network Interface Deep Audit")
    print("=" * 60)

    try:
        # Load credentials
        aws_access_key_id, aws_secret_access_key = setup_aws_credentials()

        # Suspicious network interfaces from previous audit
        suspicious_interfaces = [
            # us-east-1: "Not attached" but "in-use"
            {"region": "us-east-1", "id": "eni-0a369310199dd8b96"},
            {"region": "us-east-1", "id": "eni-01c2a771086939fe3"},
            # eu-west-2: Attached to instances that may not exist
            {"region": "eu-west-2", "id": "eni-04933185523bf68c7"},
            {"region": "eu-west-2", "id": "eni-01f92363be8241c0d"},
            # us-east-2: Check this one too
            {"region": "us-east-2", "id": "eni-070796a225e04cb80"},
        ]

        print(f"🔍 Investigating {len(suspicious_interfaces)} network interfaces...")

        cleanup_candidates = []
        active_interfaces = []

        for interface in suspicious_interfaces:
            region = interface["region"]
            eni_id = interface["id"]

            result = investigate_network_interface(region, eni_id, aws_access_key_id, aws_secret_access_key)

            if result in ["orphaned", "detached"]:
                cleanup_candidates.append({"region": region, "id": eni_id, "reason": result})
            elif result in ["active", "attached_stopped"]:
                active_interfaces.append({"region": region, "id": eni_id, "status": result})

        print("\n" + "=" * 60)
        print("🎯 DEEP AUDIT SUMMARY")
        print("=" * 60)

        if cleanup_candidates:
            print(f"🗑️  Network interfaces that can be deleted: {len(cleanup_candidates)}")
            print()
            for candidate in cleanup_candidates:
                print(f"   🗑️  {candidate['id']} ({candidate['region']}) - {candidate['reason']}")

            print("\n💡 CLEANUP RECOMMENDATIONS:")
            print("   • These network interfaces appear to be orphaned or unused")
            print("   • Deleting them will improve account hygiene")
            print("   • No cost savings but better security posture")
            print("   • Create cleanup script for safe deletion")

        if active_interfaces:
            print(f"\n✅ Active/legitimate network interfaces: {len(active_interfaces)}")
            for interface in active_interfaces:
                print(f"   ✅ {interface['id']} ({interface['region']}) - {interface['status']}")

        if not cleanup_candidates:
            print("🎉 No orphaned network interfaces found!")
            print("   All network interfaces are properly attached and in use.")

    except ClientError as e:
        print(f"❌ Critical error during deep audit: {str(e)}")
        raise


if __name__ == "__main__":
    main()
