"""
Report generation and output functions for cleanup_temp_artifacts.

Handles JSON and CSV report generation, candidate summarization, and display.
"""

from __future__ import annotations

import csv
import json
import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from cost_toolkit.common.format_utils import format_bytes, parse_size

if TYPE_CHECKING:
    from cleanup_temp_artifacts.core_scanner import Candidate

__all__ = [
    "format_bytes",
    "parse_size",
    "summarise",
    "write_reports",
    "order_candidates",
    "delete_paths",
    "print_candidates_report",
]


def summarise(candidates: list[Candidate]) -> list[tuple[str, int, int]]:
    """Return per-category summary of (name, count, total_size)."""
    summary: dict[str, tuple[int, int]] = {}
    for candidate in candidates:
        cat_name = candidate.category.name
        if cat_name in summary:
            count, total_size = summary[cat_name]
        else:
            count, total_size = 0, 0
        summary[candidate.category.name] = (count + 1, total_size + (candidate.size_bytes or 0))
    return sorted((name, cnt, size) for name, (cnt, size) in summary.items())


def write_reports(
    candidates: list[Candidate],
    *,
    json_path: Path | None,
    csv_path: Path | None,
) -> None:
    """Write candidate list to JSON and/or CSV report files."""
    rows = [
        {
            "path": str(c.path),
            "category": c.category.name,
            "size_bytes": c.size_bytes,
            "size_human": format_bytes(c.size_bytes, decimal_places=1, binary_units=False),
            "mtime": c.iso_mtime,
        }
        for c in candidates
    ]
    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(rows, indent=2))
    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["path", "category", "size_bytes", "size_human", "mtime"])
            writer.writeheader()
            writer.writerows(rows)


def order_candidates(
    candidates: list[Candidate],
    *,
    order: str,
) -> list[Candidate]:
    """Sort candidates by size or path based on order parameter."""
    if order == "size":
        return sorted(candidates, key=lambda c: c.size_bytes or 0, reverse=True)
    return sorted(candidates, key=lambda c: str(c.path))


def delete_paths(candidates: list[Candidate], *, root: Path) -> list[tuple[Candidate, Exception]]:
    """Delete files and directories, returning list of (candidate, error) for failures."""
    errors: list[tuple[Candidate, Exception]] = []
    for candidate in candidates:
        resolved = candidate.path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            errors.append((candidate, ValueError(f"{resolved} escapes root {root}")))
            continue
        try:
            if resolved.is_dir():
                shutil.rmtree(resolved)
            else:
                resolved.unlink()
        except (OSError, shutil.Error) as exc:
            logging.exception("Failed to delete %s", resolved)
            errors.append((candidate, exc))
        else:
            logging.info("Deleted %s", resolved)
    return errors


def print_candidates_report(
    candidates: list[Candidate],
    acted_upon: list[Candidate],
    base_path: Path,
) -> None:
    """Print candidate list and summary."""
    print(f"Identified {len(candidates)} candidate(s) (showing {len(acted_upon)}) under {base_path}:")
    for candidate in acted_upon:
        size_str = format_bytes(candidate.size_bytes, decimal_places=1, binary_units=False)
        print(f"- [{candidate.category.name}] {candidate.path} " f"(mtime {candidate.iso_mtime}, size {size_str})")

    summary = summarise(candidates)
    print("\nPer-category totals:")
    for name, count, size in summary:
        print(f"  {name:20} count={count:6d} " f"size={format_bytes(size, decimal_places=1, binary_units=False)}")
