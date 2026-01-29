# News Digest Syndicate: Architecture Analysis

**Date:** 2026-01-28
**Status:** Analysis Document for Review
**Purpose:** Holistic review of syndicate architecture before proceeding with fixes

---

## Executive Summary

The News Digest Syndicate is an autonomous AI news collection and publishing system. After analysis, the system's **architecture is sound but its execution is broken** due to MCP transport issues. However, this analysis reveals **significant opportunities for simplification** that we should consider before fixing the current implementation.

### Key Findings

1. **Architecture is sound**: The two-workflow pattern (collection + digest) is appropriate for the use case
2. **Agents are well-designed**: Each agent has clear responsibility and clean interfaces
3. **However: Significant complexity exists** that may not be necessary
4. **The MCP client transport is fundamentally broken** (404 errors on all calls)
5. **Some Memory MCP tools don't exist** (activities call non-existent server methods)

### Recommendation

Before implementing the fix plan, we should discuss whether the current level of complexity is justified. There are simpler approaches that might serve the same goals.

---

## Part 1: What Problem Is the Syndicate Solving?

### Core Mission

Provide AI practitioners with **timely, curated AI news** without manual effort:

1. **Continuous collection** from RSS feeds, arXiv papers, and GitHub trending repos
2. **Intelligent analysis** to identify importance, trends, and breaking news
3. **Automated publishing** of executive-style digests to Discord
4. **Breaking news alerts** for high-importance developments

### Value Proposition

- Saves practitioners from manually scanning dozens of sources
- Filters signal from noise (AI-relevant content from general tech)
- Provides trend analysis (what's rising, what's fading)
- Delivers digestible summaries rather than raw article links

---

## Part 2: Current Architecture

### Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    News Digest Syndicate                            │
│                    Temporal: namespace=default, queue=news-digest   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                │                               │
                ▼                               ▼
    ┌───────────────────────┐       ┌───────────────────────┐
    │  NewsCollectionWF     │       │   NewsDigestWF        │
    │  (every 15 minutes)   │       │   (7am & 3pm daily)   │
    └───────────────────────┘       └───────────────────────┘
                │                               │
    ┌───────────┴──────────┐           ┌───────┴───────┐
    │                      │           │               │
    ▼                      ▼           ▼               ▼
[FeedCollector]    [ResearchCollector]  [ContentAnalyst]  [DigestPublisher]
    │                      │               │               │
    ▼                      ▼               ▼               ▼
[RSS Feeds]        [arXiv, GitHub]   [LLM Analysis]  [Discord MCP]
                           │
                           ▼
                    [Memory MCP]
                    (store articles)
