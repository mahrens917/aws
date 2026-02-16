"""Tests for aws_ec2_operations.py - Security Groups and Storage operations"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.scripts.aws_ec2_operations import (
    delete_security_group,
    describe_security_groups,
    describe_snapshots,
    describe_volumes,
)
from tests.assertions import assert_equal


# Tests for describe_security_groups
@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_security_groups_success(mock_create_client):
    """Test describe_security_groups returns list of security groups."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    security_groups = [
        {"GroupId": "sg-12345", "GroupName": "default"},
        {"GroupId": "sg-67890", "GroupName": "web-sg"},
    ]
    mock_ec2.describe_security_groups.return_value = {"SecurityGroups": security_groups}

    result = describe_security_groups("us-east-1")

    assert_equal(result, security_groups)
    mock_create_client.assert_called_once_with(
        region="us-east-1",
        aws_access_key_id=None,
        aws_secret_access_key=None,
    )
    mock_ec2.describe_security_groups.assert_called_once_with()


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_security_groups_with_group_ids(mock_create_client):
    """Test describe_security_groups passes group_ids to API."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_security_groups.return_value = {"SecurityGroups": []}
    group_ids = ["sg-12345", "sg-67890"]

    describe_security_groups("us-east-1", group_ids=group_ids)

    mock_ec2.describe_security_groups.assert_called_once_with(GroupIds=group_ids)


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_security_groups_empty_result(mock_create_client):
    """Test describe_security_groups returns empty list when none found."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_security_groups.return_value = {}

    result = describe_security_groups("us-east-1")

    assert_equal(result, [])


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_security_groups_with_credentials(mock_create_client):
    """Test describe_security_groups passes credentials to client factory."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_security_groups.return_value = {"SecurityGroups": []}

    describe_security_groups("us-west-1", aws_access_key_id="test_key", aws_secret_access_key="test_secret")

    mock_create_client.assert_called_once_with(
        region="us-west-1",
        aws_access_key_id="test_key",
        aws_secret_access_key="test_secret",
    )


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_security_groups_client_error(mock_create_client):
    """Test describe_security_groups raises ClientError on API failure."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_security_groups.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "Not authorized"}},
        "DescribeSecurityGroups",
    )

    with pytest.raises(ClientError):
        describe_security_groups("us-east-1")


# Tests for delete_security_group
@patch("builtins.print")
@patch("cost_toolkit.scripts.aws_ec2_operations.create_ec2_client")
def test_delete_security_group_success(mock_create_client, mock_print):
    """Test delete_security_group successfully deletes security group."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2

    result = delete_security_group("us-east-1", "sg-12345")

    assert_equal(result, True)
    mock_create_client.assert_called_once_with(
        region="us-east-1",
        aws_access_key_id=None,
        aws_secret_access_key=None,
    )
    mock_ec2.delete_security_group.assert_called_once_with(GroupId="sg-12345")
    # Verify success message was printed
    assert any("Deleted security group" in str(call) for call in mock_print.call_args_list)


@patch("cost_toolkit.scripts.aws_ec2_operations.create_ec2_client")
def test_delete_security_group_with_credentials(mock_create_client):
    """Test delete_security_group passes credentials to client factory."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2

    result = delete_security_group(
        "eu-central-1",
        "sg-12345",
        aws_access_key_id="test_key",
        aws_secret_access_key="test_secret",
    )

    assert_equal(result, True)
    mock_create_client.assert_called_once_with(
        region="eu-central-1",
        aws_access_key_id="test_key",
        aws_secret_access_key="test_secret",
    )


