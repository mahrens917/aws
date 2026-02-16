# cost_toolkit.scripts.optimization.snapshot_export_fixed

AWS EBS Snapshot to S3 export package with fail-fast error handling.

## Modules

- `cli.py` - CLI interface for fixed snapshot export
- `constants.py` - Constants and exceptions for snapshot export operations
- `export_helpers.py` - Helper functions for fixed export operations
- `export_ops.py` - Export operations with fail-fast error handling
- `monitoring.py` - Monitoring and S3 file validation
- `recovery.py` - Recovery and cleanup utilities

## Usage

Use the CLI to export EBS snapshots to S3 with automatic recovery and validation.
