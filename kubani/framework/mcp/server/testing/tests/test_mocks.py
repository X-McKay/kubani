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
