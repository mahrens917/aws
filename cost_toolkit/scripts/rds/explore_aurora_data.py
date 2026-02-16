#!/usr/bin/env python3
"""Explore Aurora database data."""

import importlib
import os
from types import SimpleNamespace
from typing import Any

psycopg2: Any = None
PSYCOPG2_AVAILABLE = False
try:
    psycopg2 = importlib.import_module("psycopg2")
    PSYCOPG2_AVAILABLE = True
except ImportError:
    pass

from cost_toolkit.scripts.rds.db_inspection_common import (
    analyze_tables,
    get_database_size,
    list_databases,
    list_functions,
    list_schemas,
    list_tables,
    list_views,
    print_database_version_info,
)

# Constants
MAX_SAMPLE_COLUMNS = 5


def _require_env_var(name: str) -> str:  # pragma: no cover - trivial validation
    """Return a required environment variable or raise."""
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} is required to explore the Aurora cluster")
    return value.strip()


def _parse_required_port(name: str, strict: bool = True) -> int:  # pragma: no cover
    """Parse a required port environment variable."""
    raw_value = _require_env_var(name)
    try:
        return int(raw_value)
    except ValueError as exc:
        if not strict and name == "AURORA_PORT":
            return 5432
        raise RuntimeError(f"{name} must be a valid integer, got {raw_value!r}") from exc


def _load_aurora_settings():
    """Load Aurora connection settings from environment variables."""
    host = os.environ.get("AURORA_HOST")
    database = os.environ.get("AURORA_DATABASE")
    username = os.environ.get("AURORA_USERNAME")
    if host is None and (database or username):
        raise RuntimeError("AURORA_HOST is required to explore the Aurora cluster")
    if host is None:
        host = "localhost"
    if database is None:
        database = "aurora"
    if username is None:
        username = "admin"
    port = _parse_required_port("AURORA_PORT", strict=False)
    password = _require_env_var("AURORA_PASSWORD")
    return host, port, database, username, password


def _import_psycopg2():
    """Import psycopg2 using importlib to avoid module-level dependency issues."""
    try:
        return importlib.import_module("psycopg2")
    except ImportError:
        return None


def _resolve_psycopg2() -> Any:
    """Return a psycopg2-like module or None if unavailable."""
    if PSYCOPG2_AVAILABLE and psycopg2 is not None:
        return psycopg2
    if not PSYCOPG2_AVAILABLE:
        print("❌ psycopg2 module not found. Install with: pip install psycopg2-binary")
        return None
    module = _import_psycopg2()
    if module is None:
        return SimpleNamespace(
            Error=Exception,
            connect=lambda **kwargs: (_ for _ in ()).throw(Exception("psycopg2 not installed")),
        )
    return module


def explore_aurora_database():
    """Connect to the Aurora Serverless v2 cluster and explore user data"""
    psycopg2_local = _resolve_psycopg2()
    if psycopg2_local is None:
        return False

    try:
        host, port, database, username, password = _load_aurora_settings()
    except RuntimeError as exc:
        print(exc)
        return False
    if not password:
        print("❌ Aurora credentials not configured. Set AURORA_PASSWORD (and optionally AURORA_HOST/AURORA_DATABASE/AURORA_USERNAME).")
        return False

    print("🔍 Connecting to Aurora Serverless v2 cluster...")

    conn = None
    cursor = None
    try:
        conn = psycopg2_local.connect(
            host=host,
            port=port,
            database=database,
            user=username,
            password=password,
            connect_timeout=30,
        )
        print("✅ Connected successfully to Aurora Serverless v2!")
    except psycopg2_local.Error as e:
        print(f"❌ Connection failed: {e}")
        return False

    try:
        cursor = conn.cursor()

        print("\n📊 AURORA SERVERLESS V2 DATABASE INFORMATION:")
        print_database_version_info(cursor)

        list_databases(cursor)
        list_schemas(cursor)
        tables = list_tables(cursor)
        if not tables:
            print("   ❌ No user tables found - Aurora cluster appears to be empty")
        list_views(cursor)

        total_rows = analyze_tables(cursor, tables, MAX_SAMPLE_COLUMNS)

        get_database_size(cursor)

        list_functions(cursor)

        print("\n✅ Aurora Serverless v2 exploration completed!")

        if total_rows == 0:
            print("\n📈 SUMMARY:")
            print("   🚨 Aurora Serverless v2 cluster is EMPTY - no user data found")
            print("   💡 This means your original data is still in the restored RDS instance")
            print("\n🔄 NEXT STEPS:")
            print("   1. Your Aurora Serverless v2 cluster is empty")
            print("   2. Your original data is in the restored RDS instance")
            print("   3. We need the original password to access and migrate your data")
            print("   4. Once migrated, you can delete the expensive RDS instance")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
    return True


def main():  # pragma: no cover - thin CLI wrapper
    """Main function."""
    success = explore_aurora_database()
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
