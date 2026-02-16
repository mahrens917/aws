"""Comprehensive tests for aws_vpc_flow_logs_audit.py - Part 1."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cost_toolkit.scripts.audit.aws_vpc_flow_logs_audit import (
    _check_log_group_size,
    _check_vpc_endpoints,
    _check_vpc_peering_connections,
    _check_vpc_resource_counts,
    audit_flow_logs_in_region,
)


class TestCheckLogGroupSize:
    """Tests for _check_log_group_size function."""

    def test_check_log_group_size_success(self, capsys):
        """Test successful log group size check."""
        mock_logs_client = MagicMock()
        mock_logs_client.describe_log_groups.return_value = {
            "logGroups": [
                {
                    "logGroupName": "/aws/vpc/flowlogs",
                    "storedBytes": 1073741824,  # 1 GB
                }
            ]
        }

        cost = _check_log_group_size(mock_logs_client, "/aws/vpc/flowlogs")

        assert cost == 0.50
        captured = capsys.readouterr()
        assert "Log Group Size: 1.00 GB" in captured.out
        assert "storage cost: $0.50/month" in captured.out

    def test_check_log_group_size_multiple_groups(self, capsys):
        """Test with multiple log groups, returns correct one."""
        mock_logs_client = MagicMock()
        mock_logs_client.describe_log_groups.return_value = {
            "logGroups": [
                {
                    "logGroupName": "/aws/vpc/other",
                    "storedBytes": 5368709120,  # 5 GB
                },
                {
                    "logGroupName": "/aws/vpc/flowlogs",
                    "storedBytes": 2147483648,  # 2 GB
                },
            ]
        }

        cost = _check_log_group_size(mock_logs_client, "/aws/vpc/flowlogs")

        assert cost == 1.00
        captured = capsys.readouterr()
        assert "Log Group Size: 2.00 GB" in captured.out

    def test_check_log_group_size_no_stored_bytes(self, capsys):
        """Test when log group has no storedBytes field."""
        mock_logs_client = MagicMock()
        mock_logs_client.describe_log_groups.return_value = {
            "logGroups": [
                {
                    "logGroupName": "/aws/vpc/flowlogs",
                }
            ]
        }

        cost = _check_log_group_size(mock_logs_client, "/aws/vpc/flowlogs")

        assert cost == 0.0

    def test_check_log_group_size_not_found(self):
        """Test when log group is not found."""
        mock_logs_client = MagicMock()
        mock_logs_client.describe_log_groups.return_value = {
            "logGroups": [
                {
                    "logGroupName": "/aws/vpc/other",
                    "storedBytes": 1024,
                }
            ]
        }

        cost = _check_log_group_size(mock_logs_client, "/aws/vpc/flowlogs")

        assert cost == 0

    def test_check_log_group_size_client_error(self, capsys):
        """Test error handling when API call fails."""
        mock_logs_client = MagicMock()
        mock_logs_client.describe_log_groups.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "describe_log_groups")

        cost = _check_log_group_size(mock_logs_client, "/aws/vpc/flowlogs")

        assert cost == 0
        captured = capsys.readouterr()
        assert "Error checking log group" in captured.out


class TestAuditFlowLogsBasic:
    """Tests for audit_flow_logs_in_region function - basic cases."""

    def test_audit_flow_logs_no_logs(self, capsys):
        """Test when no flow logs exist."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_client.return_value = mock_ec2
            mock_ec2.describe_flow_logs.return_value = {"FlowLogs": []}

            result = audit_flow_logs_in_region("us-east-1")

        assert len(result) == 0
        captured = capsys.readouterr()
        assert "No VPC Flow Logs found" in captured.out

    def test_audit_flow_logs_success(self, capsys):
        """Test successful flow logs audit."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_logs = MagicMock()
            mock_client.side_effect = [mock_ec2, mock_logs]

            mock_ec2.describe_flow_logs.return_value = {
                "FlowLogs": [
                    {
                        "FlowLogId": "fl-123",
                        "FlowLogStatus": "ACTIVE",
                        "ResourceType": "VPC",
                        "ResourceIds": ["vpc-123"],
                        "LogDestinationType": "s3",
                        "LogDestination": "arn:aws:s3:::my-bucket",
                        "CreationTime": "2024-01-01",
                        "Tags": [],
                    }
                ]
            }

            result = audit_flow_logs_in_region("us-east-1")

        assert len(result) == 1
        assert result[0]["flow_log_id"] == "fl-123"
        assert result[0]["flow_log_status"] == "ACTIVE"
        assert result[0]["resource_type"] == "VPC"
        captured = capsys.readouterr()
        assert "Flow Log: fl-123" in captured.out


class TestAuditFlowLogsAdvanced:
    """Tests for audit_flow_logs_in_region function - advanced cases."""

    def test_audit_flow_logs_cloudwatch_destination(self, capsys):
        """Test flow logs with CloudWatch destination."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_logs = MagicMock()
            mock_client.side_effect = [mock_ec2, mock_logs]

            mock_ec2.describe_flow_logs.return_value = {
                "FlowLogs": [
                    {
                        "FlowLogId": "fl-456",
                        "FlowLogStatus": "ACTIVE",
                        "ResourceType": "VPC",
                        "ResourceIds": ["vpc-456"],
                        "LogDestinationType": "cloud-watch-logs",
                        "LogDestination": "arn:aws:logs:us-east-1:123:log-group:/aws/vpc/flowlogs",
                        "CreationTime": "2024-01-01",
                        "Tags": [{"Key": "Name", "Value": "test-flow-log"}],
                    }
                ]
            }
            mock_logs.describe_log_groups.return_value = {
                "logGroups": [
                    {
                        "logGroupName": "/aws/vpc/flowlogs",
                        "storedBytes": 1073741824,
                    }
                ]
            }

            result = audit_flow_logs_in_region("us-east-1")

        assert len(result) == 1
        assert result[0]["log_destination_type"] == "cloud-watch-logs"
        assert "storage_cost" in result[0]
        assert result[0]["storage_cost"] == 0.50
        captured = capsys.readouterr()
        assert "Tags:" in captured.out
        assert "Name: test-flow-log" in captured.out

    def test_audit_flow_logs_client_error(self, capsys):
        """Test error handling during flow logs audit."""
        with patch("boto3.client") as mock_client:
            mock_ec2 = MagicMock()
            mock_client.return_value = mock_ec2
            mock_ec2.describe_flow_logs.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "describe_flow_logs")

            result = audit_flow_logs_in_region("us-east-1")

        assert len(result) == 0
        captured = capsys.readouterr()
        assert "Error auditing Flow Logs" in captured.out


