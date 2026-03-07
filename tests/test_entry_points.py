"""Tests for CLI entry point modules."""

import duplicate_tree
from cost_toolkit import cost_overview
from cost_toolkit.scripts import config
from cost_toolkit.scripts.audit import (
    aws_ami_snapshot_analysis,
    aws_comprehensive_vpc_audit,
    aws_ebs_audit,
    aws_elastic_ip_audit,
    aws_kms_audit,
    aws_rds_audit,
    aws_s3_audit,
    aws_security_group_dependencies,
)
from cost_toolkit.scripts.billing import (
    aws_hourly_billing_report,
    aws_today_billing_report,
)
from cost_toolkit.scripts.management import (
    aws_ebs_volume_manager,
    aws_s3_standardization,
)
from cost_toolkit.scripts.migration import (
    aws_check_instance_status,
    aws_ebs_to_s3_migration,
    aws_london_ebs_analysis,
    aws_london_ebs_cleanup,
    aws_london_final_analysis_summary,
    aws_london_final_status,
    aws_london_volume_inspector,
    aws_migration_monitor,
    aws_rds_to_aurora_serverless_migration,
    aws_start_and_migrate,
)
from cost_toolkit.scripts.optimization import (
    aws_s3_to_snapshot_restore,
    aws_snapshot_to_s3_export_fixed,
)
from cost_toolkit.scripts.setup import aws_vmimport_role_setup


def test_cost_overview_imports():
    """Test that cost_overview module can be imported."""
    assert cost_overview is not None


def test_config_imports():
    """Test that config module can be imported."""
    assert config is not None


def test_duplicate_tree_imports():
    """Test that duplicate_tree package exposes its public API."""
    assert duplicate_tree is not None
    assert hasattr(duplicate_tree, "__all__")
    assert "main" in duplicate_tree.__all__


def test_aws_vmimport_role_setup_imports():
    """Test that aws_vmimport_role_setup module can be imported."""
    assert aws_vmimport_role_setup is not None
    assert hasattr(aws_vmimport_role_setup, "create_vmimport_role")


def test_audit_scripts_import():
    """Test that audit CLI scripts can be imported."""
    assert all(
        [
            aws_ami_snapshot_analysis,
            aws_comprehensive_vpc_audit,
            aws_ebs_audit,
            aws_elastic_ip_audit,
            aws_kms_audit,
            aws_rds_audit,
            aws_s3_audit,
            aws_security_group_dependencies,
        ]
    )


def test_billing_scripts_import():
    """Test that billing CLI scripts can be imported."""
    assert aws_hourly_billing_report is not None
    assert aws_today_billing_report is not None


def test_management_scripts_import():
    """Test that management CLI scripts can be imported."""
    assert all([aws_ebs_volume_manager, aws_s3_standardization])


def test_migration_scripts_import():
    """Test that migration CLI scripts can be imported."""
    assert all(
        [
            aws_check_instance_status,
            aws_ebs_to_s3_migration,
            aws_london_ebs_analysis,
            aws_london_ebs_cleanup,
            aws_london_final_analysis_summary,
            aws_london_final_status,
            aws_london_volume_inspector,
            aws_migration_monitor,
            aws_rds_to_aurora_serverless_migration,
            aws_start_and_migrate,
        ]
    )


def test_optimization_scripts_import():
    """Test that optimization CLI scripts can be imported."""
    assert all(
        [
            aws_s3_to_snapshot_restore,
            aws_snapshot_to_s3_export_fixed,
        ]
    )
