#!/usr/bin/env python3
"""Audit EC2 instance usage patterns."""


from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import (
    get_all_aws_regions,
    get_instance_details,
)

# Constants
CPU_USAGE_VERY_LOW_THRESHOLD = 5
CPU_USAGE_MODERATE_THRESHOLD = 20


def _calculate_cpu_metrics(cloudwatch, instance_id):
    """Calculate CPU metrics for an instance"""
    try:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=7)

        cpu_response = cloudwatch.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=["Average", "Maximum"],
        )

        if cpu_response["Datapoints"]:
            datapoints = sorted(cpu_response["Datapoints"], key=lambda x: x["Timestamp"])
            latest_datapoint = datapoints[-1]
            avg_cpu = sum(dp["Average"] for dp in datapoints) / len(datapoints)
            max_cpu = max(dp["Maximum"] for dp in datapoints)
            return avg_cpu, max_cpu, latest_datapoint

    except ClientError as e:
        print(f"Error getting metrics for {instance_id}: {e}")

    return None, None, None


def _determine_usage_level(avg_cpu):
    """Determine usage level based on average CPU"""
    if avg_cpu is None:
        return "❓ NO DATA"
    if avg_cpu < 1:
        return "🔴 VERY LOW (<1% avg)"
    if avg_cpu < CPU_USAGE_VERY_LOW_THRESHOLD:
        return f"🟡 LOW (<{CPU_USAGE_VERY_LOW_THRESHOLD}% avg)"
    if avg_cpu < CPU_USAGE_MODERATE_THRESHOLD:
        return f"🟢 MODERATE ({CPU_USAGE_VERY_LOW_THRESHOLD}-{CPU_USAGE_MODERATE_THRESHOLD}% avg)"
    return f"🔵 HIGH (>{CPU_USAGE_MODERATE_THRESHOLD}% avg)"


def _print_cpu_metrics(avg_cpu, max_cpu, latest_datapoint):
    """Print CPU metrics"""
    if avg_cpu is not None:
        print("  Last 7 days CPU usage:")
        print(f"    Average: {avg_cpu:.1f}%")
        print(f"    Maximum: {max_cpu:.1f}%")
        print(f"    Last recorded: {latest_datapoint['Timestamp']} " f"({latest_datapoint['Average']:.1f}%)")
    else:
        print("  ⚠️  No CPU metrics available (instance may be stopped)")


def _get_network_metrics(cloudwatch, instance_id, start_time, end_time):
    """Get network metrics for an instance"""
    try:
        network_response = cloudwatch.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="NetworkIn",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=["Sum"],
        )

        if network_response["Datapoints"]:
            total_network_in = sum(dp["Sum"] for dp in network_response["Datapoints"])
            print(f"  Network In (7 days): {total_network_in/1024/1024:.1f} MB")
        else:
            print("  Network In: No data")
    except ClientError as e:
        print(f"Network metrics error for {instance_id}: {e}")


def _estimate_monthly_cost(instance_type, state):
    """Estimate monthly cost based on instance type"""
    cost_estimates = {
        "t2.nano": 4.18,
        "t2.micro": 8.35,
        "t2.small": 16.70,
        "t2.medium": 33.41,
        "t3.nano": 3.80,
        "t3.micro": 7.59,
        "t3.small": 15.18,
        "t3.medium": 30.37,
        "m5.large": 69.12,
        "m5.xlarge": 138.24,
        "c5.large": 61.56,
        "c5.xlarge": 123.12,
    }

    if instance_type not in cost_estimates:
        return 50.0 if state == "running" else 0.0
    estimated_monthly_cost = cost_estimates[instance_type]
    return estimated_monthly_cost if state == "running" else 0


def _process_instance_details(cloudwatch, instance_details, region_name, start_time, end_time):
    """Process detailed metrics for a single EC2 instance."""
    instance_id = instance_details["instance_id"]
    instance_type = instance_details["instance_type"]
    state = instance_details["state"]
    launch_time = instance_details.get("launch_time")
    name = instance_details.get("name")

    print(f"Instance: {instance_id} ({name})")
    print(f"  Type: {instance_type}")
    print(f"  State: {state}")
    print(f"  Launch Time: {launch_time}")

    avg_cpu, max_cpu, latest_datapoint = _calculate_cpu_metrics(cloudwatch, instance_id)
    _print_cpu_metrics(avg_cpu, max_cpu, latest_datapoint)
    usage_level = _determine_usage_level(avg_cpu)
    if avg_cpu is not None:
        print(f"    Usage Level: {usage_level}")

    _get_network_metrics(cloudwatch, instance_id, start_time, end_time)

    estimated_monthly_cost = _estimate_monthly_cost(instance_type, state)
    if state == "running":
        print(f"  Estimated monthly cost: ${estimated_monthly_cost:.2f} (if running 24/7)")
    else:
        print(f"  Estimated monthly cost: $0 (currently {state})")

    print()

    return {
        "region": region_name,
        "instance_id": instance_id,
        "name": name,
        "instance_type": instance_type,
        "state": state,
        "launch_time": launch_time,
        "usage_level": usage_level,
        "estimated_monthly_cost": estimated_monthly_cost,
    }


