"""
Shared AWS credential loading utilities.

This module provides common credential loading patterns
to eliminate duplicate credential setup code across scripts.
"""

import logging

from cost_toolkit.common.aws_client_factory import (
    _resolve_env_path,
    load_credentials_from_env,
)


def setup_aws_credentials(env_path=None):
    """
    Load AWS credentials from .env file.

    Loads environment variables from ~/.env and extracts AWS credentials.

    Args:
        env_path: Optional path to .env file. If not provided, uses ~/.env

    Returns:
        tuple: (aws_access_key_id, aws_secret_access_key)

    Raises:
        ValueError: If AWS credentials are not found in .env file
    """
    creds = load_credentials_from_env(env_path)
    return creds


def check_aws_credentials():
    """
    Check if AWS credentials can be loaded from .env file.

    Returns:
        bool: True if credentials found, False otherwise (prints error message)
    """
    try:
        load_credentials_from_env()
    except ValueError:
        resolved_path = _resolve_env_path()
        logging.warning("⚠️  AWS credentials not found in %s.", resolved_path)
        logging.warning("Please ensure %s contains:", resolved_path)
        logging.warning("  AWS_ACCESS_KEY_ID=your-access-key")
        logging.warning("  AWS_SECRET_ACCESS_KEY=your-secret-key")
        logging.warning("  AWS_DEFAULT_REGION=us-east-1")
        return False
    return True
