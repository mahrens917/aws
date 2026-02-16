"""Smoke test entrypoint for migrate_v2."""

from __future__ import annotations

import os

from migrate_v2_smoke_real import run_real_smoke_test
from migrate_v2_smoke_shared import SmokeTestDeps
from migrate_v2_smoke_simulated import run_simulated_smoke_test


def run_smoke_test(config_module, drive_checker_fn, create_migrator_fn):
    """Run smoke test in real S3 mode by default; support simulated mode for tests."""
    deps = SmokeTestDeps(
        config=config_module,
        drive_checker_fn=drive_checker_fn,
        create_migrator=create_migrator_fn,
    )
    print("\n" + "=" * 70)
    print("RUNNING LOCAL SMOKE TEST")
    print("=" * 70)
    if os.environ.get("MIGRATE_V2_SMOKE_FAKE_S3") == "1":
        run_simulated_smoke_test(deps)
    else:
        run_real_smoke_test(deps)


__all__ = ["run_smoke_test"]
