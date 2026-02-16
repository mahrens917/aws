"""Unit tests for migration_verify.py - Part 2: Checksum verification functions"""

import hashlib

import pytest

from migration_verify_checksums import (
    compute_etag,
    verify_files,
    verify_multipart_file,
    verify_single_file,
    verify_singlepart_file,
)
from tests.assertions import assert_equal


def test_verify_files_integration_with_valid_files(tmp_path):
    """Test verification of valid single-part files"""
    # Create test files
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"test content 1")
    file2 = tmp_path / "file2.txt"
    file2.write_bytes(b"test content 2")

    # Calculate MD5 hashes
    md5_1 = hashlib.md5(b"test content 1", usedforsecurity=False).hexdigest()
    md5_2 = hashlib.md5(b"test content 2", usedforsecurity=False).hexdigest()

    local_files = {"file1.txt": file1, "file2.txt": file2}
    expected_file_map = {
        "file1.txt": {"size": 14, "etag": md5_1},
        "file2.txt": {"size": 14, "etag": md5_2},
    }

    results = verify_files(
        local_files=local_files,
        expected_file_map=expected_file_map,
        expected_files=2,
        expected_size=28,
    )

    assert_equal(results["verified_count"], 2)
    assert_equal(results["size_verified"], 2)
    assert_equal(results["checksum_verified"], 2)
    assert_equal(results["total_bytes_verified"], 28)


def test_verify_files_raises_on_verification_errors(tmp_path):
    """Test verify_files raises exception on verification errors"""
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"content")

    local_files = {"file1.txt": file1}
    expected_file_map = {"file1.txt": {"size": 999, "etag": "abc123"}}

    with pytest.raises(ValueError) as exc_info:
        verify_files(
            local_files=local_files,
            expected_file_map=expected_file_map,
            expected_files=1,
            expected_size=999,
        )

    assert "Verification failed" in str(exc_info.value)


def test_verify_files_handles_large_files(tmp_path):
    """Test verification handles large files with chunked reading"""
    # Create a 20 MB file (will be read in 8 MB chunks)
    file1 = tmp_path / "large_file.txt"
    chunk_size = 8 * 1024 * 1024
    file1.write_bytes(b"x" * (chunk_size * 2 + 1000))

    md5_hash = hashlib.md5(usedforsecurity=False)
    with open(file1, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            md5_hash.update(chunk)
    computed_hash = md5_hash.hexdigest()

    local_files = {"large_file.txt": file1}
    expected_file_map = {"large_file.txt": {"size": chunk_size * 2 + 1000, "etag": computed_hash}}

    results = verify_files(
        local_files=local_files,
        expected_file_map=expected_file_map,
        expected_files=1,
        expected_size=chunk_size * 2 + 1000,
    )

    assert results["verified_count"] == 1
    assert results["checksum_verified"] == 1


def test_verify_single_file_with_size_mismatch(tmp_path):
    """Test verification fails on size mismatch"""
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"content")

    local_files = {"file1.txt": file1}
    expected_file_map = {"file1.txt": {"size": 999, "etag": "abc123"}}
    stats = {
        "verified_count": 0,
        "size_verified": 0,
        "checksum_verified": 0,
        "total_bytes_verified": 0,
        "verification_errors": [],
    }

    verify_single_file("file1.txt", local_files, expected_file_map, stats)

    assert len(stats["verification_errors"]) == 1
    assert "size mismatch" in stats["verification_errors"][0]
    assert stats["verified_count"] == 0


def test_verify_single_file_with_checksum_mismatch(tmp_path):
    """Test verification fails on checksum mismatch"""
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"content")

    wrong_hash = "0" * 32

    local_files = {"file1.txt": file1}
    expected_file_map = {"file1.txt": {"size": 7, "etag": wrong_hash}}
    stats = {
        "verified_count": 0,
        "size_verified": 0,
        "checksum_verified": 0,
        "total_bytes_verified": 0,
        "verification_errors": [],
    }

    verify_single_file("file1.txt", local_files, expected_file_map, stats)

    assert len(stats["verification_errors"]) == 1
    assert "checksum mismatch" in stats["verification_errors"][0]
    assert stats["size_verified"] == 1
    assert stats["verified_count"] == 0


