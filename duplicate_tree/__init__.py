"""Duplicate tree analysis package."""

from __future__ import annotations

from . import analysis, cache, cli, deletion, workflow
from .analysis import ScanFingerprint, build_directory_index_from_db
from .cache import load_cached_report, store_cached_report
from .cli import main, parse_args
from .core import DirectoryIndex, DuplicateCluster, find_exact_duplicates

__all__ = [
    "analysis",
    "cache",
    "cli",
    "deletion",
    "workflow",
    "ScanFingerprint",
    "build_directory_index_from_db",
    "load_cached_report",
    "store_cached_report",
    "main",
    "parse_args",
    "DirectoryIndex",
    "DuplicateCluster",
    "find_exact_duplicates",
]
