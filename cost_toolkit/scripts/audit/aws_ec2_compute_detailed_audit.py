#!/usr/bin/env python3
"""Detailed EC2 compute resource audit."""

from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import get_all_aws_regions
from cost_toolkit.common.cost_utils import calculate_ebs_volume_cost
from cost_toolkit.scripts.aws_ec2_operations import get_all_regions


def _build_instance_info(instance, region_name, hourly_cost, monthly_cost):
    """Build instance information dictionary"""
    return {
        "instance_id": instance["InstanceId"],
        "instance_type": instance["InstanceType"],
        "state": instance["State"]["Name"],
        "launch_time": instance.get("LaunchTime"),
        "region": region_name,
        "hourly_cost": hourly_cost,
        "monthly_cost": monthly_cost,
        "platform": instance.get("Platform"),
        "vpc_id": instance.get("VpcId"),
        "subnet_id": instance.get("SubnetId"),
        "public_ip": instance.get("PublicIpAddress"),
        "private_ip": instance.get("PrivateIpAddress"),
        "tags": instance.get("Tags") or [],
    }


def _print_instance_details(instance_id, instance_type, state, instance_info, *, hourly_cost, monthly_cost):
    """Print detailed instance information"""
    print(f"Instance: {instance_id}")
    print(f"  Type: {instance_type}")
    print(f"  State: {state}")
    print(f"  Platform: {instance_info['platform']}")
    print(f"  Launch Time: {instance_info['launch_time']}")
    print(f"  Hourly Cost: ${hourly_cost:.4f}")

    if state == "running":
        print(f"  Monthly Cost (if running 24/7): ${monthly_cost:.2f}")
    elif state == "stopped":
        print("  Monthly Cost: $0.00 (stopped - only EBS storage charges)")
    else:
        print(f"  Monthly Cost: $0.00 ({state})")


def _print_network_and_tags(instance_info):
    """Print network information and tags"""
    if instance_info["public_ip"]:
        print(f"  Public IP: {instance_info['public_ip']}")
    if instance_info["private_ip"]:
        print(f"  Private IP: {instance_info['private_ip']}")

    if instance_info["tags"]:
        print("  Tags:")
        for tag in instance_info["tags"]:
            print(f"    {tag['Key']}: {tag['Value']}")


def _print_region_summary(region_name, instances_found, total_monthly_cost):
    """Print region summary statistics"""
    print(f"📊 Region Summary for {region_name}:")
    running_instances = [i for i in instances_found if i["state"] == "running"]
    stopped_instances = [i for i in instances_found if i["state"] == "stopped"]
    terminated_instances = [i for i in instances_found if i["state"] == "terminated"]

    print(f"  Running instances: {len(running_instances)}")
    print(f"  Stopped instances: {len(stopped_instances)}")
    print(f"  Terminated instances: {len(terminated_instances)}")
    print(f"  Total monthly compute cost: ${total_monthly_cost:.2f}")


def analyze_ec2_instances_in_region(region_name):
    """Analyze EC2 instances and their compute costs in a specific region"""
    print(f"\n🖥️  Analyzing EC2 Compute in {region_name}")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)
        response = ec2.describe_instances()

        instances_found = []
        total_monthly_cost = 0

        for reservation in response["Reservations"]:
            for instance in reservation["Instances"]:
                instance_id = instance["InstanceId"]
                instance_type = instance["InstanceType"]
                state = instance["State"]["Name"]

                hourly_cost = get_instance_hourly_cost(instance_type, region_name)
                monthly_cost = hourly_cost * 24 * 30

                instance_info = _build_instance_info(instance, region_name, hourly_cost, monthly_cost)
                _print_instance_details(
                    instance_id,
                    instance_type,
                    state,
                    instance_info,
                    hourly_cost=hourly_cost,
                    monthly_cost=monthly_cost,
                )
                _print_network_and_tags(instance_info)

                print()
                instances_found.append(instance_info)

                if state == "running":
                    total_monthly_cost += monthly_cost

        if not instances_found:
            print(f"✅ No EC2 instances found in {region_name}")
        else:
            _print_region_summary(region_name, instances_found, total_monthly_cost)

    except ClientError as e:
        print(f"❌ Error analyzing EC2 in {region_name}: {e}")
        return []

    return instances_found


