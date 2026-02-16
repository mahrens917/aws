"""Tests for migrate_v2_smoke_real helpers."""

from __future__ import annotations

import builtins
import uuid as uuid_module
from pathlib import Path
from types import SimpleNamespace

import pytest

import migrate_v2_smoke_real as real
from migrate_v2_smoke_shared import SmokeTestDeps, materialize_sample_tree


class _FakeWaiter:
    def __init__(self):
        self.calls = []

    def wait(self, **kwargs):
        """Record wait call."""
        self.calls.append(kwargs)

    def __repr__(self):
        return f"_FakeWaiter(calls={len(self.calls)})"


class _FakePaginator:
    def paginate(self, **_kwargs):
        """Yield empty object versions."""
        yield {"Versions": [], "DeleteMarkers": []}

    def __repr__(self):
        return "_FakePaginator()"


class _FakeS3:
    def __init__(self):
        self.meta = SimpleNamespace(region_name="us-west-2")
        self.created = []
        self.waiters = []
        self.put_calls = []
        self.bucket_name = "alpha"
        self.deleted_buckets = []

    def create_bucket(self, **kwargs):
        """Record bucket creation."""
        self.created.append(kwargs)

    def get_waiter(self, name):
        """Return fake waiter."""
        assert name == "bucket_exists"
        waiter = _FakeWaiter()
        self.waiters.append(waiter)
        return waiter

    def list_buckets(self):
        """Return list of buckets."""
        return {"Buckets": [{"Name": "alpha"}, {"Name": self.bucket_name}]}

    def put_object(self, **kwargs):
        """Record object put."""
        self.put_calls.append(kwargs)

    def get_paginator(self, name):
        """Return fake paginator."""
        assert name in {"list_object_versions"}
        return _FakePaginator()

    def delete_objects(self, **_kwargs):
        """Simulate object deletion."""
        return {}

    def delete_bucket(self, **_kwargs):
        """Simulate bucket deletion."""
        return {}


def _fake_drive_checker(path):
    """Fake drive checker that does nothing."""
    Path(path).mkdir(parents=True, exist_ok=True)


class _FakeMigrator:
    def __init__(self):
        self.ran = False

    def run(self):
        """Mark as run."""
        self.ran = True

    def __repr__(self):
        return f"_FakeMigrator(ran={self.ran})"


def _make_deps(tmp_path, fake_s3, monkeypatch):
    base_path = tmp_path / "drive"
    base_path.mkdir()
    config = SimpleNamespace(
        LOCAL_BASE_PATH=str(base_path),
        STATE_DB_PATH=str(tmp_path / "state.db"),
        EXCLUDED_BUCKETS=["keep-me"],
    )
    migrator = _FakeMigrator()

    class _FakeSession:
        region_name = "us-west-2"

        def client(self, service_name):
            """Return fake S3 client."""
            assert service_name == "s3"
            return fake_s3

        def __repr__(self):
            """Return string representation."""
            return f"_FakeSession(region={self.region_name})"

    monkeypatch.setattr(real, "Session", _FakeSession)
    deps = SmokeTestDeps(
        config=config,
        drive_checker_fn=_fake_drive_checker,
        create_migrator=lambda: migrator,
    )
    return deps, migrator


def testseed_real_bucket_updates_config(monkeypatch, tmp_path):
    """Test that seeding real bucket updates config."""
    fake_s3 = _FakeS3()
    deps, _ = _make_deps(tmp_path, fake_s3, monkeypatch)
    ctx = real.RealSmokeContext.create(deps)
    fake_s3.bucket_name = ctx.bucket_name
    original_input = builtins.input
    try:
        stats = real.seed_real_bucket(ctx)
    finally:
        builtins.input = original_input
    assert stats.files_created > 0
    assert deps.config.STATE_DB_PATH == str(ctx.state_db_path)
    assert ctx.bucket_name not in deps.config.EXCLUDED_BUCKETS
    assert fake_s3.put_calls  # ensure uploads occurred


def testrun_real_workflow_removes_local_data(monkeypatch, tmp_path):
    """Test that workflow removes local data after migration."""
    fake_s3 = _FakeS3()
    deps, migrator = _make_deps(tmp_path, fake_s3, monkeypatch)
    ctx = real.RealSmokeContext.create(deps)
    fake_s3.bucket_name = ctx.bucket_name
    original_input = builtins.input
    try:
        stats = real.seed_real_bucket(ctx)
    finally:
        builtins.input = original_input
    ctx.local_bucket_path.mkdir(parents=True, exist_ok=True)
    materialize_sample_tree(ctx.local_bucket_path)
    real.run_real_workflow(ctx, stats)
    assert migrator.ran
    assert not ctx.local_bucket_path.exists()


