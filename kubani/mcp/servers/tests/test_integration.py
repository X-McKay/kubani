"""
Integration tests for MCP servers.

Tests that verify all servers can be imported and their tools match contracts.

Note: These tests require server packages to be installed. They are designed
to run in the server-specific environments (e.g., kubani/mcp/servers/discord/.venv)
or when servers are installed in the main environment.

To run these tests properly from a server environment:
    cd kubani/mcp/servers/temporal
    uv run pytest ../tests/test_integration.py::TestServerImports::test_import_temporal -v
"""

import pytest

# Check which servers are available
SERVERS_AVAILABLE = {}

try:
    from discord_mcp.server import create_server as create_discord

    SERVERS_AVAILABLE["discord"] = create_discord
except ImportError:
    SERVERS_AVAILABLE["discord"] = None

try:
    from temporal_mcp.server import create_server as create_temporal

    SERVERS_AVAILABLE["temporal"] = create_temporal
except ImportError:
    SERVERS_AVAILABLE["temporal"] = None

try:
    from qdrant_mcp.server import create_server as create_qdrant

    SERVERS_AVAILABLE["qdrant"] = create_qdrant
except ImportError:
    SERVERS_AVAILABLE["qdrant"] = None

try:
    from memory_mcp.server import create_server as create_memory

    SERVERS_AVAILABLE["memory"] = create_memory
except ImportError:
    SERVERS_AVAILABLE["memory"] = None

try:
    from skills_mcp.server import create_server as create_skills

    SERVERS_AVAILABLE["skills"] = create_skills
except ImportError:
    SERVERS_AVAILABLE["skills"] = None


def skip_if_unavailable(server_name: str):
    """Decorator to skip test if server is not available."""
    return pytest.mark.skipif(
        SERVERS_AVAILABLE.get(server_name) is None,
        reason=f"{server_name}_mcp not installed",
    )


class TestServerImports:
    """Test that all servers can be imported and created."""

    @skip_if_unavailable("discord")
    def test_import_discord(self):
        mcp = SERVERS_AVAILABLE["discord"]()
        assert mcp.name == "Discord MCP Server"

    @skip_if_unavailable("temporal")
    def test_import_temporal(self):
        mcp = SERVERS_AVAILABLE["temporal"]()
        assert mcp.name == "Temporal MCP Server"

    @skip_if_unavailable("qdrant")
    def test_import_qdrant(self):
        mcp = SERVERS_AVAILABLE["qdrant"]()
        assert mcp.name == "Qdrant MCP Server"

    @skip_if_unavailable("memory")
    def test_import_memory(self):
        mcp = SERVERS_AVAILABLE["memory"]()
        assert mcp.name == "Memory MCP Server"

    @skip_if_unavailable("skills")
    def test_import_skills(self):
        mcp = SERVERS_AVAILABLE["skills"]()
        assert mcp.name == "Skills MCP Server"


class TestServerToolCounts:
    """Verify servers have expected number of tools."""

    def _count_tools(self, mcp) -> int:
        """Count tools registered on the MCP server."""
        if hasattr(mcp, "_tool_manager"):
            manager = mcp._tool_manager
            if hasattr(manager, "_tools"):
                return len(manager._tools)
        return 0

    @skip_if_unavailable("discord")
    def test_discord_has_tools(self):
        mcp = SERVERS_AVAILABLE["discord"]()
        count = self._count_tools(mcp)
        # Discord has 17 tools
        assert count >= 15, f"Expected at least 15 Discord tools, got {count}"

    @skip_if_unavailable("temporal")
    def test_temporal_has_tools(self):
        mcp = SERVERS_AVAILABLE["temporal"]()
        count = self._count_tools(mcp)
        # Temporal has 14 tools
        assert count >= 12, f"Expected at least 12 Temporal tools, got {count}"

    @skip_if_unavailable("qdrant")
    def test_qdrant_has_tools(self):
        mcp = SERVERS_AVAILABLE["qdrant"]()
        count = self._count_tools(mcp)
        # Qdrant has 10 tools
        assert count >= 8, f"Expected at least 8 Qdrant tools, got {count}"

    @skip_if_unavailable("memory")
    def test_memory_has_tools(self):
        mcp = SERVERS_AVAILABLE["memory"]()
        count = self._count_tools(mcp)
        # Memory has 20 tools
        assert count >= 15, f"Expected at least 15 Memory tools, got {count}"

    @skip_if_unavailable("skills")
    def test_skills_has_tools(self):
        mcp = SERVERS_AVAILABLE["skills"]()
        count = self._count_tools(mcp)
        # Skills has 6 tools
        assert count >= 5, f"Expected at least 5 Skills tools, got {count}"


class TestContractToolsExist:
    """Verify contracted tools exist in each server."""

    def _get_tool_names(self, mcp) -> set[str]:
        """Get tool names from MCP server."""
        if hasattr(mcp, "_tool_manager"):
            manager = mcp._tool_manager
            if hasattr(manager, "_tools"):
                return set(manager._tools.keys())
        return set()

    @skip_if_unavailable("discord")
    def test_discord_contract_tools(self):
        from kubani.mcp.servers.tests.contracts import DISCORD_CONTRACT

        mcp = SERVERS_AVAILABLE["discord"]()
        actual_tools = self._get_tool_names(mcp)
        expected_tools = set(DISCORD_CONTRACT.tool_names)

        missing = expected_tools - actual_tools
        assert not missing, f"Discord missing tools: {missing}"

    @skip_if_unavailable("temporal")
    def test_temporal_contract_tools(self):
        from kubani.mcp.servers.tests.contracts import TEMPORAL_CONTRACT

        mcp = SERVERS_AVAILABLE["temporal"]()
        actual_tools = self._get_tool_names(mcp)
        expected_tools = set(TEMPORAL_CONTRACT.tool_names)

        missing = expected_tools - actual_tools
        assert not missing, f"Temporal missing tools: {missing}"

    @skip_if_unavailable("qdrant")
    def test_qdrant_contract_tools(self):
        from kubani.mcp.servers.tests.contracts import QDRANT_CONTRACT

        mcp = SERVERS_AVAILABLE["qdrant"]()
        actual_tools = self._get_tool_names(mcp)
        expected_tools = set(QDRANT_CONTRACT.tool_names)

        missing = expected_tools - actual_tools
        assert not missing, f"Qdrant missing tools: {missing}"

    @skip_if_unavailable("memory")
    def test_memory_contract_tools(self):
        from kubani.mcp.servers.tests.contracts import MEMORY_CONTRACT

        mcp = SERVERS_AVAILABLE["memory"]()
        actual_tools = self._get_tool_names(mcp)
        expected_tools = set(MEMORY_CONTRACT.tool_names)

        missing = expected_tools - actual_tools
        assert not missing, f"Memory missing tools: {missing}"

    @skip_if_unavailable("skills")
    def test_skills_contract_tools(self):
        from kubani.mcp.servers.tests.contracts import SKILLS_CONTRACT

        mcp = SERVERS_AVAILABLE["skills"]()
        actual_tools = self._get_tool_names(mcp)
        expected_tools = set(SKILLS_CONTRACT.tool_names)

        missing = expected_tools - actual_tools
        assert not missing, f"Skills missing tools: {missing}"
