# cost_toolkit.scripts.migration

AWS resource migration and data transfer scripts.

## Modules

- `aws_check_instance_status.py` - Check EC2 instance status
- `aws_ebs_to_s3_migration.py` - Migrate EBS data to S3 storage
- `aws_london_ebs_analysis.py` - Analyze EBS volumes in London region
- `aws_london_ebs_cleanup.py` - Clean up EBS volumes in London region
- `aws_london_final_analysis_summary.py` - Generate final migration analysis summary
- `aws_london_final_status.py` - Check final migration status for London region
- `aws_london_volume_inspector.py` - Inspect EBS volumes in London region
- `aws_migration_monitor.py` - Monitor migration progress and status
- `aws_rds_to_aurora_serverless_migration.py` - Migrate RDS to Aurora Serverless v2
- `aws_start_and_migrate.py` - Start and manage migration operations

## Subpackages

- `rds_aurora_migration/` - Modular RDS to Aurora Serverless v2 migration package
