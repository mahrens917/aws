"""
Optimization recommendation functions for S3 audit.
Generates cost-saving and security recommendations.
"""

from cost_toolkit.common.format_utils import format_bytes

from .constants import DAYS_THRESHOLD_GLACIER, DAYS_THRESHOLD_IA
from .utils import calculate_monthly_cost


def _create_ia_recommendation(old_objects):
    """Create recommendation for moving objects to Standard-IA"""
    old_standard_objects = [obj for obj in old_objects if obj["storage_class"] == "STANDARD" and obj["age_days"] > DAYS_THRESHOLD_IA]
    if not old_standard_objects:
        return None

    old_size = sum(obj["size_bytes"] for obj in old_standard_objects)
    current_cost = calculate_monthly_cost(old_size, "STANDARD")
    ia_cost = calculate_monthly_cost(old_size, "STANDARD_IA")
    savings = current_cost - ia_cost

    size_str = format_bytes(old_size, binary_units=False)
    return {
        "type": "storage_class_optimization",
        "description": (f"Move {len(old_standard_objects)} objects ({size_str}) older than 30 days " "to Standard-IA"),
        "potential_savings": savings,
        "action": "Create lifecycle policy to transition to Standard-IA after 30 days",
    }


def _create_glacier_recommendation(old_objects):
    """Create recommendation for archiving objects to Glacier"""
    very_old_objects = [
        obj for obj in old_objects if obj["storage_class"] in ["STANDARD", "STANDARD_IA"] and obj["age_days"] > DAYS_THRESHOLD_GLACIER
    ]
    if not very_old_objects:
        return None

    old_size = sum(obj["size_bytes"] for obj in very_old_objects)
    current_cost = calculate_monthly_cost(old_size, "STANDARD")
    glacier_cost = calculate_monthly_cost(old_size, "GLACIER")
    savings = current_cost - glacier_cost

    size_str = format_bytes(old_size, binary_units=False)
    return {
        "type": "archival_optimization",
        "description": (f"Archive {len(very_old_objects)} objects ({size_str}) older than 90 days " "to Glacier"),
        "potential_savings": savings,
        "action": "Create lifecycle policy to transition to Glacier after 90 days",
    }


def _check_storage_class_optimization(bucket_analysis):
    """Check for objects that could be moved to cheaper storage classes"""
    recommendations = []
    storage_classes = bucket_analysis["storage_classes"]
    standard_objects = storage_classes.get("STANDARD")

    if not standard_objects or standard_objects["size_bytes"] == 0:
        return recommendations

    ia_rec = _create_ia_recommendation(bucket_analysis["old_objects"])
    if ia_rec:
        recommendations.append(ia_rec)

    glacier_rec = _create_glacier_recommendation(bucket_analysis["old_objects"])
    if glacier_rec:
        recommendations.append(glacier_rec)

    return recommendations


def _check_lifecycle_and_versioning(bucket_analysis):
    """Check for lifecycle policy and versioning configuration issues"""
    recommendations = []

    if not bucket_analysis["lifecycle_policy"]:
        recommendations.append(
            {
                "type": "lifecycle_policy",
                "description": "No lifecycle policy configured",
                "potential_savings": 0,
                "action": ("Consider implementing lifecycle policies for automatic cost optimization"),
            }
        )

    if bucket_analysis["versioning_enabled"] and not bucket_analysis["lifecycle_policy"]:
        recommendations.append(
            {
                "type": "versioning_optimization",
                "description": "Versioning enabled but no lifecycle policy for old versions",
                "potential_savings": 0,
                "action": "Configure lifecycle policy to delete or archive old object versions",
            }
        )

    return recommendations


def _check_large_objects_and_security(bucket_analysis):
    """Check for large objects and public access security issues"""
    recommendations = []

    large_objects = bucket_analysis["large_objects"]
    if large_objects:
        total_large_size = sum(obj["size_bytes"] for obj in large_objects)
        large_size_str = format_bytes(total_large_size, binary_units=False)
        recommendations.append(
            {
                "type": "large_object_optimization",
                "description": (f"{len(large_objects)} large objects ({large_size_str}) found"),
                "potential_savings": 0,
                "action": "Consider using multipart uploads and compression for large objects",
            }
        )

    if bucket_analysis["public_access"]:
        recommendations.append(
            {
                "type": "security_optimization",
                "description": "Bucket may have public access configured",
                "potential_savings": 0,
                "action": "Review and restrict public access if not needed",
            }
        )

    return recommendations


def generate_optimization_recommendations(bucket_analysis):
    """Generate specific optimization recommendations for a bucket"""
    recommendations = []

    recommendations.extend(_check_storage_class_optimization(bucket_analysis))
    recommendations.extend(_check_lifecycle_and_versioning(bucket_analysis))
    recommendations.extend(_check_large_objects_and_security(bucket_analysis))

    return recommendations


if __name__ == "__main__":
    pass
