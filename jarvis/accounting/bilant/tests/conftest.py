"""Pytest configuration for bilant schema tests.

This conftest MUST be loaded before any app modules are imported.
It patches psycopg2 and sets DATABASE_URL to avoid DB initialization
errors when importing accounting.bilant (which loads routes → database).

NOTE: pytest loads conftest.py files from outer directories first, so
a jarvis-level conftest.py handles the env setup. This file adds
path setup specific to schema tests.
"""
import sys
import os

# Ensure the jarvis/ source directory is on sys.path so 'accounting.*' resolves
_here = os.path.dirname(__file__)
_jarvis_src = os.path.abspath(os.path.join(_here, '..', '..', '..'))
if _jarvis_src not in sys.path:
    sys.path.insert(0, _jarvis_src)