def testprint_real_report_outputs_sections(capsys, monkeypatch, tmp_path):
    """Test that report printing outputs expected sections."""
    fake_s3 = _FakeS3()
    deps, _ = _make_deps(tmp_path, fake_s3, monkeypatch)
    ctx = real.RealSmokeContext.create(deps)
    stats = real.RealSmokeStats(files_created=1, dirs_created=1, total_bytes=10, manifest_expected={})
    real.print_real_report(ctx, stats)
    output = capsys.readouterr().out
    assert "SMOKE TEST REPORT" in output
    assert "Files processed" in output


def test_context_restore_resets_state(tmp_path):
    """Test that context restore resets state."""
    temp_dir = tmp_path / "ctx"
    temp_dir.mkdir()
    original_input = builtins.input
    config = SimpleNamespace(
        STATE_DB_PATH="state.db",
        EXCLUDED_BUCKETS=["x"],
    )
    ctx = real.RealSmokeContext(
        deps=SmokeTestDeps(
            config=config,
            drive_checker_fn=_fake_drive_checker,
            create_migrator=_FakeMigrator,
        ),
        temp_dir=temp_dir,
        bucket_name="bucket",
        state_db_path=Path("new_state.db"),
        external_drive_root=Path(temp_dir),
        local_bucket_path=temp_dir / "bucket",
        original_state_db="state.db",
        original_exclusions=["orig"],
        original_input=original_input,
        s3=_FakeS3(),
        region="us-west-2",
        should_cleanup=True,
        bucket_created=False,
    )
    config.STATE_DB_PATH = "changed.db"
    config.EXCLUDED_BUCKETS = ["changed"]
    builtins.input = lambda _prompt=None: "modified"
    ctx.restore()
    assert config.STATE_DB_PATH == "state.db"
    assert config.EXCLUDED_BUCKETS == ["orig"]
    assert builtins.input == original_input
    assert not temp_dir.exists()


def test_context_restore_deletes_bucket_when_created(tmp_path):
    """Test that context restore deletes bucket when bucket_created is True."""
    temp_dir = tmp_path / "ctx"
    temp_dir.mkdir()
    original_input = builtins.input
    config = SimpleNamespace(
        STATE_DB_PATH="state.db",
        EXCLUDED_BUCKETS=["x"],
    )
    fake_s3 = _FakeS3()

    def track_delete_bucket(**kwargs):
        fake_s3.deleted_buckets.append(kwargs)
        return {}

    fake_s3.delete_bucket = track_delete_bucket  # type: ignore[method-assign]

    ctx = real.RealSmokeContext(
        deps=SmokeTestDeps(
            config=config,
            drive_checker_fn=_fake_drive_checker,
            create_migrator=_FakeMigrator,
        ),
        temp_dir=temp_dir,
        bucket_name="test-bucket",
        state_db_path=Path("new_state.db"),
        external_drive_root=Path(temp_dir),
        local_bucket_path=temp_dir / "bucket",
        original_state_db="state.db",
        original_exclusions=["orig"],
        original_input=original_input,
        s3=fake_s3,
        region="us-west-2",
        should_cleanup=True,
        bucket_created=True,
    )
    ctx.restore()
    assert len(fake_s3.deleted_buckets) == 1
    assert fake_s3.deleted_buckets[0]["Bucket"] == "test-bucket"


def test_context_create_raises_when_path_exists(monkeypatch, tmp_path):
    """Test that context creation raises when local bucket path already exists."""
    fake_s3 = _FakeS3()
    deps, _ = _make_deps(tmp_path, fake_s3, monkeypatch)
    base_path = Path(deps.config.LOCAL_BASE_PATH)
    # Create context once to get the bucket name pattern
    ctx = real.RealSmokeContext.create(deps)
    ctx.restore()

    # Create a directory that will conflict
    # We need to mock uuid to get a predictable bucket name
    mock_uuid = SimpleNamespace(hex="12345678901234567890123456789012")
    monkeypatch.setattr(uuid_module, "uuid4", lambda: mock_uuid)
    conflict_path = base_path / "migrate-v2-smoke-12345678901234567890123456789012"
    conflict_path.mkdir(parents=True)

    with pytest.raises(RuntimeError, match="already exists"):
        real.RealSmokeContext.create(deps)


