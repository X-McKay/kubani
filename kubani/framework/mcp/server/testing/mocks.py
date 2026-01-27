"""
Mock backends for testing MCP servers.

These mocks provide in-memory implementations of common backends
to enable unit testing without external dependencies.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


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
