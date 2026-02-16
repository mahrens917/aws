#!/usr/bin/env python3
"""Audit RDS database instances."""

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client


def _process_rds_instance(instance):
    """Process and print a single RDS instance."""
    print(f"  Instance ID: {instance['DBInstanceIdentifier']}")
    engine_version = instance.get("EngineVersion")
    print(f"  Engine: {instance['Engine']} {engine_version}")
    print(f"  Instance Class: {instance['DBInstanceClass']}")
    print(f"  Status: {instance['DBInstanceStatus']}")
    allocated_storage = instance.get("AllocatedStorage")
    print(f"  Storage: {allocated_storage} GB")
    storage_type = instance.get("StorageType")
    print(f"  Storage Type: {storage_type}")
    multi_az = instance.get("MultiAZ")
    print(f"  Multi-AZ: {multi_az}")
    publicly_accessible = instance.get("PubliclyAccessible")
    print(f"  Publicly Accessible: {publicly_accessible}")
    creation_time = instance.get("InstanceCreateTime")
    print(f"  Creation Time: {creation_time}")

    instance_class = instance["DBInstanceClass"]
    estimated_cost = 0.0
    if "t3.micro" in instance_class:
        estimated_cost = 20.0
        print(f"  Estimated Cost: ~${estimated_cost:.2f}/month")

    if "DBClusterIdentifier" in instance:
        print(f"  Part of Cluster: {instance['DBClusterIdentifier']}")

    print()
    return estimated_cost


def _process_aurora_cluster(cluster):
    """Process and print a single Aurora cluster."""
    print(f"  Cluster ID: {cluster['DBClusterIdentifier']}")
    engine_version = cluster.get("EngineVersion")
    print(f"  Engine: {cluster['Engine']} {engine_version}")
    print(f"  Status: {cluster['Status']}")
    database_name = cluster.get("DatabaseName")
    print(f"  Database Name: {database_name}")
    master_username = cluster.get("MasterUsername")
    print(f"  Master Username: {master_username}")
    multi_az = cluster.get("MultiAZ")
    print(f"  Multi-AZ: {multi_az}")
    storage_encrypted = cluster.get("StorageEncrypted")
    print(f"  Storage Encrypted: {storage_encrypted}")
    creation_time = cluster.get("ClusterCreateTime")
    print(f"  Creation Time: {creation_time}")

    members = cluster.get("DBClusterMembers")
    if members:
        print(f"  Cluster Members: {len(members)}")
        for member in members:
            role = "Writer" if member["IsClusterWriter"] else "Reader"
            print(f"    - {member['DBInstanceIdentifier']} ({role})")

    engine_mode = cluster.get("EngineMode")
    if engine_mode == "serverless":
        print("  Engine Mode: Serverless")
        if "ScalingConfigurationInfo" in cluster:
            scaling = cluster["ScalingConfigurationInfo"]
            min_cap = scaling.get("MinCapacity")
            max_cap = scaling.get("MaxCapacity")
            print(f"  Scaling: {min_cap}-{max_cap} ACU")
    elif "ServerlessV2ScalingConfiguration" in cluster:
        print("  Engine Mode: Serverless V2")
        scaling = cluster["ServerlessV2ScalingConfiguration"]
        min_cap = scaling.get("MinCapacity")
        max_cap = scaling.get("MaxCapacity")
        print(f"  Scaling: {min_cap}-{max_cap} ACU")

    print()


def _print_billing_analysis():
    """Print billing data analysis."""
    print("\n" + "=" * 80)
    print("BILLING DATA ANALYSIS:")
    print("-" * 40)
    print("Based on your billing data:")
    print("• us-east-1: $1.29 (96% of RDS cost)")
    print("  - db.t3.micro instance: 64 hours")
    print("  - GP3 storage: 1.78 GB")
    print("• eu-west-2: $0.05 (4% of RDS cost)")
    print("  - Aurora Serverless V2: 0.36 ACU-Hr")
    print("  - Aurora storage: 0.01 GB")
    print("  - Aurora I/O: 11,735 operations")

    print("\nCOST OPTIMIZATION OPPORTUNITIES:")
    print("-" * 40)
    print("1. Aurora Serverless V2 (eu-west-2): Very low usage (0.36 ACU-Hr)")
    print("   - Consider if this database is still needed")
    print("   - Minimal storage (0.01 GB) suggests it's mostly empty")
    print("2. RDS Instance (us-east-1): t3.micro running 64/720 hours (~9%)")
    print("   - Consider stopping when not in use")
    print("   - Or migrate to Aurora Serverless for auto-scaling")


def _audit_region_databases(region):
    """Audit databases in a single region."""
    try:
        rds = create_client("rds", region=region)

        instances = rds.describe_db_instances()
        clusters = rds.describe_db_clusters()

        if not instances["DBInstances"] and not clusters["DBClusters"]:
            return 0, 0, 0.0

        print(f"\nRegion: {region}")
        print("-" * 40)

        instance_count = 0
        cluster_count = 0
        region_cost = 0.0

        if instances["DBInstances"]:
            print("RDS INSTANCES:")
            for instance in instances["DBInstances"]:
                instance_count += 1
                cost = _process_rds_instance(instance)
                region_cost += cost

        if clusters["DBClusters"]:
            print("AURORA CLUSTERS:")
            for cluster in clusters["DBClusters"]:
                cluster_count += 1
                _process_aurora_cluster(cluster)
    except ClientError as e:
        if "not available" not in str(e).lower():
            print(f"Error accessing region {region}: {e}")
        return 0, 0, 0.0
    return instance_count, cluster_count, region_cost


def audit_rds_databases():
    """Audit RDS databases across all regions to understand what's running"""

    ec2 = create_client("ec2", region="us-east-1")
    regions = [region["RegionName"] for region in ec2.describe_regions()["Regions"]]

    print("AWS RDS Database Audit")
    print("=" * 80)

    total_instances = 0
    total_clusters = 0
    total_monthly_cost = 0

    for region in regions:
        instances, clusters, cost = _audit_region_databases(region)
        total_instances += instances
        total_clusters += clusters
        total_monthly_cost += cost

    print("=" * 80)
    print("DATABASE SUMMARY:")
    print(f"Total RDS Instances: {total_instances}")
    print(f"Total Aurora Clusters: {total_clusters}")
    print(f"Estimated Monthly Cost: ${total_monthly_cost:.2f}")

    _print_billing_analysis()


def main():
    """Main function."""
    audit_rds_databases()


if __name__ == "__main__":
    main()
