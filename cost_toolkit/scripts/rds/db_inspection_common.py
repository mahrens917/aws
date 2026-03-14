#!/usr/bin/env python3
"""Common database inspection functions for PostgreSQL RDS instances."""


def list_databases(cursor):
    """List all non-template databases.

    Args:
        cursor: psycopg2 cursor object
    """
    print("\n🗄️  AVAILABLE DATABASES:")
    cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname;")
    databases = cursor.fetchall()
    for db in databases:
        print(f"   • {db[0]}")


def list_schemas(cursor):
    """List all user schemas.

    Args:
        cursor: psycopg2 cursor object
    """
    print("\n📁 USER SCHEMAS:")
    cursor.execute("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
        ORDER BY schema_name;
    """)
    schemas = cursor.fetchall()
    for schema in schemas:
        print(f"   • {schema[0]}")


def list_tables(cursor):
    """List all user tables.

    Args:
        cursor: psycopg2 cursor object

    Returns:
        List of tuples containing (schema_name, table_name, owner)
    """
    print("\n📋 USER TABLES:")
    cursor.execute("""
        SELECT schemaname, tablename, tableowner
        FROM pg_tables
        WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
        ORDER BY schemaname, tablename;
    """)
    tables = cursor.fetchall()

    if tables:
        for table in tables:
            print(f"   • {table[0]}.{table[1]} (owner: {table[2]})")
    else:
        print("   No user tables found")

    return tables


def list_views(cursor):
    """List all user views.

    Args:
        cursor: psycopg2 cursor object
    """
    print("\n👁️  USER VIEWS:")
    cursor.execute("""
        SELECT schemaname, viewname, viewowner
        FROM pg_views
        WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
        ORDER BY schemaname, viewname;
    """)
    views = cursor.fetchall()

    if views:
        for view in views:
            print(f"   • {view[0]}.{view[1]} (owner: {view[2]})")
    else:
        print("   No user views found")


def get_table_columns(cursor, schema_name, table_name, max_display=5):
    """Get and display column information for a table.

    Args:
        cursor: psycopg2 cursor object
        schema_name: Schema name
        table_name: Table name
        max_display: Maximum number of columns to display before truncating

    Returns:
        List of tuples containing column information
    """
    cursor.execute(f"""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = '{schema_name}' AND table_name = '{table_name}'
        ORDER BY ordinal_position;
    """)
    columns = cursor.fetchall()
    print(f"     Columns ({len(columns)}):")
    for col in columns[:max_display]:
        nullable = "NULL" if col[2] == "YES" else "NOT NULL"
        default = f" DEFAULT {col[3]}" if col[3] else ""
        print(f"       - {col[0]} ({col[1]}) {nullable}{default}")
    if len(columns) > max_display:
        print(f"       ... and {len(columns) - max_display} more columns")
    return columns


def show_sample_data(cursor, schema_name, table_name, limit=2):
    """Show sample data from a table.

    Args:
        cursor: psycopg2 cursor object
        schema_name: Schema name
        table_name: Table name
        limit: Number of sample rows to display
    """
    cursor.execute(f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT {limit};')
    sample_data = cursor.fetchall()
    if sample_data:
        print("     Sample data:")
        col_names = [desc[0] for desc in cursor.description]
        for i, row in enumerate(sample_data, 1):
            print(f"       Row {i}: {dict(zip(col_names, row))}")
    print()


def get_database_version_info(cursor):
    """Get PostgreSQL version and current database information.

    Args:
        cursor: psycopg2 cursor object

    Returns:
        Tuple of (version_string, current_database_name)
    """
    cursor.execute("SELECT version();")
    version = cursor.fetchone()[0]

    cursor.execute("SELECT current_database();")
    current_db = cursor.fetchone()[0]

    return version, current_db


def print_database_version_info(cursor):
    """Print PostgreSQL version and current database information.

    Args:
        cursor: psycopg2 cursor object
    """
    print("\n📊 DATABASE INFORMATION:")
    version, current_db = get_database_version_info(cursor)
    print(f"   PostgreSQL Version: {version}")
    print(f"   Current Database: {current_db}")


def list_functions(cursor):
    """List all user functions and procedures.

    Args:
        cursor: psycopg2 cursor object
    """
    print("\n⚙️  USER FUNCTIONS:")
    cursor.execute("""
        SELECT routine_schema, routine_name, routine_type
        FROM information_schema.routines
        WHERE routine_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY routine_schema, routine_name;
    """)
    functions = cursor.fetchall()

    if functions:
        for func in functions:
            print(f"   • {func[0]}.{func[1]} ({func[2]})")
    else:
        print("   No user functions found")


def get_database_size(cursor):
    """Get and display current database size.

    Args:
        cursor: psycopg2 cursor object

    Returns:
        String representation of database size
    """
    print("\n💾 DATABASE SIZE:")
    cursor.execute("SELECT pg_size_pretty(pg_database_size(current_database())) as size;")
    db_size = cursor.fetchone()[0]
    print(f"   Database Size: {db_size}")
    return db_size


def analyze_tables(cursor, tables, max_sample_columns=5):
    """Analyze table data by counting rows and showing samples.

    Args:
        cursor: psycopg2 cursor object
        tables: List of tuples containing (schema_name, table_name, owner)
        max_sample_columns: Maximum number of columns to display in table structure

    Returns:
        Total number of rows across all tables
    """
    if not tables:
        return 0

    print("\n📊 TABLE DATA ANALYSIS:")
    total_rows = 0

    for schema_name, table_name, _owner in tables:
        try:
            cursor.execute(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}";')
            count = cursor.fetchone()[0]
            total_rows += count
            print(f"   • {schema_name}.{table_name}: {count:,} rows")

            if count > 0:
                get_table_columns(cursor, schema_name, table_name, max_sample_columns)
                show_sample_data(cursor, schema_name, table_name)

        except (OSError, RuntimeError) as e:
            print(f"   • {schema_name}.{table_name}: Error reading - {e}")

    print("\n📈 SUMMARY:")
    print(f"   Total Tables: {len(tables)}")
    print(f"   Total Rows: {total_rows:,}")
    return total_rows


if __name__ == "__main__":
    # This is a utility module - import its functions from other scripts
    pass
