"""Helper functions for fixed export operations"""

import time
from dataclasses import dataclass
from threading import Event

from botocore.exceptions import BotoCoreError, ClientError

from ..snapshot_export_common import print_export_status, start_ami_export_task
from . import constants
from .constants import (
    EXPORT_STATUS_CHECK_INTERVAL_SECONDS,
    ExportAPIException,
    ExportTaskDeletedException,
    ExportTaskFailedException,
    ExportTaskStuckException,
)
from .export_ops import validate_export_task_exists
from .monitoring import check_s3_file_completion

_WAIT_EVENT = Event()


@dataclass
class MonitoringState:
    """Track monitoring state for export progress."""

    start_time: float
    last_progress_change_time: float
    last_progress_value: int = 0
    consecutive_api_errors: int = 0


@dataclass
class S3Info:
    """S3 related context information."""

    bucket_name: str
    s3_key: str
    snapshot_size_gb: float


@dataclass
class ExportContext:
    """Context data for export monitoring operations."""

    ec2_client: object
    s3_client: object
    export_task_id: str
    s3_info: S3Info
    elapsed_hours: float
    current_time: float


def _start_export_task_fixed(ec2_client, ami_id, bucket_name):
    """Start AMI export task and return task ID and S3 key."""
    export_task_id, s3_key = start_ami_export_task(ec2_client, ami_id, bucket_name)
    print("   ⏳ Monitoring export progress with intelligent completion detection...")

    return export_task_id, s3_key


def _handle_task_deletion_recovery(s3_client, bucket_name, s3_key, snapshot_size_gb, elapsed_hours):
    """Handle export task deletion by checking S3 file."""
    print(f"   ⚠️  Export task was deleted after {elapsed_hours:.1f} hours")
    print("   🔍 Checking if S3 file was completed before task deletion...")

    try:
        s3_result = check_s3_file_completion(s3_client, bucket_name, s3_key, snapshot_size_gb, fast_check=True)
        print("   ✅ S3 file found and validated! Export completed successfully despite task deletion")
        print(f"   📏 Final file size: {s3_result['size_gb']:.2f} GB")
    except (BotoCoreError, ClientError, constants.S3FileValidationException, Exception) as s3_error:
        print("   ❌ Cannot retrieve export results - task no longer exists")
        msg = f"Export task deleted and no valid S3 file found: {s3_error}"
        raise ExportTaskDeletedException(msg) from s3_error
    return True, s3_key


def _fetch_export_task_status(ec2_client, export_task_id):
    """Fetch export task status with error handling."""
    task = validate_export_task_exists(ec2_client, export_task_id)
    return task, 0


def _check_terminal_state_fixed(task, status, elapsed_hours):
    """Check if export is in terminal state."""
    if status == "completed":
        print(f"   ✅ AWS reports export completed after {elapsed_hours:.1f} hours!")
        return True, "completed"

    if status == "failed":
        error_msg = task.get("StatusMessage") or "Unknown error"
        msg = f"AWS export failed after {elapsed_hours:.1f} hours: {error_msg}"
        raise ExportTaskFailedException(msg)

    if status == "deleted":
        return True, "deleted"

    return False, None


def _print_export_status(status, progress, status_msg, elapsed_hours):
    """Print formatted export status."""
    print_export_status(status, progress, status_msg, elapsed_hours)


def _track_progress_change(state: MonitoringState, current_progress: int, current_time: float) -> None:
    """Track and log progress changes."""
    if current_progress != state.last_progress_value:
        print(f"   📈 Progress updated to {current_progress}%")
        state.last_progress_value = current_progress
        state.last_progress_change_time = current_time


