"""Comprehensive tests for aws_rds_audit.py - Part 1."""

from __future__ import annotations

from datetime import datetime

from cost_toolkit.scripts.audit.aws_rds_audit import (
    _print_billing_analysis,
    _process_aurora_cluster,
    _process_rds_instance,
)
from tests.rds_audit_test_utils import SERVERLESS_V1_CLUSTER, SERVERLESS_V2_CLUSTER


class TestProcessRdsInstance:
    """Tests for _process_rds_instance function."""

    def test_process_basic_instance(self, capsys):
        """Test processing basic RDS instance."""
        instance = {
            "DBInstanceIdentifier": "test-db-1",
            "Engine": "postgres",
            "EngineVersion": "14.5",
            "DBInstanceClass": "db.t3.small",
            "DBInstanceStatus": "available",
            "AllocatedStorage": 100,
            "StorageType": "gp2",
            "MultiAZ": False,
            "PubliclyAccessible": False,
            "InstanceCreateTime": datetime(2024, 1, 15, 10, 30),
        }

        cost = _process_rds_instance(instance)

        assert cost == 0.0
        captured = capsys.readouterr()
        assert "Instance ID: test-db-1" in captured.out
        assert "Engine: postgres 14.5" in captured.out
        assert "Instance Class: db.t3.small" in captured.out
        assert "Status: available" in captured.out
        assert "Storage: 100 GB" in captured.out
        assert "Storage Type: gp2" in captured.out
        assert "Multi-AZ: False" in captured.out
        assert "Publicly Accessible: False" in captured.out

    def test_process_t3_micro_instance(self, capsys):
        """Test processing t3.micro instance with cost estimate."""
        instance = {
            "DBInstanceIdentifier": "test-micro",
            "Engine": "mariadb",
            "EngineVersion": "10.6",
            "DBInstanceClass": "db.t3.micro",
            "DBInstanceStatus": "available",
            "AllocatedStorage": 20,
            "StorageType": "gp3",
            "MultiAZ": True,
            "PubliclyAccessible": True,
            "InstanceCreateTime": datetime(2024, 1, 15, 10, 30),
        }

        cost = _process_rds_instance(instance)

        assert cost == 20.0
        captured = capsys.readouterr()
        assert "Instance ID: test-micro" in captured.out
        assert "Instance Class: db.t3.micro" in captured.out
        assert "Estimated Cost: ~$20.00/month" in captured.out

    def test_process_instance_with_cluster(self, capsys):
        """Test processing instance that is part of Aurora cluster."""
        instance = {
            "DBInstanceIdentifier": "aurora-instance-1",
            "Engine": "aurora-postgresql",
            "EngineVersion": "13.7",
            "DBInstanceClass": "db.r5.large",
            "DBInstanceStatus": "available",
            "AllocatedStorage": 0,
            "StorageType": "aurora",
            "MultiAZ": False,
            "PubliclyAccessible": False,
            "InstanceCreateTime": datetime(2024, 1, 15, 10, 30),
            "DBClusterIdentifier": "my-aurora-cluster",
        }

        cost = _process_rds_instance(instance)

        assert cost == 0.0
        captured = capsys.readouterr()
        assert "Instance ID: aurora-instance-1" in captured.out
        assert "Part of Cluster: my-aurora-cluster" in captured.out

    def test_process_instance_missing_optional_fields(self, capsys):
        """Test processing instance with missing optional fields."""
        instance = {
            "DBInstanceIdentifier": "minimal-db",
            "Engine": "mysql",
            "DBInstanceClass": "db.m5.large",
            "DBInstanceStatus": "creating",
        }

        cost = _process_rds_instance(instance)

        assert cost == 0.0
        captured = capsys.readouterr()
        assert "Instance ID: minimal-db" in captured.out
        assert "Engine: mysql None" in captured.out
        assert "Storage: None GB" in captured.out
        assert "Storage Type: None" in captured.out
        assert "Multi-AZ: None" in captured.out
        assert "Creation Time: None" in captured.out


