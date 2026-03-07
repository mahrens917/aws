"""Tests for cost_toolkit/scripts/management/ebs_manager/utils.py"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.management.ebs_manager.utils import (
    _get_instance_name_with_client,
    find_volume_region,
    get_all_aws_regions,
    get_instance_name,
    get_instance_name_by_region,
    get_volume_tags,
)
from tests.assertions import assert_equal
from tests.aws_region_test_utils import assert_regions_success


@patch("cost_toolkit.common.aws_common.create_ec2_client")
def test_get_all_aws_regions(mock_create_client, monkeypatch):
    """Test get_all_aws_regions returns list of regions."""
    result = assert_regions_success(get_all_aws_regions, mock_create_client, monkeypatch)

    assert_equal(result, ["us-east-1", "us-west-2", "eu-west-1"])
    mock_create_client.assert_called_once_with(region="us-east-1", aws_access_key_id=None, aws_secret_access_key=None)


@patch("cost_toolkit.common.aws_common.get_all_aws_regions")
@patch("cost_toolkit.common.aws_common.create_ec2_client")
def test_find_volume_region_found(mock_create_client, mock_get_regions):
    """Test find_volume_region finds volume in second region."""
    mock_get_regions.return_value = ["us-east-1", "us-west-2", "eu-west-1"]

    # First region: volume not found
    mock_ec2_1 = MagicMock()
    mock_ec2_1.describe_volumes.side_effect = ClientError({"Error": {"Code": "InvalidVolume.NotFound"}}, "DescribeVolumes")

    # Second region: volume found
    mock_ec2_2 = MagicMock()
    mock_ec2_2.describe_volumes.return_value = {"Volumes": [{"VolumeId": "vol-1234567890abcdef0"}]}

    mock_create_client.side_effect = [mock_ec2_1, mock_ec2_2]

    result = find_volume_region("vol-1234567890abcdef0")

    assert_equal(result, "us-west-2")
    assert_equal(mock_create_client.call_count, 2)


@patch("cost_toolkit.common.aws_common.get_all_aws_regions")
@patch("cost_toolkit.common.aws_common.create_ec2_client")
def test_find_volume_region_not_found(mock_create_client, mock_get_regions):
    """Test find_volume_region returns None when volume not found."""
    mock_get_regions.return_value = ["us-east-1", "us-west-2"]

    mock_ec2 = MagicMock()
    mock_ec2.describe_volumes.side_effect = ClientError({"Error": {"Code": "InvalidVolume.NotFound"}}, "DescribeVolumes")

    mock_create_client.return_value = mock_ec2

    result = find_volume_region("vol-nonexistent")

    assert result is None
    assert_equal(mock_create_client.call_count, 2)


@patch("cost_toolkit.scripts.management.ebs_manager.utils._get_instance_name_with_client")
@patch("boto3.client")
def test_get_instance_name(mock_boto_client, mock_get_name):
    """Test get_instance_name returns instance name."""
    mock_ec2 = MagicMock()
    mock_boto_client.return_value = mock_ec2
    mock_get_name.return_value = "test-instance"

    result = get_instance_name("i-1234567890abcdef0", "us-east-1")

    assert_equal(result, "test-instance")
    mock_boto_client.assert_called_once_with("ec2", region_name="us-east-1")
    mock_get_name.assert_called_once_with(mock_ec2, "i-1234567890abcdef0")


@patch("cost_toolkit.scripts.management.ebs_manager.utils._get_instance_name_with_client")
@patch("boto3.client")
def test_get_instance_name_converts_none_to_no_name(mock_boto_client, mock_get_name):
    """Test get_instance_name returns None when not present."""
    mock_ec2 = MagicMock()
    mock_boto_client.return_value = mock_ec2
    mock_get_name.return_value = None

    result = get_instance_name("i-1234567890abcdef0", "us-east-1")

    assert result is None


@patch("cost_toolkit.scripts.management.ebs_manager.utils.create_ec2_client")
@patch("cost_toolkit.scripts.management.ebs_manager.utils.get_instance_name")
def test_get_instance_name_by_region(mock_get_name, mock_create_client):
    """Test get_instance_name_by_region creates client and delegates."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_get_name.return_value = "my-instance"

    result = get_instance_name_by_region("i-1234567890abcdef0", "us-east-1")

    assert_equal(result, "my-instance")
    mock_create_client.assert_called_once_with("us-east-1")
    mock_get_name.assert_called_once_with(mock_ec2, "i-1234567890abcdef0")


@patch("cost_toolkit.scripts.management.ebs_manager.utils._aws_common_get_instance_name")
def test_get_instance_name_with_client(mock_aws_get_name):
    """Test _get_instance_name_with_client delegates to aws_common."""
    mock_ec2 = MagicMock()
    mock_aws_get_name.return_value = "named-instance"

    result = _get_instance_name_with_client(mock_ec2, "i-1234567890abcdef0")

    assert_equal(result, "named-instance")
    mock_aws_get_name.assert_called_once_with(mock_ec2, "i-1234567890abcdef0")


def test_get_volume_tags():
    """Test get_volume_tags extracts tags from volume."""
    volume = {
        "VolumeId": "vol-1234567890abcdef0",
        "Tags": [
            {"Key": "Name", "Value": "test-volume"},
            {"Key": "Environment", "Value": "production"},
        ],
    }

    result = get_volume_tags(volume)

    assert_equal(result, {"Name": "test-volume", "Environment": "production"})


def test_get_volume_tags_no_tags():
    """Test get_volume_tags returns empty dict when no tags."""
    volume = {"VolumeId": "vol-1234567890abcdef0"}

    result = get_volume_tags(volume)

    assert_equal(result, {})
