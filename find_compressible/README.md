# find_compressible

Package for finding and compressing large locally downloaded objects.

## Modules

- `analysis.py` - File analysis and compression eligibility logic
- `cache.py` - Cache management for migration state database
- `cli.py` - CLI tool to locate and compress large locally downloaded objects
- `compression.py` - Compression operations using built-in lzma (XZ) support
- `reporting.py` - Reporting and output formatting for compression analysis

## Usage

Run the CLI to scan a directory for compressible files and optionally compress them with XZ.
