"""
Pytest configuration and shared fixtures for Memory MCP tests.
"""

import pytest


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (requires services)"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
