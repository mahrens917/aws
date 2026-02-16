# cost_toolkit.scripts.cleanup

AWS resource cleanup and decommissioning scripts.

## Modules

Covers AMI deregistration, EC2 instance termination, EBS snapshot deletion,
VPC resource removal, Lambda/EFS/RDS/KMS/Lightsail/CloudWatch/Route53 cleanup,
Global Accelerator removal, security group circular dependency resolution,
public IP removal, and termination protection management. Key scripts include:

- `aws_ami_deregister_bulk.py` - Bulk deregistration of unused AMIs
- `aws_instance_termination.py` - Safely terminate instances and handle EBS volumes
- `aws_snapshot_bulk_delete.py` - Delete multiple EBS snapshots across regions
- `aws_vpc_safe_deletion.py` - Safely delete VPC and related resources
- `aws_security_group_circular_cleanup.py` - Resolve circular security group dependencies
- `public_ip_common.py` - Shared helpers for public IP removal workflows
- `unused_security_groups.py` - Security group usage analysis and cleanup
- `unused_subnets.py` - Subnet usage analysis and cleanup
