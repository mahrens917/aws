"""
Cost data processing and analysis for AWS billing reports.
Contains functions to retrieve and process cost and usage data.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError


def get_date_range():
    """Get the date range for the current month to today"""
    end_date = datetime.now().date()
    start_date = end_date.replace(day=1)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def get_combined_billing_data():
    """Retrieve both cost and usage data from AWS Cost Explorer"""
    ce_client = boto3.client("ce", region_name="us-east-1")

    start_date, end_date = get_date_range()

    print(f"Retrieving billing data from {start_date} to {end_date}")
    print("=" * 80)

    try:
        # Get cost and usage data grouped by service and region
        cost_response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity="MONTHLY",
            Metrics=["BlendedCost", "UsageQuantity"],
            GroupBy=[
                {"Type": "DIMENSION", "Key": "SERVICE"},
                {"Type": "DIMENSION", "Key": "REGION"},
            ],
        )

        # Get detailed usage data grouped by service and usage type
        usage_response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity="MONTHLY",
            Metrics=["UsageQuantity"],
            GroupBy=[
                {"Type": "DIMENSION", "Key": "SERVICE"},
                {"Type": "DIMENSION", "Key": "USAGE_TYPE"},
            ],
        )

    except ClientError as e:
        print(f"Error retrieving billing data: {str(e)}")
        return None, None

    return cost_response, usage_response


def process_cost_data(cost_data: Dict[str, Any]) -> tuple[Dict[str, Dict[str, Any]], float]:
    """Process cost data and return service costs and total cost."""
    total_cost = 0.0
    service_costs: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"cost": 0.0, "regions": defaultdict(float)})

    for result in cost_data["ResultsByTime"]:
        period_start = result["TimePeriod"]["Start"]
        period_end = result["TimePeriod"]["End"]

        print(f"\nBilling Period: {period_start} to {period_end}")
        print("-" * 80)

        for group in result["Groups"]:
            keys = group["Keys"]
            service = keys[0] if len(keys) > 0 else "Unknown Service"
            region = keys[1] if len(keys) > 1 else "Unknown Region"

            cost_amount = float(group["Metrics"]["BlendedCost"]["Amount"])

            if cost_amount > 0:
                service_costs[service]["cost"] += cost_amount
                service_costs[service]["regions"][region] += cost_amount
                total_cost += cost_amount

    return service_costs, total_cost


def process_usage_data(usage_data):
    """Process usage data and return service usage details."""
    service_usage = defaultdict(list)

    if usage_data and "ResultsByTime" in usage_data:
        for result in usage_data["ResultsByTime"]:
            for group in result["Groups"]:
                keys = group["Keys"]
                service = keys[0] if len(keys) > 0 else "Unknown Service"
                usage_type = keys[1] if len(keys) > 1 else "Unknown Usage Type"

                quantity = float(group["Metrics"]["UsageQuantity"]["Amount"])
                unit = group["Metrics"]["UsageQuantity"]["Unit"]

                if quantity > 0:
                    service_usage[service].append((usage_type, quantity, unit))

    return service_usage


def categorize_services(service_costs, resolved_services):
    """Categorize services into resolved, noted, and unresolved lists."""
    resolved_services_list = []
    noted_services_list = []
    unresolved_services_list = []

    for service, data in service_costs.items():
        service_key = service.upper()
        status_message = resolved_services.get(service_key)
        if status_message and "✅ RESOLVED" in status_message:
            resolved_services_list.append((service, data))
        elif status_message and "📝 NOTED" in status_message:
            noted_services_list.append((service, data))
        else:
            unresolved_services_list.append((service, data))

    unresolved_services_list.sort(key=lambda x: x[1]["cost"], reverse=True)
    noted_services_list.sort(key=lambda x: x[1]["cost"], reverse=True)
    resolved_services_list.sort(key=lambda x: x[1]["cost"], reverse=True)

    return unresolved_services_list + noted_services_list + resolved_services_list


if __name__ == "__main__":
    raise SystemExit("This module is library-only. Run cost_toolkit.scripts.billing.billing_report.cli instead.")
