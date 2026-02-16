# cleanup_temp_artifacts

Scan trees for disposable cache and temp artifacts and optionally delete them.

## Modules

- `args_parser.py` - Argument parsing for the cleanup CLI
- `cache.py` - Cache management for loading and writing cached scan results
- `categories.py` - Category definitions and matcher functions for artifact types
- `cli.py` - Command-line interface and main entry point
- `config.py` - Configuration and path resolution
- `core_scanner.py` - Core scanning logic for candidate detection
- `db_loader.py` - Database loading and caching integration
- `reports.py` - Report generation for JSON, CSV, and display output

## Usage

Run the CLI to scan a database for temporary artifacts, review candidates, and clean up.