def get_instance_details_in_region(region_name):
    """Get detailed information about EC2 instances in a region"""
    print(f"\n🔍 Auditing EC2 instances in {region_name}")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)
        cloudwatch = create_client("cloudwatch", region=region_name)

        instances = [
            instance["InstanceId"] for reservation in ec2.describe_instances()["Reservations"] for instance in reservation["Instances"]
        ]

        if not instances:
            print(f"✅ No EC2 instances found in {region_name}")
            return []

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=7)

        region_summary = []
        for instance_id in instances:
            details = get_instance_details(ec2, instance_id)
            if details is None:
                continue
            region_summary.append(_process_instance_details(cloudwatch, details, region_name, start_time, end_time))

    except ClientError as e:
        print(f"❌ Error auditing instances in {region_name}: {e}")
        return []

    return region_summary


def _print_summary_header(all_instances, total_estimated_cost):
    """Print summary header with instance counts and costs."""
    running_instances = [inst for inst in all_instances if inst["state"] == "running"]
    stopped_instances = [inst for inst in all_instances if inst["state"] == "stopped"]

    print(f"Total instances found: {len(all_instances)}")
    print(f"  🟢 Running: {len(running_instances)}")
    print(f"  🔴 Stopped: {len(stopped_instances)}")
    print(f"Estimated monthly cost for running instances: ${total_estimated_cost:.2f}")


def _print_low_usage_recommendations(all_instances):
    """Print recommendations for low usage instances."""
    low_usage_instances = []
    for inst in all_instances:
        usage_level = inst.get("usage_level")
        if usage_level and ("LOW" in usage_level or "VERY LOW" in usage_level):
            low_usage_instances.append(inst)

    if low_usage_instances:
        print(f"  🔴 {len(low_usage_instances)} instances with low CPU usage:")
        for inst in low_usage_instances:
            print(f"    - {inst['name']} ({inst['instance_id']}) in {inst['region']}")
            print(f"      Usage: {inst['usage_level']}")
            print(f"      Cost: ${inst['estimated_monthly_cost']:.2f}/month")


def _print_cost_reduction_options():
    """Print available cost reduction options."""
    print("\n📋 OPTIONS FOR COST REDUCTION:")
    print("  1. STOP instances when not needed (keeps data, stops compute charges)")
    print("  2. TERMINATE unused instances (deletes everything, stops all charges)")
    print("  3. DOWNSIZE over-provisioned instances to smaller types")
    print("  4. SCHEDULE instances to run only when needed")
    print("  5. RELEASE Elastic IPs for terminated instances")

    print("\n⚠️  IMPORTANT NOTES:")
    print("  - Stopping instances keeps EBS volumes (small storage cost continues)")
    print("  - Elastic IPs cost money whether instance is running or not")
    print("  - You can restart stopped instances anytime")
    print("  - Terminated instances cannot be recovered")


def main():
    """Audit EC2 instance usage patterns."""
    print("AWS EC2 Usage Audit")
    print("=" * 80)
    print("Analyzing EC2 instances and their recent usage patterns...")

    regions = get_all_aws_regions()

    all_instances = []
    total_estimated_cost = 0

    for region in regions:
        instances = get_instance_details_in_region(region)
        all_instances.extend(instances)

        region_cost = sum(inst["estimated_monthly_cost"] for inst in instances)
        total_estimated_cost += region_cost

    print("\n" + "=" * 80)
    print("🎯 OVERALL SUMMARY")
    print("=" * 80)

    _print_summary_header(all_instances, total_estimated_cost)

    print("\n💡 OPTIMIZATION RECOMMENDATIONS:")
    _print_low_usage_recommendations(all_instances)
    _print_cost_reduction_options()


if __name__ == "__main__":
    main()
