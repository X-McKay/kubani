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

## Phase 2: Memory MCP Design (mem0-inspired)

### 2.1 Generic Interface (Not Domain-Specific)

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

### 2.2 Backend: mem0 + Neo4j

- **Vector storage**: Qdrant (via mem0)
- **Graph relationships**: Neo4j (via mem0 graph memory)
- **Dedup cache**: Redis

### 2.3 Data Lineage Example

```
Raw Article (collected) ──analyzed_from──▶ Analysis ──trend_detected_in──▶ Trend
    │                                          │                              │
    └──────────── All linked via Neo4j graph ──┴──────────────────────────────┘
```

---

## Phase 3: Real Agent Skill Evaluation

### 3.1 Architecture Overview

```
Current (LLM Simulation):
SKILL.md → Agent(system_prompt=SKILL.md) → LLM generates JSON → Check assertions

Proposed (Real MCP via Strands SDK):
SKILL.md → Agent(system_prompt, tools=[MCPClient], hooks=[ToolTracker])
         → Agent calls real MCP tools
         → AgentResult.metrics.tool_metrics + hook data
         → Check assertions + invocations
```

### 3.2 Leveraging Strands SDK Built-in Features

**NO custom MCPToolWrapper needed.** Strands provides everything:

#### 3.2.1 MCPClient as ToolProvider

```python
from strands import Agent
from strands.tools.mcp import MCPClient
from mcp.client.sse import sse_client

# Create MCP client for SSE transport (our MCP servers use SSE)
def create_discord_transport():
    return sse_client("https://discord-mcp.almckay.io/sse")

discord_client = MCPClient(create_discord_transport)

# Pass directly to Agent - Strands manages lifecycle
agent = Agent(
    model=model,
    system_prompt=skill_sop,
    tools=[discord_client],  # MCPClient implements ToolProvider
)
```

#### 3.2.2 Tool Invocation Tracking via Hooks

```python
from strands.hooks import BeforeToolInvocationEvent, AfterToolInvocationEvent

@dataclass
class ToolInvocation:
    tool_name: str
    arguments: dict
    result: Any
    success: bool
    duration_ms: float

class ToolInvocationTracker:
    """Hook provider to capture tool invocations."""

    def __init__(self):
        self.invocations: list[ToolInvocation] = []
        self._current_tool: dict = {}

    def before_tool_invocation(self, event: BeforeToolInvocationEvent):
        """Capture tool name and arguments before invocation."""
        self._current_tool = {
            "tool_name": event.tool.name,
            "arguments": event.tool_use.get("input", {}),
            "start_time": time.time(),
        }

    def after_tool_invocation(self, event: AfterToolInvocationEvent):
        """Capture result after invocation."""
        if self._current_tool:
            invocation = ToolInvocation(
                tool_name=self._current_tool["tool_name"],
                arguments=self._current_tool["arguments"],
                result=event.result,
                success=event.result.get("status") != "error",
                duration_ms=(time.time() - self._current_tool["start_time"]) * 1000,
            )
            self.invocations.append(invocation)
            self._current_tool = {}
```

#### 3.2.3 Accessing Metrics After Execution

```python
result = await agent.invoke_async(prompt)

# Get tool usage from metrics
tool_metrics = result.metrics.tool_metrics
for tool_name, metrics in tool_metrics.items():
    print(f"{tool_name}: {metrics.call_count} calls, {metrics.success_rate}% success")

# Get full summary
summary = result.metrics.get_summary()
print(f"Tools used: {summary['tool_usage'].keys()}")
```

### 3.3 Mock MCP Provider for Testing

For unit tests, create mock tool functions that mimic MCP responses:

```python
from strands import tool

def create_mock_tools(mocks: dict) -> list:
    """Create mock tools from test case mocks section."""
    tools = []

    for mock_path, response in mocks.items():
        server, tool_name = mock_path.split(".")
        full_name = f"{server}__{tool_name}"  # Strands naming convention

        @tool(name=full_name)
        def mock_tool(**kwargs) -> dict:
            return response

        tools.append(mock_tool)

    return tools
```

### 3.4 Implementation Tasks

