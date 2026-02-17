"""
AWS Cost Optimization Opportunity Analysis
Scans for unattached EBS volumes, unused Elastic IPs, and old snapshots.
"""

from datetime import datetime, timedelta, timezone

import boto3

from cost_toolkit.common.aws_common import get_all_aws_regions
from cost_toolkit.common.cost_utils import calculate_ebs_volume_cost, calculate_snapshot_cost


def _scan_region_for_unattached_volumes(region):
    """Scan a single region for unattached EBS volumes.

    Raises:
        ClientError: If API call fails
    """
    ec2 = boto3.client("ec2", region_name=region)
    volumes = ec2.describe_volumes()["Volumes"]

    count = 0
    total_cost = 0.0

    for volume in volumes:
        attachments = []
        if "Attachments" in volume:
            attachments = volume["Attachments"]
        if not attachments:
            count += 1
            size_gb = volume["Size"]
            volume_type = volume["VolumeType"]
            total_cost += calculate_ebs_volume_cost(size_gb, volume_type)
    return count, total_cost


def _check_unattached_ebs_volumes():
    """Check for unattached EBS volumes across regions.

    Raises:
        ClientError: If API call fails
    """
    regions = get_all_aws_regions()
    unattached_volumes = 0
    unattached_cost = 0.0

    for region in regions:
        count, cost = _scan_region_for_unattached_volumes(region)
        unattached_volumes += count
        unattached_cost += cost

    if unattached_volumes > 0:
        return {
            "category": "EBS Optimization",
            "description": f"{unattached_volumes} unattached EBS volumes",
            "potential_savings": unattached_cost,
            "risk": "Low",
            "action": "Delete unused volumes after verification",
        }
    return None


def _check_unused_elastic_ips():
    """Check for unused Elastic IPs across regions.

    Raises:
        ClientError: If API call fails
    """
    elastic_ips = 0
    regions = get_all_aws_regions()
    for region in regions:
        ec2 = boto3.client("ec2", region_name=region)
        addresses = ec2.describe_addresses()["Addresses"]

        for address in addresses:
            if "InstanceId" not in address:
                elastic_ips += 1

    if elastic_ips > 0:
        return {
            "category": "VPC Optimization",
            "description": f"{elastic_ips} unattached Elastic IPs",
            "potential_savings": elastic_ips * 3.60,
            "risk": "Low",
            "action": "Release unused Elastic IPs",
        }
    return None


def _check_old_snapshots():
    """Check for old snapshots across regions.

    Raises:
        ClientError: If API call fails
    """
    old_snapshots = 0
    snapshot_cost = 0.0
    cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=90)

    for region in get_all_aws_regions():
        ec2 = boto3.client("ec2", region_name=region)
        snapshots = ec2.describe_snapshots(OwnerIds=["self"])["Snapshots"]

        for snapshot in snapshots:
            if snapshot["StartTime"] < cutoff_date:
                old_snapshots += 1
                size_gb = snapshot["VolumeSize"]
                snapshot_cost += calculate_snapshot_cost(size_gb)

    if old_snapshots > 0:
        return {
            "category": "Snapshot Optimization",
            "description": f"{old_snapshots} snapshots older than 90 days",
            "potential_savings": snapshot_cost,
            "risk": "Medium",
            "action": "Review and delete unnecessary old snapshots",
        }
    return None


def analyze_optimization_opportunities():
    """Analyze potential cost optimization opportunities"""
    opportunities = []

    checkers = [
        _check_unattached_ebs_volumes,
        _check_unused_elastic_ips,
        _check_old_snapshots,
    ]

    for checker in checkers:
        opportunity = checker()
        if opportunity:
            opportunities.append(opportunity)

    return opportunities
