# News Service Architecture: Three Approaches

**Date**: 2026-01-27
**Status**: Draft - Pending Discussion
**Author**: Claude (with human guidance)

---

## Executive Summary

This document presents three architectural approaches for reimplementing the Kubani News Service, aligned with the skills → agents → syndicates hierarchy. Each approach offers different trade-offs between complexity, flexibility, and operational overhead.

### Objectives Recap

1. **Continuous Ingestion & Analysis** - Extract metadata, entities, themes, summaries from configured feeds
2. **Breaking News Alerts** - Flag and post breaking items with efficient-to-consume formatting
3. **Periodic Digest** - Executive Summary, Research Deep-dives (arxiv), Tool Spotlights, Company Updates
4. **Trend Analysis** - Identify broader themes gaining/losing popularity over time

---

## Approach A: Single Syndicate, Enhanced Skills

**Philosophy**: Minimal structural changes, maximum skill investment. One syndicate orchestrates all objectives using rich, composable skills.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    NewsSyndicate (Temporal)                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Concurrent Tasks:                                           ││
│  │  - Breaking News Monitor (every 15 min)                     ││
│  │  - Daily Digest (7am, 3pm)                                  ││
│  │  - Weekly Trend Analysis (Sundays)                          ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
           ┌───────────────┐    ┌───────────────┐
           │ FeedCollector │    │ ContentAnalyst│
           │     Agent     │    │     Agent     │
           └───────────────┘    └───────────────┘
                    │                   │
                    ▼                   ▼
           ┌───────────────┐    ┌───────────────┐
           │ DigestPublish │    │ TrendAnalyst  │
           │     Agent     │    │     Agent     │
           └───────────────┘    └───────────────┘
```

### Skills Required

**Collection Phase** (existing + new):
| Skill | Status | Description |
|-------|--------|-------------|
| `news/collection/fetch-rss-feeds` | Exists | Fetch articles from RSS feeds |
| `news/collection/filter-duplicates` | Exists | Deduplicate by URL/hash |
| `news/collection/fetch-arxiv-papers` | **NEW** | Fetch recent arxiv papers (cs.AI, cs.LG, cs.CL) |
| `news/collection/fetch-github-trending` | **NEW** | Fetch trending AI repos |
| `news/collection/fetch-company-updates` | **NEW** | Poll company blogs with priority |

**Analysis Phase** (existing + enhanced):
| Skill | Status | Description |
|-------|--------|-------------|
| `news/diagnostic/analyze-article` | Exists | Basic article analysis |
| `news/diagnostic/analyze-article-deep` | **NEW** | Full analysis with opinions, critiques |
| `news/diagnostic/analyze-arxiv-paper` | **NEW** | Research paper deep-dive |
| `news/diagnostic/analyze-github-repo` | **NEW** | Tool/repo evaluation |
| `news/diagnostic/detect-breaking-news` | Exists | Breaking news detection |
| `news/diagnostic/analyze-trends` | Exists | Basic trend detection |
| `news/diagnostic/analyze-trends-historical` | **NEW** | Compare against memory for trend velocity |

**Action Phase** (existing + enhanced):
| Skill | Status | Description |
|-------|--------|-------------|
| `news/action/compose-digest` | Exists | Basic digest composition |
| `news/action/compose-executive-digest` | **NEW** | Rich digest with sections |
| `news/action/compose-breaking-alert` | **NEW** | Breaking news formatting |
| `news/action/compose-trend-report` | **NEW** | Trend analysis report |
| `news/action/publish-to-discord` | Exists | Discord publishing |

### Agents (4 total)

1. **FeedCollectorAgent** - Orchestrates all collection skills
2. **ContentAnalystAgent** - Runs analysis skills, uses memory for context
3. **DigestPublisherAgent** - Composes and publishes all content types
4. **TrendAnalystAgent** (NEW) - Dedicated to trend analysis with historical memory

### Memory Usage

```python
# Store article analysis for trend comparison
await memory.store_learning(
    agent_id="content-analyst",
    learning_type="article_analysis",
    content=json.dumps(processed_article),
    confidence=0.9,
    tags=["article", article.category, *article.entities],
    context={"url": article.url, "date": article.published_at}
)

