# cost_toolkit.scripts.migration.rds_aurora_migration

AWS RDS to Aurora Serverless v2 migration package.

## Modules

- `cli.py` - CLI interface for RDS to Aurora Serverless migration
- `cluster_ops.py` - RDS and Aurora cluster operations
- `migration_workflow.py` - Migration workflow utilities and cost calculations

## Usage

Run the CLI to discover RDS instances, validate migration compatibility, create snapshots,
and migrate to Aurora Serverless v2 with cost estimation.
