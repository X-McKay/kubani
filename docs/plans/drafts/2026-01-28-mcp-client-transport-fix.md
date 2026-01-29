# Plan: Fix MCP Client Transport & Align All Callers

**Date:** 2026-01-28
**Status:** Draft
**Author:** Claude
**Priority:** High (blocking all MCP communication)

---

## Guiding Principles

1. **Zero Tech Debt**: Clean up all legacy code, dead code, and obsolete patterns as we go
2. **No Backward Compatibility**: Remove old code entirely, don't keep deprecated shims
3. **Clean Tests**: Update or delete tests that reference removed code
4. **Single Source of Truth**: One way to do things, not multiple paths

---

## Executive Summary

All MCP communication across Kubani is broken due to two fundamental issues:

1. **Transport Mismatch**: The `MCPServerClient` uses HTTP POST to `/tools/call`, but all MCP servers run SSE transport which doesn't expose that endpoint (returns 404).

2. **Non-existent Tools**: The news digest syndicate calls domain-specific Memory MCP tools (`store_article`, `check_article_exists`, `query_articles`, `store_trend_snapshot`, `get_trend_snapshot`) that don't exist on the server and shouldn't exist — the Memory MCP is a generic service.

This plan fixes both issues in 5 phases.

---

## Phase 1: Fix MCP Client Transport

### Problem

The current `MCPServerClient.call_tool()` in `kubani/framework/mcp/client.py` does:

```python
response = await client.post("/tools/call", json={"name": tool_name, "arguments": kwargs})
```

All 4 custom MCP servers (Temporal, Qdrant, Memory, Discord) run SSE transport via `mcp.run_sse_async()`. SSE servers expose:
- `GET /sse` — Event stream endpoint
- `POST /messages/` — Message submission endpoint

They do **not** expose `/tools/call`. All calls return 404.

### Solution

Replace the HTTP POST transport with the MCP SDK's SSE client (`mcp.client.sse.sse_client` + `mcp.ClientSession`).

### Implementation

**File: `kubani/framework/mcp/client.py`**

#### Step 1.1: Add SSE client imports

At the top of the file, add:

```python
import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.client.sse import sse_client
from mcp import ClientSession
from mcp.types import CallToolResult
```

#### Step 1.2: Rewrite `MCPServerClient` class

Replace the entire class with:

```python
class MCPServerClient:
    """Client for a single MCP server using SSE transport.

    Uses the MCP SDK's SSE client for proper protocol communication.
    Each call creates a fresh connection since SSE connections are stateful.
    """

    def __init__(self, name: str, url: str, timeout: float = 30.0):
        self.name = name
        # Ensure URL ends with /sse for SSE transport
        self.url = url.rstrip("/")
        if not self.url.endswith("/sse"):
            self.url = f"{self.url}/sse"
        self.timeout = timeout

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[ClientSession]:
        """Create an SSE connection to the MCP server.

        Yields:
            ClientSession ready for tool calls.
        """
        async with sse_client(self.url, timeout=self.timeout) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def call_tool(self, tool_name: str, **kwargs) -> MCPResponse:
        """
        Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call
            **kwargs: Tool arguments

        Returns:
            MCPResponse with the result
        """
        try:
            async with self._connect() as session:
                result: CallToolResult = await session.call_tool(tool_name, arguments=kwargs)

                if result.isError:
                    # Extract error message from content
                    error_msg = self._extract_text_from_content(result.content)
                    logger.error(f"MCP {self.name} tool {tool_name} returned error: {error_msg}")
                    return MCPResponse(success=False, data=None, error=error_msg)

                # Parse content into Python data
                data = self._parse_content(result.content)
                return MCPResponse(success=True, data=data)

        except Exception as e:
            logger.error(f"MCP {self.name} tool {tool_name} error: {e}")
            return MCPResponse(success=False, data=None, error=str(e))

    def _extract_text_from_content(self, content: list) -> str:
        """Extract text from MCP content blocks."""
        texts = []
        for block in content:
            if hasattr(block, "text"):
                texts.append(block.text)
        return " ".join(texts) if texts else "Unknown error"

    def _parse_content(self, content: list) -> Any:
        """Parse MCP content blocks into Python data.

        MCP returns content as [{"type": "text", "text": "{...json...}"}].
        This extracts and parses the JSON data.
        """
        if not content:
            return None

        # Get text from first content block
        first_block = content[0]
        if hasattr(first_block, "text"):
            text = first_block.text
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text

        return content

    def _extract_data(self, response: MCPResponse) -> Any:
        """Extract clean data from an MCPResponse.

        Raises:
            RuntimeError: If the MCP call failed.
        """
        if not response.success:
            raise RuntimeError(response.error or "MCP call failed")
        return response.data

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools on the MCP server."""
        try:
            async with self._connect() as session:
                result = await session.list_tools()
                return [
                    {"name": tool.name, "description": tool.description}
                    for tool in result.tools
                ]
        except Exception as e:
            logger.error(f"Failed to list tools for {self.name}: {e}")
            return []

    async def health_check(self) -> bool:
        """Check if the MCP server is healthy by attempting to list tools."""
        try:
            tools = await self.list_tools()
            return len(tools) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """No-op for SSE client (connections are per-call)."""
        pass
```

