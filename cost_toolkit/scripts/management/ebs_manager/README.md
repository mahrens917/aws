# cost_toolkit.scripts.management.ebs_manager

Manages AWS EBS volumes including deletion, information retrieval, and snapshot creation.

## Modules

- `cli.py` - Command-line argument parsing and execution
- `exceptions.py` - Custom exceptions for the EBS manager
- `operations.py` - Volume deletion and information retrieval operations
- `reporting.py` - Report formatting and output for volume information and snapshots
- `snapshot.py` - Snapshot creation and related operations
- `utils.py` - Helper functions for region discovery and tag management

## Usage

Run via the CLI to inspect, snapshot, or delete EBS volumes across AWS regions.
