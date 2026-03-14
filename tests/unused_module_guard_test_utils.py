"""Shared helpers for unused_module_guard shim tests."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import ci_tools.scripts.unused_module_guard as guard_module


def load_shim_module(isolate: bool = False):
    """
    Load the shim module directly from its source file.

    Args:
        isolate: If True, load in isolation without running bootstrap.
    """
    shim_path = Path(__file__).parent.parent / "ci_tools" / "scripts" / "unused_module_guard.py"

    if isolate:
        # Load module with a temporary fake shared guard to allow bootstrap to succeed
        # This avoids needing exec() to partially load the module
        with tempfile.TemporaryDirectory() as tmpdir:
            shared_root = Path(tmpdir) / "ci_shared"
            scripts_dir = shared_root / "ci_tools" / "scripts"
            scripts_dir.mkdir(parents=True)

            guard_file = scripts_dir / "unused_module_guard.py"
            guard_file.write_text("""
SUSPICIOUS_PATTERNS = ()

def find_unused_modules(root, exclude_patterns=None):
    return []

def find_suspicious_duplicates(root):
    return []
""")

            with patch.dict(os.environ, {"CI_SHARED_ROOT": str(shared_root)}):
                spec = importlib.util.spec_from_file_location("_test_shim_isolated", shim_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Cannot load {shim_path}")

                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module

                try:
                    spec.loader.exec_module(module)
                except AttributeError as exc:
                    if "main" not in str(exc):
                        raise

                return module

    return guard_module


@pytest.fixture
def backup_guard_config():
    """Backup and restore the unused_module_guard config file."""
    config_file = Path(__file__).parent.parent / "unused_module_guard.config.json"
    original_content = config_file.read_text() if config_file.exists() else None

    yield

    if original_content is not None:
        config_file.write_text(original_content, encoding="utf-8")
    elif config_file.exists():
        config_file.unlink()
