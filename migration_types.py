"""Shared types for the migration system."""

from enum import Enum


class Phase(Enum):
    """Migration phases"""

    SCANNING = "scanning"
    GLACIER_RESTORE = "glacier_restore"
    GLACIER_WAIT = "glacier_wait"
    SYNCING = "syncing"
    VERIFYING = "verifying"
    DELETING = "deleting"
    COMPLETE = "complete"
