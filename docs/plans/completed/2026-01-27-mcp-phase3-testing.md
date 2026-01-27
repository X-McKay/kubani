# Phase 3: Unified Testing Harness

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a contract-based testing framework for all MCP servers with mocks and integration tests.

**Architecture:** Testing utilities in `kubani/framework/mcp/server/testing/` that provide reusable harnesses, contracts, and mocks for testing MCP servers.

**Tech Stack:** pytest, pytest-asyncio, pydantic

**Prerequisites:** Complete Phase 1 and Phase 2

---

## Task 1: Create Testing Module Structure

**Files:**
- Create: `kubani/framework/mcp/server/testing/__init__.py`
- Create: `kubani/framework/mcp/server/testing/contracts.py`
- Create: `kubani/framework/mcp/server/testing/harness.py`
- Create: `kubani/framework/mcp/server/testing/mocks.py`

**Step 1: Create testing/__init__.py**

```python
"""
Testing utilities for MCP servers.

Provides:
- Contract definitions for server validation
- Test harness for running MCP tests
- Mock backends for unit testing
"""

from kubani.framework.mcp.server.testing.contracts import (
    MCPContract,
    ToolContract,
)
from kubani.framework.mcp.server.testing.harness import (
    MCPTestHarness,
    ValidationResult,
)
from kubani.framework.mcp.server.testing.mocks import (
    MockQdrant,
    MockRedis,
    MockTemporalClient,
)

__all__ = [
    # Contracts
    "MCPContract",
    "ToolContract",
    # Harness
    "MCPTestHarness",
    "ValidationResult",
    # Mocks
    "MockQdrant",
    "MockRedis",
    "MockTemporalClient",
]
```

**Step 2: Commit**

```bash
git add kubani/framework/mcp/server/testing/
git commit -m "feat(mcp): scaffold testing utilities module

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Implement Contract Definitions

**Files:**
- Create: `kubani/framework/mcp/server/testing/contracts.py`
- Create: `kubani/framework/mcp/server/testing/tests/test_contracts.py`

**Step 1: Write the failing test**

```python
# kubani/framework/mcp/server/testing/tests/test_contracts.py
"""Tests for MCP contract definitions."""

import pytest

from kubani.framework.mcp.server.testing.contracts import MCPContract, ToolContract


class TestToolContract:
    """Tests for ToolContract."""

    def test_basic_tool(self):
        tool = ToolContract(
            name="my_tool",
            parameters={
                "query": {"type": "string", "required": True},
            },
        )
        assert tool.name == "my_tool"
        assert "query" in tool.parameters

    def test_tool_with_description(self):
        tool = ToolContract(
            name="search",
            description="Search for items",
            parameters={
                "query": {"type": "string", "required": True},
                "limit": {"type": "integer", "required": False},
            },
        )
        assert tool.description == "Search for items"

    def test_required_parameters(self):
        tool = ToolContract(
            name="test",
            parameters={
                "required_param": {"type": "string", "required": True},
                "optional_param": {"type": "string", "required": False},
            },
        )
        assert tool.required_parameters == ["required_param"]

    def test_optional_parameters(self):
        tool = ToolContract(
            name="test",
            parameters={
                "required_param": {"type": "string", "required": True},
                "optional_param": {"type": "string", "required": False},
            },
        )
        assert tool.optional_parameters == ["optional_param"]


class TestMCPContract:
    """Tests for MCPContract."""

    def test_basic_contract(self):
        contract = MCPContract(
            server_name="test-server",
            tools=[
                ToolContract(name="tool1", parameters={}),
                ToolContract(name="tool2", parameters={}),
            ],
        )
        assert contract.server_name == "test-server"
        assert len(contract.tools) == 2

    def test_get_tool(self):
        contract = MCPContract(
            server_name="test-server",
            tools=[
                ToolContract(name="find", parameters={}),
                ToolContract(name="search", parameters={}),
            ],
        )
        tool = contract.get_tool("find")
        assert tool is not None
        assert tool.name == "find"

    def test_get_tool_not_found(self):
        contract = MCPContract(
            server_name="test-server",
            tools=[],
        )
        tool = contract.get_tool("nonexistent")
        assert tool is None

    def test_tool_names(self):
        contract = MCPContract(
            server_name="test-server",
            tools=[
                ToolContract(name="a", parameters={}),
                ToolContract(name="b", parameters={}),
                ToolContract(name="c", parameters={}),
            ],
        )
        assert contract.tool_names == ["a", "b", "c"]
