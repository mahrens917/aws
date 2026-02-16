"""
Tests for object processing functions in
cost_toolkit/scripts/audit/s3_audit/bucket_analysis.py
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from cost_toolkit.scripts.audit.s3_audit.bucket_analysis import _process_object
from tests.assertions import assert_equal


def test_process_object_standard_storage():
    """Test _process_object handles standard storage class objects."""
    bucket_analysis = {
        "total_objects": 0,
        "total_size_bytes": 0,
        "storage_classes": defaultdict(lambda: {"count": 0, "size_bytes": 0}),
        "last_modified_oldest": None,
        "last_modified_newest": None,
        "large_objects": [],
        "old_objects": [],
    }

    obj = {
        "Key": "test-key.txt",
        "Size": 1024,
        "StorageClass": "STANDARD",
        "LastModified": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }

    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
    large_object_threshold = 100 * 1024 * 1024

    _process_object(obj, bucket_analysis, ninety_days_ago, large_object_threshold)

    assert_equal(bucket_analysis["total_objects"], 1)
    assert_equal(bucket_analysis["total_size_bytes"], 1024)
    assert_equal(bucket_analysis["storage_classes"]["STANDARD"]["count"], 1)
    assert_equal(bucket_analysis["storage_classes"]["STANDARD"]["size_bytes"], 1024)
    assert_equal(bucket_analysis["last_modified_oldest"], datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert_equal(bucket_analysis["last_modified_newest"], datetime(2024, 1, 1, tzinfo=timezone.utc))


def test_process_object_no_storage_class_defaults_to_standard():
    """Test _process_object defaults to STANDARD when StorageClass is missing."""
    bucket_analysis = {
        "total_objects": 0,
        "total_size_bytes": 0,
        "storage_classes": defaultdict(lambda: {"count": 0, "size_bytes": 0}),
        "last_modified_oldest": None,
        "last_modified_newest": None,
        "large_objects": [],
        "old_objects": [],
    }

    obj = {
        "Key": "test-key.txt",
        "Size": 2048,
        "LastModified": datetime(2024, 6, 1, tzinfo=timezone.utc),
        "StorageClass": "STANDARD",
    }

    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
    large_object_threshold = 100 * 1024 * 1024

    _process_object(obj, bucket_analysis, ninety_days_ago, large_object_threshold)

    assert_equal(bucket_analysis["storage_classes"]["STANDARD"]["count"], 1)
    assert_equal(bucket_analysis["storage_classes"]["STANDARD"]["size_bytes"], 2048)


def test_process_object_large_object():
    """Test _process_object identifies large objects."""
    bucket_analysis = {
        "total_objects": 0,
        "total_size_bytes": 0,
        "storage_classes": defaultdict(lambda: {"count": 0, "size_bytes": 0}),
        "last_modified_oldest": None,
        "last_modified_newest": None,
        "large_objects": [],
        "old_objects": [],
    }

    large_size = 200 * 1024 * 1024  # 200MB
    obj = {
        "Key": "large-file.bin",
        "Size": large_size,
        "StorageClass": "STANDARD",
        "LastModified": datetime(2024, 10, 1, tzinfo=timezone.utc),
    }

    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
    large_object_threshold = 100 * 1024 * 1024

    _process_object(obj, bucket_analysis, ninety_days_ago, large_object_threshold)

    assert_equal(len(bucket_analysis["large_objects"]), 1)
    large_obj = bucket_analysis["large_objects"][0]
    assert_equal(large_obj["key"], "large-file.bin")
    assert_equal(large_obj["size_bytes"], large_size)
    assert_equal(large_obj["storage_class"], "STANDARD")


def test_process_object_old_object():
    """Test _process_object identifies old objects."""
    bucket_analysis = {
        "total_objects": 0,
        "total_size_bytes": 0,
        "storage_classes": defaultdict(lambda: {"count": 0, "size_bytes": 0}),
        "last_modified_oldest": None,
        "last_modified_newest": None,
        "large_objects": [],
        "old_objects": [],
    }

    old_date = datetime.now(timezone.utc) - timedelta(days=200)
    obj = {
        "Key": "old-file.txt",
        "Size": 5000,
        "StorageClass": "STANDARD",
        "LastModified": old_date,
    }

    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
    large_object_threshold = 100 * 1024 * 1024

    _process_object(obj, bucket_analysis, ninety_days_ago, large_object_threshold)

    assert_equal(len(bucket_analysis["old_objects"]), 1)
    old_obj = bucket_analysis["old_objects"][0]
    assert_equal(old_obj["key"], "old-file.txt")
    assert_equal(old_obj["size_bytes"], 5000)
    assert_equal(old_obj["storage_class"], "STANDARD")
    # Age should be approximately 200 days (allow small variance for test execution time)
    assert old_obj["age_days"] >= 199 and old_obj["age_days"] <= 201


def test_process_object_updates_oldest_and_newest():
    """Test _process_object tracks oldest and newest objects."""
    bucket_analysis = {
        "total_objects": 0,
        "total_size_bytes": 0,
        "storage_classes": defaultdict(lambda: {"count": 0, "size_bytes": 0}),
        "last_modified_oldest": None,
        "last_modified_newest": None,
        "large_objects": [],
        "old_objects": [],
    }

    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
    large_object_threshold = 100 * 1024 * 1024

    # First object
    obj1 = {
        "Key": "middle.txt",
        "Size": 1000,
        "StorageClass": "STANDARD",
        "LastModified": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }
    _process_object(obj1, bucket_analysis, ninety_days_ago, large_object_threshold)

    # Older object
    obj2 = {
        "Key": "oldest.txt",
        "Size": 1000,
        "StorageClass": "STANDARD",
        "LastModified": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    _process_object(obj2, bucket_analysis, ninety_days_ago, large_object_threshold)

    # Newer object
    obj3 = {
        "Key": "newest.txt",
        "Size": 1000,
        "StorageClass": "STANDARD",
        "LastModified": datetime(2024, 11, 1, tzinfo=timezone.utc),
    }
    _process_object(obj3, bucket_analysis, ninety_days_ago, large_object_threshold)

    assert_equal(bucket_analysis["last_modified_oldest"], datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert_equal(bucket_analysis["last_modified_newest"], datetime(2024, 11, 1, tzinfo=timezone.utc))
    assert_equal(bucket_analysis["total_objects"], 3)


def test_process_object_multiple_storage_classes():
    """Test _process_object handles multiple storage classes."""
    bucket_analysis = {
        "total_objects": 0,
        "total_size_bytes": 0,
        "storage_classes": defaultdict(lambda: {"count": 0, "size_bytes": 0}),
        "last_modified_oldest": None,
        "last_modified_newest": None,
        "large_objects": [],
        "old_objects": [],
    }

    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
    large_object_threshold = 100 * 1024 * 1024

    obj1 = {
        "Key": "standard.txt",
        "Size": 1000,
        "StorageClass": "STANDARD",
        "LastModified": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }
    obj2 = {
        "Key": "glacier.txt",
        "Size": 2000,
        "StorageClass": "GLACIER",
        "LastModified": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }
    obj3 = {
        "Key": "ia.txt",
        "Size": 3000,
        "StorageClass": "STANDARD_IA",
        "LastModified": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }

    _process_object(obj1, bucket_analysis, ninety_days_ago, large_object_threshold)
    _process_object(obj2, bucket_analysis, ninety_days_ago, large_object_threshold)
    _process_object(obj3, bucket_analysis, ninety_days_ago, large_object_threshold)

    assert_equal(bucket_analysis["storage_classes"]["STANDARD"]["count"], 1)
    assert_equal(bucket_analysis["storage_classes"]["STANDARD"]["size_bytes"], 1000)
    assert_equal(bucket_analysis["storage_classes"]["GLACIER"]["count"], 1)
    assert_equal(bucket_analysis["storage_classes"]["GLACIER"]["size_bytes"], 2000)
    assert_equal(bucket_analysis["storage_classes"]["STANDARD_IA"]["count"], 1)
    assert_equal(bucket_analysis["storage_classes"]["STANDARD_IA"]["size_bytes"], 3000)
    assert_equal(bucket_analysis["total_size_bytes"], 6000)