| Task | File | Description |
|------|------|-------------|
| 3.4.1 | `kubani/workflows/skill_auto/capabilities/tool_tracker.py` | Create ToolInvocationTracker hook provider |
| 3.4.2 | `kubani/workflows/skill_auto/capabilities/mock_tools.py` | Create mock tool factory for testing |
| 3.4.3 | `kubani/workflows/skill_auto/capabilities/mcp_evaluator.py` | Create evaluation agent using real MCPClient |
| 3.4.4 | `kubani/workflows/skill_auto/capabilities/llm_evaluator.py` | Add `use_mcp` flag, integrate with new components |

---

## Phase 4: Enhanced Test Case Structure

### 4.1 New Test Case Format (v2)

```yaml
version: "2.0"

test_cases:
  - name: happy_path_publish
    description: Publish message to Discord
    category: happy_path

    # === Input/Output ===
    inputs:
      message: "Daily AI News"
      channel_id: "123"

    # === Mocked MCP Responses (for unit tests) ===
    mocks:
      discord.send_message:
        success: true
        message_id: "msg-001"

    # === Output Assertions (existing) ===
    assertions:
      - type: equals
        field: status
        value: "success"

    # === NEW: Invocation Assertions ===
    invocation_assertions:
      - type: tool_invoked
        tool: "discord/send_message"
      - type: tool_invoked_with
        tool: "discord/send_message"
        arguments:
          channel_id: "123"
      - type: tool_not_invoked
        tool: "memory/store"
        reason: "Publishing should not access memory"

    # === NEW: Skill Invocation Appropriateness ===
    invocation:
      should_invoke: true

  - name: negative_empty_message
    description: Should not invoke for empty message
    category: negative
    inputs:
      message: ""
    invocation:
      should_invoke: false
      rejection_reason: "Empty message should be rejected"
```

### 4.2 New Assertion Types

| Type | Purpose | Example |
|------|---------|---------|
| `tool_invoked` | Verify tool was called | `tool: "discord/send_message"` |
| `tool_not_invoked` | Verify tool was NOT called | `tool: "kubernetes/pods_delete"` |
| `tool_invoked_with` | Verify tool called with args | `arguments: {channel_id: "123"}` |
| `invocation_count` | Verify call count | `count: 3` |
| `call_sequence` | Verify order | `sequence: [memory.search, discord.send]` |
| `schema` | JSON Schema validation | `schema: {type: object, required: [...]}` |
| `length` | Array/string length | `operator: gte, value: 5` |
| `regex` | Pattern matching | `pattern: "\\d{4}-\\d{2}-\\d{2}"` |

### 4.3 Implementation Tasks

| Task | File | Description |
|------|------|-------------|
| 4.3.1 | `kubani/workflows/skill_auto/capabilities/invocation_assertions.py` | Create invocation assertion checker |
| 4.3.2 | `kubani/workflows/skill_auto/capabilities/llm_evaluator.py` | Add schema, length, regex assertion types |
| 4.3.3 | `kubani/workflows/skill_auto/capabilities/draft_test_cases.py` | Update Pydantic models for v2 format |
| 4.3.4 | `kubani/workflows/skill_auto/models.py` | Add MCPExpectation, InvocationSpec models |

---

## Phase 5: Updated News Skills

### 5.1 Skills Summary

| Skill | Status | allowed-tools |
|-------|--------|---------------|
| `fetch-rss-feeds` | **Keep** | `rss`, `memory/add` |
| `fetch-arxiv-papers` | **Keep** | `rss`, `memory/add` |
| `fetch-github-trending` | **Keep** | `http_request`, `memory/add` |
| `deduplicate-articles` | **Deprecate** | Auto-dedup via Memory MCP |
| `filter-ai-relevant` | **Deprecate** | Merge into `analyze-article` |
| `analyze-article` | **Keep** | `use_llm`, `memory/add`, `memory/link` |
| `detect-trends` | **Keep** | `use_llm`, `memory/search`, `memory/add` |
| `identify-breaking-news` | **Keep** | `use_llm`, `memory/search` |
| `compose-digest` | **Keep** | `use_llm`, `memory/search` |
| `publish-discord` | **Keep** | `discord/*`, `memory/add` |

