"""Additional tests for migration_sync.py edge cases."""

from __future__ import annotations

from threading import Event
from unittest import mock

from migration_sync import sync_bucket


def test_multiple_sync_calls_share_base_dir(tmp_path):
    """sync_bucket can sync multiple buckets into base path."""
    fake_s3 = mock.Mock()
    fake_s3.get_paginator.return_value.paginate.return_value = [{"Contents": []}]

    sync_bucket(fake_s3, mock.Mock(), tmp_path, "bucket-a", Event())
    sync_bucket(fake_s3, mock.Mock(), tmp_path, "bucket-b", Event())

    assert (tmp_path / "bucket-a").exists()
    assert (tmp_path / "bucket-b").exists()
