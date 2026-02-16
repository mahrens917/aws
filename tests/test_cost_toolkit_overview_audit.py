"""Tests for cost_toolkit/overview/audit.py module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cost_toolkit.overview.audit import (
    _extract_summary_lines,
    _run_audit_script,
    report_lightsail_cost_breakdown,
    run_quick_audit,
)


def test_extract_summary_lines_with_keywords():
    """Test _extract_summary_lines extracts lines with keywords."""
    output = """
Line 1
Total: 10 items
Line 3
Found 5 volumes
Line 5
RECOMMENDATIONS:
Line 7
"""
    result = _extract_summary_lines(output)
    assert len(result) <= 5
    assert any("Total" in line for line in result)
    assert any("Found" in line for line in result)


def test_extract_summary_lines_returns_last_five():
    """Test that _extract_summary_lines returns at most 5 lines."""
    output = "\n".join([f"Total: {i}" for i in range(20)])
    result = _extract_summary_lines(output)
    assert len(result) == 5


def test_run_audit_script_not_found(capsys, tmp_path):
    """Test _run_audit_script when script doesn't exist."""
    script_path = tmp_path / "nonexistent.py"
    _run_audit_script("Test Audit", str(script_path))

    captured = capsys.readouterr()
    assert "Script not found" in captured.out


def test_run_audit_script_success(capsys, tmp_path):
    """Test _run_audit_script with successful execution."""
    script_path = tmp_path / "test_script.py"
    script_path.write_text(
        "\n".join(
            [
                "def main(_argv=None):",
                "    print('Total: 10 items')",
                "    print('Found 5 volumes')",
                "",
            ]
        )
    )

    _run_audit_script("Test Audit", str(script_path))

    captured = capsys.readouterr()
    assert "Total: 10 items" in captured.out


def test_run_audit_script_failure(tmp_path):
    """Test _run_audit_script propagates non-ClientError exceptions."""
    script_path = tmp_path / "test_script.py"
    script_path.write_text("raise Exception('boom')")

    with pytest.raises(Exception, match="boom"):
        _run_audit_script("Test Audit", str(script_path))


def test_run_audit_script_timeout(capsys, tmp_path):
    """Test _run_audit_script handles load failure."""
    script_path = tmp_path / "test_script.py"
    script_path.write_text("print('test')")

    with patch("cost_toolkit.overview.audit.importlib.util.spec_from_file_location") as mock_spec:
        mock_spec.return_value = None
        _run_audit_script("Test Audit", str(script_path))

    captured = capsys.readouterr()
    assert "Unable to load script" in captured.out


def test_run_audit_script_client_error(capsys, tmp_path):
    """Test _run_audit_script handles ClientError."""
    script_path = tmp_path / "test_script.py"
    script_path.write_text("print('test')")

    with (
        patch("cost_toolkit.overview.audit.importlib.util.spec_from_file_location") as mock_spec,
        patch("cost_toolkit.overview.audit.importlib.util.module_from_spec") as mock_mod,
    ):
        mock_spec.return_value = MagicMock(loader=MagicMock())
        mock_module = MagicMock()
        mock_module.main.side_effect = ClientError({"Error": {"Code": "TestError"}}, "test")
        mock_mod.return_value = mock_module
        _run_audit_script("Test Audit", str(script_path))

    captured = capsys.readouterr()
    assert "Error running audit" in captured.out


def test_run_quick_audit(capsys, tmp_path):
    """Test run_quick_audit executes audit scripts."""
    scripts_dir = tmp_path
    audit_dir = scripts_dir / "audit"
    audit_dir.mkdir()

    ebs_script = audit_dir / "aws_ebs_audit.py"
    vpc_script = audit_dir / "aws_vpc_audit.py"
    ebs_script.write_text("print('EBS test')")
    vpc_script.write_text("print('VPC test')")

    with patch("cost_toolkit.overview.audit._run_audit_script") as mock_run:
        run_quick_audit(str(scripts_dir))

        assert mock_run.call_count == 2
        captured = capsys.readouterr()
        assert "Quick Resource Audit" in captured.out


def test_report_lightsail_cost_breakdown_with_data(capsys):
    """Test report_lightsail_cost_breakdown with cost data."""
    with patch("boto3.client") as mock_client:
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "Groups": [
                        {
                            "Keys": ["USW2-BoxUsage:1"],
                            "Metrics": {"UnblendedCost": {"Amount": "10.50"}},
                        },
                        {
                            "Keys": ["USW2-LoadBalancer"],
                            "Metrics": {"UnblendedCost": {"Amount": "5.25"}},
                        },
                    ]
                }
            ]
        }
        mock_client.return_value = mock_ce

        report_lightsail_cost_breakdown()

        captured = capsys.readouterr()
        assert "LIGHTSAIL COST BREAKDOWN" in captured.out
        assert "10.50" in captured.out or "5.25" in captured.out


def test_report_lightsail_cost_breakdown_no_data(capsys):
    """Test report_lightsail_cost_breakdown with no cost data."""
    with patch("boto3.client") as mock_client:
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = {"ResultsByTime": [{"Groups": []}]}
        mock_client.return_value = mock_ce

        report_lightsail_cost_breakdown()

        captured = capsys.readouterr()
        assert "No Lightsail spend" in captured.out


def test_report_lightsail_cost_breakdown_error(capsys):
    """Test report_lightsail_cost_breakdown handles errors."""
    with patch("boto3.client") as mock_client:
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.side_effect = ClientError({"Error": {"Code": "TestError"}}, "test")
        mock_client.return_value = mock_ce

        report_lightsail_cost_breakdown()

        captured = capsys.readouterr()
        assert "Unable to fetch" in captured.out