```

**Step 2: Run test to verify it fails**

```bash
cd kubani/framework && uv run pytest mcp/server/testing/tests/test_contracts.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# kubani/framework/mcp/server/testing/contracts.py
"""
Contract definitions for MCP server testing.

Contracts define the expected interface of an MCP server, including
what tools it should provide and their parameter schemas.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContract:
    """
    Contract for an MCP tool.

    Defines the expected name, parameters, and behavior of a tool.
    """

    name: str
    parameters: dict[str, dict[str, Any]] = field(default_factory=dict)
    description: str | None = None

    @property
    def required_parameters(self) -> list[str]:
        """Get list of required parameter names."""
        return [
            name
            for name, spec in self.parameters.items()
            if spec.get("required", False)
        ]

    @property
    def optional_parameters(self) -> list[str]:
        """Get list of optional parameter names."""
        return [
            name
            for name, spec in self.parameters.items()
            if not spec.get("required", False)
        ]


@dataclass
class MCPContract:
    """
    Contract for an MCP server.

    Defines the expected tools and capabilities of the server.
    """

    server_name: str
    tools: list[ToolContract] = field(default_factory=list)
    description: str | None = None

    def get_tool(self, name: str) -> ToolContract | None:
        """Get a tool contract by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    @property
    def tool_names(self) -> list[str]:
        """Get list of all tool names."""
        return [tool.name for tool in self.tools]
```

**Step 4: Run test to verify it passes**

```bash
cd kubani/framework && uv run pytest mcp/server/testing/tests/test_contracts.py -v
```
Expected: PASS (all 7 tests)

**Step 5: Commit**

```bash
git add kubani/framework/mcp/server/testing/contracts.py kubani/framework/mcp/server/testing/tests/test_contracts.py
git commit -m "feat(mcp): add contract definitions for testing

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Implement Test Harness

**Files:**
- Create: `kubani/framework/mcp/server/testing/harness.py`
- Create: `kubani/framework/mcp/server/testing/tests/test_harness.py`

**Step 1: Write the failing test**

```python
# kubani/framework/mcp/server/testing/tests/test_harness.py
"""Tests for MCP test harness."""

import pytest

from kubani.framework.mcp.server import MCPServerBase
from kubani.framework.mcp.server.testing import (
    MCPContract,
    MCPTestHarness,
    ToolContract,
)


class MockServer(MCPServerBase):
    """Mock server for testing the harness."""

    name = "mock-server"
    description = "A mock server for testing"

    async def connect_backend(self) -> None:
        pass

    async def disconnect_backend(self) -> None:
        pass

    def register_tools(self, mcp) -> None:
        @mcp.tool()
        async def echo(message: str) -> dict:
            """Echo the message back."""
            return {"echo": message}

        @mcp.tool()
        async def add(a: int, b: int) -> dict:
            """Add two numbers."""
            return {"result": a + b}


MOCK_CONTRACT = MCPContract(
    server_name="mock-server",
    tools=[
        ToolContract(
            name="echo",
            parameters={"message": {"type": "string", "required": True}},
        ),
        ToolContract(
            name="add",
            parameters={
                "a": {"type": "integer", "required": True},
                "b": {"type": "integer", "required": True},
            },
        ),
        ToolContract(name="health", parameters={}),
    ],
)


class TestMCPTestHarness:
    """Tests for MCPTestHarness."""

    @pytest.mark.asyncio
    async def test_validate_tools_exist(self):
        server = MockServer()
        harness = MCPTestHarness(server, MOCK_CONTRACT)

        result = await harness.validate_tools_exist()
        assert result.passed
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_tools_missing(self):
        server = MockServer()
        contract_with_missing = MCPContract(
            server_name="mock-server",
            tools=[
                ToolContract(name="echo", parameters={}),
                ToolContract(name="nonexistent_tool", parameters={}),
            ],
        )
        harness = MCPTestHarness(server, contract_with_missing)

        result = await harness.validate_tools_exist()
        assert not result.passed
        assert "nonexistent_tool" in str(result.errors)

    @pytest.mark.asyncio
    async def test_call_tool(self):
        server = MockServer()
        harness = MCPTestHarness(server, MOCK_CONTRACT)

        await harness.setup()
        result = await harness.call_tool("echo", message="hello")
        await harness.teardown()

        assert result == {"echo": "hello"}

    @pytest.mark.asyncio
    async def test_call_tool_with_multiple_args(self):
        server = MockServer()
        harness = MCPTestHarness(server, MOCK_CONTRACT)

        await harness.setup()
        result = await harness.call_tool("add", a=2, b=3)
        await harness.teardown()

        assert result == {"result": 5}

    @pytest.mark.asyncio
    async def test_validation_result_to_dict(self):
        server = MockServer()
        harness = MCPTestHarness(server, MOCK_CONTRACT)

        result = await harness.validate_tools_exist()
        d = result.to_dict()

        assert "passed" in d
        assert "errors" in d
        assert d["passed"] is True
```