```

### Workflow 1: NewsCollectionWorkflow

**Schedule:** Every 15 minutes
**Purpose:** Gather fresh content from all sources

**Phases:**
1. Collect from RSS feeds (FeedCollectorAgent)
2. Collect research papers from arXiv (ResearchCollectorAgent)
3. Collect trending repos from GitHub (ResearchCollectorAgent)
4. Store articles with deduplication (Memory MCP)
5. Check for breaking news (ContentAnalystAgent)

### Workflow 2: NewsDigestWorkflow

**Schedule:** 7am and 3pm daily
**Purpose:** Compose and publish curated digests

**Phases:**
1. Query articles from Memory MCP
2. Analyze articles for trends (ContentAnalystAgent)
3. Analyze research papers (ResearchAnalystAgent)
4. Analyze repos for spotlights (ResearchAnalystAgent)
5. Compose executive digest (DigestPublisherAgent)
6. Publish to Discord (Discord MCP)
7. Store trend snapshot for historical comparison

---

## Part 3: Agent Inventory

### Agent 1: FeedCollectorAgent

**Location:** `kubani/agents/feed_collector/`
**Lines of Code:** ~314
**Purpose:** Fetch articles from configured RSS feeds

**Key Features:**
- Persistent deduplication via Redis (7-day TTL)
- Within-run deduplication (same article from multiple feeds)
- AI relevance filtering for general tech feeds
- Configurable max age (default: 24 hours)

**Interface:**
```python
async def collect() -> CollectionResult
async def collect_as_dicts() -> list[dict]  # For Temporal
```

**Complexity Assessment:** **Appropriate**
- Deduplication is necessary (same news appears in multiple feeds)
- Age filtering is necessary (avoid stale news)
- Relevance filtering is necessary (general tech → AI-relevant)

---

### Agent 2: ContentAnalystAgent

**Location:** `kubani/agents/content_analyst/`
**Lines of Code:** ~777
**Purpose:** Analyze articles for insights, trends, and breaking news

**Key Features:**
- Parallel LLM analysis (8 concurrent workers)
- Content hash deduplication
- Breaking news detection (importance ≥ 8)
- Trend analysis across articles
- Historical trend comparison

**Interface:**
```python
async def analyze_articles(articles, deduplicate=True) -> AnalysisResult
async def detect_breaking_news(articles) -> list[ProcessedArticle]
async def analyze_trends(articles, hot_threshold=3) -> list[TrendingTopic]
async def analyze_trends_historical(articles, lookback_days=14) -> dict
async def full_analysis(articles) -> AnalysisResult
```

**Complexity Assessment:** **High - Potentially Over-Engineered**

This agent does a lot:
1. LLM-based article analysis (summary, category, entities, importance)
2. Breaking news detection
3. Trend analysis (current)
4. Historical trend analysis (velocity calculation)
5. Trend snapshot storage

**Question to Discuss:** Do we need historical trend analysis with velocity calculation? Is "what's trending right now" sufficient, or do we need "what's accelerating vs. decelerating"?

---

### Agent 3: ResearchCollectorAgent

**Location:** `kubani/agents/research_collector/`
**Lines of Code:** ~400 (estimated)
**Purpose:** Fetch papers from arXiv and trending repos from GitHub

**Key Features:**
- Rate limiting (GitHub: 60/hour, arXiv: 3s delay)
- Persistent deduplication (30 days papers, 14 days repos)
- Trending score calculation for repos

**Complexity Assessment:** **Appropriate**
- Rate limiting is necessary (API limits)
- Deduplication is necessary (avoid repeating same papers)

---

### Agent 4: ResearchAnalystAgent

**Location:** `kubani/agents/research_analyst/`
**Lines of Code:** ~500 (estimated)
**Purpose:** Deep analysis of papers and repos for digest inclusion

**Key Features:**
- LLM-based paper analysis (research type, main claim, practitioner summary)
- Relevance scoring with weighted components
- Repo quality assessment
- Major lab detection (OpenAI, Anthropic, Google boost)

**Interface:**
```python
async def analyze_paper(paper) -> PaperAnalysis
async def analyze_repo(repo) -> RepoAnalysis
```

**Complexity Assessment:** **Moderate - Could Be Simpler**

**Question to Discuss:** Do we need weighted relevance scoring with components (applicability, timeliness, novelty, impact)? Or would a simpler "is this worth featuring?" boolean suffice?

---

### Agent 5: DigestPublisherAgent

**Location:** `kubani/agents/digest_publisher/`
**Lines of Code:** ~1300
**Purpose:** Compose and publish digests to Discord

**Key Features:**
- History tracking (avoid featuring same papers/repos repeatedly)
- Two digest modes: simple and executive
- Multi-section formatting (executive summary, research, tools, company updates, trends)
- Discord message chunking (2000 char limit)
- LLM-generated summaries with fallback

**Interface:**
```python
async def compose_and_publish(articles, trends, channel_name) -> PublishResult
async def compose_executive_digest(...) -> ExecutiveDigestResult
async def publish_breaking(article, channel_name) -> PublishResult
```

**Complexity Assessment:** **High - Significantly Over-Engineered**

This is the most complex agent at 1300 lines. It handles:
1. History tracking for papers and repos
2. Simple digest composition
3. Executive digest composition with 5 sections
4. LLM-based executive summary generation
5. LLM-based research deep-dive formatting
6. LLM-based tool spotlight formatting
7. Company updates grouping and formatting
8. Trend watch section formatting
9. Discord message chunking
10. Breaking news alert formatting

**Question to Discuss:** Do we need both simple and executive digest modes? The executive digest has 5 sections - is that the right level of detail, or is it information overload?

---

## Part 4: Skills Used by Each Agent

### FeedCollectorAgent
- **No external skills** - implements feed collection internally
- Uses `DedupService` from framework for persistence

### ContentAnalystAgent
- Implements `analyze-article` skill internally (LLM analysis)
- Implements `analyze-trends-historical` skill internally
- Uses `store_learning` via Memory MCP (for trend snapshots)
- Uses `query_learnings` via Memory MCP (for historical data)

### ResearchCollectorAgent
- **No external skills** - implements collection internally
- Uses `DedupService` from framework

### ResearchAnalystAgent
- Implements paper/repo analysis internally via LLM
- **No external skill dependencies**

### DigestPublisherAgent
- Implements `compose-digest` skill internally
- Implements `compose-executive-digest` skill internally
- Implements `publish-to-discord` skill internally
- Uses `DigestHistoryTracker` (custom Redis-based dedup)
- Uses Discord MCP for publishing

---

## Part 5: What's Broken Right Now

### Issue 1: MCP Transport Mismatch (Critical)

**Problem:** The `MCPServerClient` uses HTTP POST to `/tools/call`, but MCP servers run SSE transport which exposes different endpoints.

**Location:** `kubani/framework/mcp/client.py:70-89`

```python
# Current (broken):
response = await client.post("/tools/call", json={"name": tool_name, "arguments": kwargs})

