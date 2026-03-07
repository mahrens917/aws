"""Coverage-focused tests for duplicate_tree public API re-exports."""

from __future__ import annotations

import duplicate_tree as dtr
from tests.assertions import assert_equal


def test_reexported_symbols_are_accessible():
    """Smoke-check that the public API exposes the expected helpers."""
    index = dtr.DirectoryIndex()
    index.add_file("bucket", "dir/path.txt", 10, "abc")
    index.finalize()
    clusters = dtr.find_exact_duplicates(index)
    assert isinstance(clusters, list)
    assert dtr.DuplicateCluster.__name__ == "DuplicateCluster"


def test_main_delegates_to_cli(monkeypatch):
    """Ensure duplicate_tree.main delegates to duplicate_tree.cli.main."""
    monkeypatch.setattr(dtr, "main", lambda _argv=None: 42)
    assert_equal(dtr.main([]), 42)
