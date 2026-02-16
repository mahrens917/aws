"""Helper fixtures moved from ``tests.conftest`` to keep that module small."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest

from cleanup_temp_artifacts.categories import Category
from cleanup_temp_artifacts.core_scanner import Candidate
from migration_state_v2 import MigrationStateV2, Phase


@pytest.fixture
def mock_block_s3_dependencies(mock_aws_identity, sample_policy):  # pylint: disable=redefined-outer-name
    """Common mocks for block_s3.py tests (context manager)."""

    class MockContext:  # pylint: disable=too-many-instance-attributes
        """Context manager for block_s3 test mocking."""

        def __init__(self):
            self.identity_patch = self.policy_patch = self.save_patch = None  # type: ignore
            self.identity_mock = self.policy_mock = self.save_mock = None

        def __enter__(self):
            self.identity_patch = mock.patch("block_s3.get_aws_identity", return_value=mock_aws_identity)
            self.policy_patch = mock.patch("block_s3.generate_restrictive_bucket_policy", return_value=sample_policy)
            self.save_patch = mock.patch("block_s3.save_policy_to_file")
            self.identity_mock = self.identity_patch.__enter__()
            self.policy_mock = self.policy_patch.__enter__()
            self.save_mock = self.save_patch.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.save_patch.__exit__(exc_type, exc_val, exc_tb)  # type: ignore
            self.policy_patch.__exit__(exc_type, exc_val, exc_tb)  # type: ignore
            self.identity_patch.__exit__(exc_type, exc_val, exc_tb)  # type: ignore

    return MockContext()


@pytest.fixture
def create_policy_file(policies_dir):  # pylint: disable=redefined-outer-name
    """Helper function to create policy files with given bucket name and policy content."""

    def _create_policy_file(bucket_name, policy_content=None):
        if policy_content is None:
            policy_content = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow"}]}
        policy_file = policies_dir / f"{bucket_name}_policy.json"
        policy_file.write_text(json.dumps(policy_content))
        return policy_file

    return _create_policy_file


@pytest.fixture
def mock_apply_block_dependencies():
    """Context manager with mocked apply_bucket_policy for apply_block.py tests."""

    class MockContext:  # pylint: disable=too-many-instance-attributes
        """Context manager for apply_block test mocking."""

        def __init__(self):
            self.apply_patch = self.apply_mock = None  # type: ignore

        def __enter__(self):
            self.apply_patch = mock.patch("apply_block.apply_bucket_policy")
            self.apply_mock = self.apply_patch.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.apply_patch.__exit__(exc_type, exc_val, exc_tb)  # type: ignore

    return MockContext()


@pytest.fixture
def mock_aws_info_context(mock_aws_info_identity):  # pylint: disable=redefined-outer-name
    """Context manager mocking get_aws_identity, list_s3_buckets, and print for aws_info tests."""

    class MockContext:  # pylint: disable=too-many-instance-attributes
        """Context manager for aws_info test mocking."""

        def __init__(self, identity):
            self.identity = identity
            self.buckets = []
            self.identity_patch = self.buckets_patch = self.print_patch = None  # type: ignore
            self.identity_mock = self.buckets_mock = self.print_mock = None

        def with_buckets(self, buckets):
            """Set the buckets list for this context"""
            self.buckets = buckets
            return self

        def __enter__(self):
            self.identity_patch = mock.patch("aws_info.get_aws_identity", return_value=self.identity)
            self.buckets_patch = mock.patch("aws_info.list_s3_buckets", return_value=self.buckets)
            self.print_patch = mock.patch("builtins.print")
            self.identity_mock = self.identity_patch.__enter__()
            self.buckets_mock = self.buckets_patch.__enter__()
            self.print_mock = self.print_patch.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.print_patch.__exit__(exc_type, exc_val, exc_tb)  # type: ignore
            self.buckets_patch.__exit__(exc_type, exc_val, exc_tb)  # type: ignore
            self.identity_patch.__exit__(exc_type, exc_val, exc_tb)  # type: ignore

    return MockContext(mock_aws_info_identity)


@pytest.fixture
def empty_policy():
    """Empty S3 bucket policy"""
    return {"Version": "2012-10-17", "Statement": []}


@pytest.fixture
def mock_block_s3_context(mock_aws_identity):  # pylint: disable=redefined-outer-name
    """Fixture providing context manager for block_s3 tests with policy/save mocking."""

    class MockContext:  # pylint: disable=too-many-instance-attributes
        """Context manager for mocking block_s3 operations in tests."""

        def __init__(self, identity):
            self.identity = identity
            self.policy = {"Version": "2012-10-17", "Statement": []}
            self.buckets = []
            self.identity_patch = self.policy_patch = None  # type: ignore
            self.identity_mock = self.policy_mock = None
            self.save_policy_patch = None
            self.save_policy_mock = None

        def with_policy(self, policy):
            """Set the policy to be returned by mocked generate_restrictive_bucket_policy."""
            self.policy = policy
            return self

        def with_buckets(self, buckets):
            """Set the list of buckets to be used in tests."""
            self.buckets = buckets
            return self

        def __enter__(self):
            self.identity_patch = mock.patch("block_s3.get_aws_identity", return_value=self.identity)
            self.policy_patch = mock.patch("block_s3.generate_restrictive_bucket_policy", return_value=self.policy)
            self.save_policy_patch = mock.patch("block_s3.save_policy_to_file")
            self.identity_mock = self.identity_patch.__enter__()
            self.policy_mock = self.policy_patch.__enter__()
            self.save_policy_mock = self.save_policy_patch.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.save_policy_patch.__exit__(exc_type, exc_val, exc_tb)  # type: ignore
            self.policy_patch.__exit__(exc_type, exc_val, exc_tb)  # type: ignore
            self.identity_patch.__exit__(exc_type, exc_val, exc_tb)  # type: ignore

    return MockContext(mock_aws_identity)


@pytest.fixture
def mock_db_connection():
    """Mock database connection context manager factory for MigrationStateV2 tests."""

    def _create_mock_connection(rows):
        mock_conn = mock.Mock()
        mock_conn.execute.return_value = rows

        mock_cm = mock.MagicMock()
        mock_cm.__enter__.return_value = mock_conn
        mock_cm.__exit__.return_value = False

        return mock_cm

    return _create_mock_connection


@pytest.fixture
def mock_migration_scanner_deps():
    """Mock dependencies (s3, state) for migration scanner tests."""
    s3_client = mock.Mock()
    state_manager = mock.Mock(spec=MigrationStateV2)

    return {"s3": s3_client, "state": state_manager}


@pytest.fixture
def s3_paginator_response():
    """Factory for creating S3 paginator responses with given contents."""

    def _create_response(contents):
        return [{"Contents": contents}]

    return _create_response


@pytest.fixture
def s3_mock():
    """Create mock S3 client for migration scanner tests"""
    return mock.Mock()


@pytest.fixture
def state_mock():
    """Create mock MigrationStateV2 for migration scanner tests"""
    return mock.Mock(spec=MigrationStateV2)


@pytest.fixture
def interrupted():
    """Create a threading.Event for interrupt signalling in scanner tests."""
    from threading import Event

    return Event()


@pytest.fixture
def mock_orchestrator_deps(tmp_path):
    """Mock dependencies for migration orchestrator tests."""
    base_path = tmp_path / "migration"
    base_path.mkdir()

    return {
        "s3": mock.Mock(),
        "state": mock.Mock(),
        "base_path": base_path,
        "drive_checker": mock.Mock(),
    }


@pytest.fixture
def mock_bucket_info():
    """Factory for creating bucket info dicts with custom values."""

    def _create_bucket_info(
        sync_complete=False,
        verify_complete=False,
        delete_complete=False,
        file_count=100,
        total_size=1000,
    ):
        """Create a bucket info dict with the given values"""
        return {
            "sync_complete": sync_complete,
            "verify_complete": verify_complete,
            "delete_complete": delete_complete,
            "file_count": file_count,
            "total_size": total_size,
        }

    return _create_bucket_info


@pytest.fixture
def all_phases():
    """List of all migration phases in order"""
    return [
        Phase.SCANNING,
        Phase.GLACIER_RESTORE,
        Phase.GLACIER_WAIT,
        Phase.SYNCING,
        Phase.VERIFYING,
        Phase.DELETING,
        Phase.COMPLETE,
    ]


@pytest.fixture
def common_phases():
    """Common migration phases (without VERIFYING and DELETING)"""
    return [
        Phase.SCANNING,
        Phase.GLACIER_RESTORE,
        Phase.GLACIER_WAIT,
        Phase.SYNCING,
        Phase.COMPLETE,
    ]


@pytest.fixture
def setup_verify_test(tmp_path, mock_db_connection):  # pylint: disable=redefined-outer-name
    """Setup verification test environment with test files, mock state, and db connection."""

    def _setup(file_data_map):
        """
        Setup verification test with given file data.

        Returns bucket_path, mock_state, and metadata.
        """
        bucket_path = tmp_path / "test-bucket"
        bucket_path.mkdir()

        # Create files and generate metadata
        file_metadata = []
        for filename, content in file_data_map.items():
            (bucket_path / filename).write_bytes(content)
            md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
            file_metadata.append({"key": filename, "size": len(content), "etag": md5})

        # Setup mock state
        state_manager = mock.Mock()
        state_manager.get_bucket_info.return_value = {
            "file_count": len(file_data_map),
            "total_size": sum(len(c) for c in file_data_map.values()),
        }

        # Setup db connection
        mock_cm = mock_db_connection(file_metadata)
        state_manager.db_conn.get_connection.return_value = mock_cm

        return {
            "bucket_path": bucket_path,
            "mock_state": state_manager,
            "file_metadata": file_metadata,
            "tmp_path": tmp_path,
        }

    return _setup


@pytest.fixture
def empty_verify_stats():
    """an empty verification stats dict"""
    return {
        "verified_count": 0,
        "size_verified": 0,
        "checksum_verified": 0,
        "total_bytes_verified": 0,
        "verification_errors": [],
    }


@pytest.fixture
def create_mock_process():
    """Factory for creating mock subprocess.Popen processes."""

    def _create_process(stdout_lines, returncodes):
        """Create mock process with specified stdout lines and return codes."""
        mock_process = mock.Mock()
        mock_process.stdout.readline.side_effect = [line.encode() if line else b"" for line in stdout_lines]
        mock_process.poll.side_effect = returncodes
        return mock_process

    return _create_process


@pytest.fixture
def make_candidate():
    """Factory for creating cleanup_temp_artifacts Candidate instances for testing."""

    def _make_candidate(
        path: str | Path,
        category_name: str = "test-category",
        size_bytes: int | None = 1024,
        mtime: float = 1234567890.0,
    ) -> Candidate:
        """Create a Candidate for testing."""
        category = Category(
            name=category_name,
            description="Test category",
            matcher=lambda p, is_dir: True,
            prune=True,
        )
        return Candidate(path=Path(path), category=category, size_bytes=size_bytes, mtime=mtime)

    return _make_candidate
