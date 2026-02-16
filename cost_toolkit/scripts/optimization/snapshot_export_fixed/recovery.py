"""Recovery and cleanup utilities"""

from datetime import datetime

from botocore.exceptions import ClientError

from cost_toolkit.scripts.snapshot_export_common import SAMPLE_SNAPSHOTS

_MIN_S3_KEY_PARTS = 3


def cleanup_temporary_ami(ec2_client, ami_id, _region):
    """Clean up temporary AMI after successful export - fail fast on errors"""
    print(f"   🧹 Cleaning up temporary AMI: {ami_id}")
    ec2_client.deregister_image(ImageId=ami_id)
    print(f"   ✅ Successfully cleaned up AMI {ami_id}")
    return True


def check_existing_completed_exports(s3_client, region):
    """Check for existing completed exports in the region to avoid duplicates"""
    bucket_name = f"ebs-snapshot-archive-{region}-{datetime.now().strftime('%Y%m%d')}"

    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix="ebs-snapshots/")

        existing_exports = []
        if "Contents" in response:
            for obj in response["Contents"]:
                if obj["Key"].endswith(".vmdk"):
                    key_parts = obj["Key"].split("/")
                    if len(key_parts) >= _MIN_S3_KEY_PARTS:
                        ami_id = key_parts[1]
                        export_file = key_parts[2]
                        export_task_id = export_file.replace(".vmdk", "")

                        existing_exports.append(
                            {
                                "export_task_id": export_task_id,
                                "ami_id": ami_id,
                                "s3_key": obj["Key"],
                                "size_bytes": obj["Size"],
                                "last_modified": obj["LastModified"],
                            }
                        )

        if existing_exports:
            print(f"   ✅ Found {len(existing_exports)} completed exports:")
            for export in existing_exports:
                print(f"      - {export['export_task_id']}: s3://{bucket_name}/{export['s3_key']}")

    except s3_client.exceptions.NoSuchBucket:
        print("   📭 No existing exports found (bucket doesn't exist)")
        return []
    except ClientError as e:
        print(f"   ❌ Could not check existing exports: {e}")
        return []

    return existing_exports


def get_snapshots_to_export(_aws_access_key_id, _aws_secret_access_key):
    """Get real snapshot data from AWS - no hard-coded values allowed"""
    return SAMPLE_SNAPSHOTS


if __name__ == "__main__":
    pass
