"""Comprehensive tests for migration_sync.py - Function signature."""

from threading import Event
from unittest import mock

from migration_sync import sync_bucket


class TestSyncBucketFunction:
    """Test sync_bucket function interface"""

    def test_sync_bucket_creates_local_directory(self, tmp_path):
        """Test that sync_bucket creates the local bucket directory"""
        fake_s3 = mock.Mock()
        fake_s3.get_paginator.return_value.paginate.return_value = [{"Contents": []}]
        fake_state = mock.Mock()
        base_path = tmp_path / "sync"

        sync_bucket(fake_s3, fake_state, base_path, "my-bucket", Event())

        assert (base_path / "my-bucket").exists()

    def test_sync_bucket_accepts_event_for_interrupt(self, tmp_path):
        """Test that sync_bucket accepts a threading.Event for interruption"""
        fake_s3 = mock.Mock()
        fake_s3.get_paginator.return_value.paginate.return_value = [{"Contents": []}]
        fake_state = mock.Mock()
        interrupted = Event()

        # Should complete without error
        sync_bucket(fake_s3, fake_state, tmp_path, "my-bucket", interrupted)
        assert not interrupted.is_set()
