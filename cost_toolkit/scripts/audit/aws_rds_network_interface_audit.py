#!/usr/bin/env python3
"""
AWS RDS and Network Interface Correlation Audit

Identifies which RDS instances are using which network interfaces and determines cleanup
opportunities.
"""

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.credential_utils import setup_aws_credentials
from cost_toolkit.scripts.aws_ec2_operations import get_all_regions


def _extract_instance_info(instance):
    """Extract and format information from an RDS instance"""
    db_subnet_group = {}
    if "DBSubnetGroup" in instance:
        db_subnet_group = instance["DBSubnetGroup"]
    endpoint = {}
    if "Endpoint" in instance:
        endpoint = instance["Endpoint"]
    subnets = []
    if "Subnets" in db_subnet_group:
        subnets = db_subnet_group["Subnets"]
    return {
        "identifier": instance["DBInstanceIdentifier"],
        "engine": instance["Engine"],
        "engine_version": instance["EngineVersion"],
        "instance_class": instance["DBInstanceClass"],
        "status": instance["DBInstanceStatus"],
        "vpc_id": db_subnet_group.get("VpcId"),
        "subnet_group": db_subnet_group.get("DBSubnetGroupName"),
        "subnets": [subnet["SubnetIdentifier"] for subnet in subnets],
        "endpoint": endpoint.get("Address"),
        "port": endpoint.get("Port"),
        "publicly_accessible": instance.get("PubliclyAccessible"),
        "multi_az": instance.get("MultiAZ"),
        "storage_type": instance.get("StorageType"),
        "allocated_storage": instance.get("AllocatedStorage"),
        "creation_time": instance.get("InstanceCreateTime"),
    }


def _extract_cluster_info(cluster):
    """Extract and format information from an RDS cluster"""
    db_subnet_group = {}
    if "DBSubnetGroup" in cluster:
        db_subnet_group = cluster["DBSubnetGroup"]
    subnets = []
    if "Subnets" in db_subnet_group:
        subnets = db_subnet_group["Subnets"]
    return {
        "identifier": cluster["DBClusterIdentifier"],
        "engine": cluster["Engine"],
        "engine_version": cluster["EngineVersion"],
        "engine_mode": cluster.get("EngineMode"),
        "status": cluster["Status"],
        "vpc_id": db_subnet_group.get("VpcId"),
        "subnet_group": db_subnet_group.get("DBSubnetGroupName"),
        "subnets": [subnet["SubnetIdentifier"] for subnet in subnets],
        "endpoint": cluster.get("Endpoint"),
        "reader_endpoint": cluster.get("ReaderEndpoint"),
        "port": cluster.get("Port"),
        "creation_time": cluster.get("ClusterCreateTime"),
        "serverless_v2_scaling": cluster.get("ServerlessV2ScalingConfiguration"),
        "capacity": cluster.get("Capacity"),
    }