# Query historical trends
historical = await memory.query_learnings(
    query="GPT-4 mentions",
    min_confidence=0.7,
    since=datetime.now() - timedelta(days=30),
    tags=["article"]
)
```

### Temporal Workflow

```python
@workflow.defn
class NewsWorkflow:
    """Single workflow handling all news operations"""

    @workflow.run
    async def run(self, input: NewsInput) -> NewsResult:
        match input.operation:
            case "breaking_monitor":
                return await self._run_breaking_monitor()
            case "daily_digest":
                return await self._run_daily_digest()
            case "trend_analysis":
                return await self._run_trend_analysis()
```

### Costs & Benefits

| Aspect | Assessment |
|--------|------------|
| **Complexity** | Low - Single syndicate, familiar pattern |
| **Skill Count** | ~15 skills (8 existing + 7 new) |
| **Testing** | Skills testable in isolation |
| **Memory** | Centralized, simple queries |
| **Deployment** | One worker, one task queue |
| **Flexibility** | Moderate - Adding objectives requires skill changes |
| **Scalability** | Limited - All work in one worker |

### Trade-offs

**Pros**:
- Minimal architectural change from current implementation
- Skills are highly reusable and testable
- Single point of orchestration
- Easier to understand and debug
- Lower operational overhead

**Cons**:
- Agent responsibilities become broad
- Trend analysis may compete with digest generation
- No parallelism across objectives
- Single point of failure

---

## Approach B: Objective-Based Syndicates

**Philosophy**: One syndicate per objective. Each syndicate is specialized and independently deployable.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Event Bus (Redis Streams)                             │
└─────────────────────────────────────────────────────────────────────────────┘
       │              │                │                │
       ▼              ▼                ▼                ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  Ingestion  │ │  Breaking   │ │   Digest    │ │   Trends    │
│  Syndicate  │ │  Syndicate  │ │  Syndicate  │ │  Syndicate  │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
       │              │                │                │
       ▼              ▼                ▼                ▼
  ┌─────────┐    ┌─────────┐    ┌─────────────┐  ┌───────────┐
  │Collector│    │BreakDet │    │ Research    │  │Historical │
  │  Agent  │    │  Agent  │    │   Agent     │  │  Analyst  │
  └─────────┘    └─────────┘    ├─────────────┤  └───────────┘
       │              │         │ Spotlight   │        │
       ▼              ▼         │   Agent     │        ▼
  ┌─────────┐    ┌─────────┐    ├─────────────┤  ┌───────────┐
  │Enricher │    │BreakPub │    │ Company     │  │  Trend    │
  │  Agent  │    │  Agent  │    │   Agent     │  │ Publisher │
  └─────────┘    └─────────┘    ├─────────────┤  └───────────┘
                                │ Composer    │
                                │   Agent     │
                                └─────────────┘
```

### Syndicates (4)

#### 1. IngestionSyndicate
**Purpose**: Continuously ingest and enrich content, store in memory

**Agents**:
- `CollectorAgent` - Fetches from all sources (RSS, arxiv, GitHub)
- `EnricherAgent` - Analyzes and stores enriched content in memory

**Schedule**: Every 30 minutes

**Events Published**:
- `NEWS_ARTICLE_INGESTED` - New article stored
- `NEWS_PAPER_INGESTED` - New arxiv paper stored
- `NEWS_REPO_INGESTED` - New GitHub repo stored

#### 2. BreakingSyndicate
**Purpose**: Detect and publish breaking news immediately

**Agents**:
- `BreakingDetectorAgent` - Monitors ingestion events, detects breaking
- `BreakingPublisherAgent` - Publishes alerts to Discord

**Trigger**: Event-driven (subscribes to `NEWS_*_INGESTED`)

**Events Published**:
- `NEWS_BREAKING_PUBLISHED`

#### 3. DigestSyndicate
**Purpose**: Produce rich periodic digests

**Agents**:
- `ResearchAgent` - Selects and analyzes arxiv papers for deep-dives
- `SpotlightAgent` - Evaluates trending repos for spotlights
- `CompanyAgent` - Summarizes company updates
- `ComposerAgent` - Assembles final digest with all sections

**Schedule**: Daily at 7am

**Events Published**:
- `NEWS_DIGEST_PUBLISHED`

