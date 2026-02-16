"""Comprehensive tests for aws_ebs_post_termination_audit.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.audit.aws_ebs_post_termination_audit import (
    _build_attachment_info,
    _build_volume_detail,
    check_terminated_instances_volumes,
    get_ebs_volumes_by_region,
    main,
)


class TestBuildAttachmentInfo:
    """Tests for _build_attachment_info function."""

    def test_build_attachment_info_with_attachments(self):
        """Test building attachment info with attachments."""
        attachments = [
            {
                "InstanceId": "i-123",
                "Device": "/dev/sda1",
                "State": "attached",
                "DeleteOnTermination": True,
            }
        ]

        result = _build_attachment_info(attachments)

        assert "i-123" in result
        assert "/dev/sda1" in result
        assert "attached" in result
        assert "DeleteOnTermination: True" in result

    def test_build_attachment_info_no_attachments(self):
        """Test building attachment info with empty list."""
        result = _build_attachment_info([])

        assert result == "Unattached"

    def test_build_attachment_info_missing_fields(self):
        """Test building attachment info with missing fields."""
        attachments = [{"InstanceId": "i-123"}]

        result = _build_attachment_info(attachments)

        assert "i-123" in result
        assert "None" in result
        assert "DeleteOnTermination: None" in result


class TestBuildVolumeDetail:
    """Tests for _build_volume_detail function."""

    def test_build_volume_detail_complete(self):
        """Test building volume detail with complete data."""
        volume = {
            "VolumeId": "vol-123",
            "Size": 100,
            "State": "available",
            "VolumeType": "gp3",
            "CreateTime": "2024-01-01",
            "Attachments": [
                {
                    "InstanceId": "i-123",
                    "Device": "/dev/sda1",
                    "State": "attached",
                    "DeleteOnTermination": False,
                }
            ],
            "Tags": [{"Key": "Name", "Value": "test-volume"}],
        }

        result = _build_volume_detail(volume)

        assert result["VolumeId"] == "vol-123"
        assert result["Name"] == "test-volume"
        assert result["Size"] == 100
        assert result["State"] == "available"
        assert result["VolumeType"] == "gp3"
        assert result["MonthlyCost"] == 8.0

    def test_build_volume_detail_no_tags(self):
        """Test building volume detail with no tags."""
        volume = {
            "VolumeId": "vol-456",
            "Size": 50,
            "State": "in-use",
            "VolumeType": "gp2",
            "CreateTime": "2024-01-01",
            "Attachments": [],
            "Tags": [],
        }

        result = _build_volume_detail(volume)

        assert result["Name"] is None
        assert result["Tags"] == {}

    def test_build_volume_detail_cost_calculation(self):
        """Test volume cost calculation."""
        volume = {
            "VolumeId": "vol-789",
            "Size": 250,
            "State": "available",
            "VolumeType": "gp3",
            "CreateTime": "2024-01-01",
            "Attachments": [],
            "Tags": [],
        }

        result = _build_volume_detail(volume)

        assert result["MonthlyCost"] == 20.0

    def test_build_volume_detail_unattached(self):
        """Test building volume detail for unattached volume."""
        volume = {
            "VolumeId": "vol-unattached",
            "Size": 10,
            "State": "available",
            "VolumeType": "gp2",
            "CreateTime": "2024-01-01",
            "Attachments": [],
            "Tags": [{"Key": "Name", "Value": "orphan"}],
        }

        result = _build_volume_detail(volume)

        assert result["Attachment"] == "Unattached"


class TestGetEbsVolumesByRegion:
    """Tests for get_ebs_volumes_by_region function."""

    def test_get_volumes_success(self):
        """Test successful volume retrieval."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_client.return_value = mock_ec2
            mock_ec2.describe_volumes.return_value = {
                "Volumes": [
                    {
                        "VolumeId": "vol-123",
                        "Size": 100,
                        "State": "available",
                        "VolumeType": "gp3",
                        "CreateTime": "2024-01-01",
                        "Attachments": [],
                        "Tags": [{"Key": "Name", "Value": "test"}],
                    }
                ]
            }

            result = get_ebs_volumes_by_region("us-east-1")

            assert len(result) == 1
            assert result[0]["VolumeId"] == "vol-123"

    def test_get_volumes_empty(self):
        """Test volume retrieval with no volumes."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_client.return_value = mock_ec2
            mock_ec2.describe_volumes.return_value = {"Volumes": []}

            result = get_ebs_volumes_by_region("us-east-1")

            assert not result

    def test_get_volumes_error(self, capsys):
        """Test error handling during volume retrieval."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_client.return_value = mock_ec2
            mock_ec2.describe_volumes.side_effect = ClientError({"Error": {"Code": "UnauthorizedOperation"}}, "describe_volumes")

            result = get_ebs_volumes_by_region("us-east-1")

            assert not result
            captured = capsys.readouterr()
            assert "Error getting volumes" in captured.out


