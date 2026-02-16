#!/usr/bin/env python3
"""Explore RDS user data and credentials."""


import importlib
import os
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


def _require_env_var(name: str) -> str:
    """Return a required environment variable or raise."""
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} is required to explore restored RDS data")
    return value.strip()


def _parse_required_port(name: str) -> int:
    """Parse a required port environment variable."""
    raw_value = _require_env_var(name)
    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a valid integer, got {raw_value!r}") from exc


def _split_required_list(name: str) -> list[str]:
    """Split a required comma-separated environment variable into values."""
    raw_value = _require_env_var(name)
    values = [value.strip() for value in raw_value.split(",") if value.strip()]
    if not values:
        raise RuntimeError(f"{name} must contain at least one value")
    return values


def _load_restored_db_settings():
    """Load restored DB connection settings from environment variables."""
    host = _require_env_var("RESTORED_DB_HOST")
    port = _parse_required_port("RESTORED_DB_PORT")
    username = _require_env_var("RESTORED_DB_USERNAME")
    databases = _split_required_list("RESTORED_DB_NAMES")
    passwords = _split_required_list("RESTORED_DB_PASSWORDS")

    return host, port, databases, username, passwords


def _try_database_connection(host, port, possible_databases, username, possible_passwords):
    """Try connecting with different database and password combinations"""
    for db_name in possible_databases:
        for password in possible_passwords:
            try:
                print(f"   Trying database='{db_name}' with password='{password[:10]}...'")
                conn = psycopg2.connect(
                    host=host,
                    port=port,
                    database=db_name,
                    user=username,
                    password=password,
                    connect_timeout=15,
                )
                print("✅ Connected successfully!")
                print(f"   Database: {db_name}")
                print(f"   Password: {password[:10]}...")
            except psycopg2.Error as e:
                print(f"   ❌ Failed: {str(e)[:80]}...")
                continue
            else:
                return conn, db_name
    return None, None


def explore_restored_database():
    """Connect to the restored RDS instance and explore user data"""
    if not PSYCOPG2_AVAILABLE:
        print("❌ psycopg2 module not found. Install with: pip install psycopg2-binary")
        return False

    host, port, possible_databases, username, possible_passwords = _load_restored_db_settings()

    print("🔍 Connecting to restored RDS instance (contains your original data)...")

    conn, _database = _try_database_connection(host, port, possible_databases, username, possible_passwords)

    if not conn:
        print("❌ Could not connect with any combination")
        print("Please check the database configuration")
        return False

    cursor = conn.cursor()

    print("\n📊 DATABASE INFORMATION:")
    print_database_version_info(cursor)

    list_databases(cursor)
    list_schemas(cursor)
    tables = list_tables(cursor)
    list_views(cursor)
    analyze_tables(cursor, tables, MAX_SAMPLE_COLUMNS)

    get_database_size(cursor)

    list_functions(cursor)

    cursor.close()
    conn.close()

    print("\n✅ Database exploration completed!")
    return True


def main():
    """Main function."""
    success = explore_restored_database()
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
