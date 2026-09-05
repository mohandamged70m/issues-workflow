#!/usr/bin/env python3
"""Backwards-compat shim. Real code now lives in components: main.py, github.py, filters.py, notify.py, config.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import main

if __name__ == "__main__":
    sys.exit(main())