#### Step 1.3: Clean Up MemoryMCPClient - Remove Domain-Specific Methods

**Delete these methods entirely** (lines ~388-502) — they call tools that don't exist and shouldn't exist on the generic Memory MCP server:

```python
# DELETE THESE METHODS:
async def store_article(...)      # Lines ~390-417
async def check_article_exists(...) # Lines ~419-430
async def query_articles(...)     # Lines ~432-453
async def query_knowledge(...)    # Lines ~455-468 (wrong signature)
async def store_trend_snapshot(...) # Lines ~472-491
async def get_trend_snapshot(...)   # Lines ~493-502
```

**Why delete instead of deprecate?** No backward compatibility needed. Activities will use generic tools directly. Keeping dead methods creates confusion.

#### Step 1.4: Add query_knowledge method with correct signature

The Memory MCP server has `query_knowledge(query, limit)`. Add/fix the method:

```python
async def query_knowledge(
    self,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Query knowledge. Returns list of knowledge entry dicts."""
    response = await self.call_tool(
        "query_knowledge",
        query=query,
        limit=limit,
    )
    return self._extract_data(response)
```

#### Step 1.5: Remove Legacy HTTP Client Code

Delete the following legacy code from `MCPServerClient`:

```python
# DELETE - No longer used with SSE transport:
self._client: httpx.AsyncClient | None = None  # Line ~59

async def _get_client(self) -> httpx.AsyncClient:  # Lines ~61-68
    """Get or create HTTP client."""
    ...

# The old call_tool implementation using httpx POST
# (already replaced in Step 1.2)
```

Also remove the `httpx` import if no other code in the file uses it:
```python
# DELETE if unused:
import httpx  # Line ~36
```

#### Step 1.6: Clean Up Tests for MCP Client

Find and update tests that mock the old HTTP transport:

```bash
# Find affected tests
grep -r "post.*tools/call" tests/ kubani/
grep -r "MCPServerClient" tests/
grep -r "_get_client" tests/
```

For each test file found:
- Remove mocks of `httpx.AsyncClient`
- Remove mocks of `/tools/call` endpoint
- Update to mock the new SSE client or test against real server
- Delete tests that only test removed methods (store_article, etc.)

### Verification

1. Port-forward to Memory MCP server:
   ```bash
   kubectl port-forward -n ai-agents svc/memory-mcp-server 8083:8083
   ```

2. Test script in scratchpad:
   ```python
   import asyncio
   from kubani.framework.mcp import get_mcp_client

   async def test():
       client = get_mcp_client()

       # Test 1: List tools (proves connectivity)
       tools = await client.memory.list_tools()
       print(f"Available tools: {[t['name'] for t in tools]}")

       # Test 2: Store a learning
       result = await client.memory.store_learning(
           agent_id="test-agent",
           learning_type="pattern",
           content="Test learning content",
           confidence=0.8,
       )
       print(f"Store learning result: {result}")

       # Test 3: Query learnings
       result = await client.memory.query_learnings(
           query="test learning",
           limit=5,
       )
       print(f"Query learnings result: {result}")

   asyncio.run(test())
   ```

3. Expected output:
   - Tools list includes: store_learning, query_learnings, store_knowledge, query_knowledge, cache_get, cache_set, etc.
   - Store learning returns dict with `learning_id`
   - Query learnings returns dict with `learnings` list

---

## Phase 2: Redesign News Digest Activities

### Problem

The activities in `kubani/framework/temporal/memory.py` call non-existent tools:
- `store_article` → doesn't exist
- `check_article_exists` → doesn't exist
- `query_articles` → doesn't exist
- `store_trend_snapshot` → doesn't exist
- `get_trend_snapshot` → doesn't exist

### Solution

Map domain-specific operations to generic tools that DO exist on the Memory MCP server.

### Available Generic Tools (confirmed on real server)

