#!/usr/bin/env python3
"""
S3 Bucket Migration Script V2 - Optimized with AWS CLI sync.

This script safely migrates all files from S3 buckets to local storage:
1. Scans all buckets and detects Glacier files
2. Requests Glacier restores (90 days)
3. Waits for all Glacier restores to complete
4. For each bucket (one at a time):
   a. Downloads using AWS CLI (aws s3 sync)
   b. Verifies files locally
   c. Deletes from S3 after manual confirmation

Each bucket is completed fully before moving to the next.
Interrupted migrations resume from the last incomplete bucket.

Usage:
    python migrate_v2.py           # Run/resume migration
    python migrate_v2.py status    # Show current status
    python migrate_v2.py reset     # Reset and start over
"""
import argparse
import shutil
import signal
import sys
from pathlib import Path
from threading import Event

import boto3

import config as config_module
import migrate_v2_smoke as smoke_tests
from migration_orchestrator import (
    MigrationFatalError,
    migrate_all_buckets,
    show_migration_status,
)
from migration_scanner import request_all_restores, scan_all_buckets, wait_for_restores
from migration_state_v2 import MigrationStateV2, Phase
from state_db_admin import recreate_state_db

LOCAL_BASE_PATH = config_module.LOCAL_BASE_PATH
STATE_DB_PATH = config_module.STATE_DB_PATH
config = config_module  # expose module for tests


def reset_migration_state():
    """Reset all cached migrate_v2 state and recreate an empty database."""

    print("\n" + "=" * 70)
    print("RESET MIGRATION")
    print("=" * 70)
    print()
    print("This will delete all migration state and start over.")
    print("Local files will NOT be deleted.")
    print()
    response = input("Are you sure? (yes/no): ")
    if response.lower() == "yes":
        target = Path(STATE_DB_PATH).expanduser()
        existed = target.exists()
        recreated_path = recreate_state_db(target)
        print()
        if existed:
            print(f"✓ State database reset at {recreated_path}")
        else:
            print(f"✓ Created fresh state database at {recreated_path}")
        print("Run 'python migrate_v2.py' to start fresh")
    else:
        print()
        print("Reset cancelled")


def check_drive_available(base_path: Path):
    """Check if the destination drive is mounted and writable"""
    parent = base_path.parent
    if not parent.exists():
        print()
        print("=" * 70)
        print("DRIVE NOT AVAILABLE")
        print("=" * 70)
        print("The destination drive is not mounted:")
        print(f"  Expected: {parent}")
        print()
        print("Please:")
        print("  1. Connect your external drive")
        print("  2. Ensure it's mounted at the correct location")
        print("  3. Run the migration again")
        print("=" * 70)
        sys.exit(1)
    try:
        base_path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print()
        print("=" * 70)
        print("PERMISSION DENIED")
        print("=" * 70)
        print("Cannot write to destination:")
        print(f"  Path: {base_path}")
        print()
        print("Please check:")
        print("  1. The drive is properly mounted")
        print("  2. You have write permissions")
        print("=" * 70)
        sys.exit(1)


class S3MigrationV2:
    """Main orchestrator for S3 to local migration using AWS CLI"""

    def __init__(self, s3, state: MigrationStateV2, base_path: Path):
        self.s3 = s3
        self.state = state
        self.base_path = base_path
        self.interrupted = Event()
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, _signum, _frame):
        """Handle Ctrl+C gracefully"""
        self.interrupted.set()
        print("\n" + "=" * 70)
        print("MIGRATION INTERRUPTED")
        print("=" * 70)
        print("State has been saved.")
        print("Run 'python migrate_v2.py' to resume from where you left off.")
        print("=" * 70)
        sys.exit(0)

    def run(self):
        """Main entry point - determines current phase and continues"""
        print("\n" + "=" * 70)
        print("S3 MIGRATION V2 - OPTIMIZED WITH AWS CLI")
        print("=" * 70)
        print(f"Destination: {LOCAL_BASE_PATH}")
        print(f"State DB: {STATE_DB_PATH}")
        print()
        if shutil.which("aws") is None:
            print("✗ AWS CLI not found on PATH. Install AWS CLI v2 and retry.")
            print("Download: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html")
            sys.exit(1)
        check_drive_available(self.base_path)
        current_phase = self.state.get_current_phase()
        if current_phase == Phase.COMPLETE:
            print("✓ Migration already complete!")
            show_migration_status(self.state)
            return
        print(f"Resuming from: {current_phase.value}")
        print()
        if current_phase == Phase.SCANNING:
            scan_all_buckets(self.s3, self.state, self.interrupted)
            current_phase = Phase.GLACIER_RESTORE
        if current_phase == Phase.GLACIER_RESTORE:
            request_all_restores(self.s3, self.state, self.interrupted)
            current_phase = Phase.GLACIER_WAIT
        if current_phase == Phase.GLACIER_WAIT:
            wait_for_restores(self.s3, self.state, self.interrupted)
            current_phase = Phase.SYNCING
        if current_phase in {Phase.SYNCING, Phase.VERIFYING, Phase.DELETING}:
            try:
                migrate_all_buckets(self.s3, self.state, self.base_path, check_drive_available, self.interrupted)
            except MigrationFatalError:
                sys.exit(1)
            current_phase = self.state.get_current_phase()
        if current_phase == Phase.COMPLETE:
            self._print_completion_message()

    def _print_completion_message(self):
        """Print migration completion message"""
        self.state.set_current_phase(Phase.COMPLETE)
        print("\n" + "=" * 70)
        print("✓ MIGRATION COMPLETE!")
        print("=" * 70)
        print("All files have been migrated and verified.")
        print("All S3 buckets have been deleted.")
        print("=" * 70)

    def show_status(self):
        """Display current migration status"""
        show_migration_status(self.state)

    def reset(self):
        """Reset all state and start from beginning"""
        reset_migration_state()


def create_migrator() -> S3MigrationV2:
    """Factory function to create S3MigrationV2 with all dependencies"""
    state = MigrationStateV2(config.STATE_DB_PATH)
    s3 = boto3.client("s3")
    base_path = Path(config.LOCAL_BASE_PATH)
    return S3MigrationV2(s3, state, base_path)


def run_smoke_test():
    """Run the smoke test using the shared helper module."""
    smoke_tests.run_smoke_test(config, check_drive_available, create_migrator)


def main():
    """Main entry point for S3 migration"""
    parser = argparse.ArgumentParser(
        description="S3 Bucket Migration Tool V2 - Optimized with AWS CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["status", "reset"],
        help="Command to execute (default: run migration)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run a local smoke test that simulates the backup workflow",
    )
    args = parser.parse_args()
    if args.test:
        run_smoke_test()
        return
    migrator = create_migrator()
    if args.command == "status":
        migrator.show_status()
    elif args.command == "reset":
        migrator.reset()
    else:
        migrator.run()


if __name__ == "__main__":
    main()
