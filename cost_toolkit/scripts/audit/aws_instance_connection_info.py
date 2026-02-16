#!/usr/bin/env python3
"""Get EC2 instance connection information."""


from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.scripts.aws_utils import get_instance_info


def _print_instance_basic_info(instance):
    """Print basic instance information."""
    print(f"Instance ID: {instance['InstanceId']}")
    print(f"Instance Type: {instance['InstanceType']}")
    print(f"State: {instance['State']['Name']}")
    print(f"Launch Time: {instance['LaunchTime']}")


def _print_network_info(instance):
    """Print network information for an instance."""
    print("\n📡 NETWORK INFORMATION:")

    public_ip = instance.get("PublicIpAddress")
    print(f"  Public IP: {public_ip if public_ip else 'None'}")

    public_dns = instance.get("PublicDnsName")
    print(f"  Public DNS: {public_dns if public_dns else 'None'}")

    private_ip = instance.get("PrivateIpAddress")
    if private_ip:
        print(f"  Private IP: {private_ip}")

    private_dns = instance.get("PrivateDnsName")
    if private_dns:
        print(f"  Private DNS: {private_dns}")

    vpc_id = instance.get("VpcId")
    subnet_id = instance.get("SubnetId")
    print(f"  VPC ID: {vpc_id}")
    print(f"  Subnet ID: {subnet_id}")

    security_groups = []
    if "SecurityGroups" in instance:
        security_groups = instance["SecurityGroups"]
    print("\n🔒 SECURITY GROUPS:")
    for sg in security_groups:
        print(f"  {sg['GroupId']} ({sg['GroupName']})")


def _check_internet_gateway(route_tables):
    """Check if route tables have an internet gateway."""
    for route_table in route_tables:
        routes = []
        if "Routes" in route_table:
            routes = route_table["Routes"]
        for route in routes:
            dest_cidr = route.get("DestinationCidrBlock")
            if dest_cidr == "0.0.0.0/0":
                gateway_id = route.get("GatewayId")
                if gateway_id and gateway_id.startswith("igw-"):
                    return True, gateway_id
    return False, None


def _check_subnet_configuration(ec2, subnet_id):
    """Check subnet configuration and internet routing."""
    subnet_response = ec2.describe_subnets(SubnetIds=[subnet_id])
    subnet = subnet_response["Subnets"][0]
    map_public_ip = subnet.get("MapPublicIpOnLaunch")
    print("\n🌐 SUBNET CONFIGURATION:")
    print(f"  Subnet auto-assigns public IP: {map_public_ip}")

    rt_response = ec2.describe_route_tables(Filters=[{"Name": "association.subnet-id", "Values": [subnet_id]}])

    has_internet_route = False
    if rt_response["RouteTables"]:
        has_internet_route, gateway_id = _check_internet_gateway(rt_response["RouteTables"])
        if has_internet_route:
            print(f"  Internet route via: {gateway_id}")

    if not has_internet_route:
        print("  Internet route: None found")

    return has_internet_route


def _print_connection_options(instance_id, region_name, public_ip, public_dns):
    """Print available connection options."""
    print("\n💡 CONNECTION OPTIONS:")

    if public_ip and public_dns:
        print("  ✅ Direct Internet Connection:")
        print(f"     SSH: ssh -i your-key.pem ec2-user@{public_ip}")
        print(f"     SSH: ssh -i your-key.pem ec2-user@{public_dns}")
    elif public_dns and not public_ip:
        print("  ⚠️  Public DNS available but no public IP:")
        print(f"     SSH: ssh -i your-key.pem ec2-user@{public_dns}")
        print("     (This may not work without a public IP)")
    else:
        print("  ❌ No direct internet connection available")
        print("  Alternative connection methods:")
        print("     1. AWS Systems Manager Session Manager:")
        print(f"        aws ssm start-session --target {instance_id} --region {region_name}")
        print("     2. VPN or Direct Connect to VPC")
        print("     3. Bastion host in the same VPC")
        print("     4. Re-assign a public IP (will cost $3.60/month)")


def _check_ssm_availability(instance_id, region_name):
    """Check if SSM is available for the instance."""
    try:
        ssm = create_client("ssm", region=region_name)
        ssm_response = ssm.describe_instance_information(Filters=[{"Key": "InstanceIds", "Values": [instance_id]}])

        if ssm_response["InstanceInformationList"]:
            ssm_info = ssm_response["InstanceInformationList"][0]
            print("\n🔧 AWS SYSTEMS MANAGER:")
            print(f"  ✅ SSM Agent Status: {ssm_info['PingStatus']}")
            print(f"  Last Ping: {ssm_info['LastPingDateTime']}")
            print(f"  Platform: {ssm_info['PlatformType']} {ssm_info['PlatformVersion']}")
            print("  Connection command:")
            print(f"    aws ssm start-session --target {instance_id} --region {region_name}")
        else:
            print("\n🔧 AWS SYSTEMS MANAGER:")
            print("  ❌ SSM Agent not responding or not installed")
    except ClientError as e:
        print("\n🔧 AWS SYSTEMS MANAGER:")
        print(f"  ⚠️  Could not check SSM status: {e}")


def get_instance_connection_info(instance_id, region_name):
    """Get connection information for an EC2 instance"""
    print(f"\n🔍 Getting connection info for instance {instance_id} in {region_name}")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)
        instance = get_instance_info(instance_id, region_name)

        _print_instance_basic_info(instance)
        _print_network_info(instance)

        subnet_id = instance.get("SubnetId")
        has_internet_route = _check_subnet_configuration(ec2, subnet_id)

        public_ip = instance.get("PublicIpAddress")
        public_dns = instance.get("PublicDnsName")
        _print_connection_options(instance_id, region_name, public_ip, public_dns)
        _check_ssm_availability(instance_id, region_name)

        tags = []
        if "Tags" in instance:
            tags = instance["Tags"]
        if tags:
            print("\n🏷️  INSTANCE TAGS:")
            for tag in tags:
                print(f"  {tag['Key']}: {tag['Value']}")

        return {
            "instance_id": instance_id,
            "public_ip": public_ip,
            "public_dns": public_dns,
            "private_ip": instance.get("PrivateIpAddress"),
            "private_dns": instance.get("PrivateDnsName"),
            "has_internet_access": has_internet_route,
            "state": instance["State"]["Name"],
        }

    except ClientError as e:
        print(f"❌ Error getting instance info: {e}")
        return None


def main():
    """Get and display EC2 instance connection information."""
    print("AWS Instance Connection Information")
    print("=" * 80)

    # Check the specific instance
    instance_info = get_instance_connection_info("i-00c39b1ba0eba3e2d", "us-east-2")

    if instance_info:
        print("\n" + "=" * 80)
        print("🎯 SUMMARY")
        print("=" * 80)

        if instance_info["public_ip"] or instance_info["public_dns"]:
            print("✅ Instance has public connectivity")
            if instance_info["public_dns"]:
                print(f"   Primary connection: {instance_info['public_dns']}")
            if instance_info["public_ip"]:
                print(f"   IP address: {instance_info['public_ip']}")
        else:
            print("❌ Instance has no public connectivity")
            print("   Use AWS Systems Manager Session Manager for access")
            print("   Command: aws ssm start-session --target i-00c39b1ba0eba3e2d --region us-east-2")


if __name__ == "__main__":
    main()