#### 4. TrendsSyndicate
**Purpose**: Analyze and report on trends over time

**Agents**:
- `HistoricalAnalystAgent` - Queries memory, identifies patterns
- `TrendPublisherAgent` - Composes and publishes trend reports

**Schedule**: Weekly on Sunday

**Events Published**:
- `NEWS_TRENDS_PUBLISHED`

### Skills Required

Same skills as Approach A, but organized by syndicate:

| Syndicate | Skills Used |
|-----------|-------------|
| Ingestion | fetch-rss-feeds, fetch-arxiv-papers, fetch-github-trending, analyze-article, store-memory |
| Breaking | detect-breaking-news, compose-breaking-alert, publish-to-discord |
| Digest | analyze-arxiv-paper, analyze-github-repo, compose-executive-digest, publish-to-discord |
| Trends | analyze-trends-historical, search-memory, compose-trend-report, publish-to-discord |

### Memory Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Memory Layer                              │
├─────────────────┬─────────────────┬─────────────────────────────┤
│    Articles     │     Papers      │         Repos               │
│   (Qdrant)      │    (Qdrant)     │        (Qdrant)             │
├─────────────────┴─────────────────┴─────────────────────────────┤
│                    Knowledge Graph (Neo4j)                       │
│  - Entity relationships                                          │
│  - Topic hierarchies                                             │
│  - Trend velocity edges                                          │
└─────────────────────────────────────────────────────────────────┘
```

**Ingestion writes, others read:**
```python
# Ingestion stores
await memory.store_learning(
    agent_id="enricher",
    learning_type="article",
    content=json.dumps(article),
    tags=[article.category, *article.entities],
    context={"source": article.source, "importance": article.importance_score}
)

# Trends queries
recent = await memory.query_learnings(
    query=None,  # All
    learning_type="article",
    since=datetime.now() - timedelta(days=7),
    limit=1000
)
```

### Temporal Configuration

Each syndicate has its own workflow and task queue:

```python
# 4 separate workers
Worker(client, task_queue="news-ingestion", workflows=[IngestionWorkflow], ...)
Worker(client, task_queue="news-breaking", workflows=[BreakingWorkflow], ...)
Worker(client, task_queue="news-digest", workflows=[DigestWorkflow], ...)
Worker(client, task_queue="news-trends", workflows=[TrendsWorkflow], ...)
```

### Costs & Benefits

| Aspect | Assessment |
|--------|------------|
| **Complexity** | Medium-High - 4 syndicates, event coordination |
| **Skill Count** | ~15 skills (shared across syndicates) |
| **Testing** | Syndicates testable in isolation |
| **Memory** | Shared, with clear read/write boundaries |
| **Deployment** | 4 workers, 4 task queues |
| **Flexibility** | High - Each objective independently evolvable |
| **Scalability** | High - Scale each syndicate independently |

### Trade-offs

**Pros**:
- Clear separation of concerns
- Independent scaling and deployment
- Failure isolation (breaking news works even if trends fails)
- Easier to add new objectives
- Parallel development possible

**Cons**:
- More complex event coordination
- Potential for duplicate processing
- Higher operational overhead (4 workers)
- Memory consistency challenges
- More complex debugging (distributed tracing needed)

---

## Approach C: Pipeline Architecture with Specialized Workers

**Philosophy**: Treat news processing as a data pipeline. Separate ingestion, processing, and output stages with specialized workers.

### Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           News Pipeline                                     │
└────────────────────────────────────────────────────────────────────────────┘

 Stage 1: Ingestion        Stage 2: Processing       Stage 3: Output
 ─────────────────         ─────────────────         ─────────────────

┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│  RSS Collector  │──┐    │ Article Analyst │──┐    │ Breaking Alert  │
└─────────────────┘  │    └─────────────────┘  │    │    Worker       │
                     │                          │    └─────────────────┘
┌─────────────────┐  │    ┌─────────────────┐  │
│ Arxiv Collector │──┼───▶│ Paper Analyst   │──┼───▶┌─────────────────┐
└─────────────────┘  │    └─────────────────┘  │    │ Digest Builder  │
                     │                          │    │    Worker       │
┌─────────────────┐  │    ┌─────────────────┐  │    └─────────────────┘
│GitHub Collector │──┘    │ Repo Analyst    │──┤
└─────────────────┘       └─────────────────┘  │    ┌─────────────────┐
                                               │    │ Trend Reporter  │
                          ┌─────────────────┐  │    │    Worker       │
                          │ Trend Detector  │──┘    └─────────────────┘
                          └─────────────────┘
                                                    ┌─────────────────┐
                                                    │ Discord Gateway │
                                                    └─────────────────┘

                 ┌─────────────────────────────────────────────┐
                 │              Message Queue (Redis)           │
                 │  Queues: raw-articles, raw-papers, raw-repos │
                 │          processed-*, alerts-*, digests-*    │
                 └─────────────────────────────────────────────┘
```

