#!/usr/bin/env python3
"""
AWS EBS Post-Termination Audit
Checks if EBS volumes from terminated instances were properly deleted
"""


from botocore.exceptions import ClientError

from cost_toolkit.common.aws_client_factory import create_client
from cost_toolkit.common.aws_common import get_resource_tags


def _build_attachment_info(attachments):
    """Build attachment information string from volume attachments."""
    if not attachments:
        return "Unattached"

    attachment = attachments[0]
    instance_id = attachment.get("InstanceId")
    device = attachment.get("Device")
    state = attachment.get("State")
    delete_on_termination = attachment.get("DeleteOnTermination")
    return f"{instance_id} ({device}) - State: {state}, " f"DeleteOnTermination: {delete_on_termination}"


def _build_volume_detail(volume):
    """Build volume detail dictionary from volume data."""
    size_gb = volume["Size"]
    monthly_cost = size_gb * 0.08
    attachments = []
    if "Attachments" in volume:
        attachments = volume["Attachments"]
    attachment_info = _build_attachment_info(attachments)
    tags = get_resource_tags(volume)
    name = tags.get("Name")

    return {
        "VolumeId": volume["VolumeId"],
        "Name": name,
        "Size": size_gb,
        "State": volume["State"],
        "VolumeType": volume["VolumeType"],
        "CreateTime": volume["CreateTime"],
        "Attachment": attachment_info,
        "MonthlyCost": monthly_cost,
        "Tags": tags,
    }


def get_ebs_volumes_by_region(region_name):
    """Get all EBS volumes in a specific region with detailed information"""
    try:
        ec2 = create_client("ec2", region=region_name)
        response = ec2.describe_volumes()
        volumes = response["Volumes"]
        return [_build_volume_detail(volume) for volume in volumes]

    except ClientError as e:
        print(f"❌ Error getting volumes in {region_name}: {str(e)}")
        return []


def check_terminated_instances_volumes():
    """Check if volumes from our recently terminated instances still exist"""

    # The instances we just terminated
    terminated_instances = {
        "i-032b756f4ad7b1821": "Talker GPU",
        "i-079d5fb7d85c5e9ae": "Model",
        "i-0cfce47f50e3c34ff": "mufasa",
    }

    print("AWS EBS Post-Termination Audit")
    print("=" * 80)
    print("Checking if EBS volumes from terminated instances were properly deleted...")
    print()

    # Check us-east-1 where the terminated instances were
    print("🔍 Checking US-East-1 volumes...")
    print("-" * 50)

    us_east_1_volumes = get_ebs_volumes_by_region("us-east-1")

    total_cost = 0
    orphaned_volumes = []

    for volume in us_east_1_volumes:
        total_cost += volume["MonthlyCost"]

        # Check if this volume was attached to any of our terminated instances
        attachment_info = volume["Attachment"]
        is_orphaned = False

        for instance_id, instance_name in terminated_instances.items():
            if instance_id in attachment_info:
                is_orphaned = True
                orphaned_volumes.append(
                    {
                        "volume": volume,
                        "terminated_instance": instance_name,
                        "instance_id": instance_id,
                    }
                )
                break

        status_icon = "🔴" if is_orphaned else "✅"
        print(f"{status_icon} {volume['VolumeId']} - {volume['Name']}")
        print(f"    Size: {volume['Size']}GB | State: {volume['State']} | " f"Cost: ${volume['MonthlyCost']:.2f}/month")
        print(f"    Attachment: {volume['Attachment']}")
        print()

    print("=" * 80)
    print("📊 SUMMARY:")
    print(f"  Total volumes in us-east-1: {len(us_east_1_volumes)}")
    print(f"  Total monthly cost: ${total_cost:.2f}")
    print(f"  Orphaned volumes from terminated instances: {len(orphaned_volumes)}")

    if orphaned_volumes:
        print("\n🔴 ORPHANED VOLUMES FOUND:")
        orphaned_cost = 0
        for orphan in orphaned_volumes:
            vol = orphan["volume"]
            orphaned_cost += vol["MonthlyCost"]
            print(f"  • {vol['VolumeId']} ({vol['Size']}GB) - ${vol['MonthlyCost']:.2f}/month")
            print(f"    Was attached to: {orphan['terminated_instance']} ({orphan['instance_id']})")

        print(f"\n💰 Total orphaned volume cost: ${orphaned_cost:.2f}/month")
        print("⚠️  These volumes are still charging you even though instances are terminated!")
    else:
        print("\n✅ No orphaned volumes found - all volumes were properly deleted!")

    return orphaned_volumes


def main():
    """Check and report orphaned EBS volumes after instance termination."""
    orphaned_volumes = check_terminated_instances_volumes()

    if orphaned_volumes:
        print("\n" + "=" * 80)
        print("🛠️  RECOMMENDED ACTION:")
        print("Create a script to delete these orphaned volumes to stop ongoing charges.")
        print("Make sure to backup any important data first!")


if __name__ == "__main__":
    main()
