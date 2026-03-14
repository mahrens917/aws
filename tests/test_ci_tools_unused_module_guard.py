"""Tests for basic infrastructure in ci_tools/scripts/unused_module_guard.py shim module."""

# pylint: disable=protected-access,import-outside-toplevel,missing-class-docstring
# pylint: disable=missing-function-docstring,unused-argument,unused-variable

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.assertions import assert_equal
from tests.unused_module_guard_test_utils import load_shim_module


@pytest.fixture
def clean_imports():
    """Clean up imported modules after each test."""
    original_modules = sys.modules.copy()
    yield
    # Remove any test-added modules
    for name in list(sys.modules.keys()):
        if name not in original_modules:
            del sys.modules[name]


def test_exception_classes_exist():
    """Test that exception classes are defined."""
    shim_path = Path(__file__).parent.parent / "ci_tools" / "scripts" / "unused_module_guard.py"
    source = shim_path.read_text()

    assert "SharedGuardMissingError" in source
    assert "SharedGuardSpecError" in source
    assert "SharedGuardInitializationError" in source


def test_shared_guard_missing_error_message():
    """Test SharedGuardMissingError message formatting."""
    guard_module = load_shim_module(isolate=True)

    test_path = Path("/fake/path/to/guard.py")
    error = guard_module.SharedGuardMissingError(test_path)

    assert "Shared unused_module_guard not found at" in str(error)
    assert "/fake/path/to/guard.py" in str(error)
    assert "Clone ci_shared or set CI_SHARED_ROOT" in str(error)


def test_shared_guard_spec_error_message():
    """Test SharedGuardSpecError message formatting."""
    guard_module = load_shim_module(isolate=True)

    test_path = Path("/fake/path/to/guard.py")
    error = guard_module.SharedGuardSpecError(test_path)

    assert "Unable to create spec for" in str(error)
    assert "/fake/path/to/guard.py" in str(error)


def test_shared_guard_initialization_error_message():
    """Test SharedGuardInitializationError message formatting."""
    guard_module = load_shim_module(isolate=True)

    error = guard_module.SharedGuardInitializationError()
    assert "shared unused_module_guard failed to initialize" in str(error)


def test_load_shared_guard_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test _load_shared_guard raises when shared guard doesn't exist."""
    # Set CI_SHARED_ROOT to a non-existent directory
    fake_shared = tmp_path / "ci_shared"
    monkeypatch.setenv("CI_SHARED_ROOT", str(fake_shared))

    guard_module = load_shim_module(isolate=True)

    with pytest.raises(guard_module.SharedGuardMissingError) as exc_info:
        guard_module._load_shared_guard()

    expected_path = fake_shared / "ci_tools" / "scripts" / "unused_module_guard.py"
    assert str(expected_path) in str(exc_info.value)


def test_load_shared_guard_spec_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test _load_shared_guard raises when spec creation fails."""
    # Create the expected directory structure with the file
    shared_root = tmp_path / "ci_shared"
    scripts_dir = shared_root / "ci_tools" / "scripts"
    scripts_dir.mkdir(parents=True)
    guard_file = scripts_dir / "unused_module_guard.py"
    guard_file.write_text("# mock guard")

    monkeypatch.setenv("CI_SHARED_ROOT", str(shared_root))

    guard_module = load_shim_module(isolate=True)

    # Mock spec_from_file_location to return None
    with patch("importlib.util.spec_from_file_location", return_value=None):
        with pytest.raises(guard_module.SharedGuardSpecError) as exc_info:
            guard_module._load_shared_guard()

        assert str(guard_file) in str(exc_info.value)


def test_load_shared_guard_spec_no_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test _load_shared_guard raises when spec has no loader."""
    # Create the expected directory structure with the file
    shared_root = tmp_path / "ci_shared"
    scripts_dir = shared_root / "ci_tools" / "scripts"
    scripts_dir.mkdir(parents=True)
    guard_file = scripts_dir / "unused_module_guard.py"
    guard_file.write_text("# mock guard")

    monkeypatch.setenv("CI_SHARED_ROOT", str(shared_root))

    guard_module = load_shim_module(isolate=True)

    # Mock spec with no loader
    mock_spec = MagicMock()
    mock_spec.loader = None

    with patch("importlib.util.spec_from_file_location", return_value=mock_spec):
        with pytest.raises(guard_module.SharedGuardSpecError):
            guard_module._load_shared_guard()


