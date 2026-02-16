"""RDS and Aurora cluster operations"""

import time

import boto3
from botocore.exceptions import ClientError

from ...aws_utils import (
    get_aws_regions,
    setup_aws_credentials,
    wait_for_db_cluster_available,
    wait_for_db_snapshot_completion,
)


def _extract_instance_info(instance, region):
    """Extract instance information into a dictionary."""
    vpc_security_groups = []
    if "VpcSecurityGroups" in instance:
        vpc_security_groups = instance["VpcSecurityGroups"]
    db_subnet_group = instance.get("DBSubnetGroup")
    db_param_groups = []
    if "DBParameterGroups" in instance:
        db_param_groups = instance["DBParameterGroups"]

    return {
        "region": region,
        "identifier": instance["DBInstanceIdentifier"],
        "engine": instance["Engine"],
        "engine_version": instance["EngineVersion"],
        "instance_class": instance["DBInstanceClass"],
        "status": instance["DBInstanceStatus"],
        "allocated_storage": instance["AllocatedStorage"],
        "storage_type": instance["StorageType"],
        "multi_az": instance["MultiAZ"],
        "publicly_accessible": instance["PubliclyAccessible"],
        "vpc_security_groups": [sg["VpcSecurityGroupId"] for sg in vpc_security_groups],
        "db_subnet_group": (db_subnet_group["DBSubnetGroupName"] if db_subnet_group and "DBSubnetGroupName" in db_subnet_group else None),
        "parameter_group": (
            db_param_groups[0]["DBParameterGroupName"] if db_param_groups and "DBParameterGroupName" in db_param_groups[0] else None
        ),
        "backup_retention": instance.get("BackupRetentionPeriod"),
        "preferred_backup_window": instance.get("PreferredBackupWindow"),
        "preferred_maintenance_window": instance.get("PreferredMaintenanceWindow"),
        "storage_encrypted": instance["StorageEncrypted"],
        "kms_key_id": instance.get("KmsKeyId"),
        "deletion_protection": instance["DeletionProtection"],
    }


def _print_instance_info(instance_info):
    """Print discovered instance details."""
    print(f"\n📦 Found RDS Instance: {instance_info['identifier']}")
    print(f"   Region: {instance_info['region']}")
    print(f"   Engine: {instance_info['engine']} {instance_info['engine_version']}")
    print(f"   Class: {instance_info['instance_class']}")
    print(f"   Status: {instance_info['status']}")
    print(f"   Storage: {instance_info['allocated_storage']} GB " f"({instance_info['storage_type']})")


def _discover_in_region(region):
    """Discover standalone RDS instances in a single region."""
    instances = []
    rds_client = boto3.client("rds", region_name=region)
    response = rds_client.describe_db_instances()
    if "DBInstances" not in response:
        return instances
    for instance in response["DBInstances"]:
        if instance.get("DBClusterIdentifier"):
            continue
        instance_info = _extract_instance_info(instance, region)
        instances.append(instance_info)
        _print_instance_info(instance_info)
    return instances


def discover_rds_instances():
    """Discover all RDS instances across regions"""
    setup_aws_credentials()

    print("🔍 DISCOVERING RDS INSTANCES")
    print("=" * 80)

    regions = get_aws_regions()
    discovered_instances = []

    for region in regions:
        try:
            discovered_instances.extend(_discover_in_region(region))
        except ClientError as e:
            if "not available" not in str(e).lower():
                print(f"❌ Error accessing region {region}: {e}")

    if not discovered_instances:
        print("✅ No standalone RDS instances found for migration")
        return []

    print(f"\n📊 Total instances found: {len(discovered_instances)}")
    return discovered_instances


def validate_migration_compatibility(instance_info):
    """Validate if instance can be migrated to Aurora Serverless v2"""
    print(f"\n🔍 Validating migration compatibility for {instance_info['identifier']}")

    compatibility_issues = []

    compatible_engines = {
        "mysql": ["aurora-mysql"],
        "postgres": ["aurora-postgresql"],
        "mariadb": ["aurora-mysql"],
    }

    source_engine = instance_info["engine"].lower()
    if source_engine not in compatible_engines:
        compatibility_issues.append(f"Engine '{instance_info['engine']}' is not compatible with Aurora Serverless v2")

    if instance_info["status"] != "available":
        compatibility_issues.append(f"Instance status is '{instance_info['status']}', must be 'available' for migration")

    if instance_info["allocated_storage"] < 1:
        compatibility_issues.append("Storage size too small for Aurora migration")

    if compatibility_issues:
        print("❌ Migration compatibility issues found:")
        for issue in compatibility_issues:
            print(f"   • {issue}")
        return False, compatibility_issues

    target_engine = compatible_engines[source_engine][0]
    print(f"✅ Compatible for migration: {instance_info['engine']} → {target_engine}")

    return True, target_engine