# SSE servers expose:
# GET /sse - Event stream
# POST /messages/ - Message submission
# NOT /tools/call!
```

**Result:** ALL MCP tool calls return 404 errors.

---

### Issue 2: Non-Existent Memory MCP Tools

**Problem:** Activities call tools that don't exist on the Memory MCP server.

**Called (don't exist):**
- `store_article` ✗
- `check_article_exists` ✗
- `query_articles` ✗
- `store_trend_snapshot` ✗
- `get_trend_snapshot` ✗

**Actually available:**
- `store_learning` ✓
- `query_learnings` ✓
- `store_knowledge` ✓
- `query_knowledge` ✓
- `cache_get` ✓
- `cache_set` ✓

---

### Issue 3: Cascading Failure

1. MCP transport fails → All tool calls return 404
2. `store_article_activity` fails → Articles never stored
3. `query_articles_activity` returns nothing → Digest has no content
4. Entire news system is non-functional

---

## Part 6: Complexity Analysis

### Lines of Code by Component

| Component | Lines | Purpose |
|-----------|-------|---------|
| FeedCollectorAgent | 314 | RSS collection |
| ContentAnalystAgent | 777 | Article analysis, trends |
| ResearchCollectorAgent | ~400 | arXiv/GitHub collection |
| ResearchAnalystAgent | ~500 | Paper/repo analysis |
| DigestPublisherAgent | 1300 | Digest composition & publishing |
| NewsCollectionWorkflow | ~300 | Collection orchestration |
| NewsDigestWorkflow | ~400 | Digest orchestration |
| Memory activities | ~250 | Storage operations |
| **Total** | **~4200** | |

### Where Is the Complexity?

1. **DigestPublisher (1300 lines)** - Multiple digest formats, LLM calls, history tracking
2. **ContentAnalyst (777 lines)** - Multiple analysis modes, trend velocity calculation
3. **Workflows (~700 lines)** - Multi-phase orchestration

---

## Part 7: Questions for Discussion

Before implementing the fix plan, let's discuss these questions:

### Question 1: Do we need the executive digest format?

The executive digest has 5 sections:
1. Executive Summary
2. Research Deep-dives (2-3 papers)
3. Tool Spotlights (2-3 repos)
4. Company Updates (grouped by company)
5. Trend Watch

**Alternative:** A simpler "here are today's top stories with links" format. Less impressive, but:
- Faster to implement
- Easier to maintain
- Less LLM cost per digest

### Question 2: Do we need historical trend analysis?

Current: Compare today's entities against 14-day history to calculate velocity (surging/rising/stable/declining/fading).

**Alternative:** Just show "trending topics mentioned by 3+ sources today". Simpler, still useful.

### Question 3: Do we need separate collection and digest workflows?

Current: Collection runs every 15 minutes, digest runs 2x daily.

**Alternative:** Single workflow that runs 2x daily, collects and publishes in one go. Simpler, but:
- Loses "breaking news" detection during off-hours
- Loses cross-run deduplication benefits

### Question 4: Is the agent abstraction helping or hurting?

The agents inherit from `KubaniAgent` but mostly implement everything internally:
- `on_skill_complete` is abstract but only used for logging
- `get_additional_tools` is never overridden
- Skills are implemented inside agents, not loaded from Skills MCP

**Alternative:** Plain classes without the agent abstraction for these specific use cases.

### Question 5: How much LLM usage is appropriate?

Current LLM calls per digest:
- 50+ calls for article analysis (parallel)
- 1 call for executive summary
- 3 calls for paper deep-dives
- 3 calls for tool spotlights
- ~60 LLM calls total

**Question:** Is this the right trade-off between quality and cost/latency?

---

## Part 8: Paths Forward

### Path A: Fix Current Implementation

Follow the existing plan in `docs/plans/drafts/2026-01-28-mcp-client-transport-fix.md`:

1. Fix MCP transport (SSE client instead of HTTP POST)
2. Map activities to generic Memory MCP tools
3. Audit all callers
4. Verify end-to-end
5. Deploy

**Pros:** Preserves all existing functionality
**Cons:** Inherits all existing complexity

### Path B: Fix + Simplify

Fix the transport issues, then simplify:

1. Fix MCP transport (required)
2. Consolidate to single digest format (remove executive vs simple distinction)
3. Remove historical trend analysis (keep current-period trends only)
4. Simplify DigestPublisher to ~500 lines

**Pros:** More maintainable long-term
**Cons:** Loses some features

### Path C: Minimal Viable Implementation

Question: What's the simplest thing that could work?

1. Single workflow: collect → analyze top 10 → format as bullet list → post to Discord
2. No trend analysis, no history tracking, no multi-section digests
3. ~500 total lines of code

**Pros:** Ship fast, iterate later
**Cons:** Loses significant value

---

## Part 9: Recommendation

**My recommendation: Path A (Fix Current) with an eye toward Path B (Simplify) after it's working.**

Rationale:
1. The architecture is sound - collection/digest separation makes sense
2. The agent abstractions are clean - they just need to work
3. The features (trends, executive digest) add real value
4. But complexity should be reduced iteratively after we have a working baseline

**Immediate actions:**
1. Fix MCP transport (Phase 1 of existing plan)
2. Map activities to generic tools (Phase 2)
3. Get end-to-end flow working
4. Then evaluate which features to keep/simplify

---

## Appendix: Data Flow Example

### Morning Digest at 7am

```
7:00am → NewsDigestWorkflow triggers