def _handle_api_errors(state: MonitoringState, exception: ClientError) -> None:
    """Handle API errors with retry logic."""
    state.consecutive_api_errors += 1
    print(f"   ❌ API error {state.consecutive_api_errors}/" f"{constants.MAX_CONSECUTIVE_API_ERRORS}: {exception}")

    if state.consecutive_api_errors >= constants.MAX_CONSECUTIVE_API_ERRORS:
        msg = f"Too many consecutive API errors ({state.consecutive_api_errors}) - failing fast"
        raise ExportAPIException(msg)


def _fetch_and_reset_errors(ec2_client, export_task_id, state):
    """Fetch task status and reset error counter."""
    task, _ = _fetch_export_task_status(ec2_client, export_task_id)
    state.consecutive_api_errors = 0
    return task


def _process_task_status(task, state, export_context):
    """Process and report task status, return tuple (should_continue, return_value or None)."""
    task_progress = task.get("Progress") or "N/A"
    task_status_msg = task.get("StatusMessage")
    _print_export_status(
        task["Status"],
        task_progress,
        task_status_msg,
        export_context.elapsed_hours,
    )

    current_progress = int(task_progress) if task_progress != "N/A" else 0
    _track_progress_change(state, current_progress, export_context.current_time)

    is_terminal, terminal_type = _check_terminal_state_fixed(task, task["Status"], export_context.elapsed_hours)
    if is_terminal:
        if terminal_type == "completed":
            return False, (True, export_context.s3_info.s3_key)
        if terminal_type == "deleted":
            return False, _handle_task_deletion_recovery(
                export_context.s3_client,
                export_context.s3_info.bucket_name,
                export_context.s3_info.s3_key,
                export_context.s3_info.snapshot_size_gb,
                export_context.elapsed_hours,
            )

    return True, None


def monitor_export_with_recovery(ec2_client, s3_client, export_task_id, s3_key, *, bucket_name, snapshot_size_gb):
    """Monitor export progress with recovery mechanisms."""
    current_time = time.time()
    state = MonitoringState(start_time=current_time, last_progress_change_time=current_time)

    while True:
        current_time = time.time()
        elapsed_hours = (current_time - state.start_time) / 3600

        if elapsed_hours >= constants.EXPORT_MAX_DURATION_HOURS:
            msg = f"Export exceeded maximum duration of {constants.EXPORT_MAX_DURATION_HOURS} hours - aborting"
            raise ExportTaskStuckException(msg)

        try:
            task = _fetch_and_reset_errors(ec2_client, export_task_id, state)
        except ExportTaskDeletedException:
            return _handle_task_deletion_recovery(s3_client, bucket_name, s3_key, snapshot_size_gb, elapsed_hours)
        except ClientError as e:
            _handle_api_errors(state, e)
            _WAIT_EVENT.wait(constants.EXPORT_STATUS_CHECK_INTERVAL_SECONDS)
            continue

        export_context = ExportContext(
            ec2_client=ec2_client,
            s3_client=s3_client,
            export_task_id=export_task_id,
            s3_info=S3Info(
                bucket_name=bucket_name,
                s3_key=s3_key,
                snapshot_size_gb=snapshot_size_gb,
            ),
            elapsed_hours=elapsed_hours,
            current_time=current_time,
        )
        should_continue, return_value = _process_task_status(task, state, export_context)
        if not should_continue:
            return return_value

        _WAIT_EVENT.wait(EXPORT_STATUS_CHECK_INTERVAL_SECONDS)


def export_ami_to_s3_with_recovery(ec2_client, s3_client, ami_id, bucket_name, _region, snapshot_size_gb):
    """
    Export AMI to S3 with proper error handling and recovery - fail fast on unrecoverable errors
    """
    export_task_id, s3_key = _start_export_task_fixed(ec2_client, ami_id, bucket_name)

    success, result_key = monitor_export_with_recovery(
        ec2_client,
        s3_client,
        export_task_id,
        s3_key,
        bucket_name=bucket_name,
        snapshot_size_gb=snapshot_size_gb,
    )

    if success:
        return export_task_id, result_key

    return None, None
