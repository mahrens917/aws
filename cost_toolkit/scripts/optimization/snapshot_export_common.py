"""Canonical AWS-facing functions for snapshot export operations across all variants.

Reporting and sample data live in cost_toolkit.scripts.snapshot_export_common; import from
this module for any AWS interactions to avoid duplicated implementations.
"""

from datetime import datetime

from botocore.exceptions import ClientError

from cost_toolkit.common.s3_utils import create_s3_bucket_with_region
from cost_toolkit.common.waiter_utils import wait_ami_available


def wait_for_ami_available(ec2_client, ami_id, delay=30, max_attempts=40):
    """Wrapper used for test overrides while delegating to the canonical waiter."""
    return wait_ami_available(ec2_client, ami_id, delay=delay, max_attempts=max_attempts)


def create_s3_bucket_if_not_exists(s3_client, bucket_name, region, enable_versioning=True):
    """Create S3 bucket if it doesn't exist

    Args:
        s3_client: Boto3 S3 client
        bucket_name: Name of the bucket to create
        region: AWS region for bucket creation
        enable_versioning: Whether to enable versioning on new buckets

    Returns:
        True if bucket exists or was created successfully, False otherwise
    """
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"   ✅ S3 bucket {bucket_name} already exists")
    except ClientError:
        try:
            create_s3_bucket_with_region(s3_client, bucket_name, region)

            if enable_versioning:
                s3_client.put_bucket_versioning(Bucket=bucket_name, VersioningConfiguration={"Status": "Enabled"})
                print(f"   ✅ Enabled versioning for {bucket_name}")

        except ClientError as e:
            print(f"   ❌ Error creating bucket {bucket_name}: {e}")
            return False

        return True
    else:
        return True


def setup_s3_bucket_versioning(s3_client, bucket_name):
    """Enable S3 bucket versioning for data protection"""
    try:
        s3_client.put_bucket_versioning(Bucket=bucket_name, VersioningConfiguration={"Status": "Enabled"})
    except ClientError as exc:
        print(f"   ❌ Failed to enable versioning: {exc}")
        return False

    print(f"   ✅ Enabled versioning for {bucket_name}")
    return True


def create_ami_from_snapshot(
    ec2_client,
    snapshot_id,
    snapshot_description,
    *,
    volume_type="gp3",
    boot_mode=None,
    ena_support=True,
    attempt_suffix="",
):
    """Create an AMI from an EBS snapshot

    Args:
        ec2_client: Boto3 EC2 client
        snapshot_id: EBS snapshot ID to create AMI from
        snapshot_description: Description for the AMI
        volume_type: EBS volume type (gp3, gp2, etc.)
        boot_mode: Boot mode for the AMI (legacy-bios, uefi, or None for auto)
        ena_support: Whether to enable ENA support
        attempt_suffix: Suffix to add to AMI name (e.g., for retry attempts)

    Returns:
        AMI ID if successful, None otherwise
    """
    try:
        ami_id = _register_ami(
            ec2_client,
            snapshot_id,
            snapshot_description,
            volume_type=volume_type,
            boot_mode=boot_mode,
            ena_support=ena_support,
            attempt_suffix=attempt_suffix,
        )
        print(f"   ⏳ Waiting for AMI {ami_id} to become available...")
        wait_for_ami_available(ec2_client, ami_id, delay=30, max_attempts=40)
        print(f"   ✅ AMI {ami_id} is now available")
    except ClientError as e:
        print(f"   ❌ Error creating AMI from snapshot {snapshot_id}: {e}")
        return None
    return ami_id


def _register_ami(ec2_client, snapshot_id, description, *, volume_type, boot_mode, ena_support, attempt_suffix):
    """Register AMI from snapshot and return AMI ID"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    ami_name = f"export-{snapshot_id}-{timestamp}{attempt_suffix}"

    print(f"   🔄 Creating AMI from snapshot {snapshot_id}...")

    register_params = {
        "Name": ami_name,
        "Description": f"AMI for S3 export from {snapshot_id}: {description}",
        "Architecture": "x86_64",
        "RootDeviceName": "/dev/sda1",
        "BlockDeviceMappings": [
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "SnapshotId": snapshot_id,
                    "VolumeType": volume_type,
                    "DeleteOnTermination": True,
                },
            }
        ],
        "VirtualizationType": "hvm",
        "SriovNetSupport": "simple",
        "EnaSupport": ena_support,
    }

    if boot_mode:
        register_params["BootMode"] = boot_mode

    response = ec2_client.register_image(**register_params)
    ami_id = response["ImageId"]
    print(f"   ✅ Created AMI: {ami_id}")

    return ami_id


def start_ami_export_task(ec2_client, ami_id, bucket_name, snapshot_id=None):
    """Start AMI export to S3 and return export task ID

    Args:
        ec2_client: Boto3 EC2 client
        ami_id: AMI ID to export
        bucket_name: S3 bucket name for export
        snapshot_id: Optional snapshot ID for description

    Returns:
        Tuple of (export_task_id, s3_key)
    """
    print(f"   🔄 Starting export of AMI {ami_id} to S3 bucket {bucket_name}...")

    description = f"Export of AMI {ami_id} for cost optimization"
    if snapshot_id:
        description = f"Export of AMI {ami_id} from snapshot {snapshot_id}"

    response = ec2_client.export_image(
        ImageId=ami_id,
        DiskImageFormat="VMDK",
        S3ExportLocation={"S3Bucket": bucket_name, "S3Prefix": f"ebs-snapshots/{ami_id}/"},
        Description=description,
    )

    export_task_id = response["ExportImageTaskId"]
    s3_key = f"ebs-snapshots/{ami_id}/{export_task_id}.vmdk"

    print(f"   ✅ Started export task: {export_task_id}")

    return export_task_id, s3_key


def print_export_status(status, progress, status_msg, elapsed_hours):
    """Print formatted export status update

    Args:
        status: Export task status string
        progress: Progress percentage (int or 'N/A')
        status_msg: Optional status message from AWS
        elapsed_hours: Hours elapsed since export started
    """
    if status_msg:
        print(f"   📊 AWS Status: {status} | Progress: {progress}% | " f"Message: {status_msg} | Elapsed: {elapsed_hours:.1f}h")
    else:
        print(f"   📊 AWS Status: {status} | Progress: {progress}% | Elapsed: {elapsed_hours:.1f}h")


if __name__ == "__main__":
    raise SystemExit("This module is library-only. Import functions from cost_toolkit.scripts.optimization.snapshot_export_common.")