### 5.2 General Skills Summary

| Skill | Status | allowed-tools |
|-------|--------|---------------|
| `send-discord-notification` | **Keep** | `discord/send_message_to_channel_name` |
| `request-discord-approval` | **Keep** | `discord/send_message_to_channel_name`, `discord/add_reaction`, `discord/await_reaction` |
| `store-memory` | **Keep** | `memory/add` |
| `search-memory` | **Keep** | `memory/search` |

### 5.3 Key Changes Per Skill

**fetch-rss-feeds:**
- Use Strands `rss` tool instead of embedded feedparser code
- Store via `memory/add(type="document", namespace="news/articles")`

**analyze-article:**
- Add `relevance_score` and `is_ai_relevant` to output (absorbs filter-ai-relevant)
- Use `use_llm` tool for analysis
- Link analysis to original article via `memory/link`

**detect-trends:**
- Use `use_llm` for intelligent trend identification
- Query analyzed articles via `memory/search(type="analysis")`
- Store trends linked to source articles

**compose-digest:**
- Use `use_llm` to write human-readable digest
- Query articles and trends from Memory MCP

**store-memory / search-memory:**
- Replace tier-specific methods (`memory.add_working`, `memory.search_episodic`, etc.)
- Use generic `memory/add` and `memory/search` with type/namespace parameters

### 5.4 Deprecations

**deduplicate-articles**: Memory MCP handles dedup automatically via `memory/check_seen` and `memory/mark_seen` during store operations.

**filter-ai-relevant**: Relevance scoring merged into `analyze-article` as single LLM call is more efficient.

---

## Phase 6: Integration with Existing Evaluator

### 6.1 Modified Evaluation Flow

```python
# kubani/workflows/skill_auto/capabilities/llm_evaluator.py

async def _run_test_case(self, skill_sop: str, test_case: dict, config) -> TestResult:
    tracker = ToolInvocationTracker()

    # Build tools (mocked or real MCP based on config)
    if self.use_mcp:
        if self.use_mocks:
            tools = create_mock_tools(test_case.get("mocks", {}))
        else:
            mcp_servers = self._extract_mcp_servers(skill_sop)
            tools = [self._get_mcp_client(server) for server in mcp_servers]
    else:
        tools = []

    # Create agent with tools and hook
    agent = Agent(
        model=model,
        system_prompt=self._build_prompt(skill_sop),
        tools=tools,
        hooks={"before_tool_invocation": tracker.before_tool_invocation,
               "after_tool_invocation": tracker.after_tool_invocation},
    )

    # Execute
    result = await agent.invoke_async(f"Execute with: {inputs}")
    output = self._parse_result(result)

    # Check output assertions (existing)
    output_results = check_assertions(output, test_case.get("assertions", []))

    # Check invocation assertions (NEW) - use tracker.invocations or result.metrics
    invocation_results = check_invocation_assertions(
        tracker.invocations,
        test_case.get("invocation_assertions", [])
    )

    # Combine results
    all_passed = all(r.passed for r in output_results + invocation_results)

    return TestResult(
        passed=all_passed,
        assertions_passed=[...],
        assertions_failed=[...],
        tool_metrics=result.metrics.tool_metrics,  # Include Strands metrics
        invocations=tracker.invocations,
    )
```

### 6.2 Backward Compatibility

- `version: "1.0"` (or missing): Use existing LLM simulation
- `version: "2.0"`: Use new MCP-integrated evaluation
- `use_mcp=False` flag: Force old behavior

---

## Phase 7: News Digest Syndicate Architecture

### 7.1 Agents & Skills Mapping

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

### 7.2 Temporal Workflow

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

### 7.3 Data Flow Through Memory MCP

```
1. Collection: rss/fetch → memory/add(type="document") → Raw article stored
2. Analysis:   memory/search(type="document") → use_llm → memory/add(type="analysis") + memory/link
3. Trends:     memory/search(type="analysis") → use_llm → memory/add(type="trend") + memory/link
4. Publish:    memory/search(types=["analysis","trend"]) → use_llm → discord/send_embed
```

