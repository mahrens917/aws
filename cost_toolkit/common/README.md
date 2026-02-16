# cost_toolkit.common

Shared utilities and helpers used across the cost toolkit.

## Modules

- `aws_client_factory.py` - AWS client factory for creating boto3 clients
- `aws_common.py` - Shared AWS client creation utilities
- `aws_test_constants.py` - Shared constants for AWS toolkit tests
- `backup_utils.py` - Shared AWS data-protection utilities
- `cli_utils.py` - Shared CLI utilities for common command-line patterns
- `confirmation_prompts.py` - Shared confirmation prompts for bulk cleanup workflows
- `cost_utils.py` - AWS cost calculation utilities
- `credential_utils.py` - Shared AWS credential loading utilities
- `format_utils.py` - Shared formatting utilities for consistent output
- `lightsail_utils.py`, `route53_utils.py`, `s3_utils.py` - Service-specific helpers
- `security_group_constants.py` - Security group constants for cleanup and audit
- `terminal_utils.py` - Shared terminal utilities for CLI scripts
- `vpc_cleanup_utils.py` - Shared VPC cleanup utilities
- `waiter_utils.py` - Consolidated AWS waiter utilities