### Pipeline Stages

#### Stage 1: Ingestion Workers (Stateless)
Each worker type focuses on one source:

```python
# RSS Worker - runs every 30 min
@workflow.defn
class RSSIngestionWorkflow:
    async def run(self) -> None:
        articles = await workflow.execute_activity(fetch_rss_activity, ...)
        for article in articles:
            await workflow.execute_activity(
                enqueue_activity,
                args=["raw-articles", article]
            )
```

**Workers**: 3 (RSS, Arxiv, GitHub)
**Output**: Raw items to Redis queues

#### Stage 2: Processing Workers (Stateless)
Each worker type processes one content type:

```python
# Article Processor - triggered by queue
@workflow.defn
class ArticleProcessingWorkflow:
    async def run(self, article: dict) -> None:
        # Analyze
        processed = await workflow.execute_activity(analyze_article_activity, article)

        # Store in memory
        await workflow.execute_activity(store_in_memory_activity, processed)

        # Check for breaking
        if processed["is_breaking"]:
            await workflow.execute_activity(enqueue_activity, ["alerts-breaking", processed])

        # Queue for digest consideration
        await workflow.execute_activity(enqueue_activity, ["processed-articles", processed])
```

**Workers**: 4 (Article, Paper, Repo, Trend)
**Output**: Processed items to Redis queues + Memory

#### Stage 3: Output Workers (Scheduled)
Each worker produces a specific output type:

```python
# Digest Builder - runs daily at 7am
@workflow.defn
class DigestBuilderWorkflow:
    async def run(self) -> None:
        # Drain processed queues
        articles = await drain_queue("processed-articles")
        papers = await drain_queue("processed-papers")
        repos = await drain_queue("processed-repos")

        # Select best content
        selected = await select_content(articles, papers, repos)

        # Compose sections
        digest = await compose_digest(selected)

        # Publish
        await publish_to_discord(digest)
```

**Workers**: 3 (Breaking Alert, Digest Builder, Trend Reporter)
**Output**: Discord messages

### Skills as Activities

In this approach, skills become activities that workers call:

```python
# Activity wrapping a skill
@activity.defn
async def analyze_article_activity(article: dict) -> dict:
    skill_path = "kubani/skills/news/diagnostic/analyze-article"
    llm = FrameworkLLM()
    return await llm.execute_skill(
        skill_sop=read_skill(skill_path),
        inputs={"article": article}
    )
```

### Agents as Activity Orchestrators

Agents become lightweight orchestrators that combine activities:

```python
class ArticleAnalystAgent:
    """Orchestrates article processing activities"""

    async def process(self, article: dict) -> dict:
        # Run analysis skill
        processed = await self.execute_skill("analyze-article", article)

        # Optionally run deep analysis
        if processed["importance_score"] >= 7:
            processed = await self.execute_skill("analyze-article-deep", processed)

        return processed
```

### Memory as Pipeline State

Memory serves as durable state between pipeline stages:

```
┌───────────────────────────────────────────────────────────────────────────┐
│                            Memory Layer                                    │
├────────────────────┬────────────────────┬─────────────────────────────────┤
│  Working Memory    │  Episodic Memory   │  Semantic Memory                │
│  (Redis + TTL)     │  (Qdrant)          │  (Neo4j)                        │
├────────────────────┼────────────────────┼─────────────────────────────────┤
│ - Current batch    │ - All processed    │ - Entity relationships          │
│ - Processing state │   articles (30d)   │ - Topic hierarchies             │
│ - Queue backlog    │ - Papers (90d)     │ - Learned patterns              │
└────────────────────┴────────────────────┴─────────────────────────────────┘
```