| Tool | Parameters | Purpose |
|------|------------|---------|
| `store_learning` | agent_id, learning_type, content, confidence, context, tags | Store agent learnings |
| `query_learnings` | query, agent_id, learning_type, min_confidence, limit | Query learnings |
| `store_knowledge` | topic, content, source, related_topics, metadata | Store knowledge |
| `query_knowledge` | query, limit | Query knowledge |
| `cache_get` | key | Get cached value |
| `cache_set` | key, value, ttl_seconds | Set cached value |
| `cache_delete` | key | Delete cached value |
| `get_knowledge_graph` | topic, depth | Get knowledge graph |
| `find_related_topics` | topic | Find related topics |
| `consolidate_learnings` | agent_id | Consolidate learnings |
| `create_relationship` | source_topic, target_topic, relationship_type | Create relationship |
| `get_agent_learnings` | agent_id, limit | Get agent's learnings |
| `get_entity_relationships` | entity | Get entity relationships |
| `get_memory_stats` | | Get memory stats |

### Mapping Strategy

| Domain Operation | Generic Tool(s) | Key Pattern |
|-----------------|-----------------|-------------|
| Store article | `store_knowledge` + `cache_set` | Use topic=`article:{url_hash}`, cache for dedup |
| Check article exists | `cache_get` | Check cache key `article:dedup:{url_hash}` |
| Query articles | `query_knowledge` | Query with knowledge, filter by topic prefix `article:` |
| Store trend snapshot | `cache_set` | Key=`trend:snapshot:{date}`, value=JSON |
| Get trend snapshot | `cache_get` | Key=`trend:snapshot:{date}` |

### Implementation

**File: `kubani/framework/temporal/memory.py`**

#### Step 2.0: Remove Dead Code First

Before implementing new activities, clean up:

1. **Remove old import comments** that reference non-existent tools
2. **Remove any leftover attribute-style access patterns** (e.g., `result.learning_id`)
3. **Ensure consistent dict access** throughout: use `.get("key")` everywhere

#### Step 2.1: Add URL hashing helper

At the top of the file, after imports:

```python
import hashlib

def _url_hash(url: str) -> str:
    """Create a short hash of a URL for cache keys."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]
```

#### Step 2.2: Rewrite `store_article_activity`

Replace the existing function (lines ~334-393):

```python
@activity.defn
async def store_article_activity(
    url: str,
    title: str,
    source: str,
    published_at: str | None = None,
    ai_summary: str = "",
    entities: list[str] | None = None,
    importance_score: int = 5,
    category: str = "general",
    content_hash: str = "",
    ttl_days: int = 14,
) -> dict[str, Any]:
    """Store a news article using generic Memory MCP tools.

    Strategy:
    1. Store article content as knowledge entry with topic="article:{url_hash}"
    2. Set cache key for URL deduplication

    Args:
        url: Article URL
        title: Article title
        source: Source name
        published_at: ISO format publication date
        ai_summary: AI-generated summary
        entities: Extracted entities/topics
        importance_score: Importance 1-10
        category: Article category
        content_hash: Hash for deduplication
        ttl_days: Days to retain

    Returns:
        Dict with article_id (knowledge_id) and status
    """
    logger.info(f"store_article_activity: Storing '{title}' from {source}")

    try:
        client = _get_memory_client()
        url_hash = _url_hash(url)

        # Build content string for knowledge storage
        content_parts = [f"# {title}", f"Source: {source}"]
        if published_at:
            content_parts.append(f"Published: {published_at}")
        if ai_summary:
            content_parts.append(f"\n{ai_summary}")
        content = "\n".join(content_parts)

        # Build metadata
        metadata = {
            "url": url,
            "source": source,
            "category": category,
            "importance_score": importance_score,
            "entities": entities or [],
        }
        if published_at:
            metadata["published_at"] = published_at
        if content_hash:
            metadata["content_hash"] = content_hash

        # Store as knowledge entry
        knowledge_result = await client.memory.store_knowledge(
            topic=f"article:{url_hash}",
            content=content,
            source=source,
            related_topics=[f"category:{category}"] + [f"entity:{e}" for e in (entities or [])[:5]],
            metadata=metadata,
        )

        # Set cache key for deduplication (TTL in seconds)
        await client.memory.cache_set(
            key=f"article:dedup:{url_hash}",
            value={"url": url, "stored_at": datetime.utcnow().isoformat()},
            ttl_seconds=ttl_days * 86400,
        )

        return {
            "success": True,
            "article_id": knowledge_result.get("knowledge_id"),
            "url": url,
        }

    except Exception as e:
        logger.error(f"store_article_activity: Failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }
```

#### Step 2.3: Rewrite `check_article_exists_activity`

Replace the existing function (lines ~396-430):