def test_verify_multipart_file_with_hyphen_in_etag(tmp_path):
    """Test verification of multipart file (contains hyphen)"""
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"multipart content")

    local_files = {"file1.txt": file1}
    expected_file_map = {"file1.txt": {"size": 17, "etag": "abc123-2"}}  # Hyphen indicates multipart
    stats = {
        "verified_count": 0,
        "size_verified": 0,
        "checksum_verified": 0,
        "total_bytes_verified": 0,
        "verification_errors": [],
    }

    verify_single_file("file1.txt", local_files, expected_file_map, stats)

    # Multipart files are verified via SHA256 health check
    assert stats["verified_count"] == 1
    assert stats["checksum_verified"] == 1


def test_verify_multipart_file_handles_read_error(tmp_path):
    """Test multipart verification handles file read errors"""
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"test")

    # Make file unreadable
    file1.chmod(0o000)

    stats = {
        "verified_count": 0,
        "size_verified": 0,
        "checksum_verified": 0,
        "total_bytes_verified": 0,
        "verification_errors": [],
    }

    verify_multipart_file("file1.txt", file1, stats)

    # Restore permissions for cleanup
    file1.chmod(0o644)

    assert len(stats["verification_errors"]) == 1
    assert "file health check failed" in stats["verification_errors"][0]


def test_verify_singlepart_file_succeeds(tmp_path):
    """Test verification of single-part file succeeds"""
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"test")

    md5_hash = hashlib.md5(b"test", usedforsecurity=False).hexdigest()
    stats = {
        "verified_count": 0,
        "size_verified": 0,
        "checksum_verified": 0,
        "total_bytes_verified": 0,
        "verification_errors": [],
    }

    verify_singlepart_file("file1.txt", file1, md5_hash, stats)

    assert stats["verified_count"] == 1
    assert stats["checksum_verified"] == 1


def test_verify_singlepart_file_fails_on_checksum_mismatch(tmp_path):
    """Test single-part verification fails on checksum mismatch"""
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"test")

    wrong_hash = "0" * 32
    stats = {
        "verified_count": 0,
        "size_verified": 0,
        "checksum_verified": 0,
        "total_bytes_verified": 0,
        "verification_errors": [],
    }

    verify_singlepart_file("file1.txt", file1, wrong_hash, stats)

    assert len(stats["verification_errors"]) == 1
    assert "checksum mismatch" in stats["verification_errors"][0]
    assert stats["verified_count"] == 0


def test_verify_singlepart_file_handles_read_error(tmp_path):
    """Test single-part verification handles file read errors"""
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"test")

    # Make file unreadable (remove read permissions)
    file1.chmod(0o000)

    stats = {
        "verified_count": 0,
        "size_verified": 0,
        "checksum_verified": 0,
        "total_bytes_verified": 0,
        "verification_errors": [],
    }

    verify_singlepart_file("file1.txt", file1, "abc123", stats)

    # Restore permissions for cleanup
    file1.chmod(0o644)

    assert len(stats["verification_errors"]) == 1
    assert "checksum computation failed" in stats["verification_errors"][0]


def test_compute_etag_matches_valid_hash(tmp_path):
    """Test ETag computation matches provided hash"""
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"test content")

    md5_hash = hashlib.md5(b"test content", usedforsecurity=False).hexdigest()

    computed, is_match = compute_etag(file1, md5_hash)

    assert is_match is True
    assert computed == md5_hash


def test_compute_etag_detects_mismatch(tmp_path):
    """Test ETag computation detects mismatches"""
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"test content")

    wrong_hash = "0" * 32

    computed, is_match = compute_etag(file1, wrong_hash)

    assert is_match is False
    assert computed != wrong_hash


def test_compute_etag_strips_quotes_from_etag(tmp_path):
    """Test ETag computation handles quoted ETags from S3"""
    file1 = tmp_path / "file1.txt"
    file1.write_bytes(b"test")

    md5_hash = hashlib.md5(b"test", usedforsecurity=False).hexdigest()
    quoted_etag = f'"{md5_hash}"'

    _computed, is_match = compute_etag(file1, quoted_etag)

    assert is_match is True