### Temporal Configuration

```python
# Stage 1: Ingestion (scheduled)
Worker(client, task_queue="news-ingestion-rss", workflows=[RSSIngestionWorkflow])
Worker(client, task_queue="news-ingestion-arxiv", workflows=[ArxivIngestionWorkflow])
Worker(client, task_queue="news-ingestion-github", workflows=[GitHubIngestionWorkflow])

# Stage 2: Processing (queue-triggered via Temporal schedules)
Worker(client, task_queue="news-process-articles", workflows=[ArticleProcessingWorkflow])
Worker(client, task_queue="news-process-papers", workflows=[PaperProcessingWorkflow])
Worker(client, task_queue="news-process-repos", workflows=[RepoProcessingWorkflow])
Worker(client, task_queue="news-process-trends", workflows=[TrendProcessingWorkflow])

# Stage 3: Output (scheduled)
Worker(client, task_queue="news-output-breaking", workflows=[BreakingAlertWorkflow])
Worker(client, task_queue="news-output-digest", workflows=[DigestBuilderWorkflow])
Worker(client, task_queue="news-output-trends", workflows=[TrendReporterWorkflow])
```

### Costs & Benefits

| Aspect | Assessment |
|--------|------------|
| **Complexity** | High - 10+ workers, queue coordination |
| **Skill Count** | ~15 skills (wrapped as activities) |
| **Testing** | Each stage testable with mocked queues |
| **Memory** | Tiered, with clear lifecycle |
| **Deployment** | 10+ workers, multiple queues |
| **Flexibility** | Very High - Add/remove stages easily |
| **Scalability** | Excellent - Scale each stage independently |

### Trade-offs

