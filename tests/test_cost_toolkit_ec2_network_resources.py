"""Tests for aws_ec2_operations.py - Network Resource operations"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.scripts.aws_ec2_operations import (
    describe_addresses,
    describe_network_interfaces,
    get_common_regions,
)
from tests.assertions import assert_equal


# Tests for get_common_regions
def test_get_common_regions():
    """Test get_common_regions extends default regions with additional regions."""
    result = get_common_regions()

    assert "us-east-1" in result
    assert "us-west-2" in result
    assert "eu-west-3" in result
    assert "ap-northeast-1" in result


# Tests for describe_addresses
@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_addresses_success(mock_create_client):
    """Test describe_addresses returns list of Elastic IPs."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    addresses = [
        {"PublicIp": "203.0.113.1", "AllocationId": "eipalloc-12345"},
        {"PublicIp": "203.0.113.2", "AllocationId": "eipalloc-67890"},
    ]
    mock_ec2.describe_addresses.return_value = {"Addresses": addresses}

    result = describe_addresses("us-east-1")

    assert_equal(result, addresses)
    mock_create_client.assert_called_once_with(
        region="us-east-1",
        aws_access_key_id=None,
        aws_secret_access_key=None,
    )
    mock_ec2.describe_addresses.assert_called_once()


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_addresses_empty_result(mock_create_client):
    """Test describe_addresses returns empty list when no addresses found."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_addresses.return_value = {"Addresses": []}

    result = describe_addresses("us-east-1")

    assert_equal(result, [])


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_addresses_with_credentials(mock_create_client):
    """Test describe_addresses passes credentials to client factory."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_addresses.return_value = {"Addresses": []}

    describe_addresses("ap-south-1", aws_access_key_id="test_key", aws_secret_access_key="test_secret")

    mock_create_client.assert_called_once_with(
        region="ap-south-1",
        aws_access_key_id="test_key",
        aws_secret_access_key="test_secret",
    )


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_addresses_client_error(mock_create_client):
    """Test describe_addresses raises ClientError on API failure."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_addresses.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "Not authorized"}},
        "DescribeAddresses",
    )

    with pytest.raises(ClientError):
        describe_addresses("us-east-1")


# Tests for describe_network_interfaces
@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_network_interfaces_success(mock_create_client):
    """Test describe_network_interfaces returns list of network interfaces."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    interfaces = [
        {"NetworkInterfaceId": "eni-12345", "Status": "available"},
        {"NetworkInterfaceId": "eni-67890", "Status": "in-use"},
    ]
    mock_ec2.describe_network_interfaces.return_value = {"NetworkInterfaces": interfaces}

    result = describe_network_interfaces("us-east-1")

    assert_equal(result, interfaces)
    mock_create_client.assert_called_once_with(
        region="us-east-1",
        aws_access_key_id=None,
        aws_secret_access_key=None,
    )
    mock_ec2.describe_network_interfaces.assert_called_once_with()


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_network_interfaces_with_filters(mock_create_client):
    """Test describe_network_interfaces passes filters to API."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_network_interfaces.return_value = {"NetworkInterfaces": []}
    filters = [{"Name": "status", "Values": ["available"]}]

    describe_network_interfaces("us-east-1", filters=filters)

    mock_ec2.describe_network_interfaces.assert_called_once_with(Filters=filters)


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_network_interfaces_empty_result(mock_create_client):
    """Test describe_network_interfaces returns empty list when none found."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_network_interfaces.return_value = {"NetworkInterfaces": []}

    result = describe_network_interfaces("us-east-1")

    assert_equal(result, [])


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_network_interfaces_with_credentials(mock_create_client):
    """Test describe_network_interfaces passes credentials to client factory."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_network_interfaces.return_value = {"NetworkInterfaces": []}

    describe_network_interfaces("ca-central-1", aws_access_key_id="test_key", aws_secret_access_key="test_secret")

    mock_create_client.assert_called_once_with(
        region="ca-central-1",
        aws_access_key_id="test_key",
        aws_secret_access_key="test_secret",
    )


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_network_interfaces_client_error(mock_create_client):
    """Test describe_network_interfaces raises ClientError on API failure."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_network_interfaces.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "Not authorized"}},
        "DescribeNetworkInterfaces",
    )

    with pytest.raises(ClientError):
        describe_network_interfaces("us-east-1")