class TestCheckTerminatedInstancesVolumes:
    """Tests for check_terminated_instances_volumes function."""

    def test_check_no_orphaned_volumes(self, capsys):
        """Test when no orphaned volumes found."""
        with patch(
            "cost_toolkit.scripts.audit.aws_ebs_post_termination_audit.get_ebs_volumes_by_region",
            return_value=[
                {
                    "VolumeId": "vol-123",
                    "Name": "test",
                    "Size": 100,
                    "State": "available",
                    "VolumeType": "gp3",
                    "CreateTime": "2024-01-01",
                    "Attachment": "i-999 (/dev/sda1)",
                    "MonthlyCost": 8.0,
                    "Tags": {},
                }
            ],
        ):
            result = check_terminated_instances_volumes()

            assert not result
            captured = capsys.readouterr()
            assert "No orphaned volumes found" in captured.out

    def test_check_with_orphaned_volumes(self, capsys):
        """Test when orphaned volumes are found."""
        with patch(
            "cost_toolkit.scripts.audit.aws_ebs_post_termination_audit.get_ebs_volumes_by_region",
            return_value=[
                {
                    "VolumeId": "vol-orphan",
                    "Name": "orphan-volume",
                    "Size": 50,
                    "State": "available",
                    "VolumeType": "gp2",
                    "CreateTime": "2024-01-01",
                    "Attachment": "i-032b756f4ad7b1821 (/dev/sda1)",
                    "MonthlyCost": 4.0,
                    "Tags": {},
                }
            ],
        ):
            result = check_terminated_instances_volumes()

            assert len(result) == 1
            assert result[0]["volume"]["VolumeId"] == "vol-orphan"
            assert result[0]["terminated_instance"] == "Talker GPU"
            captured = capsys.readouterr()
            assert "ORPHANED VOLUMES FOUND" in captured.out
            assert "$4.00" in captured.out

    def test_check_summary_output(self, capsys):
        """Test summary output format."""
        with patch(
            "cost_toolkit.scripts.audit.aws_ebs_post_termination_audit.get_ebs_volumes_by_region",
            return_value=[
                {
                    "VolumeId": "vol-1",
                    "Name": "volume-1",
                    "Size": 100,
                    "State": "in-use",
                    "VolumeType": "gp3",
                    "CreateTime": "2024-01-01",
                    "Attachment": "i-999",
                    "MonthlyCost": 8.0,
                    "Tags": {},
                }
            ],
        ):
            check_terminated_instances_volumes()

            captured = capsys.readouterr()
            assert "SUMMARY:" in captured.out
            assert "Total volumes in us-east-1:" in captured.out
            assert "Total monthly cost:" in captured.out


class TestMain:
    """Tests for main function."""

    def test_main_with_orphaned_volumes(self, capsys):
        """Test main function with orphaned volumes."""
        audit_mod = "cost_toolkit.scripts.audit.aws_ebs_post_termination_audit"
        with patch(
            f"{audit_mod}.check_terminated_instances_volumes",
            return_value=[
                {
                    "volume": {"VolumeId": "vol-123", "MonthlyCost": 5.0},
                    "terminated_instance": "Test",
                    "instance_id": "i-123",
                }
            ],
        ):
            main()

            captured = capsys.readouterr()
            assert "RECOMMENDED ACTION:" in captured.out

    def test_main_without_orphaned_volumes(self, capsys):
        """Test main function without orphaned volumes."""
        audit_mod = "cost_toolkit.scripts.audit.aws_ebs_post_termination_audit"
        with patch(
            f"{audit_mod}.check_terminated_instances_volumes",
            return_value=[],
        ):
            main()

            captured = capsys.readouterr()
            assert "RECOMMENDED ACTION:" not in captured.out