**Step 2: Run test to verify it fails**

```bash
cd kubani/framework && uv run pytest mcp/server/testing/tests/test_harness.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# kubani/framework/mcp/server/testing/harness.py
"""
Test harness for MCP servers.

Provides utilities for testing MCP servers against their contracts.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from kubani.framework.mcp.server.base import MCPServerBase
from kubani.framework.mcp.server.testing.contracts import MCPContract

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class MCPTestHarness:
    """
    Test harness for MCP servers.

    Provides utilities for:
    - Validating servers against contracts
    - Calling tools in tests
    - Managing server lifecycle

    Usage:
        server = MyMCPServer()
        harness = MCPTestHarness(server, MY_CONTRACT)

        # Validate contract
        result = await harness.validate_tools_exist()
        assert result.passed

        # Call tools
        await harness.setup()
        result = await harness.call_tool("my_tool", arg="value")
        await harness.teardown()
    """

    def __init__(self, server: MCPServerBase, contract: MCPContract):
        """
        Initialize the test harness.

        Args:
            server: The MCP server to test
            contract: The contract to validate against
        """
        self.server = server
        self.contract = contract
        self._mcp = None
        self._tools: dict[str, Any] = {}

    async def setup(self) -> None:
        """Set up the harness for testing (connect to backend)."""
        await self.server.startup()
        self._mcp = self.server.create_server()
        self._discover_tools()

    async def teardown(self) -> None:
        """Tear down the harness after testing."""
        await self.server.shutdown()

    def _discover_tools(self) -> None:
        """Discover tools registered on the MCP server."""
        if self._mcp is None:
            return

        # Access the tool manager to find registered tools
        # FastMCP stores tools in _tool_manager
        if hasattr(self._mcp, "_tool_manager"):
            manager = self._mcp._tool_manager
            if hasattr(manager, "_tools"):
                self._tools = dict(manager._tools)

    async def validate_tools_exist(self) -> ValidationResult:
        """
        Validate that all contracted tools exist on the server.

        Returns:
            ValidationResult with pass/fail and any errors
        """
        # Create server to register tools (don't need to connect)
        mcp = self.server.create_server()
        self._mcp = mcp
        self._discover_tools()

        errors = []
        for tool_contract in self.contract.tools:
            if tool_contract.name not in self._tools:
                errors.append(f"Missing tool: {tool_contract.name}")

        return ValidationResult(
            passed=len(errors) == 0,
            errors=errors,
        )

    async def call_tool(self, name: str, **kwargs: Any) -> Any:
        """
        Call a tool on the server.

        Args:
            name: Tool name
            **kwargs: Tool arguments

        Returns:
            Tool result

        Raises:
            KeyError: If tool not found
        """
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")

        tool = self._tools[name]
        # The tool is an async function, call it with the kwargs
        return await tool.fn(**kwargs)
```

**Step 4: Run test to verify it passes**

```bash
cd kubani/framework && uv run pytest mcp/server/testing/tests/test_harness.py -v
```
Expected: PASS (all 5 tests)

**Step 5: Commit**

```bash
git add kubani/framework/mcp/server/testing/harness.py kubani/framework/mcp/server/testing/tests/test_harness.py
git commit -m "feat(mcp): add test harness for contract validation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Implement Mock Backends

**Files:**
- Create: `kubani/framework/mcp/server/testing/mocks.py`
- Create: `kubani/framework/mcp/server/testing/tests/test_mocks.py`

**Step 1: Write the failing test**

```python
# kubani/framework/mcp/server/testing/tests/test_mocks.py
"""Tests for mock backends."""