def get_instance_hourly_cost(instance_type, region_name):
    """Get approximate hourly cost for an instance type"""
    # This is a simplified pricing model - actual costs may vary
    # Based on On-Demand pricing for Linux instances

    pricing_map = {
        # General Purpose
        "t2.nano": 0.0058,
        "t2.micro": 0.0116,
        "t2.small": 0.023,
        "t2.medium": 0.0464,
        "t2.large": 0.0928,
        "t3.nano": 0.0052,
        "t3.micro": 0.0104,
        "t3.small": 0.0208,
        "t3.medium": 0.0416,
        "t3.large": 0.0832,
        "t4g.nano": 0.0042,
        "t4g.micro": 0.0084,
        "t4g.small": 0.0168,
        "t4g.medium": 0.0336,
        "t4g.large": 0.0672,
        # Compute Optimized
        "c5.large": 0.085,
        "c5.xlarge": 0.17,
        "c5.2xlarge": 0.34,
        "c5.4xlarge": 0.68,
        "c6i.large": 0.0765,
        "c6i.xlarge": 0.153,
        "c6i.2xlarge": 0.306,
        "c7g.medium": 0.0363,
        "c7g.large": 0.0725,
        "c7g.xlarge": 0.145,
        "c7gn.medium": 0.0435,  # Network optimized
        "c7gn.large": 0.087,
        "c7gn.xlarge": 0.174,
        # Memory Optimized
        "r5.large": 0.126,
        "r5.xlarge": 0.252,
        "r5.2xlarge": 0.504,
        "r6i.large": 0.1008,
        "r6i.xlarge": 0.2016,
        # Storage Optimized
        "i3.large": 0.156,
        "i3.xlarge": 0.312,
        "i4i.large": 0.1562,
        "i4i.xlarge": 0.3125,
    }

    # Regional pricing adjustments (us-east-1 is baseline)
    regional_multipliers = {
        "us-east-1": 1.0,
        "us-east-2": 1.0,
        "us-west-1": 1.1,
        "us-west-2": 1.0,
        "eu-west-1": 1.1,
        "eu-west-2": 1.1,
        "eu-central-1": 1.1,
        "ap-southeast-1": 1.15,
        "ap-northeast-1": 1.15,
    }

    if instance_type not in pricing_map:
        raise ValueError(f"Unknown instance type: {instance_type}. " f"Add pricing for this instance type to the pricing_map.")
    base_cost = pricing_map[instance_type]

    if region_name not in regional_multipliers:
        raise ValueError(f"Unknown region: {region_name}. " f"Add pricing multiplier for this region to regional_multipliers.")
    regional_multiplier = regional_multipliers[region_name]

    return base_cost * regional_multiplier


def _process_single_volume(volume):
    """Process a single EBS volume and return its details."""
    volume_id = volume["VolumeId"]
    volume_type = volume["VolumeType"]
    size_gb = volume["Size"]
    state = volume["State"]
    iops = volume.get("Iops")
    throughput = volume.get("Throughput")

    monthly_cost = calculate_ebs_monthly_cost(volume_type, size_gb, iops, throughput)

    attachments = []
    if "Attachments" in volume:
        attachments = volume["Attachments"]
    attached_to = attachments[0]["InstanceId"] if attachments and "InstanceId" in attachments[0] else None

    print(f"Volume: {volume_id}")
    print(f"  Type: {volume_type}")
    print(f"  Size: {size_gb} GB")
    print(f"  State: {state}")
    print(f"  IOPS: {iops}")
    if throughput:
        print(f"  Throughput: {throughput} MB/s")
    print(f"  Attached to: {attached_to or 'None'}")
    print(f"  Monthly cost: ${monthly_cost:.2f}")
    print()

    return {
        "volume_id": volume_id,
        "volume_type": volume_type,
        "size_gb": size_gb,
        "state": state,
        "attached_to": attached_to,
        "monthly_cost": monthly_cost,
    }


def analyze_ebs_volumes_in_region(region_name):
    """Analyze EBS volumes and their costs"""
    print(f"\n💾 Analyzing EBS Storage in {region_name}")
    print("=" * 80)

    try:
        ec2 = create_client("ec2", region=region_name)
        volumes_response = ec2.describe_volumes()
        volumes = []
        if "Volumes" in volumes_response:
            volumes = volumes_response["Volumes"]

        if not volumes:
            print(f"✅ No EBS volumes found in {region_name}")
            return []

        volume_details = [_process_single_volume(volume) for volume in volumes]
        total_storage_cost = sum(vol["monthly_cost"] for vol in volume_details)

        print(f"📊 EBS Summary for {region_name}:")
        print(f"  Total volumes: {len(volumes)}")
        print(f"  Total monthly storage cost: ${total_storage_cost:.2f}")

    except ClientError as e:
        print(f"❌ Error analyzing EBS in {region_name}: {e}")
        return []

    return volume_details


def calculate_ebs_monthly_cost(volume_type, size_gb, iops, throughput):
    """
    Calculate monthly EBS cost based on volume type and specifications.
    Delegates to canonical implementation in cost_utils.
    """
    return calculate_ebs_volume_cost(size_gb, volume_type, iops, throughput)


