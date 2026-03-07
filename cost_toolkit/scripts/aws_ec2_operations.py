#!/usr/bin/env python3
"""
AWS EC2 Operations Module
Common EC2 API operations extracted to reduce code duplication.
"""

from typing import Optional

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_ec2_client
from cost_toolkit.common.aws_common import find_resource_region
from cost_toolkit.common.aws_common import (
    get_all_aws_regions,
    get_common_regions_extended,
    get_instance_name,
)
from cost_toolkit.scripts.aws_security import delete_security_group as delete_security_group_shared
from cost_toolkit.scripts.ec2_describe_ops import (
    describe_addresses,
    describe_network_interfaces,
    describe_security_groups,
    describe_snapshots,
    describe_volumes,
)


get_all_regions = get_all_aws_regions


def get_common_regions() -> list[str]:
    """Get list of commonly used AWS regions for cost optimization."""
    regions = get_common_regions_extended()
    return regions


__all__ = [
    "get_all_regions",
    "get_common_regions",
    "get_instance_name",
    "describe_instance",
    "find_resource_region",
    "delete_snapshot",
    "terminate_instance",
    "describe_addresses",
    "describe_network_interfaces",
    "describe_security_groups",
    "describe_snapshots",
    "describe_volumes",
]


def describe_instance(
    region: str,
    instance_id: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> dict:
    """Get detailed information about a single EC2 instance."""
    ec2_client = create_ec2_client(
        region=region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    return response["Reservations"][0]["Instances"][0]


def delete_snapshot(
    snapshot_id: str,
    region: str,
    verbose: bool = False,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    ec2_client=None,
) -> bool:
    """Delete an EBS snapshot."""
    try:
        client = ec2_client or create_ec2_client(
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        if verbose:
            # Get snapshot info first
            response = client.describe_snapshots(SnapshotIds=[snapshot_id])
            snapshot = response["Snapshots"][0]
            size_gb = snapshot["VolumeSize"]
            description = snapshot.get("Description")
            start_time = snapshot["StartTime"]
            monthly_cost = size_gb * 0.05

            print(f"🔍 Snapshot to delete: {snapshot_id}")
            print(f"   Size: {size_gb} GB")
            print(f"   Created: {start_time}")
            print(f"   Description: {description}")
            print(f"   Estimated monthly cost: ${monthly_cost:.2f}")

        print(f"🗑️  Deleting snapshot: {snapshot_id} in {region}")
        client.delete_snapshot(SnapshotId=snapshot_id)
        print(f"   ✅ Successfully deleted {snapshot_id}")
    except ClientError as e:
        error_code = e.response["Error"]["Code"] if hasattr(e, "response") and "Code" in e.response["Error"] else None
        if error_code == "InvalidSnapshot.NotFound":
            print(f"   ℹ️  Snapshot {snapshot_id} not found in {region}")
            return False
        print(f"   ❌ Error deleting {snapshot_id}: {e}")
        return False
    return True


def terminate_instance(
    region: str,
    instance_id: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> bool:
    """
    Terminate an EC2 instance.

    Args:
        region: AWS region name
        instance_id: EC2 instance ID
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        ec2_client = create_ec2_client(
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        print(f"🗑️  Terminating instance: {instance_id}")
        response = ec2_client.terminate_instances(InstanceIds=[instance_id])

        current_state = response["TerminatingInstances"][0]["CurrentState"]["Name"]
        previous_state = response["TerminatingInstances"][0]["PreviousState"]["Name"]

        print(f"   State change: {previous_state} → {current_state}")

    except ClientError as e:
        print(f"   ❌ Failed to terminate {instance_id}: {str(e)}")
        return False
    return True


def delete_security_group(
    region: str,
    group_id: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    group_name: Optional[str] = None,
    ec2_client=None,
    region_or_client=None,
) -> bool:
    """Delete a security group with either a region or an EC2 client."""
    target_group_name = group_name
    if not isinstance(region, str):
        # Positional call pattern: delete_security_group(client, group_id, group_name, region)
        target_group_name = group_name or aws_access_key_id
        return delete_security_group_shared(
            region_or_client=region,
            group_id=group_id,
            group_name=target_group_name,
            region=region_or_client or aws_secret_access_key,
            ec2_client=region,
        )

    resolved_region = region_or_client if isinstance(region_or_client, str) else region
    client = ec2_client or (region_or_client if not isinstance(region_or_client, str) else None)
    if client is None:
        client = create_ec2_client(
            region=resolved_region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
    return delete_security_group_shared(
        region_or_client=resolved_region,
        group_id=group_id,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        group_name=target_group_name,
        ec2_client=client,
        region=resolved_region,
    )


def disable_termination_protection(
    region: str,
    instance_id: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
) -> bool:
    """
    Disable termination protection on an EC2 instance.

    Args:
        region: AWS region name
        instance_id: EC2 instance ID
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        ec2_client = create_ec2_client(
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        print(f"🔓 Disabling termination protection for: {instance_id}")
        ec2_client.modify_instance_attribute(
            InstanceId=instance_id,
            DisableApiTermination={"Value": False},
        )
        print("   ✅ Termination protection disabled")

    except ClientError as e:
        print(f"   ❌ Failed to disable termination protection: {str(e)}")
        return False
    return True


if __name__ == "__main__":  # pragma: no cover - script entry point
    pass
