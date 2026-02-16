"""Tests for migration_sync.py streaming downloads."""

from __future__ import annotations

from io import BytesIO
from threading import Event
from unittest import mock

from migration_sync import sync_bucket


class _FakeBody:
    def __init__(self, payload: bytes):
        """Initialize fake streaming body."""
        self._payload = payload

    def iter_chunks(self, chunk_size=8192):
        """Yield data in consistent chunk sizes."""
        stream = BytesIO(self._payload)
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            yield chunk


class _FakePaginator:
    def __init__(self, contents):
        """Store paginator contents."""
        self._contents = contents

    def paginate(self, **_kwargs):
        """Yield a single paginator page."""
        yield {"Contents": self._contents}


class _FakeS3:
    def __init__(self, objects: dict[str, bytes]):
        """Create fake S3 client with in-memory objects."""
        self.objects = objects

    def get_paginator(self, _name):
        """Return a paginator that exposes the configured contents."""
        contents = [{"Key": key, "Size": len(data)} for key, data in self.objects.items()]
        return _FakePaginator(contents)

    def get_object(self, _Bucket, Key, **_kwargs):  # pylint: disable=invalid-name  # noqa: N803 - boto3 casing
        """Return a fake object body."""
        data = self.objects.get(Key)
        if data is None:
            raise RuntimeError("Missing object")
        return {"Body": _FakeBody(data)}


def test_sync_bucket_downloads_files(tmp_path):
    """sync_bucket writes downloaded objects to disk."""
    fake_s3 = _FakeS3({"file1.txt": b"hello", "dir/file2.bin": b"data"})

    sync_bucket(fake_s3, mock.Mock(), tmp_path, "my-bucket", Event())

    assert (tmp_path / "my-bucket" / "file1.txt").read_bytes() == b"hello"
    assert (tmp_path / "my-bucket" / "dir" / "file2.bin").read_bytes() == b"data"


def test_sync_bucket_respects_interrupt(tmp_path):
    """Sync stops when interrupted flag is set."""
    fake_s3 = _FakeS3({"file1.txt": b"hello", "file2.txt": b"data"})
    interrupted = Event()
    interrupted.set()

    # Should not raise but also not download files
    sync_bucket(fake_s3, mock.Mock(), tmp_path, "bucket", interrupted)
    assert not (tmp_path / "bucket" / "file1.txt").exists()
