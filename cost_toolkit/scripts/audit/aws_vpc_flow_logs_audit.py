#!/usr/bin/env python3
"""Audit VPC Flow Logs configuration."""


from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import get_all_aws_regions


def _check_log_group_size(logs_client, log_group_name):
    """Check CloudWatch log group size and calculate cost."""
    try:
        log_group_response = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
        log_groups = []
        if "logGroups" in log_group_response:
            log_groups = log_group_response["logGroups"]
        for log_group in log_groups:
            if log_group["logGroupName"] == log_group_name:
                stored_bytes = log_group.get("storedBytes")
                if stored_bytes is None:
                    return 0
                stored_gb = stored_bytes / (1024**3)
                monthly_storage_cost = stored_gb * 0.50
                print(f"  Log Group Size: {stored_gb:.2f} GB")
                print(f"  Estimated storage cost: ${monthly_storage_cost:.2f}/month")
                return monthly_storage_cost
    except ClientError as e:
        print(f"  Error checking log group: {e}")
    return 0


def _build_flow_info(flow_log, region_name):
    """Extract flow log information from API response."""
    resource_ids = []
    if "ResourceIds" in flow_log:
        resource_ids = flow_log["ResourceIds"]
    tags = []
    if "Tags" in flow_log:
        tags = flow_log["Tags"]
    return {
        "region": region_name,
        "flow_log_id": flow_log.get("FlowLogId"),
        "flow_log_status": flow_log.get("FlowLogStatus"),
        "resource_type": flow_log.get("ResourceType"),
        "resource_id": resource_ids,
        "log_destination_type": flow_log.get("LogDestinationType"),
        "log_destination": flow_log.get("LogDestination"),
        "creation_time": flow_log.get("CreationTime"),
        "tags": tags,
    }


def _print_flow_info(flow_info):
    """Print flow log details."""
    print(f"Flow Log: {flow_info['flow_log_id']}")
    print(f"  Status: {flow_info['flow_log_status']}")
    print(f"  Resource Type: {flow_info['resource_type']}")
    print(f"  Resource IDs: {flow_info['resource_id']}")
    print(f"  Destination Type: {flow_info['log_destination_type']}")
    print(f"  Destination: {flow_info['log_destination']}")
    print(f"  Created: {flow_info['creation_time']}")


def _process_flow_log_with_cost(flow_info, logs_client):
    """Process flow log and calculate storage cost if applicable."""
    if flow_info["log_destination_type"] == "cloud-watch-logs":
        log_group_name = flow_info["log_destination"].split(":")[-1]
        storage_cost = _check_log_group_size(logs_client, log_group_name)
        if storage_cost > 0:
            flow_info["storage_cost"] = storage_cost


def _print_flow_tags(tags):
    """Print flow log tags."""
    if tags:
        print("  Tags:")
        for tag in tags:
            print(f"    {tag['Key']}: {tag['Value']}")


def audit_flow_logs_in_region(region_name):
    """Audit VPC Flow Logs in a specific region"""
    print(f"\n🔍 Auditing VPC Flow Logs in {region_name}")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)
        logs_client = create_client("logs", region=region_name)

        response = ec2.describe_flow_logs()
        flow_logs = []
        if "FlowLogs" in response:
            flow_logs = response["FlowLogs"]

        if not flow_logs:
            print(f"✅ No VPC Flow Logs found in {region_name}")
            return []

        region_summary = []
        for flow_log in flow_logs:
            flow_info = _build_flow_info(flow_log, region_name)
            _print_flow_info(flow_info)
            _process_flow_log_with_cost(flow_info, logs_client)
            _print_flow_tags(flow_info["tags"])
            print()
            region_summary.append(flow_info)

    except ClientError as e:
        print(f"❌ Error auditing Flow Logs in {region_name}: {e}")
        return []

    return region_summary


def _check_vpc_peering_connections(ec2):
    """Check VPC peering connections."""
    response = ec2.describe_vpc_peering_connections()
    peering_connections = []
    if "VpcPeeringConnections" in response:
        peering_connections = response["VpcPeeringConnections"]
    print(f"VPC Peering Connections: {len(peering_connections)}")
    for peering in peering_connections:
        status_obj = {}
        if "Status" in peering:
            status_obj = peering["Status"]
        status = status_obj.get("Code")
        print(f"  Peering: {peering['VpcPeeringConnectionId']} - {status}")


def _check_vpc_endpoints(ec2):
    """Check VPC endpoints."""
    response = ec2.describe_vpc_endpoints()
    endpoints = []
    if "VpcEndpoints" in response:
        endpoints = response["VpcEndpoints"]
    print(f"VPC Endpoints: {len(endpoints)}")
    for endpoint in endpoints:
        endpoint_type = endpoint.get("VpcEndpointType")
        print(f"  Endpoint: {endpoint['VpcEndpointId']} ({endpoint_type})")
        service_name = endpoint.get("ServiceName")
        print(f"    Service: {service_name}")
        state = endpoint.get("State")
        print(f"    State: {state}")
        created = endpoint.get("CreationTimestamp")
        print(f"    Created: {created}")