```python
@activity.defn
async def check_article_exists_activity(
    url: str | None = None,
    content_hash: str | None = None,
) -> dict[str, Any]:
    """Check if an article already exists using cache lookup.

    Args:
        url: Article URL to check
        content_hash: Content hash to check (unused in cache strategy)

    Returns:
        Dict with exists status
    """
    if not url:
        return {"success": True, "exists": False, "article_id": None}

    try:
        client = _get_memory_client()
        url_hash = _url_hash(url)

        result = await client.memory.cache_get(key=f"article:dedup:{url_hash}")

        exists = result.get("found", False)
        return {
            "success": True,
            "exists": exists,
            "article_id": f"article:{url_hash}" if exists else None,
        }

    except Exception as e:
        logger.error(f"check_article_exists_activity: Failed: {e}")
        return {
            "success": False,
            "exists": False,
            "error": str(e),
        }
```

#### Step 2.4: Rewrite `query_articles_activity`

Replace the existing function (lines ~433-489):

```python
@activity.defn
async def query_articles_activity(
    start_date: str | None = None,
    end_date: str | None = None,
    source: str | None = None,
    entity: str | None = None,
    category: str | None = None,
    min_importance: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Query stored articles using generic knowledge query.

    Note: Date filtering is approximate since we're using semantic search.
    For precise date filtering, articles would need to be stored with
    date-indexed topics.

    Args:
        start_date: ISO format start date (used in query text)
        end_date: ISO format end date (used in query text)
        source: Filter by source (used in query text)
        entity: Filter by entity (used in query text)
        category: Filter by category (used in query text)
        min_importance: Minimum importance score (post-filter)
        limit: Maximum results

    Returns:
        Dict with articles list
    """
    logger.info("query_articles_activity: Querying articles")

    try:
        client = _get_memory_client()

        # Build semantic query
        query_parts = ["news articles"]
        if source:
            query_parts.append(f"from {source}")
        if entity:
            query_parts.append(f"about {entity}")
        if category:
            query_parts.append(f"in {category} category")
        if start_date:
            query_parts.append(f"after {start_date}")

        query = " ".join(query_parts)

        # Query knowledge entries
        entries = await client.memory.query_knowledge(
            query=query,
            limit=limit * 2,  # Over-fetch to account for filtering
        )

        # Parse entries - they may come as list or dict with entries key
        if isinstance(entries, dict):
            entries = entries.get("entries", entries.get("knowledge", []))
        if not isinstance(entries, list):
            entries = []

        # Filter and transform to article format
        articles = []
        for entry in entries:
            # Skip non-article entries (check topic prefix)
            topic = entry.get("topic", "")
            if not topic.startswith("article:"):
                continue

            metadata = entry.get("metadata", {})
            importance = metadata.get("importance_score", 5)

            if importance < min_importance:
                continue

            articles.append({
                "article_id": entry.get("knowledge_id"),
                "url": metadata.get("url", ""),
                "title": entry.get("content", "").split("\n")[0].lstrip("# "),
                "source": metadata.get("source", entry.get("source", "")),
                "published_at": metadata.get("published_at"),
                "category": metadata.get("category", "general"),
                "importance_score": importance,
                "entities": metadata.get("entities", []),
            })

            if len(articles) >= limit:
                break

        return {
            "success": True,
            "articles": articles,
            "count": len(articles),
        }

    except Exception as e:
        logger.error(f"query_articles_activity: Failed: {e}")
        return {
            "success": False,
            "articles": [],
            "count": 0,
            "error": str(e),
        }
```

#### Step 2.5: Rewrite `store_trend_snapshot_activity`

Replace the existing function (lines ~497-542):

```python
@activity.defn
async def store_trend_snapshot_activity(
    trends: list[dict[str, Any]],
    emerging_topics: list[str] | None = None,
    declining_topics: list[str] | None = None,
    total_articles: int = 0,
    ttl_days: int = 30,
) -> dict[str, Any]:
    """Store a trend snapshot using cache.

    Args:
        trends: List of trend dicts
        emerging_topics: Emerging topics
        declining_topics: Declining topics
        total_articles: Article count
        ttl_days: Days to retain

    Returns:
        Dict with snapshot_id
    """
    logger.info(f"store_trend_snapshot_activity: Storing {len(trends)} trends")

    try:
        client = _get_memory_client()

        # Use today's date as snapshot key
        snapshot_date = datetime.utcnow().strftime("%Y-%m-%d")

        snapshot = {
            "snapshot_date": snapshot_date,
            "trends": trends,
            "emerging_topics": emerging_topics or [],
            "declining_topics": declining_topics or [],
            "total_articles": total_articles,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Store in cache with TTL
        await client.memory.cache_set(
            key=f"trend:snapshot:{snapshot_date}",
            value=snapshot,
            ttl_seconds=ttl_days * 86400,
        )

        # Also store as "latest" for easy retrieval
        await client.memory.cache_set(
            key="trend:snapshot:latest",
            value=snapshot,
            ttl_seconds=ttl_days * 86400,
        )

        return {
            "success": True,
            "snapshot_id": f"trend:snapshot:{snapshot_date}",
            "trends_count": len(trends),
        }

    except Exception as e:
        logger.error(f"store_trend_snapshot_activity: Failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }
```

