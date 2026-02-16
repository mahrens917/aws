"""Public API for duplicate tree detection plus CLI shim."""

from __future__ import annotations

import sys

from duplicate_tree.core import (
    DirectoryIndex,
    DuplicateCluster,
    find_exact_duplicates,
)

__all__ = [
    "DirectoryIndex",
    "DuplicateCluster",
    "find_exact_duplicates",
]


def main(argv=None) -> int:
    """Route to the CLI implementation."""
    if "duplicate_tree_cli" in sys.modules:
        cli = sys.modules["duplicate_tree_cli"]
    else:
        from duplicate_tree import cli

    return cli.main(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
