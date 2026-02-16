"""
Cleanup temporary artifacts package.

Scan backup trees for disposable cache/temp artifacts and optionally delete them.
"""

from . import (
    args_parser,
    cache,
    categories,
    cli,
    config,
    core_scanner,
    db_loader,
    reports,
)
from .categories import Category, build_categories
from .core_scanner import Candidate, CandidateLoadError, CandidateLoadResult
from .db_loader import load_candidates_from_db

__all__ = [
    "Category",
    "Candidate",
    "CandidateLoadError",
    "CandidateLoadResult",
    "args_parser",
    "build_categories",
    "cache",
    "categories",
    "cli",
    "config",
    "core_scanner",
    "db_loader",
    "load_candidates_from_db",
    "reports",
]