import pytest

from kubani.framework.mcp.server.testing.mocks import (
    MockQdrant,
    MockRedis,
    MockTemporalClient,
)


class TestMockQdrant:
    """Tests for MockQdrant."""

    @pytest.mark.asyncio
    async def test_create_collection(self):
        mock = MockQdrant()
        await mock.connect()

        await mock.create_collection("test", vector_size=128)
        collections = await mock.list_collections()

        assert "test" in collections
        await mock.close()

    @pytest.mark.asyncio
    async def test_upsert_and_search(self):
        mock = MockQdrant()
        await mock.connect()
        await mock.create_collection("test", vector_size=4)

        # Upsert a vector
        await mock.upsert(
            collection="test",
            id="1",
            vector=[1.0, 0.0, 0.0, 0.0],
            payload={"name": "test item"},
        )

        # Search should find it
        results = await mock.search(
            collection="test",
            query_vector=[1.0, 0.0, 0.0, 0.0],
            limit=10,
        )

        assert len(results) == 1
        assert results[0]["id"] == "1"
        await mock.close()


class TestMockRedis:
    """Tests for MockRedis."""

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        mock = MockRedis()
        await mock.connect()

        await mock.set("key", "value")
        result = await mock.get("key")

        assert result == "value"
        await mock.close()

    @pytest.mark.asyncio
    async def test_get_missing_key(self):
        mock = MockRedis()
        await mock.connect()

        result = await mock.get("nonexistent")
        assert result is None
        await mock.close()

    @pytest.mark.asyncio
    async def test_delete(self):
        mock = MockRedis()
        await mock.connect()

        await mock.set("key", "value")
        await mock.delete("key")
        result = await mock.get("key")

        assert result is None
        await mock.close()


class TestMockTemporalClient:
    """Tests for MockTemporalClient."""

    @pytest.mark.asyncio
    async def test_start_workflow(self):
        mock = MockTemporalClient()
        await mock.connect()

        handle = await mock.start_workflow(
            workflow_type="TestWorkflow",
            workflow_id="test-1",
            task_queue="test-queue",
        )

        assert handle.id == "test-1"
        await mock.close()

    @pytest.mark.asyncio
    async def test_list_workflows(self):
        mock = MockTemporalClient()
        await mock.connect()

        await mock.start_workflow(
            workflow_type="TestWorkflow",
            workflow_id="test-1",
            task_queue="test-queue",
        )

        workflows = []
        async for w in mock.list_workflows():
            workflows.append(w)

        assert len(workflows) == 1
        assert workflows[0].id == "test-1"
        await mock.close()
