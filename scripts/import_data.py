#!/usr/bin/env python
"""
Import MLB data from /data directory into database.

Usage:
    python scripts/import_data.py

Or from project root:
    python -m scripts.import_data

Data files (CSV/JSON) should be placed in the project's data/ directory.
File format to be defined when data is uploaded.
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# TODO: Implement when data format is defined
# - Scan data/ for *.csv, *.json
# - Parse and validate
# - Load into MLBPlayer, MLBPlayerSeason, etc.
# - Use django.setup() and Django ORM if needed

if __name__ == '__main__':
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    if not os.path.exists(data_dir):
        print(f"Data directory not found: {data_dir}")
        sys.exit(1)
    files = [f for f in os.listdir(data_dir) if f.endswith(('.csv', '.json'))]
    if not files:
        print(f"No CSV/JSON files found in {data_dir}. Add data files and run again.")
        sys.exit(0)
    print(f"Found {len(files)} file(s): {files}")
    print("Import logic not yet implemented. Define data format when files are uploaded.")
