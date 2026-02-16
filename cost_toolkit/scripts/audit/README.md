# cost_toolkit.scripts.audit

AWS resource audit scripts for cost analysis and compliance.

## Modules

Covers S3, EBS, EC2, RDS, KMS, VPC, Route53, Elastic IP, network interface,
AMI/snapshot, and security group audits. Key scripts include:

- `aws_s3_audit.py` - Comprehensive S3 bucket audit and cost analysis
- `aws_ebs_audit.py` - Audit EBS volumes and storage costs
- `aws_ec2_usage_audit.py` - Audit EC2 instance usage patterns
- `aws_comprehensive_vpc_audit.py` - Comprehensive VPC audit across regions
- `aws_route53_audit.py` - Audit Route53 DNS records and costs
- `aws_elastic_ip_audit.py` - Audit Elastic IP addresses for unassociated charges
- `aws_security_group_dependencies.py` - Audit security group dependencies
- `vpc_audit_helpers.py` - VPC audit helper functions

## Subpackages
- `s3_audit/` - Modular S3 bucket analysis and optimization