---

## Critical Files Summary

### New Files to Create

**Memory MCP Server:**
- `kubani/mcp/servers/memory/server.py` - Memory MCP with mem0 + Neo4j backend
- `kubani/mcp/servers/memory/mem0_backend.py` - mem0 integration with graph memory

**Skill Evaluation:**
- `kubani/workflows/skill_auto/capabilities/tool_tracker.py` - Hook provider for invocation tracking
- `kubani/workflows/skill_auto/capabilities/mock_tools.py` - Mock tool factory
- `kubani/workflows/skill_auto/capabilities/invocation_assertions.py` - Invocation assertion checker

### Files to Modify

**Skills to Rewrite (add allowed-tools, remove embedded code):**
- `kubani/skills/news/collection/fetch-rss-feeds/SKILL.md`
- `kubani/skills/news/collection/fetch-arxiv-papers/SKILL.md`
- `kubani/skills/news/collection/fetch-github-trending/SKILL.md`
- `kubani/skills/news/analysis/analyze-article/SKILL.md` (add relevance scoring)
- `kubani/skills/news/analysis/detect-trends/SKILL.md`
- `kubani/skills/news/analysis/identify-breaking-news/SKILL.md`
- `kubani/skills/news/publishing/compose-digest/SKILL.md`
- `kubani/skills/news/publishing/publish-discord/SKILL.md`
- `kubani/skills/general/notifications/send-discord-notification/SKILL.md`
- `kubani/skills/general/notifications/request-discord-approval/SKILL.md`
- `kubani/skills/general/memory/store-memory/SKILL.md`
- `kubani/skills/general/memory/search-memory/SKILL.md`

**Skills to Deprecate:**
- `kubani/skills/news/collection/deduplicate-articles/` (auto-dedup in Memory MCP)
- `kubani/skills/news/collection/filter-ai-relevant/` (merged into analyze-article)

**Evaluation System:**
- `kubani/workflows/skill_auto/capabilities/llm_evaluator.py` - Add tool invocation support
- `kubani/workflows/skill_auto/utils.py` - Validate allowed-tools frontmatter

---

## Verification Plan

### Unit Tests
```bash
# Test tool invocation tracker
pytest kubani/workflows/skill_auto/capabilities/test_tool_tracker.py

# Test invocation assertions
pytest kubani/workflows/skill_auto/capabilities/test_invocation_assertions.py

# Test skill format validation
pytest tests/skills/test_skill_format.py
```

### Integration Tests
```bash
# Run skill evaluation with mocked MCP
kubani skill auto --evaluate kubani/skills/news/publishing/publish-discord --use-mcp --mock

# Run skill evaluation with real MCP (requires running servers)
kubani skill auto --evaluate kubani/skills/news/publishing/publish-discord --use-mcp
```

### Validation Checklist
- [ ] Skills declare `allowed-tools` in frontmatter
- [ ] `mcp_tool:` references use short server names
- [ ] Test cases include `invocation_assertions` for MCP-using skills
- [ ] Negative test cases verify skills are NOT invoked inappropriately
- [ ] Evaluation captures and validates actual MCP tool calls via Strands hooks/metrics

---

## Success Criteria

| Criterion | Target |
|-----------|--------|
| All skills use `allowed-tools` frontmatter | 100% |
| Memory MCP supports generic operations (not domain-specific) | ✓ |
| Memory MCP integrates mem0 with Neo4j for relationships | ✓ |
| Skills use Strands tools (rss, http_request, use_llm) where available | 100% |
| Deprecated skills removed (deduplicate-articles, filter-ai-relevant) | ✓ |
| Evaluation captures tool invocations via Strands hooks | Working |
| News Digest Syndicate workflow functional end-to-end | Working |

## Implementation Order

1. **Memory MCP Server** - Foundation for all storage
2. **Update skill frontmatter** - Add allowed-tools to all skills
3. **Rewrite skill bodies** - Replace embedded code with tool guidance
4. **Update test cases** - Add invocation assertions
5. **Integrate with syndicate** - Update activities to use new skills