```

**Step 2: Run test to verify it fails**

```bash
cd kubani/framework && uv run pytest mcp/server/testing/tests/test_mocks.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# kubani/framework/mcp/server/testing/mocks.py
"""
Mock backends for testing MCP servers.

These mocks provide in-memory implementations of common backends
to enable unit testing without external dependencies.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


class MockQdrant:
    """
    In-memory mock of Qdrant vector database.

    Provides basic collection and vector operations for testing.
    """

    def __init__(self):
        self._collections: dict[str, dict[str, Any]] = {}
        self._vectors: dict[str, dict[str, dict[str, Any]]] = {}
        self._connected = False

    async def connect(self) -> None:
        """Connect to mock backend."""
        self._connected = True

    async def close(self) -> None:
        """Disconnect from mock backend."""
        self._connected = False

    async def create_collection(
        self,
        name: str,
        vector_size: int,
    ) -> None:
        """Create a collection."""
        self._collections[name] = {"vector_size": vector_size}
        self._vectors[name] = {}

    async def delete_collection(self, name: str) -> None:
        """Delete a collection."""
        self._collections.pop(name, None)
        self._vectors.pop(name, None)

    async def list_collections(self) -> list[str]:
        """List all collections."""
        return list(self._collections.keys())

    async def upsert(
        self,
        collection: str,
        id: str,
        vector: list[float],
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a vector."""
        if collection not in self._vectors:
            self._vectors[collection] = {}

        self._vectors[collection][id] = {
            "id": id,
            "vector": vector,
            "payload": payload or {},
        }

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for similar vectors (returns all for simplicity)."""
        if collection not in self._vectors:
            return []

        # Simple mock: return all vectors (no actual similarity calculation)
        results = list(self._vectors[collection].values())[:limit]
        return results

    async def get(self, collection: str, id: str) -> dict[str, Any] | None:
        """Get a vector by ID."""
        if collection not in self._vectors:
            return None
        return self._vectors[collection].get(id)

    async def delete(self, collection: str, id: str) -> None:
        """Delete a vector."""
        if collection in self._vectors:
            self._vectors[collection].pop(id, None)


class MockRedis:
    """
    In-memory mock of Redis.

    Provides basic key-value operations for testing.
    """

    def __init__(self):
        self._data: dict[str, str] = {}
        self._connected = False

    async def connect(self) -> None:
        """Connect to mock backend."""
        self._connected = True

    async def close(self) -> None:
        """Disconnect from mock backend."""
        self._connected = False

    async def get(self, key: str) -> str | None:
        """Get a value by key."""
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """Set a value (expiration ignored in mock)."""
        self._data[key] = value

    async def delete(self, key: str) -> None:
        """Delete a key."""
        self._data.pop(key, None)

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        return key in self._data

    async def keys(self, pattern: str = "*") -> list[str]:
        """List keys (pattern ignored in mock)."""
        return list(self._data.keys())


@dataclass
class MockWorkflowHandle:
    """Mock workflow handle."""

    id: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_type: str = "MockWorkflow"
    status: str = "RUNNING"

    async def describe(self) -> "MockWorkflowHandle":
        """Describe the workflow."""
        return self

    async def signal(self, signal_name: str, args: list[Any] | None = None) -> None:
        """Send a signal (no-op in mock)."""
        pass

    async def cancel(self) -> None:
        """Cancel the workflow."""
        self.status = "CANCELED"

    async def terminate(self, reason: str | None = None) -> None:
        """Terminate the workflow."""
        self.status = "TERMINATED"


class MockTemporalClient:
    """
    In-memory mock of Temporal client.

    Provides basic workflow operations for testing.
    """

    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        self._workflows: dict[str, MockWorkflowHandle] = {}
        self._connected = False

    async def connect(self) -> None:
        """Connect to mock backend."""
        self._connected = True

    async def close(self) -> None:
        """Disconnect from mock backend."""
        self._connected = False

    async def start_workflow(
        self,
        workflow_type: str,
        workflow_id: str,
        task_queue: str,
        args: list[Any] | None = None,
    ) -> MockWorkflowHandle:
        """Start a workflow."""
        handle = MockWorkflowHandle(
            id=workflow_id,
            workflow_type=workflow_type,
        )
        self._workflows[workflow_id] = handle
        return handle

    def get_workflow_handle(
        self,
        workflow_id: str,
        run_id: str | None = None,
    ) -> MockWorkflowHandle:
        """Get a workflow handle."""
        if workflow_id not in self._workflows:
            # Create a mock handle even for unknown workflows
            self._workflows[workflow_id] = MockWorkflowHandle(id=workflow_id)
        return self._workflows[workflow_id]

    async def list_workflows(
        self,
        query: str | None = None,
    ) -> AsyncIterator[MockWorkflowHandle]:
        """List workflows."""
        for handle in self._workflows.values():
            yield handle
```

**Step 4: Run test to verify it passes**

```bash
cd kubani/framework && uv run pytest mcp/server/testing/tests/test_mocks.py -v
```
Expected: PASS (all 7 tests)

**Step 5: Commit**

```bash
git add kubani/framework/mcp/server/testing/mocks.py kubani/framework/mcp/server/testing/tests/test_mocks.py
git commit -m "feat(mcp): add mock backends for testing

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Create Contract Definitions for All Servers

**Files:**
- Create: `kubani/mcp/servers/tests/__init__.py`
- Create: `kubani/mcp/servers/tests/contracts.py`

**Step 1: Create contracts for all servers**

```python
# kubani/mcp/servers/tests/contracts.py
"""
Contract definitions for all MCP servers.

