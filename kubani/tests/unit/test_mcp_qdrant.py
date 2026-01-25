"""Tests for QdrantMCPClient."""

import httpx
import pytest

from kubani.framework.mcp.client import QdrantMCPClient


class TestQdrantMCPClientCollections:
    """Test collection management"""

    @pytest.mark.asyncio
    async def test_list_collections(self, respx_mock):
        """list_collections should return all collections"""
        respx_mock.post("http://localhost:8082/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"collections": ["skills", "learnings", "knowledge"]}},
            )
        )

        client = QdrantMCPClient("qdrant", "http://localhost:8082")
        response = await client.list_collections()

        assert response.success is True
        assert len(response.data["collections"]) == 3
        await client.close()

    @pytest.mark.asyncio
    async def test_create_collection(self, respx_mock):
        """create_collection should create new vector collection"""
        respx_mock.post("http://localhost:8082/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"created": True}})
        )

        client = QdrantMCPClient("qdrant", "http://localhost:8082")
        response = await client.create_collection(
            name="test_collection", vector_size=768, distance="Cosine"
        )

        assert response.success is True
        await client.close()


class TestQdrantMCPClientVectors:
    """Test vector operations"""

    @pytest.mark.asyncio
    async def test_search_vectors(self, respx_mock):
        """search_vectors should find similar vectors"""
        respx_mock.post("http://localhost:8082/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": {
                        "results": [
                            {"id": "vec-1", "score": 0.95, "payload": {"text": "result 1"}},
                            {"id": "vec-2", "score": 0.87, "payload": {"text": "result 2"}},
                        ]
                    }
                },
            )
        )

        client = QdrantMCPClient("qdrant", "http://localhost:8082")
        response = await client.search_vectors(
            collection="skills", query_vector=[0.1] * 768, limit=10
        )

        assert response.success is True
        assert len(response.data["results"]) == 2
        assert response.data["results"][0]["score"] == 0.95
        await client.close()

    @pytest.mark.asyncio
    async def test_upsert_vectors(self, respx_mock):
        """upsert_vectors should insert or update vectors"""
        respx_mock.post("http://localhost:8082/tools/call").mock(
            return_value=httpx.Response(
                200, json={"content": {"operation_id": 123, "status": "completed"}}
            )
        )

        client = QdrantMCPClient("qdrant", "http://localhost:8082")
        response = await client.upsert_vectors(
            collection="skills",
            points=[
                {"id": "vec-1", "vector": [0.1] * 768, "payload": {"text": "skill 1"}},
                {"id": "vec-2", "vector": [0.2] * 768, "payload": {"text": "skill 2"}},
            ],
        )

        assert response.success is True
        await client.close()

    @pytest.mark.asyncio
    async def test_delete_points(self, respx_mock):
        """delete_points should remove vectors from collection"""
        respx_mock.post("http://localhost:8082/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"deleted": 2}})
        )

        client = QdrantMCPClient("qdrant", "http://localhost:8082")
        response = await client.delete_points(collection="skills", point_ids=["vec-1", "vec-2"])

        assert response.success is True
        await client.close()
