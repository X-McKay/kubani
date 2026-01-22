"""Test fixtures for agent framework."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_skills_dir():
    """Create a temporary skills directory with a test skill."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)

        # Create a test skill
        test_skill_dir = skills_dir / "test" / "example-skill"
        test_skill_dir.mkdir(parents=True)

        skill_content = """---
name: example-skill
version: "1.0.0"
description: A test skill for unit tests
category: test
---

# Example Skill

This is a test skill used for unit testing.

## Steps

1. Log the input context
2. Return a success message
"""
        (test_skill_dir / "SKILL.md").write_text(skill_content)

        yield skills_dir


@pytest.fixture
def temp_trace_dir():
    """Create a temporary trace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
