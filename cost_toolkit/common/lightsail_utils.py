"""
Shared utilities for AWS Lightsail cost estimation.

This module provides canonical implementations for Lightsail pricing lookups.
All Lightsail cost estimation code should use these functions.
"""


class UnknownBundleError(ValueError):
    """Raised when a Lightsail bundle ID is not recognized."""


# Lightsail instance bundle pricing (approximate monthly costs)
INSTANCE_BUNDLE_COSTS = {
    "nano_2_0": 3.50,
    "micro_2_0": 5.00,
    "small_2_0": 10.00,
    "medium_2_0": 20.00,
    "large_2_0": 40.00,
    "xlarge_2_0": 80.00,
    "2xlarge_2_0": 160.00,
}

# Lightsail database bundle pricing (approximate monthly costs)
DATABASE_BUNDLE_COSTS = {
    "micro_1_0": 15.00,
    "small_1_0": 30.00,
    "medium_1_0": 60.00,
    "large_1_0": 115.00,
}


def estimate_instance_cost(bundle_id: str) -> float:
    """
    Estimate monthly cost for a Lightsail instance bundle.

    This is the canonical implementation. All code should use this.

    Args:
        bundle_id: Lightsail instance bundle ID (e.g., "nano_2_0")

    Returns:
        Estimated monthly cost in USD

    Raises:
        UnknownBundleError: If bundle_id is not in the known pricing table
    """
    if bundle_id not in INSTANCE_BUNDLE_COSTS:
        raise UnknownBundleError(f"Unknown Lightsail instance bundle: {bundle_id}")
    return INSTANCE_BUNDLE_COSTS[bundle_id]


def estimate_database_cost(bundle_id: str) -> float:
    """
    Estimate monthly cost for a Lightsail database bundle.

    This is the canonical implementation. All code should use this.

    Args:
        bundle_id: Lightsail database bundle ID (e.g., "micro_1_0")

    Returns:
        Estimated monthly cost in USD

    Raises:
        UnknownBundleError: If bundle_id is not in the known pricing table
    """
    if bundle_id not in DATABASE_BUNDLE_COSTS:
        raise UnknownBundleError(f"Unknown Lightsail database bundle: {bundle_id}")
    return DATABASE_BUNDLE_COSTS[bundle_id]


def load_lightsail_resources(lightsail_client) -> tuple[list[dict], list[dict]]:
    """
    Fetch Lightsail instances and databases in a single call site.

    This keeps client request handling consistent across cleanup scripts.
    """
    instances_response = lightsail_client.get_instances()
    instances = []
    if "instances" in instances_response:
        instances = instances_response["instances"]
    databases_response = lightsail_client.get_relational_databases()
    databases = []
    if "relationalDatabases" in databases_response:
        databases = databases_response["relationalDatabases"]
    return instances, databases