def _check_vpc_resource_counts(ec2):
    """Check counts of various VPC resources."""
    sg_response = ec2.describe_security_groups()
    nacl_response = ec2.describe_network_acls()
    rt_response = ec2.describe_route_tables()
    subnet_response = ec2.describe_subnets()

    sgs = []
    if "SecurityGroups" in sg_response:
        sgs = sg_response["SecurityGroups"]
    nacls = []
    if "NetworkAcls" in nacl_response:
        nacls = nacl_response["NetworkAcls"]
    rts = []
    if "RouteTables" in rt_response:
        rts = rt_response["RouteTables"]
    subnets = []
    if "Subnets" in subnet_response:
        subnets = subnet_response["Subnets"]

    print(f"Security Groups: {len(sgs)}")
    print(f"Network ACLs: {len(nacls)}")
    print(f"Route Tables: {len(rts)}")
    print(f"Subnets: {len(subnets)}")


def audit_additional_vpc_costs_in_region(region_name):
    """Check for other potential VPC cost sources"""
    print(f"\n🔍 Checking additional VPC cost sources in {region_name}")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)
        _check_vpc_peering_connections(ec2)
        _check_vpc_endpoints(ec2)
        _check_vpc_resource_counts(ec2)

    except ClientError as e:
        print(f"❌ Error checking additional VPC costs in {region_name}: {e}")


def _print_flow_logs_summary(all_flow_logs, total_flow_log_cost):
    """Print flow logs summary."""
    print("\n" + "=" * 80)
    print("🎯 FLOW LOGS & ADDITIONAL COSTS SUMMARY")
    print("=" * 80)

    print(f"Total VPC Flow Logs found: {len(all_flow_logs)}")
    print(f"Estimated Flow Logs storage cost: ${total_flow_log_cost:.2f}/month")

    if all_flow_logs:
        print("\n📊 Flow Logs Breakdown:")
        active_flow_logs = [fl for fl in all_flow_logs if fl["flow_log_status"] == "ACTIVE"]
        inactive_flow_logs = [fl for fl in all_flow_logs if fl["flow_log_status"] != "ACTIVE"]

        print(f"  🟢 Active Flow Logs: {len(active_flow_logs)}")
        print(f"  🔴 Inactive Flow Logs: {len(inactive_flow_logs)}")

        if active_flow_logs:
            print("\n💰 ACTIVE FLOW LOGS (potential cost sources):")
            for flow_log in active_flow_logs:
                print(f"  {flow_log['flow_log_id']} -> {flow_log['log_destination']}")
                if "storage_cost" in flow_log:
                    print(f"    Storage cost: ${flow_log['storage_cost']:.2f}/month")


def _print_cost_analysis(total_flow_log_cost):
    """Print cost analysis."""
    print("\n📋 COST ANALYSIS:")
    print("  Known Public IPv4 cost: $3.60/month")
    print(f"  Flow Logs storage cost: ${total_flow_log_cost:.2f}/month")
    print(f"  Total identified: ${3.60 + total_flow_log_cost:.2f}/month")
    print("  Your reported VPC cost: $9.60/month")
    print(f"  Unaccounted for: ${9.60 - 3.60 - total_flow_log_cost:.2f}/month")

    if (9.60 - 3.60 - total_flow_log_cost) > 1.0:
        print("\n🤔 REMAINING MYSTERY COSTS:")
        print(f"  Possible sources for the remaining ${9.60 - 3.60 - total_flow_log_cost:.2f}:")
        print("    - Data transfer charges (ingress/egress)")
        print("    - VPC DNS queries")
        print("    - Recently deleted resources still in billing")
        print("    - Resources in other regions not checked")
        print("    - Partial month billing calculations")


def main():
    """Audit VPC Flow Logs and associated costs."""
    print("AWS VPC Flow Logs and Additional Cost Audit")
    print("=" * 80)
    print("Analyzing VPC Flow Logs and other potential cost sources...")

    regions = get_all_aws_regions()

    all_flow_logs = []
    total_flow_log_cost = 0

    for region in regions:
        flow_logs = audit_flow_logs_in_region(region)
        audit_additional_vpc_costs_in_region(region)

        all_flow_logs.extend(flow_logs)

        for flow_log in flow_logs:
            if "storage_cost" in flow_log:
                total_flow_log_cost += flow_log["storage_cost"]

    _print_flow_logs_summary(all_flow_logs, total_flow_log_cost)
    _print_cost_analysis(total_flow_log_cost)


if __name__ == "__main__":
    main()
