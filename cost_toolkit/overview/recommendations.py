"""
AWS Service-Specific Cost Recommendations
Provides tailored recommendations for different AWS services based on usage patterns.
"""

import json
import os

# Cost thresholds for recommendations
COST_RECOMMENDATION_THRESHOLD = 5  # Minimum cost in dollars to trigger recommendations


def get_completed_cleanups():
    """Get list of completed cleanup actions to avoid duplicate recommendations"""
    cleanup_log_path = os.path.join("config", "cleanup_log.json")
    completed_services = set()

    try:
        if os.path.exists(cleanup_log_path):
            with open(cleanup_log_path, "r", encoding="utf-8") as f:
                log_data = json.load(f)
                cleanup_actions = []
                if "cleanup_actions" in log_data:
                    cleanup_actions = log_data["cleanup_actions"]
                for action in cleanup_actions:
                    status = action.get("status")
                    if status == "completed":
                        service = action.get("service")
                        completed_services.add(service.lower())
    except OSError as e:
        print(f"Failed to read cleanup log at {cleanup_log_path}: {e}")
    except json.JSONDecodeError as e:
        print(f"Cleanup log is not valid JSON at {cleanup_log_path}: {e}")

    return completed_services


def _add_storage_recommendations(recommendations, service, cost, percentage):
    """Add S3/storage-specific recommendations."""
    recommendations.append(f"💡 {service}: ${cost:.2f}/month ({percentage:.1f}%)")
    recommendations.append("   📋 Implement lifecycle policies or Glacier transitions for infrequently accessed data")
    recommendations.append("   🔧 Action: Review objects older than 30 days and move cold data to IA/Glacier classes")


def _add_ec2_recommendations(recommendations, service, cost, percentage):
    """Add EC2-specific recommendations."""
    recommendations.append(f"💡 {service}: ${cost:.2f}/month ({percentage:.1f}%)")
    recommendations.append("   📋 Consider Reserved or Savings Plans for predictable compute usage")
    recommendations.append("   🔧 Action: Analyze utilization metrics and match steady workloads with discounted capacity")


def _add_database_recommendations(recommendations, service, cost, percentage):
    """Add RDS/database-specific recommendations."""
    recommendations.append(f"💡 {service}: ${cost:.2f}/month ({percentage:.1f}%)")
    recommendations.append("   📋 Review DB instance sizing, storage type, and idle clusters; Aurora Serverless may fit bursty usage")
    recommendations.append("   🔧 Action: Monitor CPU/memory and storage metrics, then right-size or pause unused databases")


def _add_lightsail_recommendations(recommendations, service, cost, percentage, completed_cleanups):
    """Add Lightsail-specific recommendations."""
    if "lightsail" in completed_cleanups:
        recommendations.append(f"✅ {service}: ${cost:.2f}/month ({percentage:.1f}%)")
        recommendations.append("   📋 Lightsail cleanup previously completed; monitor for residual billing only")
        recommendations.append("   🔧 Status: No action needed unless new resources appear")
    else:
        recommendations.append(f"💡 {service}: ${cost:.2f}/month ({percentage:.1f}%)")
        recommendations.append("   📋 Lightsail resources detected - remove instances, databases, or static IPs to stop charges")
        recommendations.append("   🔧 Action: Run python cost_toolkit/scripts/cleanup/aws_lightsail_cleanup.py")


def _add_accelerator_recommendations(recommendations, service, cost, percentage):
    """Add Global Accelerator-specific recommendations."""
    recommendations.append(f"💡 {service}: ${cost:.2f}/month ({percentage:.1f}%)")
    recommendations.append("   📋 Global Accelerator is running; validate whether the accelerator still serves traffic")
    recommendations.append("   🔧 Action: Review listeners/endpoints and disable unused accelerators")


def _add_vpc_recommendations(recommendations, service, cost, percentage):
    """Add VPC-specific recommendations."""
    recommendations.append(f"💡 {service}: ${cost:.2f}/month ({percentage:.1f}%)")
    recommendations.append("   📋 VPC charges often originate from NAT Gateways or unattached Elastic IPs")
    recommendations.append("   🔧 Action: Audit gateway usage and release unused Elastic IPs")


def _add_cloudwatch_recommendations(recommendations, service, cost, percentage):
    """Add CloudWatch-specific recommendations."""
    recommendations.append(f"💡 {service}: ${cost:.2f}/month ({percentage:.1f}%)")
    recommendations.append("   📋 Review log retention and custom metrics to avoid storing data indefinitely")
    recommendations.append("   🔧 Action: Set retention to 30-90 days and remove unused canaries/metrics")


def _add_generic_recommendations(recommendations, service, cost, percentage):
    """Add generic service recommendations."""
    recommendations.append(f"💡 {service}: ${cost:.2f}/month ({percentage:.1f}%)")
    recommendations.append("   📋 Review usage patterns and consider optimization opportunities")


def _match_service_type(service_upper):
    """Determine service type from service name."""
    service_patterns = {
        "storage": ["S3", "STORAGE"],
        "ec2": ["EC2"],
        "database": ["RDS", "DATABASE"],
        "lightsail": ["LIGHTSAIL"],
        "accelerator": ["GLOBAL ACCELERATOR"],
        "vpc": ["VPC", "PRIVATE CLOUD"],
        "cloudwatch": ["CLOUDWATCH"],
    }

    for service_type, patterns in service_patterns.items():
        for pattern in patterns:
            if pattern in service_upper:
                return service_type

    return "generic"


def _route_to_service_handler(service_upper, recommendations, service, *, cost, percentage, completed_cleanups):
    """Route to appropriate service-specific handler."""
    service_type = _match_service_type(service_upper)

    handlers = {
        "storage": lambda: _add_storage_recommendations(recommendations, service, cost, percentage),
        "ec2": lambda: _add_ec2_recommendations(recommendations, service, cost, percentage),
        "database": lambda: _add_database_recommendations(recommendations, service, cost, percentage),
        "lightsail": lambda: _add_lightsail_recommendations(recommendations, service, cost, percentage, completed_cleanups),
        "accelerator": lambda: _add_accelerator_recommendations(recommendations, service, cost, percentage),
        "vpc": lambda: _add_vpc_recommendations(recommendations, service, cost, percentage),
        "cloudwatch": lambda: _add_cloudwatch_recommendations(recommendations, service, cost, percentage),
        "generic": lambda: _add_generic_recommendations(recommendations, service, cost, percentage),
    }

    handlers[service_type]()


def _add_service_recommendation(recommendations, service, cost, percentage, completed_cleanups):
    """Add recommendations for a specific service based on its type."""
    service_upper = service.upper()
    _route_to_service_handler(
        service_upper,
        recommendations,
        service,
        cost=cost,
        percentage=percentage,
        completed_cleanups=completed_cleanups,
    )


def get_service_recommendations(service_costs):
    """Get specific recommendations based on current service usage"""
    recommendations = []
    total_cost = sum(service_costs.values())
    completed_cleanups = get_completed_cleanups()

    for service, cost in sorted(service_costs.items(), key=lambda x: x[1], reverse=True)[:8]:
        if cost > COST_RECOMMENDATION_THRESHOLD:
            percentage = (cost / total_cost) * 100
            _add_service_recommendation(recommendations, service, cost, percentage, completed_cleanups)

    return recommendations
