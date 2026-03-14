#!/usr/bin/env python3
"""Fix RDS default subnet group configuration."""

import boto3
from botocore.exceptions import ClientError

from ..aws_utils import (
    setup_aws_credentials,
    wait_for_db_instance_available,
    wait_for_db_snapshot_completion,
)
from .constants import create_public_subnet_group


def _create_migration_snapshot(rds, snapshot_id):
    """Create a snapshot for migration purposes"""
    try:
        rds.create_db_snapshot(DBSnapshotIdentifier=snapshot_id, DBInstanceIdentifier="simba-db-restored")
        print(f"✅ Snapshot creation initiated: {snapshot_id}")

        # Wait for snapshot to complete
        print("⏳ Waiting for snapshot to complete...")
        wait_for_db_snapshot_completion(rds, snapshot_id, max_attempts=20)
        print("✅ Snapshot completed!")
    except ClientError as e:
        if "already exists" in str(e).lower():
            print(f"✅ Snapshot {snapshot_id} already exists, proceeding...")
        else:
            raise


def _restore_instance_to_public_subnet(rds, snapshot_id, new_instance_id, subnet_group_name):
    """Restore DB instance to new subnet group"""
    print(f"🔄 Restoring to new instance in public subnets: {new_instance_id}")

    rds.restore_db_instance_from_db_snapshot(
        DBInstanceIdentifier=new_instance_id,
        DBSnapshotIdentifier=snapshot_id,
        DBInstanceClass="db.t4g.micro",
        DBSubnetGroupName=subnet_group_name,
        PubliclyAccessible=True,
        VpcSecurityGroupIds=["sg-265aa043"],
    )

    print("✅ New instance restoration initiated!")
    print("⏳ Waiting for new instance to be available...")

    # Wait for new instance to be available
    wait_for_db_instance_available(rds, new_instance_id)

    print("✅ New instance is available in public subnets!")
    print(f"🔍 You can now connect to: {new_instance_id}")
    print("💡 After confirming connectivity, you can delete the old instance")


def fix_default_subnet_group():
    """Modify the default subnet group to only include public subnets"""

    setup_aws_credentials()
    rds = boto3.client("rds", region_name="us-east-1")

    print("🔧 Fixing default subnet group to only include public subnets...")

    try:
        subnet_group_name = "public-rds-subnets"
        create_public_subnet_group(rds, subnet_group_name)

        # Since we can't modify the subnet group directly, let's try a different approach
        # We'll create a snapshot and restore to a new instance in the public subnet group
        print("🔄 Creating snapshot for subnet group migration...")

        snapshot_id = "simba-db-public-migration-snapshot"
        _create_migration_snapshot(rds, snapshot_id)

        # Restore to new instance in public subnet group
        new_instance_id = "simba-db-public"
        _restore_instance_to_public_subnet(rds, snapshot_id, new_instance_id, subnet_group_name)

    except ClientError as e:
        print(f"Error: {e}")


def main():
    """Main function."""
    fix_default_subnet_group()


if __name__ == "__main__":
    main()