Phase 1: Query Articles
  └─ query_articles_activity(lookback=12h)
      └─ Memory MCP: query_knowledge(query="news articles...")
          └─ Returns ~50 articles from 7pm-7am

Phase 2: Analyze Articles
  └─ run_agent_activity("content-analyst", articles)
      └─ LLM analyzes all 50 in parallel (8 workers)
          ├─ Extracts entities: [OpenAI, GPT-4, Scaling...]
          ├─ Scores importance: [9, 7, 6, 5...]
          └─ Groups by entity → Trends: {OpenAI: 8x, GPT: 5x}

Phase 3: Analyze Papers
  └─ query_knowledge_activity(prefix="arxiv")
      └─ run_agent_activity("research-analyst", papers)
          └─ LLM evaluates → PaperAnalysis objects

Phase 4: Analyze Repos
  └─ run_agent_activity("research-analyst", repos)
      └─ Evaluates for spotlight worthiness

Phase 5: Compose Digest
  └─ run_agent_activity("digest-publisher", all_data)
      ├─ Selects top articles by importance
      ├─ Groups by company
      ├─ Filters papers/repos to avoid repeats
      ├─ Composes multi-section Markdown
      └─ Splits into Discord chunks

Phase 6: Publish to Discord
  └─ Discord MCP: send_message(channel="ai-news", chunks)

Phase 7: Store Trend Snapshot
  └─ Memory MCP: cache_set(key="trend:snapshot:2026-01-28")

Workflow complete ✓
```

---

## Next Steps

1. **Review this document together** - Does the analysis match your understanding?
2. **Decide on path forward** - Fix only vs. fix + simplify
3. **Execute the plan** - Once we agree on scope
