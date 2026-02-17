"""Shared test fixtures for Nexus tests."""

from __future__ import annotations

import sys
import os

# Ensure the kubani package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
