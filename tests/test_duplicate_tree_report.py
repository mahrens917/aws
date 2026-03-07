"""Tests for duplicate_tree_report functionality."""

from duplicate_tree import DirectoryIndex, find_exact_duplicates
from tests.assertions import assert_equal


def _build_sample_index():
    index = DirectoryIndex()
    # Exact twin directories
    index.add_file("bucket", "dirA/file1.txt", 100, "aaa")
    index.add_file("bucket", "dirA/sub/file2.txt", 200, "bbb")
    index.add_file("bucket", "dirB/file1.txt", 100, "aaa")
    index.add_file("bucket", "dirB/sub/file2.txt", 200, "bbb")
    index.finalize()
    return index


def test_find_exact_duplicates_groups_identical_directories():
    """Test that exact duplicates are correctly identified."""
    index = _build_sample_index()
    clusters = find_exact_duplicates(index)

    match = next(
        (cluster for cluster in clusters if {("bucket", "dirA"), ("bucket", "dirB")}.issubset({node.path for node in cluster.nodes})),
        None,
    )
    assert match is not None
    assert_equal(match.nodes[0].total_files, 2)
    assert_equal(match.nodes[0].total_size, 300)


def test_directory_index_ignores_system_files():
    """Test that system files are properly ignored in indexing."""
    index = DirectoryIndex()
    index.add_file("bucket", "dirA/.DS_Store", 10, "ignored")
    index.add_file("bucket", "dirA/._.DS_Store", 10, "ignored2")
    index.add_file("bucket", "dirA/real.txt", 5, "keep")
    index.finalize()
    node = index.nodes[("bucket", "dirA")]
    assert_equal(node.direct_files, 1)
    assert_equal(node.direct_size, 5)
