"""Cache management for migration state database."""

from __future__ import annotations

import sys
from pathlib import Path

from cost_toolkit.common.cli_utils import handle_state_db_reset
from state_db_admin import reseed_state_db_from_local_drive

# Ensure the repository root is importable for state_db_admin import.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

__all__ = ["handle_state_db_reset", "reseed_state_db_from_local_drive"]