**Pros**:
- Highest scalability (horizontal scaling per stage)
- Clear data flow, easy to monitor
- Backpressure handling via queues
- Stage isolation (failure doesn't propagate)
- Easy to add new content types or outputs
- Natural fit for high-volume processing

**Cons**:
- Highest complexity
- Most operational overhead
- Latency from queue hops
- Debugging requires distributed tracing
- Overkill for current volume
- Skills become implementation detail

---

## Comparison Matrix

| Criterion | Approach A (Single) | Approach B (Objective) | Approach C (Pipeline) |
|-----------|---------------------|------------------------|----------------------|
| **Complexity** | Low | Medium | High |
| **Workers** | 1 | 4 | 10+ |
| **Skill Reuse** | High | High | Medium (wrapped) |
| **Testing** | Skills in isolation | Syndicates in isolation | Stages in isolation |
| **Scalability** | Limited | Good | Excellent |
| **Failure Isolation** | Low | Good | Excellent |
| **Operational Overhead** | Low | Medium | High |
| **Development Velocity** | Fast | Medium | Slower initially |
| **Memory Integration** | Simple | Partitioned | Tiered |
| **Continuous Learning** | Easy | Medium | Complex |
| **Current State Match** | Very Close | Some Changes | Major Refactor |

---

## Recommendation Criteria

### Choose Approach A if:
- Volume is modest (< 1000 articles/day)
- Team is small and values simplicity
- Quick iteration is priority
- Current implementation works well enough

### Choose Approach B if:
- Each objective has distinct requirements
- Independent deployment per objective is valuable
- Team can manage event-driven coordination
- Moderate scale expected

### Choose Approach C if:
- High volume processing expected
- Strict SLAs per processing type
- Team has distributed systems experience
- Future extensibility is critical

---

## Questions for Discussion

1. **Volume expectations**: How many articles/day? Papers/week? Repos/week?

2. **Latency requirements**: How fast must breaking news be published after detection?

3. **Digest richness**: How detailed should research deep-dives be? (Quick summary vs. full analysis)

4. **Memory retention**: How far back should trend analysis look? (7 days? 30 days? 90 days?)

5. **Failure tolerance**: If trend analysis fails, should digest still publish?

6. **Learning priority**: Which aspects benefit most from continuous improvement?

7. **Operational capacity**: How many workers can we comfortably manage?

---

---

## Analysis & Recommendation

### Historical Volume Analysis

Based on the feed configuration in `kubani/agents/feed_collector/feeds.py`:

| Source Category | Feeds | Estimated Daily Volume |
|-----------------|-------|------------------------|
| Company Blogs | 6 | 3-5 articles |
| AI Publications | 4 | 8-16 articles |
| General Tech (filtered) | 5 | 9-26 articles |
| ArXiv Research | 3 | 80-150 papers |
| Security | 2 | 5-10 articles |
| **Total Raw** | **20** | **105-207 items** |
| **After Dedup** | - | **~100-150 unique** |

**Key insight**: Volume is modest (~125 articles/day average). The current system processes only 10-20% of its LLM capacity.

### Cluster Capacity Analysis

| Node | CPU Usage | Memory Usage | Role |
|------|-----------|--------------|------|
| rig0 | 4% | 61% | GPU node (vLLM inference) |
| sparky | 6% | 26% | GPU node (vLLM, Flux, cert-manager) |
| asio | 1% | 46% | Worker node |
| osprey | 3% | 49% | Worker node |
| strix | 3% | 16% | Worker node |

**Current workloads**: vLLM (3 instances), Flux GitOps, GPU operator, cert-manager, CSI drivers

**Available headroom**: Significant - all nodes under 10% CPU, memory varies but rig0/sparky have GPU workloads, asio/osprey/strix are lightly loaded.

### Recommendation: **Approach A (Single Syndicate)** with Staged Enhancements

Given:
- **Modest volume** (~125 articles/day) - doesn't justify pipeline complexity
- **Relaxed latency** - breaking news doesn't need to be instant
- **7-14 day trend window** - manageable memory footprint
- **Available capacity** - cluster is lightly loaded, no need to distribute

**Approach A is the right choice** because:
1. Simpler to develop, test, and operate
2. Current volume doesn't justify 4+ workers
3. Skills remain the unit of composition and testing
4. Easy to evolve to Approach B later if needed
5. Single worker fits comfortably on any worker node

### Proposed Implementation Phases

#### Phase 1: Core Skills & Memory (Week 1-2)
- Implement new skills: `fetch-arxiv-papers`, `fetch-github-trending`, `analyze-arxiv-paper`, `analyze-github-repo`
- Set up memory schema for 14-day retention
- Test skills in isolation using skill_auto workflow

#### Phase 2: Enhanced Digest (Week 2-3)
- Implement `compose-executive-digest` skill with sections:
  - Executive Summary
  - Research Deep-dives (1-2 arxiv papers)
  - Tool Spotlights (1-2 trending repos)
  - Company Updates
- Update DigestPublisherAgent to use new skill
- Test full digest pipeline

#### Phase 3: Trend Analysis (Week 3-4)
- Implement `analyze-trends-historical` skill with memory queries
- Add TrendAnalystAgent to syndicate
- Implement weekly trend report workflow
- Test trend detection over 7-14 day windows

#### Phase 4: Polish & Evaluation (Week 4)
- Create evaluation suites for all new skills
- Tune prompts based on critic feedback
- Add monitoring and observability
- Deploy to cluster

### Memory Schema

```yaml
# Article storage (14-day retention)
collection: news_articles
fields:
  - url (unique key)
  - title
  - source
  - category
  - entities (list)
  - importance_score
  - summary
  - published_at
  - ingested_at
  - content_hash
ttl: 14 days

# Trend snapshots (for velocity calculation)
collection: trend_snapshots
fields:
  - snapshot_date
  - entity
  - mention_count
  - sources (list)
  - avg_importance
ttl: 30 days
```

### Resource Allocation

| Component | Node | Resources |
|-----------|------|-----------|
| News Worker (Temporal) | asio or osprey | 500m CPU, 1Gi memory |
| Memory (Qdrant) | existing | Shared instance |
| LLM | sparky/rig0 | Existing vLLM instances |

**Impact**: Minimal - adds one lightweight worker to an underutilized node.

---

## Next Steps

1. ~~Discuss approaches and select one~~ → **Selected Approach A**
2. Define detailed skill specifications for new skills
3. Create evaluation criteria for skills
4. Design memory schema for chosen approach
5. Implement incrementally, starting with core pipeline
