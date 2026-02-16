"""Real S3 smoke-test flow for migrate_v2."""

from __future__ import annotations

import builtins
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boto3.session import Session
from botocore.exceptions import ClientError

from cost_toolkit.common.s3_utils import create_s3_bucket_with_region
from migrate_v2_smoke_shared import (
    SmokeTestDeps,
    create_sample_objects_in_s3,
    ensure_matching_manifests,
    manifest_directory,
)


def run_real_smoke_test(deps: SmokeTestDeps):
    """Seed real S3 data and run the full migrator."""
    ctx = RealSmokeContext.create(deps)
    try:
        stats = seed_real_bucket(ctx)
        run_real_workflow(ctx, stats)
        print_real_report(ctx, stats)
    finally:
        ctx.restore()


def _create_bucket(s3_client, bucket_name: str, region: str):
    """Create an S3 bucket in the desired region."""
    create_s3_bucket_with_region(s3_client, bucket_name, region)
    waiter = s3_client.get_waiter("bucket_exists")
    waiter.wait(Bucket=bucket_name)


def _collect_delete_objects(page):
    """Collect all objects and delete markers from a page for batch deletion."""
    objects = []
    if "Versions" in page:
        for version in page["Versions"]:
            objects.append({"Key": version["Key"], "VersionId": version["VersionId"]})
    if "DeleteMarkers" in page:
        for marker in page["DeleteMarkers"]:
            objects.append({"Key": marker["Key"], "VersionId": marker["VersionId"]})
    return objects


def _delete_bucket_and_contents(s3_client, bucket: str):
    """Delete all objects (and versions) from the bucket and remove the bucket."""
    try:
        paginator = s3_client.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=bucket):
            objects = _collect_delete_objects(page)
            if objects:
                s3_client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
        s3_client.delete_bucket(Bucket=bucket)
    except ClientError as exc:  # pragma: no cover - cleanup best effort
        error_obj = exc.response.get("Error")
        error_code = error_obj.get("Code") if error_obj else None
        if error_code not in {"NoSuchBucket", "404"}:
            raise


@dataclass
class RealSmokeContext:
    """Tracks resources allocated for the real S3 smoke test."""

    deps: SmokeTestDeps
    temp_dir: Path
    bucket_name: str
    state_db_path: Path
    external_drive_root: Path
    local_bucket_path: Path
    original_state_db: str
    original_exclusions: list[str]
    original_input: Any
    s3: Any
    region: str
    should_cleanup: bool
    bucket_created: bool

    @classmethod
    def create(cls, deps: SmokeTestDeps):
        """Build and validate the smoke-test context."""
        temp_dir = Path(tempfile.mkdtemp(prefix="migrate_v2_test_"))
        bucket_name = f"migrate-v2-smoke-{uuid.uuid4().hex}"
        session = Session()
        s3 = session.client("s3")
        region = session.region_name
        if not region:
            region = s3.meta.region_name
        if not region:
            raise RuntimeError(
                "AWS region not configured. Set AWS_DEFAULT_REGION environment variable "
                "or configure a default region in your AWS config."
            )
        state_db_path = temp_dir / "smoke_state.db"
        external_drive_root = Path(deps.config.LOCAL_BASE_PATH)
        deps.drive_checker_fn(external_drive_root)
        local_bucket_path = external_drive_root / bucket_name
        if local_bucket_path.exists():
            msg = f"Smoke-test path already exists: {local_bucket_path}"
            raise RuntimeError(msg)
        return cls(
            deps=deps,
            temp_dir=temp_dir,
            bucket_name=bucket_name,
            state_db_path=state_db_path,
            external_drive_root=external_drive_root,
            local_bucket_path=local_bucket_path,
            original_state_db=deps.config.STATE_DB_PATH,
            original_exclusions=list(deps.config.EXCLUDED_BUCKETS),
            original_input=builtins.input,
            s3=s3,
            region=region,
            should_cleanup=True,
            bucket_created=False,
        )

    def restore(self):
        """Restore global state and clean up allocated resources."""
        builtins.input = self.original_input
        config = self.deps.config
        config.STATE_DB_PATH = self.original_state_db
        config.EXCLUDED_BUCKETS = self.original_exclusions
        if self.bucket_created:
            _delete_bucket_and_contents(self.s3, self.bucket_name)
        if self.should_cleanup:
            shutil.rmtree(self.temp_dir, ignore_errors=True)


@dataclass(frozen=True)
class RealSmokeStats:
    """Captures the generated sample data for the real smoke test."""

    files_created: int
    dirs_created: int
    total_bytes: int
    manifest_expected: dict[str, str]


def seed_real_bucket(ctx: RealSmokeContext) -> RealSmokeStats:
    """Create a real S3 bucket with sample data."""
    print("Step 1/3: Creating sample data directly in S3...")
    _create_bucket(ctx.s3, ctx.bucket_name, ctx.region)
    ctx.bucket_created = True
    manifest_expected, files_created, dirs_created, total_bytes = create_sample_objects_in_s3(ctx.s3, ctx.bucket_name)
    print(f"  Uploaded {files_created} files to s3://{ctx.bucket_name}")
    buckets_response = ctx.s3.list_buckets()
    buckets_list = []
    if "Buckets" in buckets_response:
        buckets_list = buckets_response["Buckets"]
    existing_buckets = [b["Name"] for b in buckets_list]
    ctx.deps.config.EXCLUDED_BUCKETS = [b for b in existing_buckets if b != ctx.bucket_name]
    ctx.deps.config.STATE_DB_PATH = str(ctx.state_db_path)
    builtins.input = lambda _prompt="": "yes"
    return RealSmokeStats(
        files_created=files_created,
        dirs_created=dirs_created,
        total_bytes=total_bytes,
        manifest_expected=manifest_expected,
    )


def run_real_workflow(ctx: RealSmokeContext, stats: RealSmokeStats):
    """Execute the real migrator and clean up local artifacts."""
    print()
    print("Step 2/3: Running migrate_v2.py against the real S3 bucket...")
    migrator = ctx.deps.create_migrator()
    migrator.run()
    if not ctx.local_bucket_path.exists():
        msg = "Expected downloaded data at " f"{ctx.local_bucket_path}, but nothing was created"
        raise RuntimeError(msg)
    manifest_after = manifest_directory(ctx.local_bucket_path)
    ensure_matching_manifests(stats.manifest_expected, manifest_after)
    print("  Verified downloaded data matches the S3 source.")
    print()
    print("Step 3/3: Removing smoke-test data from the external drive...")
    shutil.rmtree(ctx.local_bucket_path, ignore_errors=True)
    print(f"  Deleted {ctx.local_bucket_path}")


def print_real_report(ctx: RealSmokeContext, stats: RealSmokeStats):
    """Display the final real smoke-test report."""
    print("\nSmoke test completed successfully!")
    print("=" * 70)
    print("SMOKE TEST REPORT")
    print("=" * 70)
    print(f"Bucket           : s3://{ctx.bucket_name}")
    print(f"Files processed  : {stats.files_created}")
    print(f"Directories used : {stats.dirs_created}")
    print(f"Total data       : {stats.total_bytes} bytes")
    print("External drive   :", ctx.external_drive_root)
    print("Flow             : create files -> run prod script -> delete local data")
    print("=" * 70)


__all__ = ["run_real_smoke_test"]
