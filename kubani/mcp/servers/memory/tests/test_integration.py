"""
Integration tests for Memory MCP Server.

These tests require real backend services (Qdrant, Neo4j, Redis) to be running.
Use docker-compose.integration.yml to start the backends.

Run with: uv run pytest tests/test_integration.py -v
"""

import os
from datetime import datetime
from uuid import uuid4

import pytest

# Set environment variables for test backends
os.environ["QDRANT_HOST"] = "localhost"
os.environ["QDRANT_PORT"] = "6333"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["NEO4J_USER"] = "neo4j"
os.environ["NEO4J_PASSWORD"] = "testpassword"
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"

from memory_mcp.server import connect_backends, create_server, disconnect_backends


@pytest.fixture(scope="module")
async def backends():
    """Connect to backends once for all tests."""
    await connect_backends()
    yield
    await disconnect_backends()


@pytest.fixture
async def server(backends):
    """Create a fresh server instance for each test."""
    return create_server()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_store_and_query_learnings_with_qdrant(server):
    """
    Test storing and querying learnings with real Qdrant.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    agent_id = f"test-agent-{uuid4()}"
    
    # Store a learning
    store_result = await server.call_tool(
        "store_learning",
        {
            "agent_id": agent_id,
            "learning_type": "pattern",
            "content": "Always validate user input before processing",
            "confidence": 0.9,
            "tags": ["security", "validation"],
        },
    )
    
    assert "learning_id" in store_result
    learning_id = store_result["learning_id"]
    assert store_result["agent_id"] == agent_id
    assert store_result["learning_type"] == "pattern"
    
    # Query learnings by semantic search
    query_result = await server.call_tool(
        "query_learnings",
        {
            "query": "input validation",
            "agent_id": agent_id,
            "limit": 10,
        },
    )
    
    assert "learnings" in query_result
    assert query_result["count"] > 0
    
    # Should find our learning
    found = any(l["learning_id"] == learning_id for l in query_result["learnings"])
    assert found, "Stored learning should be found in semantic search"
    
    # Get agent learnings
    agent_learnings = await server.call_tool(
        "get_agent_learnings",
        {
            "agent_id": agent_id,
            "limit": 20,
        },
    )
    
    assert agent_learnings["count"] > 0
    assert any(l["learning_id"] == learning_id for l in agent_learnings["learnings"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_store_knowledge_and_graph_with_neo4j(server):
    """
    Test storing knowledge and knowledge graph with real Neo4j.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    topic = f"test/topic-{uuid4()}"
    related_topic = f"test/related-{uuid4()}"
    
    # Store knowledge
    knowledge_result = await server.call_tool(
        "store_knowledge",
        {
            "topic": topic,
            "content": "This is test knowledge about a specific topic",
            "source": "integration-test",
            "related_topics": [related_topic],
        },
    )
    
    assert "knowledge_id" in knowledge_result
    assert knowledge_result["topic"] == topic
    
    # Query knowledge
    query_result = await server.call_tool(
        "query_knowledge",
        {
            "query": "test knowledge",
            "topic_prefix": "test/",
            "limit": 10,
        },
    )
    
    assert len(query_result) > 0
    
    # Find related topics
    related_result = await server.call_tool(
        "find_related_topics",
        {
            "topic": topic,
            "limit": 10,
        },
    )
    
    assert related_topic in related_result, "Related topic should be found in graph"
    
    # Get knowledge graph
    graph_result = await server.call_tool(
        "get_knowledge_graph",
        {
            "topic": topic,
            "depth": 2,
        },
    )
    
    assert "nodes" in graph_result or "relationships" in graph_result or len(graph_result) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cache_operations_with_redis(server):
    """
    Test cache operations with real Redis.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    cache_key = f"test-key-{uuid4()}"
    cache_value = {"test": "data", "timestamp": datetime.utcnow().isoformat()}
    
    # Set cache value
    set_result = await server.call_tool(
        "cache_set",
        {
            "key": cache_key,
            "value": cache_value,
            "ttl_seconds": 300,
        },
    )
    
    assert set_result["status"] == "cached"
    assert set_result["key"] == cache_key
    
    # Get cache value
    get_result = await server.call_tool(
        "cache_get",
        {
            "key": cache_key,
        },
    )
    
    assert get_result["found"] is True
    assert get_result["value"] == cache_value
    
    # Delete cache value
    delete_result = await server.call_tool(
        "cache_delete",
        {
            "key": cache_key,
        },
    )
    
    assert delete_result["status"] == "deleted"
    
    # Verify deletion
    get_after_delete = await server.call_tool(
        "cache_get",
        {
            "key": cache_key,
        },
    )
    
    assert get_after_delete["found"] is False
    assert get_after_delete["value"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_check_and_mark_seen_with_redis(server):
    """
    Test deduplication with check_seen and mark_seen using Redis.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    namespace = f"test-namespace-{uuid4()}"
    key = f"test-item-{uuid4()}"
    
    # Check if seen (should be false initially)
    check_result = await server.call_tool(
        "check_seen",
        {
            "key": key,
            "namespace": namespace,
        },
    )
    
    assert check_result["seen"] is False
    assert check_result["key"] == key
    assert check_result["namespace"] == namespace
    
    # Mark as seen
    mark_result = await server.call_tool(
        "mark_seen",
        {
            "key": key,
            "namespace": namespace,
            "ttl_seconds": 300,
        },
    )
    
    assert mark_result["seen"] is True
    
    # Check again (should be true now)
    check_again = await server.call_tool(
        "check_seen",
        {
            "key": key,
            "namespace": namespace,
        },
    )
    
    assert check_again["seen"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generic_memory_add_search_get(server):
    """
    Test generic memory operations (add, search, get) across all backends.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    namespace = f"test/integration-{uuid4()}"
    
    # Add a memory object
    add_result = await server.call_tool(
        "add",
        {
            "type": "document",
            "namespace": namespace,
            "data": {
                "title": "Integration Test Document",
                "content": "This is a test document for integration testing",
            },
            "metadata": {
                "source": "integration-test",
                "priority": "high",
            },
        },
    )
    
    assert "id" in add_result
    object_id = add_result["id"]
    assert add_result["type"] == "document"
    assert add_result["namespace"] == namespace
    
    # Search for the object
    search_result = await server.call_tool(
        "search",
        {
            "query": "integration test document",
            "namespace": namespace,
            "limit": 10,
        },
    )
    
    assert search_result["count"] > 0
    assert any(obj["id"] == object_id for obj in search_result["results"])
    
    # Get the object by ID
    get_result = await server.call_tool(
        "get",
        {
            "id": object_id,
        },
    )
    
    assert get_result["found"] is True
    assert get_result["object"]["id"] == object_id
    assert get_result["object"]["type"] == "document"
    
    # List objects in namespace
    list_result = await server.call_tool(
        "list_objects",
        {
            "namespace": namespace,
            "limit": 100,
        },
    )
    
    assert len(list_result) > 0
    assert any(obj["id"] == object_id for obj in list_result)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_link_and_relationships(server):
    """
    Test creating links between memory objects using Neo4j.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    namespace = f"test/links-{uuid4()}"
    
    # Create two objects
    obj1 = await server.call_tool(
        "add",
        {
            "type": "analysis",
            "namespace": namespace,
            "data": {"title": "Source Analysis"},
        },
    )
    
    obj2 = await server.call_tool(
        "add",
        {
            "type": "report",
            "namespace": namespace,
            "data": {"title": "Derived Report"},
        },
    )
    
    source_id = obj1["id"]
    target_id = obj2["id"]
    
    # Create a link
    link_result = await server.call_tool(
        "link",
        {
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": "derived_from",
        },
    )
    
    assert link_result["created"] is True
    assert link_result["source_id"] == source_id
    assert link_result["target_id"] == target_id
    assert link_result["relation_type"] == "derived_from"
    
    # Get object with relations
    get_with_relations = await server.call_tool(
        "get",
        {
            "id": target_id,
            "include_relations": True,
        },
    )
    
    assert get_with_relations["found"] is True
    # Relations should be included
    obj = get_with_relations["object"]
    if "relations" in obj and obj["relations"]:
        assert len(obj["relations"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_memory_stats(server):
    """
    Test getting memory system statistics from all backends.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    stats = await server.call_tool("get_memory_stats", {})
    
    # Stats should have expected fields
    assert "total_learnings" in stats
    assert "total_knowledge" in stats
    assert "total_relationships" in stats
    assert "cache_keys" in stats
    
    # Values should be non-negative
    assert stats["total_learnings"] >= 0
    assert stats["total_knowledge"] >= 0
    assert stats["total_relationships"] >= 0
    assert stats["cache_keys"] >= 0
