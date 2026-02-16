"""Public API listing for duplicate_tree_cli."""

from __future__ import annotations

from duplicate_tree.analysis import ScanFingerprint as ScanFingerprint
from duplicate_tree.analysis import build_directory_index_from_db as build_directory_index_from_db
from duplicate_tree.cache import load_cached_report as load_cached_report
from duplicate_tree.cache import store_cached_report as store_cached_report
from duplicate_tree.cli import main as main
from duplicate_tree.cli import parse_args as parse_args

__all__ = [
    "ScanFingerprint",
    "build_directory_index_from_db",
    "load_cached_report",
    "main",
    "parse_args",
    "store_cached_report",
]
