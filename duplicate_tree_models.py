"""Shared data models for duplicate_tree_report."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

PathTuple = Tuple[str, ...]
PROGRESS_MIN_INTERVAL = 5.0


class ChildSignatureMissingError(RuntimeError):
    """Raised when a directory node lacks a child signature during finalize."""

    def __init__(self, child_path: PathTuple) -> None:
        super().__init__(f"Child {child_path} missing signature during finalize.")


class FilesTableReadError(RuntimeError):
    """Raised when the SQLite files table cannot be read."""

    def __init__(self, db_path: str) -> None:
        super().__init__((f"Unable to read files table from {db_path!r}. " "Ensure migrate_v2 has initialized the database."))


@dataclass
class FileEntry:
    """Basic file metadata tracked for duplicate comparison."""

    name: str
    size: int
    checksum: str


@dataclass
class DirectoryNode:
    """Directory representation built from the metadata database."""

    path: PathTuple
    files: List[FileEntry] = field(default_factory=list)
    children: Set[PathTuple] = field(default_factory=set)
    direct_size: int = 0
    direct_files: int = 0
    total_size: int = 0
    total_files: int = 0
    signature: Optional[str] = None


@dataclass
class DuplicateCluster:
    """Exact duplicate cluster."""

    signature: str
    nodes: List[DirectoryNode]


class ProgressPrinter:
    """Simple in-place progress bar."""

    def __init__(self, total: int, label: str, width: int = 30):
        self.total = total
        self.label = label
        self.width = width
        self._last_update = 0.0
        self._finished = False

    def update(self, processed: int, force: bool = False):
        """Render the progress bar when enough time has elapsed."""
        now = time.time()
        if not force and processed < self.total and (now - self._last_update) < PROGRESS_MIN_INTERVAL:
            return
        self._last_update = now
        percent = (processed / self.total * 100.0) if self.total else 0.0
        filled = int(self.width * percent / 100.0) if self.total else 0
        bar_visual = "#" * filled + "-" * (self.width - filled)
        message = (
            f"\r{self.label}: [{bar_visual}] {percent:5.1f}% ({processed:,}/{self.total:,})"
            if self.total
            else f"\r{self.label}: {processed:,} entries processed"
        )
        print(message, end="", flush=True)
        if processed >= self.total:
            print()
            self._finished = True

    def finish(self, message: str | None = None):
        """Ensure the bar completes and optionally print a follow-up message."""
        if not self._finished:
            self.update(self.total, force=True)
        if message:
            print(message)


__all__ = [
    "ChildSignatureMissingError",
    "DirectoryNode",
    "DuplicateCluster",
    "FileEntry",
    "FilesTableReadError",
    "PathTuple",
    "ProgressPrinter",
    "PROGRESS_MIN_INTERVAL",
]