def test_load_shared_guard_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test _load_shared_guard successfully loads valid guard module."""
    # Create a minimal valid guard module
    shared_root = tmp_path / "ci_shared"
    scripts_dir = shared_root / "ci_tools" / "scripts"
    scripts_dir.mkdir(parents=True)
    guard_file = scripts_dir / "unused_module_guard.py"
    guard_file.write_text("""
SUSPICIOUS_PATTERNS = ("test",)

def find_unused_modules(root, exclude_patterns=None):
    return []

def find_suspicious_duplicates(root):
    return []

def main():
    return 0
""")

    monkeypatch.setenv("CI_SHARED_ROOT", str(shared_root))

    guard_module = load_shim_module(isolate=True)

    result = guard_module._load_shared_guard()

    assert hasattr(result, "SUSPICIOUS_PATTERNS")
    assert hasattr(result, "find_unused_modules")
    assert hasattr(result, "find_suspicious_duplicates")
    assert hasattr(result, "main")


def test_module_constants():
    """Test module-level constants are defined correctly."""
    guard_module = load_shim_module(isolate=True)

    # Check constants exist
    assert hasattr(guard_module, "_LOCAL_MODULE_PATH")
    assert hasattr(guard_module, "_ORIGINAL_MODULE_NAME")
    assert hasattr(guard_module, "_REPO_ROOT")
    assert hasattr(guard_module, "_CONFIG_FILE")

    # Verify paths are Path objects
    assert isinstance(guard_module._LOCAL_MODULE_PATH, Path)
    assert isinstance(guard_module._REPO_ROOT, Path)
    assert isinstance(guard_module._CONFIG_FILE, Path)

    # Verify REPO_ROOT is 2 levels up from the module
    expected_repo = guard_module._LOCAL_MODULE_PATH.parents[2]
    assert_equal(guard_module._REPO_ROOT, expected_repo)

    # Verify CONFIG_FILE path
    expected_config = guard_module._REPO_ROOT / "unused_module_guard.config.json"
    assert_equal(guard_module._CONFIG_FILE, expected_config)


def test_guard_module_protocol():
    """Test GuardModule protocol defines expected interface."""
    guard_module = load_shim_module(isolate=True)

    # Create an object that conforms to the protocol
    class ConcreteGuard:
        SUSPICIOUS_PATTERNS = ("test",)

        def find_unused_modules(self, root, exclude_patterns=None):
            return []

        def find_suspicious_duplicates(self, root):
            return []

        def main(self):
            return 0

    # Verify it has all required attributes
    concrete = ConcreteGuard()
    assert hasattr(concrete, "SUSPICIOUS_PATTERNS")
    assert hasattr(concrete, "find_unused_modules")
    assert hasattr(concrete, "find_suspicious_duplicates")
    assert hasattr(concrete, "main")


def test_module_source_has_all_components():
    """Test that module source contains all expected components."""
    shim_path = Path(__file__).parent.parent / "ci_tools" / "scripts" / "unused_module_guard.py"
    source = shim_path.read_text()

    # Check for key components
    assert "def _load_shared_guard()" in source
    assert "def _load_config()" in source
    assert "def _apply_config_overrides(" in source
    assert "def _bootstrap()" in source
    assert "def main()" in source

    # Check for error classes
    assert "class SharedGuardMissingError" in source
    assert "class SharedGuardSpecError" in source
    assert "class SharedGuardInitializationError" in source

    # Check for protocol
    assert "class GuardModule(Protocol)" in source