#### Step 2.6: Rewrite `get_trend_snapshot_activity`

Replace the existing function (lines ~545-582):

```python
@activity.defn
async def get_trend_snapshot_activity(
    date: str | None = None,
) -> dict[str, Any]:
    """Get a trend snapshot from cache.

    Args:
        date: ISO format date (YYYY-MM-DD) or None for latest

    Returns:
        Trend snapshot data
    """
    logger.info(f"get_trend_snapshot_activity: Getting snapshot for {date or 'latest'}")

    try:
        client = _get_memory_client()

        # Build cache key
        if date:
            cache_key = f"trend:snapshot:{date}"
        else:
            cache_key = "trend:snapshot:latest"

        result = await client.memory.cache_get(key=cache_key)

        if result.get("found") and result.get("value"):
            snapshot = result["value"]
            # Ensure snapshot has an ID
            if "snapshot_id" not in snapshot:
                snapshot["snapshot_id"] = cache_key
            return {
                "success": True,
                "snapshot": snapshot,
            }
        else:
            return {
                "success": True,
                "snapshot": None,
            }

    except Exception as e:
        logger.error(f"get_trend_snapshot_activity: Failed: {e}")
        return {
            "success": False,
            "snapshot": None,
            "error": str(e),
        }
```

### Verification

1. With port-forward still active, run test script:

```python
import asyncio
from datetime import datetime
from kubani.framework.temporal.memory import (
    store_article_activity,
    check_article_exists_activity,
    query_articles_activity,
    store_trend_snapshot_activity,
    get_trend_snapshot_activity,
)

# These are activities, so we call them directly (outside Temporal for testing)
async def test_activities():
    # Test store article
    result = await store_article_activity(
        url="https://example.com/test-article",
        title="Test Article Title",
        source="Test Source",
        published_at=datetime.utcnow().isoformat(),
        ai_summary="This is a test article summary.",
        entities=["AI", "Testing"],
        importance_score=7,
        category="technology",
    )
    print(f"Store article: {result}")
    assert result["success"], f"Store failed: {result}"

    # Test check exists
    result = await check_article_exists_activity(url="https://example.com/test-article")
    print(f"Check exists: {result}")
    assert result["success"] and result["exists"], f"Should exist: {result}"

    # Test query articles
    result = await query_articles_activity(source="Test Source", limit=10)
    print(f"Query articles: {result}")
    assert result["success"], f"Query failed: {result}"

    # Test store trend snapshot
    result = await store_trend_snapshot_activity(
        trends=[{"topic": "AI", "mention_count": 10, "momentum": 0.5}],
        emerging_topics=["RAG"],
        declining_topics=["NFT"],
        total_articles=100,
    )
    print(f"Store trend: {result}")
    assert result["success"], f"Store trend failed: {result}"

    # Test get trend snapshot
    result = await get_trend_snapshot_activity()
    print(f"Get trend: {result}")
    assert result["success"] and result["snapshot"], f"Get trend failed: {result}"

    print("\nAll activity tests passed!")

asyncio.run(test_activities())
```

---

#### Step 2.7: Clean Up Tests for Memory Activities

Find and update tests:

```bash
# Find affected tests
grep -r "store_article_activity" tests/
grep -r "check_article_exists" tests/
grep -r "query_articles" tests/
grep -r "store_trend_snapshot" tests/
grep -r "get_trend_snapshot" tests/
```

For each test:
- Update test expectations to match new generic-tool-based implementations
- Remove any tests that mock domain-specific tools (`store_article`, etc.)
- Add tests that verify the new cache-based deduplication strategy
- Delete tests that are no longer relevant

---

## Phase 3: Audit and Fix All Other MCP Callers

### Goal

Review all MCP callers, fix any that call non-existent tools, and remove dead code.

### Other Files That Use MCP

Based on exploration, these files need review for the transport fix propagation:

