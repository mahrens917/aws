"""Comprehensive tests for aws_rds_network_interface_audit.py - Part 1."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cost_toolkit.scripts.audit.aws_rds_network_interface_audit import (
    _extract_cluster_info,
    _extract_instance_info,
    get_all_regions,
)


def test_get_regions_success(monkeypatch):
    """Test successful retrieval of regions."""
    monkeypatch.delenv("COST_TOOLKIT_STATIC_AWS_REGIONS", raising=False)
    with patch("boto3.client") as mock_client:
        mock_ec2 = MagicMock()
        mock_ec2.describe_regions.return_value = {
            "Regions": [
                {"RegionName": "us-east-1"},
                {"RegionName": "us-west-2"},
                {"RegionName": "eu-west-1"},
                {"RegionName": "ap-southeast-1"},
            ]
        }
        mock_client.return_value = mock_ec2

        regions = get_all_regions()

    assert len(regions) == 4
    assert "us-east-1" in regions
    assert "ap-southeast-1" in regions


class TestExtractInstanceInfo:
    """Tests for _extract_instance_info function."""

    def _assert_instance_basic_fields(self, result):
        """Helper to assert basic instance fields."""
        assert result["identifier"] == "mydb-instance"
        assert result["engine"] == "postgres"
        assert result["engine_version"] == "14.7"
        assert result["instance_class"] == "db.t3.micro"
        assert result["status"] == "available"

    def _assert_instance_network_fields(self, result):
        """Helper to assert network-related fields."""
        assert result["vpc_id"] == "vpc-123"
        assert result["subnet_group"] == "default"
        assert len(result["subnets"]) == 2
        assert result["endpoint"] == "mydb.us-east-1.rds.amazonaws.com"
        assert result["port"] == 5432

    def _assert_instance_config_fields(self, result):
        """Helper to assert configuration fields."""
        assert result["publicly_accessible"] is False
        assert result["multi_az"] is True
        assert result["storage_type"] == "gp3"
        assert result["allocated_storage"] == 100

    def test_extract_complete_instance_info(self):
        """Test extracting complete instance information."""
        instance = {
            "DBInstanceIdentifier": "mydb-instance",
            "Engine": "postgres",
            "EngineVersion": "14.7",
            "DBInstanceClass": "db.t3.micro",
            "DBInstanceStatus": "available",
            "DBSubnetGroup": {
                "VpcId": "vpc-123",
                "DBSubnetGroupName": "default",
                "Subnets": [
                    {"SubnetIdentifier": "subnet-123"},
                    {"SubnetIdentifier": "subnet-456"},
                ],
            },
            "Endpoint": {"Address": "mydb.us-east-1.rds.amazonaws.com", "Port": 5432},
            "PubliclyAccessible": False,
            "MultiAZ": True,
            "StorageType": "gp3",
            "AllocatedStorage": 100,
            "InstanceCreateTime": "2024-01-01T00:00:00Z",
        }

        result = _extract_instance_info(instance)

        self._assert_instance_basic_fields(result)
        self._assert_instance_network_fields(result)
        self._assert_instance_config_fields(result)

    def test_extract_minimal_instance_info(self):
        """Test extracting minimal instance information."""
        instance = {
            "DBInstanceIdentifier": "minimal-db",
            "Engine": "mysql",
            "EngineVersion": "8.0",
            "DBInstanceClass": "db.t2.small",
            "DBInstanceStatus": "stopped",
        }

        result = _extract_instance_info(instance)

        assert result["identifier"] == "minimal-db"
        assert result["vpc_id"] is None
        assert result["subnet_group"] is None
        assert result["subnets"] == []
        assert result["endpoint"] is None
        assert result["port"] is None


class TestExtractClusterInfo:
    """Tests for _extract_cluster_info function."""

    def _assert_cluster_basic_fields(self, result):
        """Helper to assert basic cluster fields."""
        assert result["identifier"] == "aurora-cluster"
        assert result["engine"] == "aurora-postgresql"
        assert result["engine_version"] == "14.6"
        assert result["engine_mode"] == "provisioned"
        assert result["status"] == "available"

    def _assert_cluster_network_fields(self, result):
        """Helper to assert network-related fields."""
        assert result["vpc_id"] == "vpc-456"
        assert result["subnet_group"] == "aurora-subnet-group"
        assert result["endpoint"] == "aurora-cluster.cluster-xyz.us-east-1.rds.amazonaws.com"
        assert result["reader_endpoint"] == "aurora-cluster.cluster-ro-xyz.us-east-1.rds.amazonaws.com"
        assert result["port"] == 5432

    def _assert_cluster_scaling_fields(self, result):
        """Helper to assert scaling-related fields."""
        assert result["serverless_v2_scaling"] == {"MinCapacity": 0.5, "MaxCapacity": 1.0}
        assert result["capacity"] == 1

    def test_extract_complete_cluster_info(self):
        """Test extracting complete cluster information."""
        cluster = {
            "DBClusterIdentifier": "aurora-cluster",
            "Engine": "aurora-postgresql",
            "EngineVersion": "14.6",
            "EngineMode": "provisioned",
            "Status": "available",
            "DBSubnetGroup": {
                "VpcId": "vpc-456",
                "DBSubnetGroupName": "aurora-subnet-group",
                "Subnets": [{"SubnetIdentifier": "subnet-789"}],
            },
            "Endpoint": "aurora-cluster.cluster-xyz.us-east-1.rds.amazonaws.com",
            "ReaderEndpoint": "aurora-cluster.cluster-ro-xyz.us-east-1.rds.amazonaws.com",
            "Port": 5432,
            "ClusterCreateTime": "2024-01-15T00:00:00Z",
            "ServerlessV2ScalingConfiguration": {"MinCapacity": 0.5, "MaxCapacity": 1.0},
            "Capacity": 1,
        }

        result = _extract_cluster_info(cluster)

        self._assert_cluster_basic_fields(result)
        self._assert_cluster_network_fields(result)
        self._assert_cluster_scaling_fields(result)

    def test_extract_serverless_cluster_info(self):
        """Test extracting serverless cluster information."""
        cluster = {
            "DBClusterIdentifier": "serverless-cluster",
            "Engine": "aurora-mysql",
            "EngineVersion": "5.7.mysql_aurora.2.10.1",
            "EngineMode": "serverless",
            "Status": "available",
            "Endpoint": "serverless.cluster-abc.us-west-2.rds.amazonaws.com",
            "Port": 3306,
            "ClusterCreateTime": "2024-02-01T00:00:00Z",
        }

        result = _extract_cluster_info(cluster)

        assert result["engine_mode"] == "serverless"
        assert result["vpc_id"] is None
        assert result["reader_endpoint"] is None
        assert result["capacity"] is None