These contracts define the expected tools and parameters for each server.
"""

from kubani.framework.mcp.server.testing import MCPContract, ToolContract

# =========================================================================
# Discord MCP Contract
# =========================================================================

DISCORD_CONTRACT = MCPContract(
    server_name="Discord MCP Server",
    tools=[
        ToolContract(
            name="send_message",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "content": {"type": "string", "required": False},
                "embed": {"type": "object", "required": False},
            },
        ),
        ToolContract(
            name="get_messages",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "limit": {"type": "integer", "required": False},
            },
        ),
        ToolContract(
            name="list_channels",
            parameters={},
        ),
        ToolContract(name="health", parameters={}),
    ],
)

# =========================================================================
# Temporal MCP Contract
# =========================================================================

TEMPORAL_CONTRACT = MCPContract(
    server_name="Temporal MCP Server",
    tools=[
        ToolContract(
            name="list_workflows",
            parameters={
                "query": {"type": "string", "required": False},
                "limit": {"type": "integer", "required": False},
                "status": {"type": "string", "required": False},
            },
        ),
        ToolContract(
            name="get_workflow",
            parameters={
                "workflow_id": {"type": "string", "required": True},
                "run_id": {"type": "string", "required": False},
            },
        ),
        ToolContract(
            name="start_workflow",
            parameters={
                "workflow_type": {"type": "string", "required": True},
                "workflow_id": {"type": "string", "required": True},
                "task_queue": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="signal_workflow",
            parameters={
                "workflow_id": {"type": "string", "required": True},
                "signal_name": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="cancel_workflow",
            parameters={
                "workflow_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="list_schedules",
            parameters={
                "limit": {"type": "integer", "required": False},
            },
        ),
        ToolContract(name="health", parameters={}),
    ],
)

# =========================================================================
# Qdrant MCP Contract
# =========================================================================

QDRANT_CONTRACT = MCPContract(
    server_name="Qdrant MCP Server",
    tools=[
        ToolContract(
            name="list_collections",
            parameters={},
        ),
        ToolContract(
            name="create_collection",
            parameters={
                "name": {"type": "string", "required": True},
                "vector_size": {"type": "integer", "required": True},
            },
        ),
        ToolContract(
            name="search_vectors",
            parameters={
                "collection": {"type": "string", "required": True},
                "query_vector": {"type": "array", "required": True},
            },
        ),
        ToolContract(
            name="upsert_vectors",
            parameters={
                "collection": {"type": "string", "required": True},
                "vectors": {"type": "array", "required": True},
            },
        ),
        ToolContract(name="health", parameters={}),
    ],
)

# =========================================================================
# Memory MCP Contract
# =========================================================================

MEMORY_CONTRACT = MCPContract(
    server_name="Memory MCP Server",
    tools=[
        ToolContract(
            name="store_learning",
            parameters={
                "agent_id": {"type": "string", "required": True},
                "learning_type": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="query_learnings",
            parameters={
                "query": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="store_knowledge",
            parameters={
                "subject": {"type": "string", "required": True},
                "predicate": {"type": "string", "required": True},
                "object": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="query_knowledge",
            parameters={
                "query": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="cache_get",
            parameters={
                "key": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="cache_set",
            parameters={
                "key": {"type": "string", "required": True},
                "value": {"type": "string", "required": True},
            },
        ),
        ToolContract(name="health", parameters={}),
    ],
)

# =========================================================================
# Skills MCP Contract
# =========================================================================

SKILLS_CONTRACT = MCPContract(
    server_name="Skills MCP Server",
    tools=[
        ToolContract(
            name="list_skills",
            parameters={
                "category": {"type": "string", "required": False},
            },
        ),
        ToolContract(
            name="get_skill",
            parameters={
                "name": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="execute_skill",
            parameters={
                "name": {"type": "string", "required": True},
                "context": {"type": "object", "required": False},
            },
        ),
        ToolContract(
            name="refresh_skills",
            parameters={},
        ),
        ToolContract(name="health", parameters={}),
    ],
)

# =========================================================================
# All Contracts
# =========================================================================

ALL_CONTRACTS = {
    "discord": DISCORD_CONTRACT,
    "temporal": TEMPORAL_CONTRACT,
    "qdrant": QDRANT_CONTRACT,
    "memory": MEMORY_CONTRACT,
    "skills": SKILLS_CONTRACT,
}
```

**Step 2: Commit**

```bash
git add kubani/mcp/servers/tests/
git commit -m "feat(mcp): add contract definitions for all servers

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Add Contract Tests to Each Server

**Files:**
- Create: `kubani/mcp/servers/temporal/tests/test_contract.py`
- Create: `kubani/mcp/servers/qdrant/tests/test_contract.py`
- Create: `kubani/mcp/servers/memory/tests/test_contract.py`
- Create: `kubani/mcp/servers/skills/tests/test_contract.py`

**Step 1: Create temporal/tests/test_contract.py**

```python
# kubani/mcp/servers/temporal/tests/test_contract.py
"""Contract tests for Temporal MCP server."""

import pytest

from kubani.framework.mcp.server.testing import MCPTestHarness

from temporal_mcp import TemporalMCPServer

# Import shared contract
import sys
sys.path.insert(0, str(__file__).rsplit("/", 3)[0])
from tests.contracts import TEMPORAL_CONTRACT


class TestTemporalContract:
    """Contract tests for Temporal MCP server."""

    @pytest.mark.asyncio
    async def test_tools_exist(self):
        """Verify all contracted tools exist."""
        server = TemporalMCPServer()
        harness = MCPTestHarness(server, TEMPORAL_CONTRACT)
        result = await harness.validate_tools_exist()
        assert result.passed, f"Missing tools: {result.errors}"
```

**Step 2: Create similar tests for qdrant, memory, skills**

Follow the same pattern for each server.

**Step 3: Commit**

```bash
git add kubani/mcp/servers/*/tests/
git commit -m "test(mcp): add contract tests for all servers

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Create Integration Test Suite

**Files:**
- Create: `kubani/mcp/servers/tests/test_integration.py`

**Step 1: Write integration tests**

```python
# kubani/mcp/servers/tests/test_integration.py
"""
Integration tests for MCP servers.