| File | Component | Status After Phase 1 |
|------|-----------|---------------------|
| `kubani/agents/_base/agent.py` | Base Agent | Auto-fixed (uses MCPClient) |
| `kubani/agents/remediator/` | Remediator | Uses store_learning → valid tool |
| `kubani/agents/skill_learner/` | Skill Learner | Uses Memory MCP → needs review |
| `kubani/agents/critic/` | Critic | Uses Memory MCP → needs review |
| `kubani/agents/digest_publisher/` | Digest Publisher | Uses Discord MCP → auto-fixed |
| `kubani/agents/reflection/` | Reflection | Uses Memory MCP → needs review |
| `kubani/agents/skill_synthesizer/` | Skill Synthesizer | Uses Memory MCP → needs review |
| `kubani/agents/content_analyst/` | Content Analyst | Uses Memory MCP → needs review |
| `kubani/agents/trend_analyst/` | Trend Analyst | Uses Memory MCP → needs review |
| `kubani/framework/mcp/skills.py` | Skills MCP client | Auto-fixed (uses MCPClient) |
| `kubani/syndicates/learning_system/` | Learning workflows | Uses Memory MCP → needs review |
| `platform/skill-dev-tools/` | Skill dev tools | Uses Skills MCP → auto-fixed |
| `platform/cli/` | CLI runner | Uses various MCP → auto-fixed |

### Review Criteria

For each file:
1. Check what MCP tools it calls
2. Verify those tools exist on the target server
3. Verify response handling uses dict access (`.get()`) not attribute access

### K8s Monitor Syndicate

Based on exploration, K8s monitor uses only valid tools:
- `store_learning` ✅
- `query_knowledge` ✅ (need to verify parameters match)
- `cache_get` ✅
- `cache_set` ✅

No changes needed beyond the transport fix.

### Learning System Agents

Review each agent in `kubani/agents/` that uses Memory MCP:

```bash
# Find Memory MCP usage in agents
grep -r "memory\." kubani/agents/ --include="*.py"
```

For each match, verify:
1. Tool name exists in the server's tool list
2. Parameters match the server's expected signature
3. Response handling is correct

### Step 3.1: Audit Checklist

For each file that uses MCP:

| File | Tools Called | Valid? | Changes Needed |
|------|--------------|--------|----------------|
| `kubani/agents/remediator/` | `store_learning` | ✅ | None (auto-fixed) |
| `kubani/agents/skill_learner/` | TBD | TBD | TBD |
| `kubani/agents/critic/` | TBD | TBD | TBD |
| `kubani/agents/reflection/` | TBD | TBD | TBD |
| `kubani/agents/skill_synthesizer/` | TBD | TBD | TBD |
| `kubani/agents/content_analyst/` | TBD | TBD | TBD |
| `kubani/agents/trend_analyst/` | TBD | TBD | TBD |
| `kubani/syndicates/learning_system/` | TBD | TBD | TBD |

Fill in "TBD" cells during implementation by running:
```bash
grep -r "\.memory\." <file_path>
```

### Step 3.2: Remove Dead Code Across Agents

For each agent file:
1. Remove any imports of non-existent tools
2. Remove any code that calls non-existent methods on `MemoryMCPClient`
3. Remove dead variables and unused imports
4. Run `ruff check --fix` to clean up

### Step 3.3: Clean Up Agent Tests

```bash
# Find all agent tests that might reference old MCP patterns
grep -r "memory\." tests/agents/ --include="*.py"
```

For each test file:
- Remove mocks of non-existent tools
- Update assertions to match new return formats
- Delete tests for removed functionality

---

## Phase 4: End-to-End Verification

### Pre-Deployment Verification

Before building and deploying, verify against real servers:

#### 4.1: Port-Forward to MCP Servers

```bash
# Terminal 1: Memory MCP
kubectl port-forward -n ai-agents svc/memory-mcp-server 8083:8083

# Terminal 2: Discord MCP (if testing digest publishing)
kubectl port-forward -n ai-agents svc/discord-mcp-server 8084:8084
```

#### 4.2: Run Comprehensive Test Script

Save to scratchpad and run:

