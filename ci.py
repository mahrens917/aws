#!/usr/bin/env python3
"""Project-specific CI entrypoint using shared ci_tools."""

from __future__ import annotations

import sys

from ci_tools.ci import main as ci_main


def run() -> int:
    """Run the CI script via ci_tools"""
    # Default to the CI script unless the caller overrides --command.
    argv = ["ci.py", "--command", "./scripts/ci.sh", *sys.argv[1:]]
    return ci_main(argv)


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(run())
