#!/usr/bin/env python3
"""
AWS Orphaned RDS Network Interface Cleanup Script
Deletes RDS network interfaces that are no longer attached to any RDS instances.
"""

import boto3
from botocore.exceptions import ClientError

from cost_toolkit.common.credential_utils import setup_aws_credentials

# Constants
EXPECTED_ORPHANED_INTERFACES_COUNT = 2
ORPHANED_INTERFACES = [
    {
        "region": "us-east-1",
        "interface_id": "eni-0a369310199dd8b96",
        "description": "RDSNetworkInterface",
        "public_ip": "18.213.133.185",
    },
    {
        "region": "us-east-1",
        "interface_id": "eni-01c2a771086939fe3",
        "description": "RDSNetworkInterface",
        "public_ip": "34.195.43.187",
    },
]


def _handle_deletion_error(error, interface_id, interface, deleted_interfaces, failed_deletions):
    """Handle errors during network interface deletion."""
    if not hasattr(error, "response"):
        print(f"   ❌ Unexpected error deleting {interface_id}: {str(error)}")
        failed_deletions.append({"interface": interface, "reason": str(error)})
        return
    error_code = error.response["Error"]["Code"]
    if error_code == "InvalidNetworkInterfaceID.NotFound":
        print(f"   ℹ️  Interface {interface_id} already deleted")
        deleted_interfaces.append(interface)
    elif error_code == "InvalidNetworkInterface.InUse":
        print(f"   ⚠️  Interface {interface_id} is in use - cannot delete")
        failed_deletions.append({"interface": interface, "reason": "In use"})
    else:
        message = error.response["Error"]["Message"]
        print(f"   ❌ Failed to delete {interface_id}: {message}")
        failed_deletions.append({"interface": interface, "reason": message})


def delete_orphaned_rds_network_interfaces(aws_access_key_id, aws_secret_access_key):
    """Delete orphaned RDS network interfaces"""

    print(f"🎯 Target: {len(ORPHANED_INTERFACES)} orphaned RDS network interfaces")
    print()

    deleted_interfaces = []
    failed_deletions = []

    for interface in ORPHANED_INTERFACES:
        region = interface["region"]
        interface_id = interface["interface_id"]

        try:
            ec2 = boto3.client(
                "ec2",
                region_name=region,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
            )

            print(f"🗑️  Deleting orphaned RDS interface: {interface_id} ({region})")
            print(f"   Public IP: {interface['public_ip']}")
            print(f"   Description: {interface['description']}")

            # Verify it's still orphaned before deletion
            eni = ec2.describe_network_interfaces(NetworkInterfaceIds=[interface_id])["NetworkInterfaces"][0]

            # Check if it has any attachments
            attachment = {}
            if "Attachment" in eni:
                attachment = eni["Attachment"]
            instance_id = attachment.get("InstanceId")
            if attachment and instance_id:
                print(f"   ⚠️  Interface is now attached to {instance_id} - skipping")
                continue

            # Delete the network interface
            ec2.delete_network_interface(NetworkInterfaceId=interface_id)

            print(f"   ✅ Successfully deleted {interface_id}")
            deleted_interfaces.append(interface)

        except (ClientError, Exception) as e:
            _handle_deletion_error(e, interface_id, interface, deleted_interfaces, failed_deletions)

        print()

    return deleted_interfaces, failed_deletions


def main():
    """Main execution function"""
    print("AWS Orphaned RDS Network Interface Cleanup")
    print("=" * 60)
    print("Cleaning up RDS network interfaces from deleted RDS instances...")
    print()

    try:
        # Load credentials
        aws_access_key_id, aws_secret_access_key = setup_aws_credentials()

        print("⚠️  IMPORTANT: This will delete orphaned RDS network interfaces")
        print("   • These interfaces are from deleted RDS instances")
        print("   • No active RDS instances/clusters found in audit")
        print("   • This will free up public IP addresses")
        print("   • No cost savings but improves account hygiene")
        print()

        confirmation = input("Type 'DELETE ORPHANED RDS INTERFACES' to proceed: ")

        if confirmation != "DELETE ORPHANED RDS INTERFACES":
            print("❌ Operation cancelled - confirmation text did not match")
            return

        print("\n🚨 Proceeding with orphaned RDS network interface cleanup...")
        print("=" * 60)

        # Delete orphaned interfaces
        deleted_interfaces, failed_deletions = delete_orphaned_rds_network_interfaces(aws_access_key_id, aws_secret_access_key)

        # Summary
        print("=" * 60)
        print("🎯 ORPHANED RDS NETWORK INTERFACE CLEANUP SUMMARY")
        print("=" * 60)
        print(f"✅ Successfully deleted: {len(deleted_interfaces)} interfaces")
        print(f"❌ Failed deletions: {len(failed_deletions)} interfaces")
        print()

        if deleted_interfaces:
            print("✅ Successfully deleted interfaces:")
            for interface in deleted_interfaces:
                print(f"   🗑️  {interface['interface_id']} ({interface['region']}) - " f"{interface['public_ip']}")

        if failed_deletions:
            print("\n❌ Failed deletions:")
            for failure in failed_deletions:
                interface = failure["interface"]
                reason = failure["reason"]
                print(f"   ❌ {interface['interface_id']} ({interface['region']}) - {reason}")

        if len(deleted_interfaces) == EXPECTED_ORPHANED_INTERFACES_COUNT:
            print("\n🎉 Orphaned RDS network interface cleanup completed!")
            print(f"   • Freed up {EXPECTED_ORPHANED_INTERFACES_COUNT} public IP addresses")
            print("   • Improved account security hygiene")
            print("   • Cleaned up remnants from deleted RDS instances")

    except ClientError as e:
        print(f"❌ Critical error during cleanup: {str(e)}")
        raise


if __name__ == "__main__":
    main()
