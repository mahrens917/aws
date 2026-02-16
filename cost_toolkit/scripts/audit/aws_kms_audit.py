#!/usr/bin/env python3
"""Audit KMS encryption keys."""


from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import get_all_aws_regions


def _print_key_info(key_info):
    """Print details for a single KMS key"""
    description = key_info.get("Description")
    print(f"  Description: {description}")
    print(f"  Key Manager: {key_info['KeyManager']}")
    print(f"  Key State: {key_info['KeyState']}")
    print(f"  Creation Date: {key_info['CreationDate']}")

    # Estimate cost ($1/month for customer-managed keys)
    if key_info["KeyState"] in ["Enabled", "Disabled"]:
        print("  Estimated Cost: $1.00/month")
        return 1
    return 0


def _print_key_aliases(kms, key_id):
    """Print aliases for a KMS key.

    Note:
        Logs warnings on API errors but continues execution to allow audit to complete.
    """
    try:
        aliases = kms.list_aliases(KeyId=key_id)
        if aliases["Aliases"]:
            print(f"  Aliases: {[alias['AliasName'] for alias in aliases['Aliases']]}")
    except ClientError as e:
        print(f"  Aliases: (unable to retrieve: {e.response['Error']['Code']})")


def _print_key_grants(kms, key_id):
    """Print grants for a KMS key.

    Note:
        Logs warnings on API errors but continues execution to allow audit to complete.
    """
    try:
        grants = kms.list_grants(KeyId=key_id)
        if grants["Grants"]:
            print(f"  Active Grants: {len(grants['Grants'])}")
            for grant in grants["Grants"][:3]:  # Show first 3 grants
                grantee = grant.get("GranteePrincipal")
                operations = []
                if "Operations" in grant:
                    operations = grant["Operations"]
                print(f"    - Grantee: {grantee}")
                print(f"      Operations: {operations}")
    except ClientError as e:
        print(f"  Grants: (unable to retrieve: {e.response['Error']['Code']})")


def _process_kms_key(kms, key_id):
    """Process and display a single KMS key; returns cost estimate"""
    try:
        # Get key details
        key_details = kms.describe_key(KeyId=key_id)
        key_info = key_details["KeyMetadata"]

        # Skip AWS managed keys (they're free)
        if key_info["KeyManager"] == "AWS":
            return 0, False

        print(f"Key ID: {key_id}")
        cost = _print_key_info(key_info)
        _print_key_aliases(kms, key_id)
        _print_key_grants(kms, key_id)
        print()
    except ClientError as e:
        if "AccessDenied" not in str(e):
            print(f"  Error accessing key {key_id}: {e}")
        return 0, False
    return cost, True


def _audit_region_kms_keys(region):
    """Audit KMS keys in a single region; returns (region_keys, region_cost)"""
    try:
        kms = create_client("kms", region=region)
        keys = kms.list_keys()

        if not keys["Keys"]:
            return 0, 0

        print(f"\nRegion: {region}")
        print("-" * 40)

        region_keys = 0
        region_cost = 0

        for key in keys["Keys"]:
            key_id = key["KeyId"]
            cost, is_customer_key = _process_kms_key(kms, key_id)
            if is_customer_key:
                region_keys += 1
                region_cost += cost

        if region_keys > 0:
            print(f"Customer-managed keys in {region}: {region_keys}")
    except ClientError as e:
        if "not available" not in str(e).lower():
            print(f"Error accessing region {region}: {e}")
        return 0, 0
    return region_keys, region_cost


def _check_vpn_connections(ec2, region):
    """Check and display VPN connections in a region"""
    vpn_connections = ec2.describe_vpn_connections()
    if vpn_connections["VpnConnections"]:
        print(f"\nRegion {region} - VPN Connections found:")
        for vpn in vpn_connections["VpnConnections"]:
            print(f"  VPN ID: {vpn['VpnConnectionId']}")
            print(f"  State: {vpn['State']}")
            print(f"  Type: {vpn['Type']}")


def _check_customer_gateways(ec2, region):
    """Check and display customer gateways in a region"""
    customer_gateways = ec2.describe_customer_gateways()
    if customer_gateways["CustomerGateways"]:
        print(f"\nRegion {region} - Customer Gateways found:")
        for cgw in customer_gateways["CustomerGateways"]:
            print(f"  Gateway ID: {cgw['CustomerGatewayId']}")
            print(f"  State: {cgw['State']}")
            print(f"  Type: {cgw['Type']}")


def _check_vpn_gateways(ec2, region):
    """Check and display VPN gateways in a region"""
    vpn_gateways = ec2.describe_vpn_gateways()
    if vpn_gateways["VpnGateways"]:
        print(f"\nRegion {region} - VPN Gateways found:")
        for vgw in vpn_gateways["VpnGateways"]:
            print(f"  Gateway ID: {vgw['VpnGatewayId']}")
            print(f"  State: {vgw['State']}")
            print(f"  Type: {vgw['Type']}")


def _check_vpn_resources(region):
    """Check VPN resources in a specific region"""
    try:
        ec2 = create_client("ec2", region=region)
        _check_vpn_connections(ec2, region)
        _check_customer_gateways(ec2, region)
        _check_vpn_gateways(ec2, region)
    except ClientError as e:
        print(f"Error checking VPN resources in {region}: {e}")


def audit_kms_keys():
    """Audit KMS keys across all regions to identify where they're being used"""
    # Get all AWS regions
    ec2 = create_client("ec2", region="us-east-1")
    regions = [region["RegionName"] for region in ec2.describe_regions()["Regions"]]

    print("AWS KMS Key Usage Audit")
    print("=" * 80)

    total_keys = 0
    total_cost_estimate = 0

    for region in regions:
        region_keys, region_cost = _audit_region_kms_keys(region)
        total_keys += region_keys
        total_cost_estimate += region_cost

    print("\n" + "=" * 80)
    print("SUMMARY:")
    print(f"Total customer-managed KMS keys: {total_keys}")
    print(f"Estimated monthly cost: ${total_cost_estimate:.2f}")
    print("Note: AWS-managed keys (free) are not included in this count")

    # Additional check for VPN-related resources
    print("\n" + "=" * 80)
    print("CHECKING FOR VPN-RELATED KMS USAGE:")
    print("-" * 40)

    for region in get_all_aws_regions():  # Regions with KMS costs
        _check_vpn_resources(region)


def main():
    """Main function."""
    audit_kms_keys()


if __name__ == "__main__":
    main()