@patch("builtins.print")
@patch("cost_toolkit.scripts.aws_ec2_operations.create_ec2_client")
def test_delete_security_group_failure(mock_create_client, mock_print):
    """Test delete_security_group returns False on API error."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.delete_security_group.side_effect = ClientError(
        {"Error": {"Code": "DependencyViolation", "Message": "Group in use"}}, "DeleteSecurityGroup"
    )

    result = delete_security_group("us-east-1", "sg-12345")

    assert_equal(result, False)
    # Verify error message was printed
    assert any("Failed to delete security group" in str(call) for call in mock_print.call_args_list)


# Tests for describe_snapshots
@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_snapshots_success(mock_create_client):
    """Test describe_snapshots returns list of snapshots."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    snapshots = [
        {"SnapshotId": "snap-12345", "State": "completed"},
        {"SnapshotId": "snap-67890", "State": "completed"},
    ]
    mock_ec2.describe_snapshots.return_value = {"Snapshots": snapshots}

    result = describe_snapshots("us-east-1")

    assert_equal(result, snapshots)
    mock_create_client.assert_called_once_with(
        region="us-east-1",
        aws_access_key_id=None,
        aws_secret_access_key=None,
    )
    mock_ec2.describe_snapshots.assert_called_once_with()


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_snapshots_with_owner_ids(mock_create_client):
    """Test describe_snapshots passes owner_ids to API."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_snapshots.return_value = {"Snapshots": []}
    owner_ids = ["self"]

    describe_snapshots("us-east-1", owner_ids=owner_ids)

    mock_ec2.describe_snapshots.assert_called_once_with(OwnerIds=owner_ids)


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_snapshots_with_snapshot_ids(mock_create_client):
    """Test describe_snapshots passes snapshot_ids to API."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_snapshots.return_value = {"Snapshots": []}
    snapshot_ids = ["snap-12345", "snap-67890"]

    describe_snapshots("us-east-1", snapshot_ids=snapshot_ids)

    mock_ec2.describe_snapshots.assert_called_once_with(SnapshotIds=snapshot_ids)


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_snapshots_with_both_filters(mock_create_client):
    """Test describe_snapshots passes both owner_ids and snapshot_ids."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_snapshots.return_value = {"Snapshots": []}
    owner_ids = ["self"]
    snapshot_ids = ["snap-12345"]

    describe_snapshots("us-east-1", owner_ids=owner_ids, snapshot_ids=snapshot_ids)

    mock_ec2.describe_snapshots.assert_called_once_with(OwnerIds=owner_ids, SnapshotIds=snapshot_ids)


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_snapshots_empty_result(mock_create_client):
    """Test describe_snapshots returns empty list when none found."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_snapshots.return_value = {}

    result = describe_snapshots("us-east-1")

    assert_equal(result, [])


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_snapshots_with_credentials(mock_create_client):
    """Test describe_snapshots passes credentials to client factory."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_snapshots.return_value = {"Snapshots": []}

    describe_snapshots("ap-northeast-2", aws_access_key_id="test_key", aws_secret_access_key="test_secret")

    mock_create_client.assert_called_once_with(
        region="ap-northeast-2",
        aws_access_key_id="test_key",
        aws_secret_access_key="test_secret",
    )


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_snapshots_client_error(mock_create_client):
    """Test describe_snapshots raises ClientError on API failure."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_snapshots.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "Not authorized"}},
        "DescribeSnapshots",
    )

    with pytest.raises(ClientError):
        describe_snapshots("us-east-1")


# Tests for describe_volumes
@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_volumes_success(mock_create_client):
    """Test describe_volumes returns list of volumes."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    volumes = [
        {"VolumeId": "vol-12345", "State": "available", "Size": 100},
        {"VolumeId": "vol-67890", "State": "in-use", "Size": 50},
    ]
    mock_ec2.describe_volumes.return_value = {"Volumes": volumes}

    result = describe_volumes("us-east-1")

    assert_equal(result, volumes)
    mock_create_client.assert_called_once_with(
        region="us-east-1",
        aws_access_key_id=None,
        aws_secret_access_key=None,
    )
    mock_ec2.describe_volumes.assert_called_once_with()


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_volumes_with_filters(mock_create_client):
    """Test describe_volumes passes filters to API."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_volumes.return_value = {"Volumes": []}
    filters = [{"Name": "status", "Values": ["available"]}]

    describe_volumes("us-east-1", filters=filters)

    mock_ec2.describe_volumes.assert_called_once_with(Filters=filters)


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_volumes_empty_result(mock_create_client):
    """Test describe_volumes returns empty list when none found."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_volumes.return_value = {}

    result = describe_volumes("us-east-1")

    assert_equal(result, [])


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_volumes_with_credentials(mock_create_client):
    """Test describe_volumes passes credentials to client factory."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_volumes.return_value = {"Volumes": []}

    describe_volumes("sa-east-1", aws_access_key_id="test_key", aws_secret_access_key="test_secret")

    mock_create_client.assert_called_once_with(
        region="sa-east-1",
        aws_access_key_id="test_key",
        aws_secret_access_key="test_secret",
    )


@patch("cost_toolkit.scripts.ec2_describe_ops.create_ec2_client")
def test_describe_volumes_client_error(mock_create_client):
    """Test describe_volumes raises ClientError on API failure."""
    mock_ec2 = MagicMock()
    mock_create_client.return_value = mock_ec2
    mock_ec2.describe_volumes.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "Not authorized"}}, "DescribeVolumes"
    )

    with pytest.raises(ClientError):
        describe_volumes("us-east-1")
