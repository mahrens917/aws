#!/usr/bin/env python3
"""Generate final migration analysis summary."""

import boto3
from botocore.exceptions import ClientError

from cost_toolkit.scripts import aws_utils
from cost_toolkit.scripts.aws_utils import wait_for_instance_state

# Instance ID to stop
INSTANCE_ID = "i-05ad29f28fc8a8fdc"


def _stop_instance(ec2):
    """Stop the EC2 instance and wait for it to stop."""
    print(f"🛑 Stopping instance {INSTANCE_ID}...")
    try:
        ec2.stop_instances(InstanceIds=[INSTANCE_ID])
        print("   ✅ Instance stop initiated")

        print("   Waiting for instance to stop...")
        wait_for_instance_state(ec2, INSTANCE_ID, "instance_stopped")
        print("   ✅ Instance successfully stopped")

    except ClientError as e:
        print(f"   ❌ Error stopping instance: {str(e)}")
        raise

    print()


def _print_metadata_findings():
    """Print the metadata analysis findings."""
    print("🔍 METADATA ANALYSIS FINDINGS:")
    print("   ✅ All 3 remaining volumes have UNIQUE sizes:")
    print("      • Tars 3: 64 GB (boot/system volume)")
    print("      • 384 GB: 384 GB (data volume)")
    print("      • Tars 2: 1024 GB (primary data volume)")
    print()
    print("   📅 Creation Timeline:")
    print("      • 384 GB volume: Feb 5, 2025 (oldest)")
    print("      • Tars 2: Feb 6, 2025 (4.7 hours later)")
    print("      • Tars 3: Feb 6, 2025 (17 hours after Tars 2)")
    print()
    print("   📸 Snapshot Origins:")
    print("      • 384 GB: Created from blank (no snapshot)")
    print("      • Tars 2: Created from snapshot snap-03490193a42293c87")
    print("      • Tars 3: Created from snapshot snap-07a6773b0e0842e21")
    print()


def _print_duplicate_assessment():
    """Print the duplicate likelihood assessment."""
    print("💡 DUPLICATE LIKELIHOOD ASSESSMENT:")
    print("=" * 80)
    print("📦 Tars 3 (64 GB) - UNIQUE")
    print("   • Boot/system volume (attached as /dev/sda1)")
    print("   • Smallest size indicates OS/system files")
    print("   • Different purpose from data volumes")
    print("   • Verdict: KEEP - Essential system volume")
    print()

    print("📦 Tars 2 (1024 GB) - LIKELY UNIQUE")
    print("   • Large primary data volume (attached as /dev/sde)")
    print("   • Created from specific snapshot")
    print("   • Newest data volume with largest capacity")
    print("   • Verdict: KEEP - Primary data storage")
    print()

    print("📦 384 GB Volume - POTENTIALLY DUPLICATE")
    print("   • Medium data volume (attached as /dev/sdd)")
    print("   • Created 1 day before Tars 2")
    print("   • No snapshot origin (created fresh)")
    print("   • Could be: backup, different dataset, or duplicate")
    print("   • Verdict: NEEDS CONTENT INSPECTION")
    print()


def _print_final_recommendations():
    """Print final recommendations and next steps."""
    print("🎯 FINAL RECOMMENDATIONS:")
    print("=" * 80)
    print("Based on metadata analysis alone:")
    print()
    print("✅ DEFINITELY KEEP:")
    print("   • Tars 3 (64 GB) - System/boot volume - $5.12/month")
    print("   • Tars 2 (1024 GB) - Primary data volume - $81.92/month")
    print()
    print("❓ REQUIRES CONTENT ANALYSIS:")
    print("   • 384 GB volume - $30.72/month")
    print("     To determine if this is a duplicate of Tars 2 data")
    print()
    print("💰 POTENTIAL SAVINGS:")
    print("   If 384 GB volume is confirmed as duplicate: $30.72/month")
    print("   If 384 GB volume contains unique data: $0 savings")
    print()
    print("📋 NEXT STEPS FOR DEFINITIVE ANALYSIS:")
    print("   1. Start instance: python3 aws_london_ebs_analysis.py")
    print("   2. SSH into instance and mount volumes read-only")
    print("   3. Compare directory structures and file contents")
    print("   4. Look for overlapping data between 384 GB and Tars 2")
    print("   5. If duplicate confirmed, delete 384 GB volume")
    print()
    print("🏆 OPTIMIZATION SUMMARY:")
    print("   • Successfully eliminated 2 duplicate volumes (1056 GB)")
    print("   • Achieved $85/month in confirmed savings")
    print("   • Potential additional $30.72/month if 384 GB is duplicate")
    print("   • Total possible savings: $115.72/month")


def final_analysis_summary():
    """Stop instance and provide final analysis summary"""
    aws_utils.setup_aws_credentials()

    print("AWS London EBS Final Analysis Summary")
    print("=" * 80)

    ec2 = boto3.client("ec2", region_name="eu-west-2")

    _stop_instance(ec2)

    print("📊 LONDON EBS DUPLICATE ANALYSIS RESULTS")
    print("=" * 80)

    _print_metadata_findings()
    _print_duplicate_assessment()
    _print_final_recommendations()


def main():
    """Main function."""
    final_analysis_summary()


if __name__ == "__main__":
    main()
