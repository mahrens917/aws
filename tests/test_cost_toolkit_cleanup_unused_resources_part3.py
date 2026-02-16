"""Comprehensive tests for aws_cleanup_unused_resources.py - Part 3."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources import (
    _analyze_all_regions,
    _execute_cleanup,
    _group_resources_by_region,
    main,
)
from cost_toolkit.scripts.cleanup.unused_subnets import (
    delete_unused_subnets,
)


class TestDeleteUnusedSubnets:
    """Tests for delete_unused_subnets function."""

    def test_delete_success(self, capsys):
        """Test successful deletion of subnets."""
        unused_subnets = [
            {"SubnetId": "subnet-1", "CidrBlock": "10.0.1.0/24"},
            {"SubnetId": "subnet-2", "CidrBlock": "10.0.2.0/24"},
        ]

        with patch("boto3.client") as mock_boto3:
            mock_ec2 = MagicMock()
            mock_boto3.return_value = mock_ec2

            result = delete_unused_subnets(unused_subnets, "us-east-1")

            assert result is True
            assert mock_ec2.delete_subnet.call_count == 2
            captured = capsys.readouterr()
            assert "Deleted: 2" in captured.out

    def test_delete_empty_list(self, capsys):
        """Test deletion with empty list."""
        result = delete_unused_subnets([], "us-east-1")

        assert result is True
        captured = capsys.readouterr()
        assert "No unused subnets to delete" in captured.out


class TestGroupResourcesByRegion:
    """Tests for _group_resources_by_region function."""

    def test_group_resources(self):
        """Test grouping resources by region."""
        all_unused_sgs = [
            ("us-east-1", {"GroupId": "sg-1"}),
            ("us-east-1", {"GroupId": "sg-2"}),
            ("us-west-2", {"GroupId": "sg-3"}),
        ]
        all_unused_subnets = [
            ("us-east-1", {"SubnetId": "subnet-1"}),
            ("us-west-2", {"SubnetId": "subnet-2"}),
        ]

        result = _group_resources_by_region(all_unused_sgs, all_unused_subnets)

        assert len(result) == 2
        assert len(result["us-east-1"]["sgs"]) == 2
        assert len(result["us-east-1"]["subnets"]) == 1
        assert len(result["us-west-2"]["sgs"]) == 1
        assert len(result["us-west-2"]["subnets"]) == 1

    def test_group_empty_resources(self):
        """Test grouping with no resources."""
        result = _group_resources_by_region([], [])

        assert len(result) == 0


class TestAnalyzeAllRegions:
    """Tests for _analyze_all_regions function."""

    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.analyze_subnet_usage")
    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.analyze_security_groups_usage")
    def test_analyze_collects_unused(self, mock_sg_analysis, mock_subnet_analysis, capsys):
        """Test _analyze_all_regions collects unused resources."""
        mock_sg_analysis.return_value = {"unused": [{"GroupId": "sg-1"}], "used": []}
        mock_subnet_analysis.return_value = {"unused": [{"SubnetId": "subnet-1"}], "used": []}

        sgs, subnets = _analyze_all_regions(["us-east-1"])

        assert len(sgs) == 1
        assert sgs[0] == ("us-east-1", {"GroupId": "sg-1"})
        assert len(subnets) == 1
        assert subnets[0] == ("us-east-1", {"SubnetId": "subnet-1"})

    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.analyze_subnet_usage")
    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.analyze_security_groups_usage")
    def test_analyze_no_unused(self, mock_sg_analysis, mock_subnet_analysis, capsys):
        """Test _analyze_all_regions with no unused resources."""
        mock_sg_analysis.return_value = {"unused": [], "used": [{"GroupId": "sg-1"}]}
        mock_subnet_analysis.return_value = {"unused": [], "used": [{"SubnetId": "subnet-1"}]}

        sgs, subnets = _analyze_all_regions(["us-east-1"])

        assert len(sgs) == 0
        assert len(subnets) == 0


class TestExecuteCleanup:
    """Tests for _execute_cleanup function."""

    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.delete_unused_subnets")
    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.delete_unused_security_groups")
    def test_execute_cleanup_calls_both(self, mock_delete_sgs, mock_delete_subnets, capsys):
        """Test _execute_cleanup calls both deletion functions."""
        regions_with_unused = {
            "us-east-1": {
                "sgs": [{"GroupId": "sg-1"}],
                "subnets": [{"SubnetId": "subnet-1"}],
            }
        }

        _execute_cleanup(regions_with_unused)

        mock_delete_sgs.assert_called_once_with([{"GroupId": "sg-1"}], "us-east-1")
        mock_delete_subnets.assert_called_once_with([{"SubnetId": "subnet-1"}], "us-east-1")

    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.delete_unused_subnets")
    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.delete_unused_security_groups")
    def test_execute_cleanup_skips_empty(self, mock_delete_sgs, mock_delete_subnets, capsys):
        """Test _execute_cleanup skips empty resource lists."""
        regions_with_unused = {"us-east-1": {"sgs": [], "subnets": [{"SubnetId": "subnet-1"}]}}

        _execute_cleanup(regions_with_unused)

        mock_delete_sgs.assert_not_called()
        mock_delete_subnets.assert_called_once()


class TestMain:
    """Tests for main function."""

    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.get_all_aws_regions")
    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.analyze_subnet_usage")
    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.analyze_security_groups_usage")
    def test_main_no_unused(self, mock_sg, mock_subnet, mock_regions, capsys):
        """Test main with no unused resources."""
        mock_regions.return_value = ["us-east-1"]
        mock_sg.return_value = {"unused": [], "used": []}
        mock_subnet.return_value = {"unused": [], "used": []}

        main()

        captured = capsys.readouterr()
        assert "Total unused security groups found: 0" in captured.out
        assert "Total unused subnets found: 0" in captured.out

    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.delete_unused_subnets")
    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.delete_unused_security_groups")
    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.get_all_aws_regions")
    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.analyze_subnet_usage")
    @patch("cost_toolkit.scripts.cleanup.aws_cleanup_unused_resources.analyze_security_groups_usage")
    def test_main_with_unused(self, mock_sg, mock_subnet, mock_regions, _mock_del_sg, _mock_del_sub, capsys):
        """Test main triggers cleanup when resources found."""
        mock_regions.return_value = ["us-east-1"]
        mock_sg.return_value = {"unused": [{"GroupId": "sg-1"}], "used": []}
        mock_subnet.return_value = {"unused": [{"SubnetId": "subnet-1"}], "used": []}

        main()

        captured = capsys.readouterr()
        assert "CLEANUP PHASE" in captured.out
