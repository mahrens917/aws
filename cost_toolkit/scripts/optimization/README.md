# cost_toolkit.scripts.optimization

AWS resource optimization scripts for cost reduction.

## Modules

- `aws_export_recovery.py` - Checks if stuck exports have completed in S3
- `aws_s3_to_snapshot_restore.py` - Restores EBS snapshots from S3 exports
- `aws_snapshot_to_s3_export_fixed.py` - Exports EBS snapshots to S3 with fail-fast handling
- `aws_snapshot_to_s3_semi_manual.py` - Semi-manual EBS snapshot to S3 export
- `monitor_manual_exports.py` - Monitors progress of manual export tasks
- `snapshot_export_common.py` - Canonical AWS-facing functions for snapshot export operations

## Subpackages

- `snapshot_export_fixed/` - Fixed version of the snapshot export pipeline
