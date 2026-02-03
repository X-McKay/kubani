# Skills-Centric MCP Integration Plan

## Executive Summary

This plan redesigns how skills are documented, implemented, evaluated, and tested using Strands tools and MCP servers.

**Problem:** Current skills embed Python code examples that aren't executable. Evaluation uses LLM simulation without actual tool calls. Tests can pass even if tool specs are malformed.

**Solution:**
1. Skills use `allowed-tools` frontmatter to reference Strands built-in tools (rss, http_request, use_llm) and MCP tools
2. Memory MCP provides generic storage with Neo4j graph relationships (mem0-inspired)
3. Evaluation uses real Strands agents with tools (mocked or real)
4. Tests validate output format, accuracy, AND tool invocation appropriateness

**Key Architectural Decisions:**
- **Strands Tools**: Use built-in tools (rss, http_request, use_llm) where available
- **Memory MCP**: Generic interface (not news-specific) using mem0 + Neo4j for relationships
- **Skill Deprecations**: `deduplicate-articles` (auto-dedup in Memory), `filter-ai-relevant` (merge into analyze-article)

**Sources:**
- [AgentSkills Specification](https://agentskills.io/specification) - Skill format with allowed-tools
- [Strands Tools](https://github.com/strands-agents/tools) - Built-in tools (rss, http_request, use_llm, mem0_memory)
- [Mem0 Graph Memory](https://docs.mem0.ai/open-source/features/graph-memory) - Neo4j relationship support
- [ADR 007: Skills-Centric Agent Architecture](../adr/007-skills-centric-agent-architecture.md) - Architectural principles

---

## General Principles (from ADR 007)

The following principles from ADR 007 guide this implementation:

### 1. Skills-Centric Architecture

**Agents are thin orchestrators that delegate to portable skills.**

- Agents should contain minimal business logic (~150 lines vs ~300+ lines)
- Domain logic lives in SKILL.md files, not agent classes
- Skills are reusable across agents and platforms (Kubani, .claude/skills)

### 2. Progressive Disclosure

**Load skill content on-demand to minimize token usage.**

- **Phase 1 (Startup)**: Load only metadata (~300 tokens for 3 skills)
- **Phase 2 (Activation)**: Load full SKILL.md when needed (~2,000 tokens per skill)
- **Phase 3 (Resources)**: Load resource files if referenced

### 3. Functional Architecture

**Enable easy testing and composition.**

- Each component (MCP server, skill, agent) must be testable independently
- Use dependency injection for MCP clients
- Prefer pure functions where possible

### 4. Bottom-Up Testing Hierarchy

**Validate each layer before building the next.**

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 4: SYNDICATE                                              │
│ Test: End-to-end workflows via Temporal                         │
│ Dependencies: All agents working correctly                      │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: AGENTS                                                 │
│ Test: Agent orchestration with real skills                      │
│ Dependencies: Skills working with MCP servers                   │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: SKILLS                                                 │
│ Test: Skills with mocked and real MCP tools                     │
│ Dependencies: MCP servers available and validated               │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: MCP SERVERS                                            │
│ Test: Unit tests, integration tests with real backends          │
│ Dependencies: Qdrant, Neo4j, Redis, Discord API                 │
└─────────────────────────────────────────────────────────────────┘
```

**Key principle:** Each layer must pass all tests before proceeding to the next. Failures at lower layers propagate up, so we fix from the bottom.

---

## Phase 1: Skill Implementation Pattern

### 1.1 SKILL.md Frontmatter with allowed-tools

Skills declare which Strands tools and MCP tools they may use:

```yaml
---
name: fetch-rss-feeds
version: "1.0.0"
description: Fetch articles from RSS/Atom feeds
license: MIT
allowed-tools:              # Tools this skill may use
  - rss                     # Strands built-in RSS tool
  - memory/add              # Memory MCP store operation
metadata:
  kubani:
    domain: news
    category: collection
    confidence: 0.95
---
```

### 1.2 Available Strands Tools

| Tool | Purpose | Used By |
|------|---------|---------|
| `rss` | RSS feed fetch/subscribe/search | fetch-rss-feeds, fetch-arxiv-papers |
| `http_request` | HTTP API calls | fetch-github-trending |
| `use_llm` | LLM invocation for analysis | analyze-article, detect-trends, compose-digest |
| `mem0_memory` | Memory operations (or custom Memory MCP) | All skills storing data |

### 1.3 MCP Server Tools

| Server | Tools | Purpose |
|--------|-------|---------|
| `memory` | add, search, get, list, link, check_seen, mark_seen | Generic storage + relationships |
| `discord` | send_message, send_embed, add_reaction, await_reaction | Discord publishing |

### 1.4 Skill Body Content

SKILL.md body provides guidance on WHEN and HOW to use tools, not embedded code:

```markdown
## Instructions

### Step 1: Fetch RSS Feeds
Use the `rss` tool to fetch from configured AI news sources.

### Step 2: Store Articles
Store fetched articles using `memory/add` with:
- type: "document"
- namespace: "news/articles"
- metadata: source, published_at, etc.
```

---

## Phase 2: MCP Server Development and Testing

**This phase implements and validates all MCP servers before skills can use them.**

### 2.1 Memory MCP Server Design

#### 2.1.1 Generic Interface (Not Domain-Specific)

Memory MCP must be usable across all syndicates, not just news:

```yaml
# Store any object with relationships
memory/add:
  type: string        # "document", "analysis", "trend", "event"
  namespace: string   # "news/articles", "k8s/pods"
  data: object        # The content
  metadata: object    # Timestamps, source, etc.
  relations:          # Links to other objects
    - target_id: string
      relation_type: string  # "analyzed_from", "derived_from"

# Semantic search with filters
memory/search:
  type: string?
  namespace: string?
  query: string       # Semantic search query
  filters: object     # Field-level filters
  include_relations: bool
  limit: int

# Get by ID
memory/get:
  id: string
  include_relations: bool

# Create relationships between objects
memory/link:
  source_id: string
  target_id: string
  relation_type: string

# Deduplication helpers
memory/check_seen:
  key: string         # URL hash, content hash
  namespace: string

memory/mark_seen:
  key: string
  namespace: string
  ttl_seconds: int?
```

#### 2.1.2 Backend: mem0 + Neo4j

- **Vector storage**: Qdrant (via mem0)
- **Graph relationships**: Neo4j (via mem0 graph memory)
- **Dedup cache**: Redis

#### 2.1.3 Data Lineage Example

```
Raw Article (collected) ──analyzed_from──▶ Analysis ──trend_detected_in──▶ Trend
    │                                          │                              │
    └──────────── All linked via Neo4j graph ──┴──────────────────────────────┘
```

### 2.2 MCP Server Testing Strategy

**Each MCP server must pass all tests before skills can use it.**

#### 2.2.1 Layer 1 Test Categories

| Test Type | Purpose | Example |
|-----------|---------|---------|
| **Unit Tests** | Test individual tool handlers in isolation | `test_add_stores_document()` |
| **Backend Integration** | Test with real Qdrant/Neo4j/Redis | `test_search_returns_similar_documents()` |
| **MCP Protocol Tests** | Test SSE transport, tool discovery | `test_list_tools_returns_all_tools()` |
| **Error Handling** | Test graceful failure modes | `test_add_with_invalid_namespace_returns_error()` |
| **Performance Tests** | Baseline latency and throughput | `test_search_under_100ms_for_1000_docs()` |

#### 2.2.2 Memory MCP Test Suite

```python
# tests/mcp/memory/test_memory_mcp.py

class TestMemoryMCPUnit:
    """Unit tests - mocked backends"""

    def test_add_document_creates_embedding(self, mock_qdrant):
        """Verify embedding is generated and stored"""
        result = await memory.add(type="document", namespace="test", data={"text": "hello"})
        assert result["id"] is not None
        mock_qdrant.upsert.assert_called_once()

    def test_add_with_relations_creates_neo4j_edges(self, mock_neo4j):
        """Verify relations are stored in graph"""
        result = await memory.add(
            type="analysis",
            data={"summary": "test"},
            relations=[{"target_id": "doc-123", "relation_type": "analyzed_from"}]
        )
        mock_neo4j.create_relationship.assert_called_once()

    def test_check_seen_returns_false_for_new_key(self, mock_redis):
        """Verify new keys are not seen"""
        mock_redis.exists.return_value = False
        result = await memory.check_seen(key="new-hash", namespace="test")
        assert result["seen"] is False

    def test_search_includes_relations_when_requested(self, mock_qdrant, mock_neo4j):
        """Verify relations are fetched from Neo4j"""
        result = await memory.search(query="test", include_relations=True)
        assert "relations" in result["results"][0]

class TestMemoryMCPIntegration:
    """Integration tests - real backends (requires services running)"""

    @pytest.mark.integration
    async def test_add_and_search_round_trip(self, memory_client):
        """Store document, verify it's searchable"""
        # Add
        add_result = await memory_client.call_tool("add", {
            "type": "document",
            "namespace": "test",
            "data": {"title": "Test Article", "content": "AI news content"}
        })
        doc_id = add_result["id"]

        # Search
        search_result = await memory_client.call_tool("search", {
            "query": "AI news",
            "namespace": "test",
            "limit": 10
        })

        assert any(r["id"] == doc_id for r in search_result["results"])

    @pytest.mark.integration
    async def test_link_creates_traversable_relationship(self, memory_client):
        """Create two documents, link them, verify traversal"""
        doc1 = await memory_client.call_tool("add", {
            "type": "document",
            "namespace": "test",
            "data": {"title": "Original"}
        })
        doc2 = await memory_client.call_tool("add", {
            "type": "analysis",
            "namespace": "test",
            "data": {"summary": "Analysis of original"}
        })

        await memory_client.call_tool("link", {
            "source_id": doc2["id"],
            "target_id": doc1["id"],
            "relation_type": "analyzed_from"
        })

        # Get with relations
        result = await memory_client.call_tool("get", {
            "id": doc2["id"],
            "include_relations": True
        })

        assert len(result["relations"]) == 1
        assert result["relations"][0]["target_id"] == doc1["id"]

    @pytest.mark.integration
    async def test_dedup_prevents_duplicate_storage(self, memory_client):
        """Verify check_seen/mark_seen prevents duplicates"""
        key = "url-hash-12345"

        # First check - not seen
        result1 = await memory_client.call_tool("check_seen", {
            "key": key,
            "namespace": "test"
        })
        assert result1["seen"] is False

        # Mark as seen
        await memory_client.call_tool("mark_seen", {
            "key": key,
            "namespace": "test",
            "ttl_seconds": 3600
        })

        # Second check - seen
        result2 = await memory_client.call_tool("check_seen", {
            "key": key,
            "namespace": "test"
        })
        assert result2["seen"] is True

class TestMemoryMCPProtocol:
    """MCP protocol compliance tests"""

    @pytest.mark.integration
    async def test_list_tools_returns_all_memory_tools(self, sse_client):
        """Verify tool discovery works"""
        tools = await sse_client.list_tools()
        tool_names = {t.name for t in tools}

        assert "add" in tool_names
        assert "search" in tool_names
        assert "get" in tool_names
        assert "link" in tool_names
        assert "check_seen" in tool_names
        assert "mark_seen" in tool_names

    @pytest.mark.integration
    async def test_tool_schemas_are_valid_json_schema(self, sse_client):
        """Verify tool input schemas are valid"""
        tools = await sse_client.list_tools()
        for tool in tools:
            # Validate schema is proper JSON Schema
            jsonschema.Draft7Validator.check_schema(tool.inputSchema)
```

#### 2.2.3 Discord MCP Test Suite

```python
# tests/mcp/discord/test_discord_mcp.py

class TestDiscordMCPUnit:
    """Unit tests with mocked Discord API"""

    def test_send_message_formats_embed_correctly(self, mock_discord_api):
        """Verify embed structure matches Discord API spec"""
        await discord.send_message_to_channel_name(
            channel_name="test-channel",
            embed={"title": "Test", "color": 0xFF0000}
        )

        call_args = mock_discord_api.create_message.call_args
        assert "embeds" in call_args.kwargs
        assert call_args.kwargs["embeds"][0]["title"] == "Test"

    def test_add_reaction_handles_unicode_emoji(self, mock_discord_api):
        """Verify Unicode emoji is encoded correctly"""
        await discord.add_reaction(
            channel_id="123",
            message_id="456",
            emoji="✅"
        )

        mock_discord_api.add_reaction.assert_called_with(
            channel_id="123",
            message_id="456",
            emoji="%E2%9C%85"  # URL-encoded
        )

class TestDiscordMCPIntegration:
    """Integration tests with real Discord (test server)"""

    @pytest.mark.integration
    @pytest.mark.requires_discord
    async def test_send_and_receive_message(self, discord_client, test_channel_id):
        """Send message, verify it appears in channel"""
        result = await discord_client.call_tool("send_message", {
            "channel_id": test_channel_id,
            "content": f"Integration test {datetime.now().isoformat()}"
        })

        assert result["message_id"] is not None

        # Cleanup
        await discord_client.call_tool("delete_message", {
            "channel_id": test_channel_id,
            "message_id": result["message_id"]
        })
```

### 2.3 MCP Server Implementation Tasks

| Task | File | Description |
|------|------|-------------|
| 2.3.1 | `kubani/mcp/servers/memory/server.py` | Implement Memory MCP with FastMCP |
| 2.3.2 | `kubani/mcp/servers/memory/backends/mem0_backend.py` | mem0 integration with Qdrant |
| 2.3.3 | `kubani/mcp/servers/memory/backends/neo4j_backend.py` | Neo4j graph relationship storage |
| 2.3.4 | `kubani/mcp/servers/memory/backends/redis_backend.py` | Redis dedup cache |
| 2.3.5 | `tests/mcp/memory/test_unit.py` | Unit tests with mocked backends |
| 2.3.6 | `tests/mcp/memory/test_integration.py` | Integration tests with real backends |
| 2.3.7 | `tests/mcp/memory/test_protocol.py` | MCP protocol compliance tests |
| 2.3.8 | `tests/mcp/discord/test_unit.py` | Discord MCP unit tests |
| 2.3.9 | `tests/mcp/discord/test_integration.py` | Discord MCP integration tests |

### 2.4 MCP Server Validation Checklist

Before proceeding to Phase 3 (Skills), verify:

- [ ] Memory MCP `add` stores documents in Qdrant with embeddings
- [ ] Memory MCP `add` creates Neo4j nodes and relationships
- [ ] Memory MCP `search` returns semantically similar results
- [ ] Memory MCP `link` creates traversable graph edges
- [ ] Memory MCP `check_seen`/`mark_seen` deduplication works with TTL
- [ ] Memory MCP handles concurrent requests without data corruption
- [ ] Discord MCP `send_message` posts to correct channel
- [ ] Discord MCP `add_reaction` adds emoji to message
- [ ] Discord MCP `await_reaction` returns when user reacts
- [ ] All MCP servers expose correct tool schemas via `list_tools`
- [ ] All MCP servers return structured errors (not exceptions)

---

## Phase 3: Skill Development and Testing

**Skills are developed and tested AFTER MCP servers pass all tests.**

### 3.1 Skill Testing Strategy

#### 3.1.1 Layer 2 Test Categories

| Test Type | Purpose | Example |
|-----------|---------|---------|
| **Mocked MCP Tests** | Fast tests with mock tool responses | `test_fetch_stores_articles_with_mock_memory()` |
| **Real MCP Tests** | Integration with running MCP servers | `test_fetch_stores_to_real_memory()` |
| **LLM Evaluation Tests** | Verify skill produces correct output format | `test_skill_output_matches_schema()` |
| **Invocation Tests** | Verify correct tools are called | `test_skill_calls_memory_add_not_delete()` |
| **Negative Tests** | Verify skill rejects invalid inputs | `test_skill_rejects_empty_feed_list()` |

#### 3.1.2 Skill Test Case Format (v2)

```yaml
version: "2.0"

test_cases:
  - name: happy_path_fetch_rss
    description: Fetch and store articles from RSS feeds
    category: happy_path

    inputs:
      feeds:
        - url: "https://example.com/rss"
          name: "Example Feed"

    # Mocked MCP responses for unit tests
    mocks:
      memory.add:
        id: "doc-12345"
        success: true
      memory.check_seen:
        seen: false

    # Output assertions
    assertions:
      - type: schema
        schema:
          type: object
          required: [articles_fetched, articles_stored]
      - type: length
        field: articles
        operator: gte
        value: 1

    # Tool invocation assertions
    invocation_assertions:
      - type: tool_invoked
        tool: "rss/fetch"
      - type: tool_invoked
        tool: "memory/add"
      - type: tool_invoked_with
        tool: "memory/add"
        arguments:
          type: "document"
          namespace: "news/articles"
      - type: tool_not_invoked
        tool: "memory/delete"
        reason: "Fetch should only add, not delete"

  - name: negative_duplicate_article
    description: Should not store duplicate articles
    category: negative
    inputs:
      feeds:
        - url: "https://example.com/rss"
    mocks:
      memory.check_seen:
        seen: true  # Already seen
    assertions:
      - type: equals
        field: articles_stored
        value: 0
    invocation_assertions:
      - type: tool_not_invoked
        tool: "memory/add"
        reason: "Duplicate should not be stored"
```

### 3.2 Skill Evaluation with Real MCP

```python
# kubani/workflows/skill_auto/capabilities/skill_evaluator.py

class SkillEvaluator:
    """Evaluates skills with real or mocked MCP tools."""

    async def evaluate_skill(
        self,
        skill_path: Path,
        test_cases: list[dict],
        use_real_mcp: bool = False
    ) -> EvaluationResult:
        """
        Run skill test cases.

        Args:
            skill_path: Path to SKILL.md
            test_cases: Test case definitions
            use_real_mcp: If True, use real MCP servers; if False, use mocks
        """
        skill_content = skill_path.read_text()
        allowed_tools = self._extract_allowed_tools(skill_content)

        results = []
        for test_case in test_cases:
            # Build tools
            if use_real_mcp:
                tools = await self._create_mcp_clients(allowed_tools)
            else:
                tools = self._create_mock_tools(test_case.get("mocks", {}))

            # Create agent with tracking hooks
            tracker = ToolInvocationTracker()
            agent = Agent(
                system_prompt=skill_content,
                tools=tools,
                hooks={
                    "before_tool_invocation": tracker.before_tool_invocation,
                    "after_tool_invocation": tracker.after_tool_invocation,
                },
            )

            # Execute
            result = await agent.invoke_async(
                f"Execute skill with inputs: {test_case['inputs']}"
            )

            # Check assertions
            output_results = self._check_output_assertions(
                result, test_case.get("assertions", [])
            )
            invocation_results = self._check_invocation_assertions(
                tracker.invocations, test_case.get("invocation_assertions", [])
            )

            results.append(TestCaseResult(
                name=test_case["name"],
                passed=all(r.passed for r in output_results + invocation_results),
                output_assertions=output_results,
                invocation_assertions=invocation_results,
                tool_invocations=tracker.invocations,
            ))

        return EvaluationResult(
            skill_path=skill_path,
            test_results=results,
            pass_rate=sum(1 for r in results if r.passed) / len(results),
        )
```

### 3.3 Skill Implementation Tasks

| Task | File | Description |
|------|------|-------------|
| 3.3.1 | `kubani/workflows/skill_auto/capabilities/tool_tracker.py` | ToolInvocationTracker hook provider |
| 3.3.2 | `kubani/workflows/skill_auto/capabilities/mock_tools.py` | Mock tool factory for testing |
| 3.3.3 | `kubani/workflows/skill_auto/capabilities/skill_evaluator.py` | Skill evaluation with MCP integration |
| 3.3.4 | `kubani/workflows/skill_auto/capabilities/invocation_assertions.py` | Invocation assertion checker |
| 3.3.5 | Update all SKILL.md files | Add `allowed-tools`, remove embedded code |
| 3.3.6 | Update all test_cases.yaml files | Add v2 format with invocation assertions |

### 3.4 Skill Validation Checklist

Before proceeding to Phase 4 (Agents), verify for each skill:

- [ ] SKILL.md has `allowed-tools` in frontmatter
- [ ] SKILL.md body provides guidance, not embedded code
- [ ] All test cases pass with mocked MCP
- [ ] All test cases pass with real MCP servers
- [ ] Invocation assertions verify correct tool usage
- [ ] Negative test cases verify skill rejects invalid inputs
- [ ] Skill does not call tools outside `allowed-tools`

---

## Phase 4: Agent Development and Testing

**Agents are developed and tested AFTER all skills pass tests.**

### 4.1 Agent Testing Strategy

#### 4.1.1 Layer 3 Test Categories

| Test Type | Purpose | Example |
|-----------|---------|---------|
| **Orchestration Tests** | Verify agent calls correct skills | `test_feed_collector_uses_fetch_and_dedup_skills()` |
| **Integration Tests** | End-to-end with real skills and MCP | `test_feed_collector_stores_articles_in_memory()` |
| **Error Recovery Tests** | Verify graceful handling of failures | `test_agent_continues_after_one_feed_fails()` |
| **Performance Tests** | Verify agent completes within SLA | `test_agent_processes_100_feeds_under_5min()` |

#### 4.1.2 Agent Test Structure

```python
# tests/agents/test_feed_collector.py

class TestFeedCollectorOrchestration:
    """Test agent orchestrates skills correctly"""

    async def test_agent_uses_fetch_rss_skill(self, mock_skill_registry):
        """Verify agent invokes fetch-rss-feeds skill"""
        agent = FeedCollectorAgent()
        await agent.collect(feeds=[test_feed])

        assert mock_skill_registry.was_skill_invoked("fetch-rss-feeds")

    async def test_agent_deduplicates_via_memory(self, mock_memory_mcp):
        """Verify agent checks for duplicates before storing"""
        mock_memory_mcp.check_seen.return_value = {"seen": True}

        agent = FeedCollectorAgent()
        result = await agent.collect(feeds=[test_feed])

        # Should check but not store
        mock_memory_mcp.check_seen.assert_called()
        mock_memory_mcp.add.assert_not_called()

class TestFeedCollectorIntegration:
    """Integration tests with real skills and MCP"""

    @pytest.mark.integration
    async def test_end_to_end_collection(self, memory_mcp, test_feeds):
        """Full collection pipeline with real services"""
        agent = FeedCollectorAgent()
        result = await agent.collect(feeds=test_feeds)

        assert result["articles_stored"] > 0

        # Verify in memory
        search_result = await memory_mcp.search(
            query="AI news",
            namespace="news/articles"
        )
        assert len(search_result["results"]) > 0
```

### 4.2 Agent Implementation Tasks

| Task | File | Description |
|------|------|-------------|
| 4.2.1 | Refactor `FeedCollectorAgent` | Thin orchestrator using skills |
| 4.2.2 | Refactor `ContentAnalystAgent` | Thin orchestrator using skills |
| 4.2.3 | Refactor `TrendDetectorAgent` | Thin orchestrator using skills |
| 4.2.4 | Refactor `DigestComposerAgent` | Thin orchestrator using skills |
| 4.2.5 | Refactor `PublisherAgent` | Thin orchestrator using skills |
| 4.2.6 | `tests/agents/test_*.py` | Agent test suites |

### 4.3 Agent Validation Checklist

Before proceeding to Phase 5 (Syndicate), verify for each agent:

- [ ] Agent is thin orchestrator (~150 lines, not ~300+)
- [ ] Agent discovers and uses skills dynamically
- [ ] Agent orchestration tests pass with mocked skills
- [ ] Agent integration tests pass with real skills and MCP
- [ ] Agent handles skill failures gracefully
- [ ] Agent logs skill invocations for observability

---

## Phase 5: Syndicate Development and Testing

**Syndicate workflows are developed and tested AFTER all agents pass tests.**

### 5.1 Syndicate Testing Strategy

#### 5.1.1 Layer 4 Test Categories

| Test Type | Purpose | Example |
|-----------|---------|---------|
| **Workflow Tests** | Verify Temporal workflow executes correctly | `test_daily_digest_workflow_completes()` |
| **Activity Tests** | Verify activities call agents correctly | `test_collect_activity_invokes_feed_collector()` |
| **End-to-End Tests** | Full syndicate with all real services | `test_syndicate_produces_digest_in_discord()` |
| **Failure Recovery Tests** | Verify workflow handles activity failures | `test_workflow_retries_failed_collection()` |

#### 5.1.2 News Digest Syndicate Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     NEWS DIGEST SYNDICATE                                │
│                                                                         │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
│  │  FeedCollector  │    │ ContentAnalyst  │    │  TrendDetector  │     │
│  │                 │    │                 │    │                 │     │
│  │ Skills:         │    │ Skills:         │    │ Skills:         │     │
│  │ • fetch-rss     │    │ • analyze-      │    │ • detect-trends │     │
│  │ • fetch-arxiv   │    │   article       │    │ • identify-     │     │
│  │ • fetch-github  │    │                 │    │   breaking-news │     │
│  │                 │    │                 │    │                 │     │
│  │ Tools:          │    │ Tools:          │    │ Tools:          │     │
│  │ • rss           │    │ • use_llm       │    │ • use_llm       │     │
│  │ • http_request  │    │ • memory/add    │    │ • memory/search │     │
│  │ • memory/add    │    │ • memory/link   │    │ • memory/add    │     │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘     │
│           │                      │                      │               │
│           ▼                      ▼                      ▼               │
│  ┌───────────────────────────────────────────────────────────────┐     │
│  │                    MEMORY MCP (mem0 + Neo4j)                  │     │
│  │                                                               │     │
│  │   Raw Articles ──────▶ Analyses ──────▶ Trends               │     │
│  │   (type: doc)        (type: analysis)  (type: trend)         │     │
│  └───────────────────────────────────────────────────────────────┘     │
│           │                      │                      │               │
│           ▼                      ▼                      ▼               │
│  ┌─────────────────┐    ┌─────────────────┐                           │
│  │ DigestComposer  │    │   Publisher     │                           │
│  │                 │    │                 │                           │
│  │ Skills:         │    │ Skills:         │                           │
│  │ • compose-      │    │ • publish-      │                           │
│  │   digest        │    │   discord       │                           │
│  │                 │    │                 │                           │
│  │ Tools:          │    │ Tools:          │                           │
│  │ • use_llm       │    │ • discord/*     │                           │
│  │ • memory/search │    │ • memory/add    │                           │
│  └─────────────────┘    └─────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Temporal Workflow

```python
@workflow.defn
class NewsDailyDigestWorkflow:
    @workflow.run
    async def run(self):
        # 1. Collect (parallel) - stores to Memory MCP
        await asyncio.gather(
            workflow.execute_activity(collect_rss_feeds_activity),
            workflow.execute_activity(collect_arxiv_activity),
            workflow.execute_activity(collect_github_trending_activity),
        )

        # 2. Analyze - links analyses to raw articles
        await workflow.execute_activity(analyze_articles_activity)

        # 3. Detect trends & breaking news (parallel)
        trends, breaking = await asyncio.gather(
            workflow.execute_activity(detect_trends_activity),
            workflow.execute_activity(identify_breaking_activity),
        )

        # 4. Publish breaking news immediately
        if breaking:
            await workflow.execute_activity(publish_breaking_activity)

        # 5. Compose and publish digest
        digest = await workflow.execute_activity(compose_digest_activity)
        await workflow.execute_activity(publish_digest_activity, digest=digest)
```

### 5.3 Data Flow Through Memory MCP

```
1. Collection: rss/fetch → memory/add(type="document") → Raw article stored
2. Analysis:   memory/search(type="document") → use_llm → memory/add(type="analysis") + memory/link
3. Trends:     memory/search(type="analysis") → use_llm → memory/add(type="trend") + memory/link
4. Publish:    memory/search(types=["analysis","trend"]) → use_llm → discord/send_embed
```

### 5.4 Syndicate Test Structure

```python
# tests/syndicates/test_news_digest.py

class TestNewsDailyDigestWorkflow:
    """Temporal workflow tests"""

    @pytest.mark.integration
    async def test_workflow_executes_all_activities(self, temporal_client, mock_agents):
        """Verify workflow runs all activities in correct order"""
        handle = await temporal_client.start_workflow(
            NewsDailyDigestWorkflow.run,
            id="test-digest-workflow",
            task_queue="news-digest-queue",
        )

        result = await handle.result()

        # Verify all activities were called
        assert mock_agents.feed_collector.collect.called
        assert mock_agents.content_analyst.analyze.called
        assert mock_agents.trend_detector.detect.called
        assert mock_agents.digest_composer.compose.called
        assert mock_agents.publisher.publish.called

    @pytest.mark.integration
    async def test_workflow_retries_failed_activity(self, temporal_client, flaky_collector):
        """Verify workflow retries on transient failure"""
        flaky_collector.fail_count = 2  # Fail twice then succeed

        handle = await temporal_client.start_workflow(
            NewsDailyDigestWorkflow.run,
            id="test-retry-workflow",
        )

        result = await handle.result()

        assert result["success"] is True
        assert flaky_collector.call_count == 3  # 2 failures + 1 success

class TestNewsSyndicateEndToEnd:
    """Full end-to-end tests"""

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_full_digest_pipeline(
        self, temporal_client, memory_mcp, discord_mcp, test_feeds
    ):
        """Run complete digest generation with real services"""
        # Start workflow
        handle = await temporal_client.start_workflow(
            NewsDailyDigestWorkflow.run,
            id=f"e2e-digest-{datetime.now().isoformat()}",
        )

        result = await handle.result()

        # Verify articles in memory
        articles = await memory_mcp.search(
            type="document",
            namespace="news/articles",
            limit=100
        )
        assert len(articles["results"]) > 0

        # Verify analyses linked to articles
        analyses = await memory_mcp.search(
            type="analysis",
            include_relations=True,
            limit=100
        )
        for analysis in analyses["results"]:
            assert len(analysis["relations"]) > 0
            assert analysis["relations"][0]["relation_type"] == "analyzed_from"

        # Verify digest was posted to Discord
        # (Check Discord test channel for message)
```

### 5.5 Syndicate Implementation Tasks

| Task | File | Description |
|------|------|-------------|
| 5.5.1 | `kubani/syndicates/news_digest/workflows.py` | Update workflow to use new agents |
| 5.5.2 | `kubani/syndicates/news_digest/activities.py` | Update activities to use new agents |
| 5.5.3 | `tests/syndicates/test_news_digest.py` | Workflow and activity tests |
| 5.5.4 | `tests/syndicates/test_e2e.py` | End-to-end syndicate tests |

### 5.6 Syndicate Validation Checklist

Final validation before deployment:

- [ ] Temporal workflow executes all activities in correct order
- [ ] Activities invoke agents correctly
- [ ] Data flows through Memory MCP with correct relationships
- [ ] Breaking news is published immediately
- [ ] Daily digest is composed and published
- [ ] Workflow handles activity failures with retries
- [ ] End-to-end test produces digest in Discord

---

## Phase 6: Updated News Skills

### 6.1 Skills Summary

| Skill | Status | allowed-tools |
|-------|--------|---------------|
| `fetch-rss-feeds` | **Keep** | `rss`, `memory/add`, `memory/check_seen`, `memory/mark_seen` |
| `fetch-arxiv-papers` | **Keep** | `rss`, `memory/add`, `memory/check_seen`, `memory/mark_seen` |
| `fetch-github-trending` | **Keep** | `http_request`, `memory/add`, `memory/check_seen`, `memory/mark_seen` |
| `deduplicate-articles` | **Deprecate** | Auto-dedup via Memory MCP |
| `filter-ai-relevant` | **Deprecate** | Merge into `analyze-article` |
| `analyze-article` | **Keep** | `use_llm`, `memory/add`, `memory/link` |
| `detect-trends` | **Keep** | `use_llm`, `memory/search`, `memory/add` |
| `identify-breaking-news` | **Keep** | `use_llm`, `memory/search` |
| `compose-digest` | **Keep** | `use_llm`, `memory/search` |
| `publish-discord` | **Keep** | `discord/*`, `memory/add` |

### 6.2 General Skills Summary

| Skill | Status | allowed-tools |
|-------|--------|---------------|
| `send-discord-notification` | **Keep** | `discord/send_message_to_channel_name` |
| `request-discord-approval` | **Keep** | `discord/send_message_to_channel_name`, `discord/add_reaction`, `discord/await_reaction` |
| `store-memory` | **Keep** | `memory/add` |
| `search-memory` | **Keep** | `memory/search` |

### 6.3 Deprecations

**deduplicate-articles**: Memory MCP handles dedup automatically via `memory/check_seen` and `memory/mark_seen` during store operations.

**filter-ai-relevant**: Relevance scoring merged into `analyze-article` as single LLM call is more efficient.

---

## Critical Files Summary

### New Files to Create

**Memory MCP Server:**
- `kubani/mcp/servers/memory/server.py` - Memory MCP with FastMCP
- `kubani/mcp/servers/memory/backends/mem0_backend.py` - mem0 integration
- `kubani/mcp/servers/memory/backends/neo4j_backend.py` - Neo4j relationships
- `kubani/mcp/servers/memory/backends/redis_backend.py` - Redis dedup cache

**MCP Server Tests:**
- `tests/mcp/memory/test_unit.py` - Unit tests with mocked backends
- `tests/mcp/memory/test_integration.py` - Integration tests with real backends
- `tests/mcp/memory/test_protocol.py` - MCP protocol compliance
- `tests/mcp/discord/test_unit.py` - Discord MCP unit tests
- `tests/mcp/discord/test_integration.py` - Discord MCP integration tests

**Skill Evaluation:**
- `kubani/workflows/skill_auto/capabilities/tool_tracker.py` - Hook provider
- `kubani/workflows/skill_auto/capabilities/mock_tools.py` - Mock tool factory
- `kubani/workflows/skill_auto/capabilities/skill_evaluator.py` - Skill evaluation
- `kubani/workflows/skill_auto/capabilities/invocation_assertions.py` - Assertion checker

### Files to Modify

**Skills (add allowed-tools, remove embedded code):**
- All 12 skills listed in Phase 6

**Agents (thin orchestrators):**
- `kubani/agents/feed_collector/`
- `kubani/agents/content_analyst/`
- `kubani/agents/trend_detector/`
- `kubani/agents/digest_composer/`
- `kubani/agents/publisher/`

**Syndicate:**
- `kubani/syndicates/news_digest/workflows.py`
- `kubani/syndicates/news_digest/activities.py`

---

## Verification Plan

### Layer 1: MCP Server Tests
```bash
# Unit tests (fast, mocked backends)
pytest tests/mcp/memory/test_unit.py
pytest tests/mcp/discord/test_unit.py

# Integration tests (requires Qdrant, Neo4j, Redis, Discord)
pytest tests/mcp/memory/test_integration.py -m integration
pytest tests/mcp/discord/test_integration.py -m integration

# Protocol compliance
pytest tests/mcp/*/test_protocol.py -m integration
```

### Layer 2: Skill Tests
```bash
# With mocked MCP (fast)
kubani skill auto --evaluate kubani/skills/news/ --mock

# With real MCP (requires running servers)
kubani skill auto --evaluate kubani/skills/news/ --use-mcp
```

### Layer 3: Agent Tests
```bash
# Orchestration tests (mocked skills)
pytest tests/agents/ -m "not integration"

# Integration tests (real skills and MCP)
pytest tests/agents/ -m integration
```

### Layer 4: Syndicate Tests
```bash
# Workflow tests (mocked agents)
pytest tests/syndicates/ -m "not e2e"

# End-to-end tests (all real services)
pytest tests/syndicates/test_e2e.py -m e2e
```

---

## Success Criteria

| Layer | Criterion | Target |
|-------|-----------|--------|
| **MCP** | Memory MCP all tests pass | 100% |
| **MCP** | Discord MCP all tests pass | 100% |
| **Skills** | All skills use `allowed-tools` | 100% |
| **Skills** | All skill tests pass (mocked) | 100% |
| **Skills** | All skill tests pass (real MCP) | 100% |
| **Agents** | All agents are thin orchestrators | ~150 lines each |
| **Agents** | All agent tests pass | 100% |
| **Syndicate** | Workflow executes correctly | Working |
| **Syndicate** | End-to-end test produces digest | Working |

## Implementation Order

**Bottom-up, layer by layer:**

1. **Layer 1: MCP Servers**
   - Implement Memory MCP with mem0 + Neo4j
   - Write unit and integration tests
   - Verify all tests pass

2. **Layer 2: Skills**
   - Update skill frontmatter with `allowed-tools`
   - Rewrite skill bodies (remove embedded code)
   - Update test cases to v2 format
   - Verify all skill tests pass

3. **Layer 3: Agents**
   - Refactor agents to thin orchestrators
   - Write agent tests
   - Verify all agent tests pass

4. **Layer 4: Syndicate**
   - Update Temporal workflow
   - Write syndicate tests
   - Verify end-to-end test passes

5. **Deprecate**
   - Remove `deduplicate-articles` skill
   - Remove `filter-ai-relevant` skill