```python
#!/usr/bin/env python3
"""Comprehensive MCP verification script."""

import asyncio
import json
from datetime import datetime

async def test_mcp_transport():
    """Test Phase 1: Transport fix."""
    from kubani.framework.mcp import get_mcp_client

    print("=" * 60)
    print("Phase 1: Testing MCP Transport")
    print("=" * 60)

    client = get_mcp_client()

    # Test Memory MCP
    print("\n[Memory MCP]")
    tools = await client.memory.list_tools()
    tool_names = [t["name"] for t in tools]
    print(f"  Available tools: {tool_names}")

    expected_tools = ["store_learning", "query_learnings", "store_knowledge",
                      "query_knowledge", "cache_get", "cache_set"]
    missing = [t for t in expected_tools if t not in tool_names]
    if missing:
        print(f"  ERROR: Missing expected tools: {missing}")
        return False
    print("  ✓ All expected tools present")

    # Test a simple call
    result = await client.memory.store_learning(
        agent_id="mcp-test",
        learning_type="pattern",
        content="MCP transport test learning",
        confidence=0.9,
    )
    print(f"  store_learning result: {result}")
    if not result.get("learning_id"):
        print("  ERROR: No learning_id returned")
        return False
    print("  ✓ store_learning succeeded")

    return True

async def test_news_digest_activities():
    """Test Phase 2: News digest activities."""
    from kubani.framework.temporal.memory import (
        store_article_activity,
        check_article_exists_activity,
        query_articles_activity,
        store_trend_snapshot_activity,
        get_trend_snapshot_activity,
    )

    print("\n" + "=" * 60)
    print("Phase 2: Testing News Digest Activities")
    print("=" * 60)

    test_url = f"https://example.com/test-{datetime.utcnow().timestamp()}"

    # Test store article
    print("\n[store_article_activity]")
    result = await store_article_activity(
        url=test_url,
        title="MCP Test Article",
        source="Test Suite",
        published_at=datetime.utcnow().isoformat(),
        ai_summary="Testing MCP article storage",
        entities=["MCP", "Testing"],
        importance_score=8,
        category="testing",
    )
    print(f"  Result: {json.dumps(result, indent=2)}")
    if not result.get("success"):
        print(f"  ERROR: {result.get('error')}")
        return False
    print("  ✓ store_article succeeded")

    # Test check exists
    print("\n[check_article_exists_activity]")
    result = await check_article_exists_activity(url=test_url)
    print(f"  Result: {json.dumps(result, indent=2)}")
    if not result.get("success") or not result.get("exists"):
        print("  ERROR: Article should exist after storing")
        return False
    print("  ✓ check_article_exists succeeded")

    # Test query articles
    print("\n[query_articles_activity]")
    result = await query_articles_activity(limit=10)
    print(f"  Result: {json.dumps(result, indent=2)}")
    if not result.get("success"):
        print(f"  ERROR: {result.get('error')}")
        return False
    print(f"  ✓ query_articles returned {result.get('count', 0)} articles")

    # Test store trend snapshot
    print("\n[store_trend_snapshot_activity]")
    result = await store_trend_snapshot_activity(
        trends=[
            {"topic": "MCP", "mention_count": 5, "momentum": 0.8},
            {"topic": "Testing", "mention_count": 3, "momentum": 0.5},
        ],
        emerging_topics=["MCP"],
        total_articles=10,
    )
    print(f"  Result: {json.dumps(result, indent=2)}")
    if not result.get("success"):
        print(f"  ERROR: {result.get('error')}")
        return False
    print("  ✓ store_trend_snapshot succeeded")

    # Test get trend snapshot
    print("\n[get_trend_snapshot_activity]")
    result = await get_trend_snapshot_activity()
    print(f"  Result: {json.dumps(result, indent=2)}")
    if not result.get("success") or not result.get("snapshot"):
        print("  ERROR: Should have snapshot after storing")
        return False
    print("  ✓ get_trend_snapshot succeeded")

    return True

async def main():
    """Run all verification tests."""
    print("\n" + "=" * 60)
    print("MCP VERIFICATION SUITE")
    print("=" * 60)

    try:
        phase1_ok = await test_mcp_transport()
        if not phase1_ok:
            print("\n❌ Phase 1 FAILED - stopping here")
            return False

        phase2_ok = await test_news_digest_activities()
        if not phase2_ok:
            print("\n❌ Phase 2 FAILED")
            return False

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nSafe to proceed with build and deploy.")
        return True

    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
```

#### 4.3: Verification Checklist

- [ ] Memory MCP lists all expected tools
- [ ] `store_learning` returns `learning_id`
- [ ] `store_article_activity` succeeds and returns `article_id`
- [ ] `check_article_exists_activity` finds the stored article
- [ ] `query_articles_activity` returns articles without error
- [ ] `store_trend_snapshot_activity` succeeds
- [ ] `get_trend_snapshot_activity` retrieves the snapshot

---

## Execution Order & Parallelization

```
Phase 1 (Transport)  ──────────────────────────────────┐
                                                       │
                     ┌─────────────────────────────────┼─────────────────────────────────┐
                     │                                 │                                 │
                     ▼                                 ▼                                 │
        Phase 2 (News Digest)             Phase 3 (Other Callers)                       │
        ~modifies memory.py~              ~audits/modifies agents/~                     │
                     │                                 │                                 │
                     └─────────────────────────────────┼─────────────────────────────────┘
                                                       │
                                                       ▼
                                          Phase 4 (Verification)
                                                       │
                                                       ▼
                                          Phase 5 (Deploy)
```

