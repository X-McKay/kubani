"""
Pytest configuration for kubani tests.

This file auto-imports all fixture modules and configures pytest markers.
"""

import asyncio

import pytest

# Auto-import all fixture modules
# TODO: Uncomment as fixtures are created in Tasks 3-5
# pytest_plugins = [
#     "tests.fixtures.config_fixtures",
#     "tests.fixtures.mcp_mocks",
#     "tests.fixtures.event_fixtures",
# ]


# Configure asyncio for async tests
@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default asyncio event loop policy."""
    return asyncio.get_event_loop_policy()


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