def test_delete_bucket_and_contents_with_versions():
    """Test _delete_bucket_and_contents handles versions and markers."""
    deleted_objects = []

    def fake_paginate(**_kwargs):
        """Yield page with versions and markers."""
        yield {
            "Versions": [
                {"Key": "file1.txt", "VersionId": "v1"},
                {"Key": "file2.txt", "VersionId": "v2"},
            ],
            "DeleteMarkers": [
                {"Key": "deleted.txt", "VersionId": "dm1"},
            ],
        }

    fake_paginator = SimpleNamespace(paginate=fake_paginate)

    def fake_get_paginator(name):
        """Return paginator for list_object_versions."""
        assert name == "list_object_versions"
        return fake_paginator

    def fake_delete_objects(**kwargs):
        """Record delete_objects calls."""
        deleted_objects.append(kwargs)
        return {}

    fake_s3 = SimpleNamespace(
        get_paginator=fake_get_paginator,
        delete_objects=fake_delete_objects,
        delete_bucket=lambda **_kwargs: {},
    )
    real._delete_bucket_and_contents(fake_s3, "test-bucket")
    assert len(deleted_objects) == 1
    assert deleted_objects[0]["Bucket"] == "test-bucket"
    objects = deleted_objects[0]["Delete"]["Objects"]
    assert len(objects) == 3
    keys = {obj["Key"] for obj in objects}
    assert keys == {"file1.txt", "file2.txt", "deleted.txt"}


def test_run_real_smoke_test_success(monkeypatch, tmp_path, capsys):
    """Test run_real_smoke_test completes successfully."""
    fake_s3 = _FakeS3()
    deps, migrator = _make_deps(tmp_path, fake_s3, monkeypatch)
    bucket_name_holder = []

    original_seed = real.seed_real_bucket

    def patched_seed(ctx):
        bucket_name_holder.append(ctx.bucket_name)
        return original_seed(ctx)

    monkeypatch.setattr(real, "seed_real_bucket", patched_seed)

    def fake_run():
        migrator.ran = True
        # Create the local bucket path with expected structure using the actual bucket name
        base_path = Path(deps.config.LOCAL_BASE_PATH)
        bucket_path = base_path / bucket_name_holder[0]
        bucket_path.mkdir(parents=True, exist_ok=True)
        materialize_sample_tree(bucket_path)

    migrator.run = fake_run

    real.run_real_smoke_test(deps)
    output = capsys.readouterr().out
    assert "SMOKE TEST REPORT" in output
    assert migrator.ran


def test_run_real_workflow_raises_when_no_local_data(monkeypatch, tmp_path):
    """Test run_real_workflow raises when no local data is created."""
    fake_s3 = _FakeS3()
    deps, _ = _make_deps(tmp_path, fake_s3, monkeypatch)
    ctx = real.RealSmokeContext.create(deps)
    fake_s3.bucket_name = ctx.bucket_name
    original_input = builtins.input
    try:
        stats = real.seed_real_bucket(ctx)
    finally:
        builtins.input = original_input

    # Don't create local_bucket_path, so workflow should fail
    with pytest.raises(RuntimeError, match="Expected downloaded data"):
        real.run_real_workflow(ctx, stats)


def test_create_bucket_helper():
    """Test _create_bucket helper function."""
    waiter_calls = []
    created_buckets = []

    def fake_wait(**kwargs):
        """Record wait calls."""
        waiter_calls.append(kwargs)

    fake_waiter = SimpleNamespace(wait=fake_wait)

    def fake_create_bucket(**kwargs):
        """Record bucket creation."""
        created_buckets.append(kwargs)

    def fake_get_waiter(name):
        """Return fake waiter."""
        assert name == "bucket_exists"
        return fake_waiter

    fake_s3 = SimpleNamespace(
        create_bucket=fake_create_bucket,
        get_waiter=fake_get_waiter,
    )
    real._create_bucket(fake_s3, "my-bucket", "us-west-2")
    assert len(created_buckets) == 1
    assert waiter_calls[0]["Bucket"] == "my-bucket"


def test_real_smoke_stats_dataclass():
    """Test RealSmokeStats dataclass attributes."""
    stats = real.RealSmokeStats(
        files_created=5,
        dirs_created=2,
        total_bytes=1024,
        manifest_expected={"a": "b"},
    )
    assert stats.files_created == 5
    assert stats.dirs_created == 2
    assert stats.total_bytes == 1024
    assert stats.manifest_expected == {"a": "b"}