def audit_rds_instances_in_region(region_name, aws_access_key_id, aws_secret_access_key):
    """Audit RDS instances in a specific region"""
    try:
        rds = create_client(
            "rds",
            region=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        # Get RDS instances
        instances_response = rds.describe_db_instances()
        instances = instances_response["DBInstances"]

        # Get RDS clusters (for serverless)
        clusters_response = rds.describe_db_clusters()
        clusters = clusters_response["DBClusters"]

        if not instances and not clusters:
            return None

        region_data = {
            "region": region_name,
            "instances": [],
            "clusters": [],
            "total_instances": len(instances),
            "total_clusters": len(clusters),
        }

        # Process RDS instances
        for instance in instances:
            instance_info = _extract_instance_info(instance)
            region_data["instances"].append(instance_info)

        # Process RDS clusters (serverless)
        for cluster in clusters:
            cluster_info = _extract_cluster_info(cluster)
            region_data["clusters"].append(cluster_info)

    except ClientError as e:
        print(f"❌ Error auditing RDS in {region_name}: {str(e)}")
        return None

    return region_data


def get_network_interfaces_in_region(region_name, aws_access_key_id, aws_secret_access_key):
    """Get RDS network interfaces in a specific region"""
    try:
        ec2 = create_client(
            "ec2",
            region=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        # Get network interfaces with RDS description
        response = ec2.describe_network_interfaces(Filters=[{"Name": "description", "Values": ["RDSNetworkInterface"]}])

        return response["NetworkInterfaces"]

    except ClientError as e:
        print(f"❌ Error getting network interfaces in {region_name}: {str(e)}")
        return []


def _scan_region_resources(region, aws_access_key_id, aws_secret_access_key):
    """Scan RDS and network interface resources in a single region"""
    print(f"🔍 Checking region: {region}")

    rds_data = audit_rds_instances_in_region(region, aws_access_key_id, aws_secret_access_key)
    rds_interfaces = get_network_interfaces_in_region(region, aws_access_key_id, aws_secret_access_key)

    interface_info_list = []
    if rds_interfaces:
        for interface in rds_interfaces:
            association = {}
            if "Association" in interface:
                association = interface["Association"]
            interface_info = {
                "region": region,
                "interface_id": interface["NetworkInterfaceId"],
                "vpc_id": interface.get("VpcId"),
                "subnet_id": interface.get("SubnetId"),
                "private_ip": interface.get("PrivateIpAddress"),
                "public_ip": association.get("PublicIp"),
                "status": interface["Status"],
                "description": interface.get("Description"),
            }
            interface_info_list.append(interface_info)

    return rds_data, rds_interfaces, interface_info_list


def _print_region_scan_results(rds_data, rds_interfaces):
    """Print results from a single region scan"""
    if rds_data or rds_interfaces:
        if rds_data:
            print(f"   📊 RDS Instances: {rds_data['total_instances']}")
            print(f"   📊 RDS Clusters: {rds_data['total_clusters']}")
        if rds_interfaces:
            print(f"   🔗 RDS Network Interfaces: {len(rds_interfaces)}")
    else:
        print("   ✅ No RDS resources found")
    print()


def _print_rds_instance(instance):
    """Print details for a single RDS instance"""
    print(f"      🗄️  {instance['identifier']}")
    print(f"         Engine: {instance['engine']} {instance['engine_version']}")
    print(f"         Class: {instance['instance_class']}")
    print(f"         Status: {instance['status']}")
    print(f"         VPC: {instance['vpc_id']}")
    print(f"         Endpoint: {instance['endpoint']}:{instance['port']}")
    print(f"         Public: {instance['publicly_accessible']}")
    print(f"         Storage: {instance['storage_type']} ({instance['allocated_storage']} GB)")
    print(f"         Created: {instance['creation_time']}")
    print()


def _print_rds_cluster(cluster):
    """Print details for a single RDS cluster"""
    print(f"      🌐 {cluster['identifier']}")
    print(f"         Engine: {cluster['engine']} {cluster['engine_version']}")
    print(f"         Mode: {cluster['engine_mode']}")
    print(f"         Status: {cluster['status']}")
    print(f"         VPC: {cluster['vpc_id']}")
    print(f"         Endpoint: {cluster['endpoint']}:{cluster['port']}")
    if cluster["reader_endpoint"] != "N/A":
        print(f"         Reader: {cluster['reader_endpoint']}")
    if cluster["serverless_v2_scaling"]:
        print(f"         Serverless V2: {cluster['serverless_v2_scaling']}")
    print(f"         Created: {cluster['creation_time']}")
    print()


def _print_rds_details(regions_with_rds):
    """Print detailed information for all RDS resources"""
    if not regions_with_rds:
        return

    print("🗄️  RDS INSTANCES AND CLUSTERS DETAILS")
    print("=" * 50)

    for region_data in regions_with_rds:
        print(f"\n📍 Region: {region_data['region']}")
        print("-" * 30)

        if region_data["instances"]:
            print("   📊 RDS Instances:")
            for instance in region_data["instances"]:
                _print_rds_instance(instance)

        if region_data["clusters"]:
            print("   🌐 RDS Clusters:")
            for cluster in region_data["clusters"]:
                _print_rds_cluster(cluster)


def _print_network_interfaces(rds_network_interfaces):
    """Print details for all RDS network interfaces"""
    if not rds_network_interfaces:
        return

    print("\n🔗 RDS NETWORK INTERFACES DETAILS")
    print("=" * 50)

    for interface in rds_network_interfaces:
        print(f"\n🔗 Interface: {interface['interface_id']} ({interface['region']})")
        print(f"   VPC: {interface['vpc_id']}")
        print(f"   Subnet: {interface['subnet_id']}")
        print(f"   Private IP: {interface['private_ip']}")
        print(f"   Public IP: {interface['public_ip']}")
        print(f"   Status: {interface['status']}")


def _print_cleanup_recommendations(total_rds_interfaces, total_instances, total_clusters):
    """Print cleanup analysis and recommendations"""
    print("\n" + "=" * 70)
    print("💡 CLEANUP ANALYSIS AND RECOMMENDATIONS")
    print("=" * 70)

    if total_rds_interfaces > 0 and (total_instances + total_clusters) == 0:
        print("⚠️  ORPHANED RDS NETWORK INTERFACES DETECTED!")
        print("   • Found RDS network interfaces but no active RDS instances/clusters")
        print("   • These interfaces are likely from deleted RDS instances")
        print("   • Safe to delete for cost savings and hygiene")
    elif total_rds_interfaces > (total_instances + total_clusters):
        print("⚠️  EXCESS RDS NETWORK INTERFACES DETECTED!")
        print(f"   • Found {total_rds_interfaces} RDS interfaces but only " f"{total_instances + total_clusters} RDS resources")
        print("   • Some interfaces may be orphaned")
    elif total_instances > 0 and total_clusters > 0:
        print("ℹ️  MIXED RDS DEPLOYMENT DETECTED")
        print("   • Both traditional instances and serverless clusters found")
        print("   • Review if all instances are needed")
    elif total_clusters > 0:
        print("✅ SERVERLESS RDS DEPLOYMENT")
        print("   • Only serverless clusters found - optimal for cost")
    else:
        print("✅ CLEAN RDS CONFIGURATION")
        print("   • RDS network interfaces match RDS resources")


def main():
    """Main execution function"""
    print("AWS RDS and Network Interface Correlation Audit")
    print("=" * 70)

    try:
        # Load credentials
        aws_access_key_id, aws_secret_access_key = setup_aws_credentials()

        # Get all regions
        regions = get_all_regions()
        print(f"🌍 Scanning {len(regions)} AWS regions for RDS instances and network interfaces...")
        print()

        total_instances = 0
        total_clusters = 0
        total_rds_interfaces = 0
        regions_with_rds = []
        rds_network_interfaces = []

        for region in regions:
            rds_data, rds_interfaces, interface_info_list = _scan_region_resources(region, aws_access_key_id, aws_secret_access_key)

            _print_region_scan_results(rds_data, rds_interfaces)

            if rds_data:
                regions_with_rds.append(rds_data)
                total_instances += rds_data["total_instances"]
                total_clusters += rds_data["total_clusters"]

            if rds_interfaces:
                total_rds_interfaces += len(rds_interfaces)
                rds_network_interfaces.extend(interface_info_list)

        # Summary report
        print("=" * 70)
        print("📋 RDS AND NETWORK INTERFACE AUDIT SUMMARY")
        print("=" * 70)
        print(f"🌍 Regions scanned: {len(regions)}")
        print(f"📊 Total RDS instances: {total_instances}")
        print(f"📊 Total RDS clusters: {total_clusters}")
        print(f"🔗 Total RDS network interfaces: {total_rds_interfaces}")
        print()

        _print_rds_details(regions_with_rds)
        _print_network_interfaces(rds_network_interfaces)
        _print_cleanup_recommendations(total_rds_interfaces, total_instances, total_clusters)

    except ClientError as e:
        print(f"❌ Critical error during RDS audit: {str(e)}")
        raise


if __name__ == "__main__":
    main()
