"""Tests for bootstrap and integration in ci_tools/scripts/unused_module_guard.py."""

# pylint: disable=missing-class-docstring,missing-function-docstring,too-few-public-methods,protected-access,import-outside-toplevel,unused-argument

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.assertions import assert_equal
from tests.unused_module_guard_test_utils import load_shim_module


def test_bootstrap_function_loads_config(tmp_path: Path):
    """Test _bootstrap function loads config and applies overrides."""
    # Create a minimal valid guard module
    shared_root = tmp_path / "ci_shared"
    scripts_dir = shared_root / "ci_tools" / "scripts"
    scripts_dir.mkdir(parents=True)
    guard_file = scripts_dir / "unused_module_guard.py"
    guard_file.write_text("""
SUSPICIOUS_PATTERNS = ("test", "_v2")

def find_unused_modules(root, exclude_patterns=None):
    return []

def find_suspicious_duplicates(root):
    return []

def main():
    return 0
""")

    # Create config file
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"exclude_patterns": ["tests/"], "suspicious_allow_patterns": ["_v2"]}))

    # Load isolated module
    guard_module = load_shim_module(isolate=True)
    guard_module._CONFIG_FILE = config_file  # type: ignore[attr-defined]

    # Mock environment
    with patch.dict("os.environ", {"CI_SHARED_ROOT": str(shared_root)}):
        result = guard_module._bootstrap()

    # Should return a callable
    assert callable(result)


def test_main_without_initialization():
    """Test main() raises when _DELEGATED_MAIN is None."""
    guard_module = load_shim_module(isolate=True)

    # _DELEGATED_MAIN should be None since we didn't bootstrap
    with pytest.raises(guard_module.SharedGuardInitializationError) as exc_info:
        guard_module.main()

    assert "shared unused_module_guard failed to initialize" in str(exc_info.value)


def test_bootstrapped_module_has_main():
    """Test that bootstrapped module has main function."""
    import ci_tools.scripts.unused_module_guard as guard_module

    # Should have main function
    assert hasattr(guard_module, "main")
    assert callable(guard_module.main)


def test_apply_config_only_extra_excludes():
    """Test applying config with only extra excludes."""
    guard_module = load_shim_module(isolate=True)

    class SimpleGuard:
        SUSPICIOUS_PATTERNS = ("test",)
        call_log = []

        def find_unused_modules(self, root, exclude_patterns=None):
            self.call_log.append(exclude_patterns)
            return []

    guard = SimpleGuard()
    guard_module._apply_config_overrides(guard, ["build/"], [], [])

    # Call the function
    guard.find_unused_modules("/root")

    # Verify it was called with our patterns
    assert len(guard.call_log) == 1
    assert "build/" in guard.call_log[0]


def test_apply_config_only_allowed_patterns():
    """Test applying config with only allowed patterns."""
    guard_module = load_shim_module(isolate=True)

    class SimpleGuard:
        SUSPICIOUS_PATTERNS = ("test", "_backup", "other")

    guard = SimpleGuard()
    guard_module._apply_config_overrides(guard, [], ["_backup"], [])

    # Should filter out _backup
    assert "_backup" not in guard.SUSPICIOUS_PATTERNS
    assert "test" in guard.SUSPICIOUS_PATTERNS
    assert "other" in guard.SUSPICIOUS_PATTERNS


def test_apply_config_only_duplicate_excludes():
    """Test applying config with only duplicate excludes."""
    guard_module = load_shim_module(isolate=True)

    class SimpleGuard:
        SUSPICIOUS_PATTERNS = ("test",)

        def find_suspicious_duplicates(self, root):
            return [
                ("/path/migrations/file.py", "dup"),
                ("/path/src/file.py", "dup"),
            ]

    guard = SimpleGuard()
    guard_module._apply_config_overrides(guard, [], [], ["migrations/"])

    results = guard.find_suspicious_duplicates("/root")

    # Should filter out migrations
    assert len(results) == 1
    assert "src" in str(results[0])


def test_apply_config_overrides_no_duplicates_function():
    """Test _apply_config_overrides when find_suspicious_duplicates missing."""
    from unittest.mock import MagicMock

    guard_module = load_shim_module(isolate=True)

    # Create a mock without find_suspicious_duplicates
    mock_guard = MagicMock()
    mock_guard.SUSPICIOUS_PATTERNS = ("test",)
    mock_guard.find_unused_modules = MagicMock(return_value=[])
    delattr(mock_guard, "find_suspicious_duplicates")

    # Should not raise an error
    guard_module._apply_config_overrides(mock_guard, [], [], ["migrations/"])


def test_load_shared_guard_uses_env_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test _load_shared_guard respects CI_SHARED_ROOT environment variable."""
    # Create guard at custom location
    custom_shared = tmp_path / "custom_location"
    scripts_dir = custom_shared / "ci_tools" / "scripts"
    scripts_dir.mkdir(parents=True)
    guard_file = scripts_dir / "unused_module_guard.py"
    guard_file.write_text("# custom guard")

    monkeypatch.setenv("CI_SHARED_ROOT", str(custom_shared))

    guard_module = load_shim_module(isolate=True)

    # Should look in the custom location
    with pytest.raises(guard_module.SharedGuardSpecError):
        # Will fail at spec creation but proves it found the file
        with patch("importlib.util.spec_from_file_location", return_value=None):
            guard_module._load_shared_guard()


def test_load_shared_guard_default_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test _load_shared_guard uses home directory by default."""
    # Set HOME to a fake directory
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    # Remove CI_SHARED_ROOT if set
    monkeypatch.delenv("CI_SHARED_ROOT", raising=False)

    guard_module = load_shim_module(isolate=True)

    # Should look in home directory
    expected_path = fake_home / "projects" / "ci_shared" / "ci_tools" / "scripts" / "unused_module_guard.py"

    with pytest.raises(guard_module.SharedGuardMissingError) as exc_info:
        guard_module._load_shared_guard()

    assert str(expected_path) in str(exc_info.value)


def test_apply_config_overrides_all_options():
    """Test _apply_config_overrides with all options enabled."""
    guard_module = load_shim_module(isolate=True)

    class MockGuard:
        SUSPICIOUS_PATTERNS = ["test", "example", "_v2", "_backup"]

        def find_unused_modules(self, root, exclude_patterns=None):
            return {"exclude_patterns": exclude_patterns}

        def find_suspicious_duplicates(self, root):
            return [
                ("/path/to/tests/file.py", "duplicate"),
                ("/path/to/normal/file.py", "duplicate"),
            ]

    mock_shared_guard = MockGuard()

    guard_module._apply_config_overrides(
        mock_shared_guard,
        ["tests/"],
        ["_v2"],
        ["migrations/"],
    )

    # Check SUSPICIOUS_PATTERNS filtered
    assert "_v2" not in mock_shared_guard.SUSPICIOUS_PATTERNS

    # Check find_unused_modules wrapped
    result = mock_shared_guard.find_unused_modules("/fake/root")
    assert "tests/" in result["exclude_patterns"]  # type: ignore[operator]

    # Check find_suspicious_duplicates wrapped
    results = mock_shared_guard.find_suspicious_duplicates("/fake/root")
    assert_equal(len(results), 1)
    assert "/path/to/normal/file.py" in str(results[0])
