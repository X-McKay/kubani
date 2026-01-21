"""Shared test fixtures for kubani-dev tests."""

import re
from io import StringIO
from typing import Callable

import pytest
from rich.console import Console


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_pattern.sub("", text)


@pytest.fixture
def mock_console() -> Console:
    """
    Console that captures output for testing.

    The captured output can be accessed via console.captured attribute.
    """
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=80)
    # Attach StringIO for easy access
    console.captured = output  # type: ignore[attr-defined]
    return console


@pytest.fixture
def captured_output(mock_console: Console) -> Callable[[], str]:
    """
    Helper fixture to get captured console output with ANSI codes stripped.

    Usage:
        def test_something(mock_console, captured_output):
            # ... do something with mock_console
            output = captured_output()
            assert "expected" in output
    """

    def get_output() -> str:
        mock_console.captured.seek(0)  # type: ignore[attr-defined]
        raw_output = mock_console.captured.read()  # type: ignore[attr-defined]
        return strip_ansi(raw_output)

    return get_output


@pytest.fixture
def temp_skill_dir(tmp_path):
    """Create a temporary directory for skill files."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    return skill_dir