Tests that verify all servers can be imported and created.
"""

import pytest


class TestServerImports:
    """Test that all servers can be imported."""

    def test_import_discord(self):
        from discord_mcp import create_server
        mcp = create_server()
        assert mcp.name == "Discord MCP Server"

    def test_import_temporal(self):
        from temporal_mcp import TemporalMCPServer, create_server
        mcp = create_server()
        assert mcp.name == "Temporal MCP Server"

    def test_import_qdrant(self):
        from qdrant_mcp import create_server
        mcp = create_server()
        assert mcp.name == "Qdrant MCP Server"

    def test_import_memory(self):
        from memory_mcp import create_server
        mcp = create_server()
        assert mcp.name == "Memory MCP Server"

    def test_import_skills(self):
        from skills_mcp import create_server
        mcp = create_server()
        assert mcp.name == "Skills MCP Server"


class TestContractValidation:
    """Test contract validation for all servers."""

    @pytest.mark.asyncio
    async def test_all_servers_pass_contracts(self):
        """All servers should have their contracted tools."""
        from kubani.framework.mcp.server.testing import MCPTestHarness
        from tests.contracts import ALL_CONTRACTS

        from temporal_mcp import TemporalMCPServer
        from qdrant_mcp import QdrantMCPServer
        from memory_mcp import MemoryMCPServer
        from skills_mcp import SkillsMCPServer

        servers = {
            "temporal": TemporalMCPServer(),
            "qdrant": QdrantMCPServer(),
            "memory": MemoryMCPServer(),
            "skills": SkillsMCPServer(),
        }

        for name, server in servers.items():
            contract = ALL_CONTRACTS[name]
            harness = MCPTestHarness(server, contract)
            result = await harness.validate_tools_exist()
            assert result.passed, f"{name} missing tools: {result.errors}"
```

**Step 2: Commit**

```bash
git add kubani/mcp/servers/tests/
git commit -m "test(mcp): add integration test suite

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Run Full Test Suite

**Step 1: Run all framework tests**

```bash
cd kubani/framework && uv run pytest mcp/server/ -v --tb=short
```
Expected: All tests pass (40+ tests)

**Step 2: Run all server tests**

```bash
cd kubani/mcp/servers && uv run pytest -v --tb=short
```
Expected: All tests pass

**Step 3: Final commit**

```bash
git add -A
git commit -m "test(mcp): complete testing harness implementation

Testing infrastructure for MCP servers:
- Contract definitions for all 5 servers
- Test harness for contract validation
- Mock backends (Qdrant, Redis, Temporal)
- Integration tests for all servers

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

Phase 3 creates a comprehensive testing framework:

| Component | Purpose |
|-----------|---------|
| `contracts.py` | Tool contracts for validation |
| `harness.py` | Test harness for calling tools |
| `mocks.py` | Mock backends for unit testing |
| Contract tests | Per-server validation |
| Integration tests | Cross-server validation |

**Proceed to:** `2026-01-27-mcp-phase4-validation.md`