**Dependencies:**
- Phase 1 must complete before 2 or 3 can start (transport is foundation)
- **Phases 2 and 3 can run in parallel** (different files, no overlap)
- Phase 4 requires 1, 2, and 3 complete
- Phase 5 requires 4 passing

**Parallel Implementation Strategy:**

After Phase 1 is complete and verified:
1. One agent/session works on Phase 2 (memory.py activities)
2. Another agent/session works on Phase 3 (audit other callers)
3. Both converge for Phase 4 verification

---

## Phase 5: Build, Deploy, and Validate

### 5.1: Build New Image

```bash
cd kubani/syndicates/news_digest
# Bump version in pyproject.toml to 0.5.7

# Build
docker build -t registry.almckay.io/news-monitor:0.5.7 .
docker push registry.almckay.io/news-monitor:0.5.7
```

### 5.2: Update Deployment YAML

**File: `infrastructure/gitops/apps/ai-agents/news-monitor/deployment.yaml`**

Change line 29:
```yaml
image: registry.almckay.io/news-monitor:0.5.7
```

Also update line 106 (AGENT_VERSION):
```yaml
value: "0.5.7"
```

### 5.3: Deploy

```bash
kubectl apply -f infrastructure/gitops/apps/ai-agents/news-monitor/deployment.yaml
kubectl rollout status deployment/news-monitor -n ai-agents
```

### 5.4: Verify Worker Startup

```bash
kubectl logs -n ai-agents deployment/news-monitor --tail=50
```

Look for:
- Worker started successfully
- Workflows registered: `NewsCollectionWorkflow`, `NewsDigestWorkflow`

### 5.5: Test Workflow

```bash
temporal workflow start \
  --task-queue news-digest \
  --type NewsCollectionWorkflow \
  --workflow-id test-collection-057 \
  --input '{"check_breaking": false}'
```

Monitor:
```bash
kubectl logs -n ai-agents deployment/news-monitor -f
```

Look for:
- No MCP errors (no 404s, no "object is not subscriptable")
- `store_article_activity` succeeds
- `check_article_exists_activity` succeeds
- Workflow completes with articles stored

---

## Files Modified Summary

| File | Phase | Description |
|------|-------|-------------|
| `kubani/framework/mcp/client.py` | 1 | Replace transport, remove domain-specific methods, delete httpx code |
| `kubani/framework/temporal/memory.py` | 2 | Rewrite 5 activities to use generic tools |
| `tests/**/test_*mcp*.py` | 1, 2, 3 | Update or delete tests for removed methods |
| `kubani/agents/*/` | 3 | Audit and clean up MCP usage |
| `kubani/syndicates/learning_system/` | 3 | Audit and clean up MCP usage |
| `kubani/syndicates/news_digest/pyproject.toml` | 5 | Bump version |
| `infrastructure/gitops/apps/ai-agents/news-monitor/deployment.yaml` | 5 | Update image version |

## Clean-Up Verification

Before considering any phase complete, run:

```bash
# Check for dead code
ruff check --select F401,F841 kubani/

# Check for unused imports
ruff check --select I kubani/

# Run full test suite
pytest kubani/ -v

# Verify no references to deleted methods
grep -r "store_article\|check_article_exists\|query_articles\|store_trend_snapshot\|get_trend_snapshot" kubani/ --include="*.py" | grep -v "activity"
# Should return ONLY the activity function definitions, not method calls on client
```

---

## Rollback Plan

If deployment fails:

```bash
# Rollback to previous version
kubectl rollout undo deployment/news-monitor -n ai-agents

# Or manually set previous image
kubectl set image deployment/news-monitor -n ai-agents \
  worker=registry.almckay.io/news-monitor:0.5.6
```

---

## Success Criteria

1. **Transport Fixed**: `MCPServerClient.call_tool()` uses MCP SDK SSE client
2. **Activities Work**: All 5 news digest activities call valid generic tools
3. **Verification Passes**: Test script against real server succeeds
4. **Workflow Runs**: Collection workflow completes without MCP errors
5. **No Regressions**: K8s monitor and other syndicates still function
6. **Zero Tech Debt**:
   - No dead code remains (verified by `ruff check`)
   - No references to deleted methods in codebase
   - All tests pass or have been updated/deleted
   - No backward-compatibility shims or deprecated code
   - Single, clean implementation path for MCP communication