class TestCheckVpcPeeringConnections:
    """Tests for _check_vpc_peering_connections function."""

    def test_check_vpc_peering_success(self, capsys):
        """Test successful VPC peering check."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_vpc_peering_connections.return_value = {
            "VpcPeeringConnections": [
                {
                    "VpcPeeringConnectionId": "pcx-123",
                    "Status": {"Code": "active"},
                },
                {
                    "VpcPeeringConnectionId": "pcx-456",
                    "Status": {"Code": "pending-acceptance"},
                },
            ]
        }

        _check_vpc_peering_connections(mock_ec2)

        captured = capsys.readouterr()
        assert "VPC Peering Connections: 2" in captured.out
        assert "pcx-123 - active" in captured.out
        assert "pcx-456 - pending-acceptance" in captured.out

    def test_check_vpc_peering_no_connections(self, capsys):
        """Test when no peering connections exist."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_vpc_peering_connections.return_value = {"VpcPeeringConnections": []}

        _check_vpc_peering_connections(mock_ec2)

        captured = capsys.readouterr()
        assert "VPC Peering Connections: 0" in captured.out

    def test_check_vpc_peering_no_status(self, capsys):
        """Test when peering connection has no status."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_vpc_peering_connections.return_value = {
            "VpcPeeringConnections": [
                {
                    "VpcPeeringConnectionId": "pcx-789",
                }
            ]
        }

        _check_vpc_peering_connections(mock_ec2)

        captured = capsys.readouterr()
        assert "pcx-789 - None" in captured.out


class TestCheckVpcEndpoints:
    """Tests for _check_vpc_endpoints function."""

    def test_check_vpc_endpoints_success(self, capsys):
        """Test successful VPC endpoints check."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_vpc_endpoints.return_value = {
            "VpcEndpoints": [
                {
                    "VpcEndpointId": "vpce-123",
                    "VpcEndpointType": "Interface",
                    "ServiceName": "com.amazonaws.us-east-1.s3",
                    "State": "available",
                    "CreationTimestamp": "2024-01-01",
                }
            ]
        }

        _check_vpc_endpoints(mock_ec2)

        captured = capsys.readouterr()
        assert "VPC Endpoints: 1" in captured.out
        assert "vpce-123 (Interface)" in captured.out
        assert "com.amazonaws.us-east-1.s3" in captured.out
        assert "State: available" in captured.out

    def test_check_vpc_endpoints_gateway_type(self, capsys):
        """Test VPC endpoints with Gateway type."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_vpc_endpoints.return_value = {
            "VpcEndpoints": [
                {
                    "VpcEndpointId": "vpce-456",
                    "ServiceName": "com.amazonaws.us-east-1.dynamodb",
                    "State": "available",
                }
            ]
        }

        _check_vpc_endpoints(mock_ec2)

        captured = capsys.readouterr()
        assert "vpce-456 (None)" in captured.out

    def test_check_vpc_endpoints_empty(self, capsys):
        """Test when no VPC endpoints exist."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_vpc_endpoints.return_value = {"VpcEndpoints": []}

        _check_vpc_endpoints(mock_ec2)

        captured = capsys.readouterr()
        assert "VPC Endpoints: 0" in captured.out


class TestCheckVpcResourceCounts:
    """Tests for _check_vpc_resource_counts function."""

    def test_check_vpc_resource_counts_success(self, capsys):
        """Test successful VPC resource counts check."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_security_groups.return_value = {"SecurityGroups": [{}, {}]}
        mock_ec2.describe_network_acls.return_value = {"NetworkAcls": [{}]}
        mock_ec2.describe_route_tables.return_value = {"RouteTables": [{}, {}, {}]}
        mock_ec2.describe_subnets.return_value = {"Subnets": [{}, {}]}

        _check_vpc_resource_counts(mock_ec2)

        captured = capsys.readouterr()
        assert "Security Groups: 2" in captured.out
        assert "Network ACLs: 1" in captured.out
        assert "Route Tables: 3" in captured.out
        assert "Subnets: 2" in captured.out

    def test_check_vpc_resource_counts_empty(self, capsys):
        """Test when no VPC resources exist."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_security_groups.return_value = {"SecurityGroups": []}
        mock_ec2.describe_network_acls.return_value = {"NetworkAcls": []}
        mock_ec2.describe_route_tables.return_value = {"RouteTables": []}
        mock_ec2.describe_subnets.return_value = {"Subnets": []}

        _check_vpc_resource_counts(mock_ec2)

        captured = capsys.readouterr()
        assert "Security Groups: 0" in captured.out
