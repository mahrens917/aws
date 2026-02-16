# cost_toolkit.scripts.setup

AWS service setup and configuration scripts.

## Modules

- `aws_route53_domain_setup.py` - Setup Route53 domain records for DNS configuration
- `aws_vmimport_role_setup.py` - Creates the vmimport IAM service role for AMI export operations
- `domain_verification_http.py` - HTTP and DNS verification helpers for domain checks
- `domain_verification_ssl.py` - SSL certificate and Canva verification helpers for domain checks
- `exceptions.py` - Custom exceptions for AWS Route53 setup scripts
- `route53_helpers.py` - Route53 domain setup helper functions
- `verify_iwannabenewyork_domain.py` - Verify iwannabenewyork domain DNS and certificate configuration

## Usage

Run individual setup scripts to configure AWS services such as Route53 domains and IAM roles.
