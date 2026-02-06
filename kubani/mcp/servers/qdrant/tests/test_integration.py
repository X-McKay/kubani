"""
Integration tests for Qdrant MCP Server.

These tests require a real Qdrant instance to be running.
Use docker-compose.integration.yml to start Qdrant.

Run with: uv run pytest tests/test_integration.py -v
"""

import os
from uuid import uuid4

import pytest

# Set environment variables for test Qdrant server
os.environ["QDRANT_HOST"] = "localhost"
os.environ["QDRANT_PORT"] = "6333"

from qdrant_mcp.server import connect_qdrant, create_server, disconnect_qdrant


@pytest.fixture(scope="module")
async def qdrant_client():
    """Connect to Qdrant once for all tests."""
    client = await connect_qdrant()
    yield client
    await disconnect_qdrant()


@pytest.fixture
async def server(qdrant_client):
    """Create a fresh server instance for each test."""
    return create_server()


@pytest.fixture
async def test_collection(server):
    """Create a test collection and clean it up after the test."""
    collection_name = f"test-collection-{uuid4()}"
    
    # Create collection
    await server.call_tool(
        "create_collection",
        {
            "name": collection_name,
            "vector_size": 128,
            "distance": "cosine",
        },
    )
    
    yield collection_name
    
    # Cleanup
    try:
        await server.call_tool(
            "delete_collection",
            {"name": collection_name},
        )
    except Exception:
        pass  # Collection might already be deleted


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_list_collections(server):
    """
    Test creating and listing collections with real Qdrant.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    collection_name = f"test-list-{uuid4()}"
    
    # Create collection
    create_result = await server.call_tool(
        "create_collection",
        {
            "name": collection_name,
            "vector_size": 128,
            "distance": "cosine",
        },
    )
    
    assert create_result["name"] == collection_name
    assert create_result["vectors_count"] == 0
    
    # List collections
    list_result = await server.call_tool("list_collections", {})
    
    assert "collections" in list_result
    assert list_result["count"] > 0
    
    # Should find our collection
    found = any(c["name"] == collection_name for c in list_result["collections"])
    assert found, f"Collection {collection_name} should be in list"
    
    # Cleanup
    await server.call_tool("delete_collection", {"name": collection_name})


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_collection_info(server, test_collection):
    """
    Test getting collection information.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    info = await server.call_tool(
        "get_collection_info",
        {"name": test_collection},
    )
    
    assert info["name"] == test_collection
    assert "vectors_count" in info
    assert "points_count" in info
    assert "status" in info


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upsert_and_search_vectors(server, test_collection):
    """
    Test upserting and searching vectors with real Qdrant.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    # Create test vectors (128-dimensional)
    vectors = [
        [0.1] * 128,
        [0.2] * 128,
        [0.3] * 128,
    ]
    
    payloads = [
        {"text": "first document", "category": "A"},
        {"text": "second document", "category": "B"},
        {"text": "third document", "category": "A"},
    ]
    
    # Upsert vectors
    upsert_result = await server.call_tool(
        "upsert_vectors",
        {
            "collection": test_collection,
            "vectors": vectors,
            "payloads": payloads,
        },
    )
    
    assert upsert_result["upserted_count"] == 3
    assert len(upsert_result["ids"]) == 3
    
    # Search for similar vectors
    query_vector = [0.15] * 128  # Should be closest to first vector
    
    search_result = await server.call_tool(
        "search_vectors",
        {
            "collection": test_collection,
            "query_vector": query_vector,
            "limit": 2,
        },
    )
    
    assert search_result["count"] > 0
    assert len(search_result["results"]) <= 2
    
    # First result should have highest score
    if len(search_result["results"]) > 1:
        assert search_result["results"][0]["score"] >= search_result["results"][1]["score"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_with_filter(server, test_collection):
    """
    Test searching with metadata filters.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    # Create test vectors with different categories
    vectors = [
        [0.1] * 128,
        [0.2] * 128,
        [0.3] * 128,
    ]
    
    payloads = [
        {"category": "A", "value": 1},
        {"category": "B", "value": 2},
        {"category": "A", "value": 3},
    ]
    
    await server.call_tool(
        "upsert_vectors",
        {
            "collection": test_collection,
            "vectors": vectors,
            "payloads": payloads,
        },
    )
    
    # Search with filter for category A
    search_result = await server.call_tool(
        "search_vectors",
        {
            "collection": test_collection,
            "query_vector": [0.15] * 128,
            "limit": 10,
            "filter_field": "category",
            "filter_value": "A",
        },
    )
    
    # Should only return category A results
    for result in search_result["results"]:
        assert result["payload"]["category"] == "A"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_and_delete_points(server, test_collection):
    """
    Test getting and deleting points by ID.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    # Upsert a vector with known ID
    point_id = str(uuid4())
    vector = [0.5] * 128
    payload = {"test": "data"}
    
    await server.call_tool(
        "upsert_vectors",
        {
            "collection": test_collection,
            "vectors": [vector],
            "payloads": [payload],
            "ids": [point_id],
        },
    )
    
    # Get the point
    get_result = await server.call_tool(
        "get_point",
        {
            "collection": test_collection,
            "point_id": point_id,
        },
    )
    
    assert get_result["id"] == point_id
    assert get_result["payload"] == payload
    assert len(get_result["vector"]) == 128
    
    # Delete the point
    delete_result = await server.call_tool(
        "delete_points",
        {
            "collection": test_collection,
            "point_ids": [point_id],
        },
    )
    
    assert delete_result["deleted_count"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scroll_points(server, test_collection):
    """
    Test scrolling through points in a collection.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    # Upsert multiple vectors
    vectors = [[i * 0.1] * 128 for i in range(5)]
    payloads = [{"index": i} for i in range(5)]
    
    await server.call_tool(
        "upsert_vectors",
        {
            "collection": test_collection,
            "vectors": vectors,
            "payloads": payloads,
        },
    )
    
    # Scroll through points
    scroll_result = await server.call_tool(
        "scroll_points",
        {
            "collection": test_collection,
            "limit": 3,
        },
    )
    
    assert "points" in scroll_result
    assert scroll_result["count"] <= 3
    assert len(scroll_result["points"]) <= 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_count_points(server, test_collection):
    """
    Test counting points in a collection.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    # Upsert some vectors
    vectors = [[i * 0.1] * 128 for i in range(3)]
    payloads = [{"category": "test"} for _ in range(3)]
    
    await server.call_tool(
        "upsert_vectors",
        {
            "collection": test_collection,
            "vectors": vectors,
            "payloads": payloads,
        },
    )
    
    # Count all points
    count_result = await server.call_tool(
        "count_points",
        {"collection": test_collection},
    )
    
    assert count_result["count"] >= 3
    assert count_result["collection"] == test_collection


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_collection(server):
    """
    Test deleting a collection.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    collection_name = f"test-delete-{uuid4()}"
    
    # Create collection
    await server.call_tool(
        "create_collection",
        {
            "name": collection_name,
            "vector_size": 128,
        },
    )
    
    # Delete collection
    delete_result = await server.call_tool(
        "delete_collection",
        {"name": collection_name},
    )
    
    assert delete_result["status"] == "deleted"
    assert delete_result["collection"] == collection_name
    
    # Verify it's gone
    list_result = await server.call_tool("list_collections", {})
    found = any(c["name"] == collection_name for c in list_result["collections"])
    assert not found, "Deleted collection should not be in list"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_check(server):
    """
    Test health check with real Qdrant.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    health_result = await server.call_tool("health", {})
    
    assert "status" in health_result
    # Should be healthy if Qdrant is running
    assert health_result["status"] in ["healthy", "degraded"]
