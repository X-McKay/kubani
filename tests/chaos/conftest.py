"""
Pytest configuration for chaos engineering tests.

This module:
- Registers the 'chaos' marker
- Provides shared fixtures
- Configures test collection for chaos tests
"""

import os

import pytest

from tests.chaos.framework import ChaosTestHelper


def pytest_configure(config):
    """Register chaos markers."""
    config.addinivalue_line(
        "markers",
        "chaos: mark test as a chaos engineering test (requires chaos-mesh)",
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow (may take several minutes)",
    )


def pytest_addoption(parser):
    """Add chaos test options."""
    parser.addoption(
        "--chaos",
        action="store_true",
        default=False,
        help="Run chaos engineering tests (requires chaos-mesh in cluster)",
    )
    parser.addoption(
        "--chaos-namespace",
        action="store",
        default="ai-agents",
        help="Namespace for chaos tests",
    )


def pytest_collection_modifyitems(config, items):
    """Skip chaos tests unless --chaos flag is provided."""
    if not config.getoption("--chaos"):
        skip_chaos = pytest.mark.skip(reason="Need --chaos option to run chaos tests")
        for item in items:
            if "chaos" in item.keywords:
                item.add_marker(skip_chaos)


@pytest.fixture(scope="session")
def chaos_helper():
    """Session-scoped chaos test helper."""
    namespace = os.environ.get("CHAOS_TEST_NAMESPACE", "ai-agents")
    return ChaosTestHelper(namespace=namespace)


@pytest.fixture
def ensure_chaos_mesh(chaos_helper):
    """Ensure chaos-mesh is installed before running test."""
    import asyncio

    async def check():
        return await chaos_helper.check_chaos_mesh_installed()

    installed = asyncio.get_event_loop().run_until_complete(check())
    if not installed:
        pytest.skip("chaos-mesh not installed in cluster")


@pytest.fixture
def ensure_agents_healthy(chaos_helper):
    """Ensure agents are healthy before running test."""
    import asyncio

    async def check():
        return await chaos_helper.check_all_agents_healthy()

    healthy = asyncio.get_event_loop().run_until_complete(check())
    if not healthy:
        pytest.skip("Agents not healthy - cannot run chaos test")