def create_rds_snapshot(rds_client, instance_identifier, _region):
    """Create a snapshot of the RDS instance"""
    snapshot_identifier = f"{instance_identifier}-migration-{int(time.time())}"

    print(f"\n📸 Creating snapshot: {snapshot_identifier}")

    try:
        rds_client.create_db_snapshot(DBSnapshotIdentifier=snapshot_identifier, DBInstanceIdentifier=instance_identifier)

        print(f"✅ Snapshot creation initiated: {snapshot_identifier}")

        print("⏳ Waiting for snapshot to complete...")
        wait_for_db_snapshot_completion(rds_client, snapshot_identifier)

        print(f"✅ Snapshot completed: {snapshot_identifier}")

    except ClientError as e:
        print(f"❌ Error creating snapshot: {e}")
        raise

    return snapshot_identifier


def _build_cluster_params(instance_info, target_engine, cluster_identifier):
    """Build parameters for Aurora cluster creation."""
    cluster_params = {
        "DBClusterIdentifier": cluster_identifier,
        "Engine": target_engine,
        "MasterUsername": "postgres" if target_engine == "aurora-postgresql" else "admin",
        "MasterUserPassword": "TempPassword123!",
        "ServerlessV2ScalingConfiguration": {
            "MinCapacity": 0.5,
            "MaxCapacity": 4.0,
        },
        "DeletionProtection": False,
        "EnableCloudwatchLogsExports": (["postgresql"] if target_engine == "aurora-postgresql" else ["error", "general", "slowquery"]),
        "BackupRetentionPeriod": max(instance_info["backup_retention"], 1),
        "StorageEncrypted": instance_info["storage_encrypted"],
    }

    if instance_info["vpc_security_groups"]:
        cluster_params["VpcSecurityGroupIds"] = instance_info["vpc_security_groups"]

    if instance_info["db_subnet_group"]:
        cluster_params["DBSubnetGroupName"] = instance_info["db_subnet_group"]

    if instance_info["storage_encrypted"] and instance_info["kms_key_id"]:
        cluster_params["KmsKeyId"] = instance_info["kms_key_id"]

    if instance_info["preferred_backup_window"]:
        cluster_params["PreferredBackupWindow"] = instance_info["preferred_backup_window"]

    if instance_info["preferred_maintenance_window"]:
        cluster_params["PreferredMaintenanceWindow"] = instance_info["preferred_maintenance_window"]

    return cluster_params


def _get_cluster_endpoint_info(rds_client, cluster_identifier):
    """Get cluster endpoint information."""
    cluster_response = rds_client.describe_db_clusters(DBClusterIdentifier=cluster_identifier)
    cluster = cluster_response["DBClusters"][0]

    return {
        "cluster_identifier": cluster_identifier,
        "writer_endpoint": cluster["Endpoint"],
        "reader_endpoint": cluster.get("ReaderEndpoint"),
        "port": cluster["Port"],
        "engine": cluster["Engine"],
        "status": cluster["Status"],
    }


def create_aurora_serverless_cluster(rds_client, instance_info, target_engine, _snapshot_identifier):
    """Create Aurora Serverless v2 cluster from RDS snapshot"""
    cluster_identifier = f"{instance_info['identifier']}-aurora-serverless"

    print(f"\n🚀 Creating Aurora Serverless v2 cluster: {cluster_identifier}")

    try:
        cluster_params = _build_cluster_params(instance_info, target_engine, cluster_identifier)

        rds_client.create_db_cluster(**cluster_params)

        print("✅ Aurora Serverless v2 cluster creation initiated")
        print(f"   Cluster: {cluster_identifier}")
        print(f"   Engine: {target_engine}")
        print("   Scaling: 0.5-4.0 ACU")

        print("⏳ Waiting for cluster to become available...")
        wait_for_db_cluster_available(rds_client, cluster_identifier)

        print(f"✅ Aurora Serverless v2 cluster is ready: {cluster_identifier}")

        endpoint_info = _get_cluster_endpoint_info(rds_client, cluster_identifier)

    except ClientError as e:
        print(f"❌ Error creating Aurora Serverless v2 cluster: {e}")
        raise

    return endpoint_info


if __name__ == "__main__":
    pass
