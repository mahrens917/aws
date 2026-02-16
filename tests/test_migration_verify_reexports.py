"""Tests ensuring the migration_verify module is removed."""

from __future__ import annotations

import importlib

import pytest


def test_migration_verify_removed():
    """Importing the old module should raise ImportError."""
    with pytest.raises(ImportError):
        importlib.import_module("migration_verify")