class TestProcessAuroraClusterBasic:
    """Tests for _process_aurora_cluster function - basic scenarios."""

    def test_process_basic_cluster(self, capsys, aurora_postgresql_cluster):
        """Test processing basic Aurora cluster."""
        _process_aurora_cluster(aurora_postgresql_cluster)

        captured = capsys.readouterr()
        assert "Cluster ID: test-cluster" in captured.out
        assert "Engine: aurora-postgresql 14.6" in captured.out
        assert "Status: available" in captured.out
        assert "Database Name: mydb" in captured.out
        assert "Master Username: admin" in captured.out
        assert "Multi-AZ: True" in captured.out
        assert "Storage Encrypted: True" in captured.out

    def test_process_cluster_with_members(self, capsys):
        """Test processing cluster with member instances."""
        cluster = {
            "DBClusterIdentifier": "prod-cluster",
            "Engine": "aurora-mysql",
            "EngineVersion": "8.0",
            "Status": "available",
            "DatabaseName": "production",
            "MasterUsername": "dbadmin",
            "MultiAZ": False,
            "StorageEncrypted": True,
            "ClusterCreateTime": datetime(2024, 1, 15, 10, 30),
            "DBClusterMembers": [
                {"DBInstanceIdentifier": "writer-1", "IsClusterWriter": True},
                {"DBInstanceIdentifier": "reader-1", "IsClusterWriter": False},
                {"DBInstanceIdentifier": "reader-2", "IsClusterWriter": False},
            ],
        }

        _process_aurora_cluster(cluster)

        captured = capsys.readouterr()
        assert "Cluster Members: 3" in captured.out
        assert "writer-1 (Writer)" in captured.out
        assert "reader-1 (Reader)" in captured.out
        assert "reader-2 (Reader)" in captured.out

    def test_process_cluster_missing_optional_fields(self, capsys):
        """Test processing cluster with missing optional fields."""
        cluster = {
            "DBClusterIdentifier": "minimal-cluster",
            "Engine": "aurora",
            "Status": "creating",
        }

        _process_aurora_cluster(cluster)

        captured = capsys.readouterr()
        assert "Cluster ID: minimal-cluster" in captured.out
        assert "Engine: aurora None" in captured.out
        assert "Database Name: None" in captured.out
        assert "Master Username: None" in captured.out
        assert "Multi-AZ: None" in captured.out
        assert "Storage Encrypted: None" in captured.out


class TestProcessAuroraClusterServerless:
    """Tests for _process_aurora_cluster function - serverless configurations."""

    def test_process_serverless_v1_cluster(self, capsys):
        """Test processing Aurora Serverless v1 cluster."""
        _process_aurora_cluster(SERVERLESS_V1_CLUSTER)

        captured = capsys.readouterr()
        assert "Engine Mode: Serverless" in captured.out
        assert "Scaling: 2-16 ACU" in captured.out

    def test_process_serverless_v2_cluster(self, capsys):
        """Test processing Aurora Serverless v2 cluster."""
        _process_aurora_cluster(SERVERLESS_V2_CLUSTER)

        captured = capsys.readouterr()
        assert "Engine Mode: Serverless V2" in captured.out
        assert "Scaling: 0.5-4.0 ACU" in captured.out


class TestPrintBillingAnalysis:  # pylint: disable=too-few-public-methods
    """Tests for _print_billing_analysis function."""

    def _verify_billing_section(self, output):
        """Verify billing data section contains expected content."""
        assert "=" * 80 in output
        assert "BILLING DATA ANALYSIS:" in output

    def _verify_useast1_billing(self, output):
        """Verify us-east-1 billing information."""
        assert "us-east-1: $1.29 (96% of RDS cost)" in output
        assert "db.t3.micro instance: 64 hours" in output
        assert "GP3 storage: 1.78 GB" in output

    def _verify_euwest2_billing(self, output):
        """Verify eu-west-2 billing information."""
        assert "eu-west-2: $0.05 (4% of RDS cost)" in output
        assert "Aurora Serverless V2: 0.36 ACU-Hr" in output

    def _verify_optimization_section(self, output):
        """Verify cost optimization section."""
        assert "COST OPTIMIZATION OPPORTUNITIES:" in output
        assert "Aurora Serverless V2 (eu-west-2): Very low usage" in output

    def test_print_billing_analysis_output(self, capsys):
        """Test billing analysis output."""
        _print_billing_analysis()

        captured = capsys.readouterr()
        self._verify_billing_section(captured.out)
        self._verify_useast1_billing(captured.out)
        self._verify_euwest2_billing(captured.out)
        self._verify_optimization_section(captured.out)
