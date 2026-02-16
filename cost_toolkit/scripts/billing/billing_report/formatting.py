"""
Report formatting and display functions for AWS billing reports.
Contains functions to format and display billing data.
"""

from .cost_analysis import categorize_services, process_cost_data, process_usage_data
from .service_checks_extended import get_resolved_services_status


def display_regional_breakdown(service_cost, regions):
    """Display regional cost breakdown for a service."""
    print("\nRegional Breakdown:")
    print(f"{'Region':<25} {'Cost':<15} {'% of Service':<15}")
    print("-" * 55)

    sorted_regions = sorted(regions.items(), key=lambda x: x[1], reverse=True)
    for region, region_cost in sorted_regions:
        if region_cost > 0:
            region_percentage = (region_cost / service_cost * 100) if service_cost > 0 else 0
            print(f"{region:<25} ${region_cost:>12.2f} {region_percentage:>12.1f}%")


def display_usage_details(service, service_usage):
    """Display usage details for a service."""
    if service in service_usage and service_usage[service]:
        print("\nUsage Details:")
        print(f"{'Usage Type':<50} {'Quantity':<20} {'Unit':<15}")
        print("-" * 85)

        sorted_usage = sorted(service_usage[service], key=lambda x: x[1], reverse=True)[:10]
        for usage_type, quantity, unit in sorted_usage:
            print(f"{usage_type:<50} {quantity:>17,.2f} {unit:<15}")


def format_combined_billing_report(cost_data, usage_data):
    """Format and display the combined billing report with costs and usage details"""
    if not cost_data or "ResultsByTime" not in cost_data:
        print("No billing data available")
        return

    service_costs, total_cost = process_cost_data(cost_data)
    service_usage = process_usage_data(usage_data)
    resolved_services = get_resolved_services_status()

    print("\nCOMBINED AWS BILLING & USAGE REPORT")
    print("=" * 120)

    sorted_services = categorize_services(service_costs, resolved_services)

    for service, data in sorted_services:
        service_cost = data["cost"]
        percentage = (service_cost / total_cost * 100) if total_cost > 0 else 0
        service_key = service.upper()
        status_message = resolved_services.get(service_key)

        print(f"\n{service.upper()}")
        print("=" * 120)
        print(f"Total Cost: ${service_cost:,.2f} ({percentage:.1f}% of total)")

        if status_message:
            print(f"🔧 STATUS: {status_message}")

        display_regional_breakdown(service_cost, data["regions"])
        display_usage_details(service, service_usage)

        print("-" * 120)

    print(f"\nTOTAL AWS COST: ${total_cost:,.2f}")
    print("=" * 120)


if __name__ == "__main__":
    raise SystemExit("This module is library-only. Run cost_toolkit.scripts.billing.billing_report.cli instead.")
