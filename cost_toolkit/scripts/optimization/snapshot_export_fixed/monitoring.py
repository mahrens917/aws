"""Monitoring and S3 file validation"""

import time
from threading import Event

from botocore.exceptions import BotoCoreError, ClientError

from cost_toolkit.common.cost_utils import calculate_snapshot_cost

from . import constants
from .constants import S3FileValidationException

_WAIT_EVENT = Event()


def _perform_s3_stability_check_fixed(s3_client, bucket_name, s3_key, check_num):
    """Perform a single S3 stability check."""
    response = s3_client.head_object(Bucket=bucket_name, Key=s3_key)
    file_size_bytes = response["ContentLength"]
    file_size_gb = file_size_bytes / (1024**3)

    return {
        "check_num": check_num + 1,
        "size_bytes": file_size_bytes,
        "size_gb": file_size_gb,
        "last_modified": response["LastModified"],
        "timestamp": time.time(),
    }


def _handle_file_not_found(check_num):
    """Handle S3 file not found during stability check."""
    if check_num == 0:
        print("   📭 S3 file not found yet - this is normal during export")
        return []

    print("   ❌ S3 file disappeared during stability check - export may have failed")
    msg = "S3 file disappeared during validation"
    raise S3FileValidationException(msg)


def _compare_checks_fixed(stability_checks):
    """Compare stability checks and return updated list."""
    if len(stability_checks) <= 1:
        return stability_checks

    prev_check = stability_checks[-2]
    current_check = stability_checks[-1]

    if prev_check["size_bytes"] != current_check["size_bytes"]:
        print(f"   📈 File size changed: {prev_check['size_gb']:.2f} GB → " f"{current_check['size_gb']:.2f} GB")
        print("   ⏳ File still growing, continuing to monitor...")
        return [current_check]

    print(f"   ✅ File size stable: {current_check['size_gb']:.2f} GB")
    return stability_checks


def _get_stability_config(fast_check):
    """Get stability check configuration based on fast_check mode."""
    stability_required_minutes = constants.S3_FAST_CHECK_MINUTES if fast_check else constants.S3_STABILITY_CHECK_MINUTES
    check_interval_minutes = constants.S3_FAST_CHECK_INTERVAL_MINUTES if fast_check else constants.S3_STABILITY_CHECK_INTERVAL_MINUTES
    required_stable_checks = stability_required_minutes // check_interval_minutes

    return {
        "stability_required_minutes": stability_required_minutes,
        "check_interval_minutes": check_interval_minutes,
        "required_stable_checks": required_stable_checks,
    }


def _validate_final_size(final_check, expected_size_gb, stability_required_minutes):
    """Validate final file size and print results."""
    min_expected_gb = expected_size_gb * constants.VMDK_MIN_COMPRESSION_RATIO
    max_expected_gb = expected_size_gb * constants.VMDK_MAX_EXPANSION_RATIO

    if not min_expected_gb <= final_check["size_gb"] <= max_expected_gb:
        variance_percent = abs(final_check["size_gb"] - expected_size_gb) / expected_size_gb * 100
        print(
            f"   ⚠️  Size variance: Expected ~{expected_size_gb} GB, "
            f"got {final_check['size_gb']:.2f} GB ({variance_percent:.1f}% difference)"
        )

    print(f"   ✅ File stable for {stability_required_minutes} minutes " f"at {final_check['size_gb']:.2f} GB")


def check_s3_file_completion(s3_client, bucket_name, s3_key, expected_size_gb, fast_check=False):
    """Check if S3 file exists and is stable - fail fast on validation errors"""
    config = _get_stability_config(fast_check)
    stability_required_minutes = config["stability_required_minutes"]
    check_interval_minutes = config["check_interval_minutes"]
    required_stable_checks = config["required_stable_checks"]

    print(f"   🔍 Checking S3 file stability: s3://{bucket_name}/{s3_key}")

    stability_checks = []
    for check_num in range(required_stable_checks):
        try:
            check_data = _perform_s3_stability_check_fixed(s3_client, bucket_name, s3_key, check_num)
            stability_checks.append(check_data)

            print(f"   📊 Stability check {check_num + 1}/{required_stable_checks}: " f"{check_data['size_gb']:.2f} GB")

            stability_checks = _compare_checks_fixed(stability_checks)

        except s3_client.exceptions.NoSuchKey:
            stability_checks = _handle_file_not_found(check_num)
        except (BotoCoreError, ClientError) as exc:
            print(f"   ❌ Error checking S3 file: {exc}")
            msg = f"Failed to check S3 file: {exc}"
            raise S3FileValidationException(msg) from exc

        if check_num < required_stable_checks - 1:
            print(f"   ⏳ Waiting {check_interval_minutes} minutes for next stability check...")
            _WAIT_EVENT.wait(check_interval_minutes * 60)

    if len(stability_checks) < required_stable_checks:
        msg = f"File not stable - completed {len(stability_checks)}/{required_stable_checks} checks"
        raise S3FileValidationException(msg)

    final_check = stability_checks[-1]
    _validate_final_size(final_check, expected_size_gb, stability_required_minutes)

    return {
        "size_bytes": final_check["size_bytes"],
        "size_gb": final_check["size_gb"],
        "last_modified": final_check["last_modified"],
        "stability_checks": len(stability_checks),
    }


def verify_s3_export_final(s3_client, bucket_name, s3_key, expected_size_gb):
    """Final verification that the exported file exists in S3 - fail fast on errors"""
    print(f"   🔍 Final verification: s3://{bucket_name}/{s3_key}")

    response = s3_client.head_object(Bucket=bucket_name, Key=s3_key)

    file_size_bytes = response["ContentLength"]
    file_size_gb = file_size_bytes / (1024**3)
    last_modified = response["LastModified"]

    print("   ✅ File exists in S3!")
    print(f"   📏 File size: {file_size_gb:.2f} GB ({file_size_bytes:,} bytes)")
    print(f"   📅 Last modified: {last_modified}")

    min_expected_gb = expected_size_gb * constants.VMDK_MIN_COMPRESSION_RATIO
    max_expected_gb = expected_size_gb * constants.VMDK_MAX_EXPANSION_RATIO

    if not min_expected_gb <= file_size_gb <= max_expected_gb:
        msg = f"Final size validation failed: {file_size_gb:.2f} GB " f"(expected {min_expected_gb:.1f}-{max_expected_gb:.1f} GB)"
        raise S3FileValidationException(msg)

    print("   ✅ Size validation passed")

    return {"size_bytes": file_size_bytes, "size_gb": file_size_gb, "last_modified": last_modified}


def calculate_cost_savings(snapshot_size_gb):
    """
    Calculate cost savings from EBS to S3 Standard.
    Delegates EBS snapshot cost calculation to canonical implementation.
    """
    ebs_monthly_cost = calculate_snapshot_cost(snapshot_size_gb)
    s3_standard_cost = snapshot_size_gb * constants.S3_STANDARD_COST_PER_GB_MONTHLY
    monthly_savings = ebs_monthly_cost - s3_standard_cost
    annual_savings = monthly_savings * 12

    return {
        "ebs_cost": ebs_monthly_cost,
        "s3_cost": s3_standard_cost,
        "monthly_savings": monthly_savings,
        "annual_savings": annual_savings,
        "savings_percentage": (monthly_savings / ebs_monthly_cost) * 100,
    }


if __name__ == "__main__":
    pass
