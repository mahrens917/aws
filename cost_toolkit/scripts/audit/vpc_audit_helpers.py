#!/usr/bin/env python3
"""
VPC Audit Helper Functions
Contains resource collection functions for VPC auditing.
Extracted from aws_comprehensive_vpc_audit.py for modularity.
"""

from cost_toolkit.common.aws_common import extract_tag_value


def _get_resource_name(tags):
    """Extract Name tag from resource tags. Delegates to canonical implementation."""
    resource_dict = {"Tags": tags} if tags else {}
    return extract_tag_value(resource_dict, "Name")


def _get_active_instances(ec2_client):
    """Get all active instances in the region."""
    instances_response = ec2_client.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running", "stopped", "stopping", "pending"]}]
    )
    active_instances = []
    for reservation in instances_response["Reservations"]:
        for instance in reservation["Instances"]:
            tags = []
            if "Tags" in instance:
                tags = instance["Tags"]
            active_instances.append(
                {
                    "instance_id": instance["InstanceId"],
                    "vpc_id": instance.get("VpcId"),
                    "state": instance["State"]["Name"],
                    "name": _get_resource_name(tags),
                }
            )
    return active_instances


def _collect_vpc_subnets(ec2_client, vpc_id):
    """Collect all subnets for a VPC."""
    subnets_response = ec2_client.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    subnets = []
    if "Subnets" in subnets_response:
        for subnet in subnets_response["Subnets"]:
            subnet_tags = []
            if "Tags" in subnet:
                subnet_tags = subnet["Tags"]
            subnets.append(
                {
                    "subnet_id": subnet["SubnetId"],
                    "name": _get_resource_name(subnet_tags),
                    "cidr": subnet["CidrBlock"],
                    "availability_zone": subnet["AvailabilityZone"],
                    "available_ips": subnet["AvailableIpAddressCount"],
                }
            )
    return subnets


def _collect_vpc_security_groups(ec2_client, vpc_id):
    """Collect all security groups for a VPC."""
    sg_response = ec2_client.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    security_groups = []
    if "SecurityGroups" in sg_response:
        for sg in sg_response["SecurityGroups"]:
            security_groups.append(
                {
                    "group_id": sg["GroupId"],
                    "name": sg["GroupName"],
                    "description": sg["Description"],
                    "is_default": sg["GroupName"] == "default",
                }
            )
    return security_groups


def _collect_vpc_route_tables(ec2_client, vpc_id):
    """Collect all route tables for a VPC."""
    rt_response = ec2_client.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    route_tables = []
    if "RouteTables" in rt_response:
        for rt in rt_response["RouteTables"]:
            associations = []
            if "Associations" in rt:
                associations = rt["Associations"]
            routes = []
            if "Routes" in rt:
                routes = rt["Routes"]
            rt_tags = []
            if "Tags" in rt:
                rt_tags = rt["Tags"]
            route_tables.append(
                {
                    "route_table_id": rt["RouteTableId"],
                    "name": _get_resource_name(rt_tags),
                    "is_main": any(assoc.get("Main") for assoc in associations),
                    "associations": len(associations),
                    "routes": len(routes),
                }
            )
    return route_tables


def _collect_vpc_internet_gateways(ec2_client, vpc_id):
    """Collect all internet gateways attached to a VPC."""
    igw_response = ec2_client.describe_internet_gateways(Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}])
    internet_gateways = []
    if "InternetGateways" in igw_response:
        for igw in igw_response["InternetGateways"]:
            attachments = []
            if "Attachments" in igw:
                attachments = igw["Attachments"]
            igw_tags = []
            if "Tags" in igw:
                igw_tags = igw["Tags"]
            igw_state = "detached"
            if attachments:
                igw_state = attachments[0]["State"]
            internet_gateways.append(
                {
                    "gateway_id": igw["InternetGatewayId"],
                    "name": _get_resource_name(igw_tags),
                    "state": igw_state,
                }
            )
    return internet_gateways


def _collect_vpc_nat_gateways(ec2_client, vpc_id):
    """Collect all NAT gateways in a VPC."""
    nat_response = ec2_client.describe_nat_gateways(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    nat_gateways = []
    if "NatGateways" in nat_response:
        for nat in nat_response["NatGateways"]:
            nat_tags = []
            if "Tags" in nat:
                nat_tags = nat["Tags"]
            nat_gateways.append(
                {
                    "nat_gateway_id": nat["NatGatewayId"],
                    "name": _get_resource_name(nat_tags),
                    "state": nat["State"],
                    "subnet_id": nat["SubnetId"],
                }
            )
    return nat_gateways


def _collect_unused_security_groups(ec2_client):
    """Collect security groups not attached to any instances."""
    unused_security_groups = []
    all_sgs_response = ec2_client.describe_security_groups()
    if "SecurityGroups" in all_sgs_response:
        for sg in all_sgs_response["SecurityGroups"]:
            if sg["GroupName"] != "default":
                sg_instances = ec2_client.describe_instances(Filters=[{"Name": "instance.group-id", "Values": [sg["GroupId"]]}])
                if not sg_instances["Reservations"]:
                    unused_security_groups.append(
                        {
                            "group_id": sg["GroupId"],
                            "name": sg["GroupName"],
                            "description": sg["Description"],
                            "vpc_id": sg["VpcId"],
                        }
                    )
    return unused_security_groups


def _collect_unused_network_interfaces(ec2_client):
    """Collect unattached network interfaces."""
    unused_interfaces = []
    eni_response = ec2_client.describe_network_interfaces(Filters=[{"Name": "status", "Values": ["available"]}])
    if "NetworkInterfaces" in eni_response:
        for eni in eni_response["NetworkInterfaces"]:
            if "Attachment" not in eni:
                eni_tags = []
                if "TagSet" in eni:
                    eni_tags = eni["TagSet"]
                unused_interfaces.append(
                    {
                        "interface_id": eni["NetworkInterfaceId"],
                        "name": _get_resource_name(eni_tags),
                        "vpc_id": eni["VpcId"],
                        "subnet_id": eni["SubnetId"],
                        "private_ip": eni["PrivateIpAddress"],
                    }
                )
    return unused_interfaces


def _collect_vpc_endpoints(ec2_client):
    """Collect all VPC endpoints."""
    vpc_endpoints = []
    vpce_response = ec2_client.describe_vpc_endpoints()
    if "VpcEndpoints" in vpce_response:
        for vpce in vpce_response["VpcEndpoints"]:
            vpc_endpoints.append(
                {
                    "endpoint_id": vpce["VpcEndpointId"],
                    "service_name": vpce["ServiceName"],
                    "vpc_id": vpce["VpcId"],
                    "state": vpce["State"],
                    "endpoint_type": vpce["VpcEndpointType"],
                }
            )
    return vpc_endpoints


if __name__ == "__main__":
    # Utility module; no direct CLI behavior.
    pass
