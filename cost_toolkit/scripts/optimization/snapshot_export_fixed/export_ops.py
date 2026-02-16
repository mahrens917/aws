"""Export operations with fail-fast error handling"""

from cost_toolkit.common.s3_utils import create_s3_bucket_with_region

from .constants import ExportTaskDeletedException


def create_s3_bucket_new(s3_client, bucket_name, region):
    """Create new S3 bucket - fail fast on errors"""
    create_s3_bucket_with_region(s3_client, bucket_name, region)
    return True


def validate_export_task_exists(ec2_client, export_task_id):
    """Validate that export task still exists - raise exception if deleted"""
    response = ec2_client.describe_export_image_tasks(ExportImageTaskIds=[export_task_id])

    if not response["ExportImageTasks"]:
        msg = f"Export task {export_task_id} no longer exists - was deleted"
        raise ExportTaskDeletedException(msg)

    return response["ExportImageTasks"][0]


if __name__ == "__main__":  # pragma: no cover - script entry point
    pass