def _print_instance_summary(running_instances, stopped_instances, total_compute_cost):
    """Print EC2 instance summary"""
    print("💻 EC2 INSTANCES:")
    print(f"  Running instances: {len(running_instances)}")
    print(f"  Stopped instances: {len(stopped_instances)}")
    print(f"  Monthly compute cost: ${total_compute_cost:.2f}")

    if running_instances:
        print("\n  Running instance details:")
        for instance in running_instances:
            print(f"    {instance['instance_id']} ({instance['instance_type']}) - " f"${instance['monthly_cost']:.2f}/month")


def _print_storage_summary(all_volumes, total_storage_cost):
    """Print EBS storage summary"""
    print("\n💾 EBS STORAGE:")
    print(f"  Total volumes: {len(all_volumes)}")
    print(f"  Monthly storage cost: ${total_storage_cost:.2f}")


def _print_cost_breakdown(total_compute_cost, total_storage_cost):
    """Print total cost breakdown"""
    total_ec2_cost = total_compute_cost + total_storage_cost
    print("\n💰 TOTAL EC2 COSTS:")
    print(f"  Compute (instances): ${total_compute_cost:.2f}/month")
    print(f"  Storage (EBS): ${total_storage_cost:.2f}/month")
    print(f"  Total EC2: ${total_ec2_cost:.2f}/month")


def _print_billing_explanation():
    """Print explanation of billing line items"""
    print("\n📋 WHAT IS 'AMAZON ELASTIC COMPUTE CLOUD - COMPUTE'?")
    print("  This billing line item includes:")
    print("    1. EC2 Instance hours (compute time)")
    print("    2. EBS storage costs (disk space)")
    print("    3. EBS IOPS and throughput charges")
    print("    4. Data transfer within EC2")
    print("    5. Elastic IP addresses (if any)")
    print("    6. Load balancer costs (if any)")


def _print_optimization_recommendations(stopped_instances, running_instances, total_storage_cost, total_compute_cost):
    """Print cost optimization recommendations"""
    print("\n💡 COST OPTIMIZATION OPPORTUNITIES:")

    if stopped_instances:
        print("  🔄 Stopped instances still incur EBS storage costs")
        print("     Consider terminating unused instances")

    if len(running_instances) > 1:
        print("  📊 Multiple running instances detected")
        print("     Review if all instances are necessary")

    if total_storage_cost > total_compute_cost:
        print("  💾 Storage costs exceed compute costs")
        print("     Review EBS volumes for optimization opportunities")

    print("\n🔍 NEXT STEPS:")
    print("  1. Review each running instance's necessity")
    print("  2. Consider rightsizing instance types")
    print("  3. Evaluate EBS volume types and sizes")
    print("  4. Look into Reserved Instances for long-term workloads")


def _collect_regional_data(target_regions):
    """Collect EC2 instance and EBS volume data from all target regions."""
    all_instances = []
    all_volumes = []
    total_compute_cost = 0
    total_storage_cost = 0

    for region in target_regions:
        instances = analyze_ec2_instances_in_region(region)
        volumes = analyze_ebs_volumes_in_region(region)

        all_instances.extend(instances)
        all_volumes.extend(volumes)

        region_compute_cost = sum(i["monthly_cost"] for i in instances if i["state"] == "running")
        region_storage_cost = sum(v["monthly_cost"] for v in volumes)

        total_compute_cost += region_compute_cost
        total_storage_cost += region_storage_cost

    return {
        "all_instances": all_instances,
        "all_volumes": all_volumes,
        "total_compute_cost": total_compute_cost,
        "total_storage_cost": total_storage_cost,
    }


def main():
    """Perform detailed EC2 compute resource audit."""
    print("AWS EC2 Compute Detailed Cost Analysis")
    print("=" * 80)
    print("Analyzing 'Amazon Elastic Compute Cloud - Compute' costs...")

    get_all_regions()
    regions = get_all_aws_regions()

    data = _collect_regional_data(regions)
    all_instances = data["all_instances"]
    all_volumes = data["all_volumes"]
    total_compute_cost = data["total_compute_cost"]
    total_storage_cost = data["total_storage_cost"]

    print("\n" + "=" * 80)
    print("🎯 OVERALL EC2 COST BREAKDOWN")
    print("=" * 80)

    running_instances = [i for i in all_instances if i["state"] == "running"]
    stopped_instances = [i for i in all_instances if i["state"] == "stopped"]

    _print_instance_summary(running_instances, stopped_instances, total_compute_cost)
    _print_storage_summary(all_volumes, total_storage_cost)
    _print_cost_breakdown(total_compute_cost, total_storage_cost)
    _print_billing_explanation()
    _print_optimization_recommendations(stopped_instances, running_instances, total_storage_cost, total_compute_cost)


if __name__ == "__main__":
    main()
