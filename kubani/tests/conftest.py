"""
Pytest configuration for kubani tests.

This file auto-imports all fixture modules and configures pytest markers.
"""

import asyncio
import sys
from pathlib import Path

import pytest
import respx

# Auto-import all fixture modules
# Add tests directory to sys.path so fixtures can be imported
_tests_dir = Path(__file__).parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

from fixtures.config_fixtures import *  # noqa: F401, F403
from fixtures.event_fixtures import *  # noqa: F401, F403
from fixtures.mcp_mocks import *  # noqa: F401, F403


# Configure asyncio for async tests
@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default asyncio event loop policy."""
    return asyncio.get_event_loop_policy()


# Configure respx for HTTP mocking
@pytest.fixture
def respx_mock():
    """Provide a respx mock router for HTTP mocking."""
    with respx.mock:
        yield respx


# Register custom markers
def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test (requires external services)",
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow-running",
    )
