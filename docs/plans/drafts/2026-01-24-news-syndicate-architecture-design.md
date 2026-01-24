# News Syndicate Architecture Design

**Date:** 2026-01-24
**Status:** Approved for Implementation
**Author:** Claude Code + Human Collaboration

---

## Executive Summary

This document describes the architecture for a redesigned news syndicate system that:
1. Collects AI news from RSS feeds
2. Analyzes content with LLM for categorization, importance scoring, and breaking news detection
3. Publishes digests and alerts to Discord with rich formatting
4. Learns and improves over time through user feedback
5. Is designed for multi-topic extensibility (AI news today, sports/crypto/etc. tomorrow)

**Key Architectural Decisions:**
- **Workflow-Centric:** Temporal workflows handle orchestration, scheduling, and reliability
- **Shared Agents:** Generic, reusable agents configured per topic
- **Topic Syndicates:** Thin configuration + orchestration layers per topic
- **Hybrid Learning:** Local feedback collection + cross-cutting Voyager analysis
- **MCP-First:** All persistence and external tools via MCP servers

---

## Table of Contents

1. [Goals & Success Criteria](#1-goals--success-criteria)
2. [Architecture Overview](#2-architecture-overview)
3. [Multi-Topic Extensibility](#3-multi-topic-extensibility)
4. [Agents](#4-agents)
5. [Workflows](#5-workflows)
6. [Skills](#6-skills)
7. [MCP Integration](#7-mcp-integration)
8. [Feedback & Learning System](#8-feedback--learning-system)
9. [Discord Channel Strategy](#9-discord-channel-strategy)
10. [Error Handling](#10-error-handling)
11. [Testing Strategy](#11-testing-strategy)
12. [Implementation Plan](#12-implementation-plan)

---

## 1. Goals & Success Criteria

### Purpose

Build an AI news intelligence system that helps users efficiently stay current with the AI industry via Discord, while continuously improving through feedback.

### Success Criteria

| Criteria | Metric | Target |
|----------|--------|--------|
| **Timely** | Breaking news latency | < 5 minutes from detection |
| **Relevant** | User feedback ratio | > 80% positive (fire + thumbs up) |
| **Comprehensive** | Category coverage | Research, products, business, security, policy |
| **Learnable** | Improvement over time | Measurable via feedback trends |
| **Observable** | Debugging ease | Full flow visible in Temporal UI |
| **Reusable** | New topic setup time | < 1 day to add new topic |

### Design Principles Applied

- **Agentic-First:** LLM-driven analysis and composition, not hard-coded rules
- **MCP-First:** All persistence and external tools via MCP servers
- **Workflow-Centric:** Temporal orchestrates, agents execute
- **Feedback-Driven:** Every output can receive user feedback
- **Extensible:** Adding new topics requires config, not code changes

### Out of Scope (Initial Release)

- Multi-platform publishing (Slack, email) - Discord only
- User personalization - Same content for all users
- Full-text article fetching - Work with RSS summaries
- Real-time websocket feeds - RSS polling only

---

## 2. Architecture Overview

### High-Level Diagram

```
+------------------------------------------------------------------------------+
|                              Shared Components                                |
+------------------------------------------------------------------------------+
|  Agents (generic, reusable):                                                 |
|  +---------------+ +---------------+ +---------------+ +------------------+  |
|  | FeedCollector | | ArticleAnalyst| | DigestComposer| | DiscordPublisher |  |
|  | (any RSS/API) | | (any content) | | (any sections)| | (any channel)    |  |
|  +---------------+ +---------------+ +---------------+ +------------------+  |
|                                                                              |
|  Base Classes:                                                               |
|  +---------------+ +---------------+                                         |
|  | NewsSyndicate | | NewsWorkflows |  <- topic syndicates inherit            |
|  +---------------+ +---------------+                                         |
|                                                                              |
|  MCP Servers:                                                                |
|  +--------+ +--------+ +---------+ +----------+                              |
|  | Memory | | Qdrant | | Discord | | Temporal |                              |
|  +--------+ +--------+ +---------+ +----------+                              |
+------------------------------------------------------------------------------+
                                    |
          +-------------------------+-------------------------+
          |                         |                         |
          v                         v                         v
+------------------+     +-------------------+     +--------------------+
| AINewsSyndicate  |     | SportsNewsSyndicate|    | FutureTopicSyndicate|
|                  |     | (future)          |     | (future)           |
| topic: ai-news   |     | topic: sports     |     | topic: ???         |
| feeds: [...]     |     | feeds: [...]      |     | feeds: [...]       |
| prompt: ai.md    |     | prompt: sports.md |     | prompt: ???.md     |
| sections: [...]  |     | sections: [...]   |     | sections: [...]    |
| channels: {...}  |     | channels: {...}   |     | channels: {...}    |
| schedule: {...}  |     | schedule: {...}   |     | schedule: {...}    |
+------------------+     +-------------------+     +--------------------+
          |                         |                         |
          v                         v                         v
+------------------------------------------------------------------------------+
|                         Temporal Workflows                                    |
|  (same workflow structure, different topic config)                           |
|                                                                              |
|  ai-news-collection     sports-collection        future-collection           |
|  ai-news-digest         sports-digest            future-digest               |
|  ai-news-breaking       sports-breaking          future-breaking             |
+------------------------------------------------------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------------+
|                         VoyagerSyndicate (Future)                            |
|  (watches all topics, proposes cross-cutting improvements)                   |
+------------------------------------------------------------------------------+
```

### Component Responsibilities

| Component | Responsibility | Location |
|-----------|----------------|----------|
| **FeedCollector** | Generic RSS/API collection, deduplication | `kubani/agents/feed_collector/` |
| **ArticleAnalyst** | LLM analysis, categorization, scoring | `kubani/agents/article_analyst/` |
| **DigestComposer** | Section composition, narrative generation | `kubani/agents/digest_composer/` |
| **DiscordPublisher** | Discord formatting, channel routing | `kubani/agents/discord_publisher/` |
| **NewsSyndicate** | Base class for topic syndicates | `kubani/syndicates/_base/news.py` |
| **AINewsSyndicate** | AI-specific config + orchestration | `kubani/syndicates/ai_news/` |
| **NewsWorkflows** | Temporal workflow definitions | `kubani/syndicates/_base/workflows.py` |

### Syndicate-Workflow Relationship

**Key Insight:** Syndicates provide agents and configuration. Workflows provide orchestration and scheduling.

```
Syndicate = "What agents do we have and how are they configured?"
Workflows = "When do things run and in what order?"
Activities = Bridge between them (wrap agent methods for Temporal)
```

**Syndicate responsibilities:**
- Agent lifecycle management (`get_agent()`)
- Configuration loading (feeds, prompts, channels, schedules)
- Activity registration with Temporal worker
- Schedule creation on startup

**Workflow responsibilities:**
- Execution order (collect -> analyze -> store -> publish)
- Retry policies and timeouts
- Signal handling (breaking news triggers)
- Visibility in Temporal UI

---

## 3. Multi-Topic Extensibility

### Design Decision

We evaluated five architectural options for multi-topic support:

| Option | Description | Verdict |
|--------|-------------|---------|
| A. Topic-Specific Syndicates | Copy-paste everything per topic | Doesn't scale |
| B. Shared Collection | Single collector, topic publishers | Analysis can't be shared |
| C. Pipeline Stages | Collection/Analysis/Publishing syndicates | Over-engineered |
| D. Generic Engine | Single syndicate, config per topic | No isolation |
| **E. Shared Agents + Topic Syndicates** | Generic agents, thin topic config | **Selected** |

### Why Option E?

1. **Agents are truly reusable** - Same code, different config
2. **Topics are isolated** - Each has own syndicate, schedules, channels
3. **Cross-topic features possible** - Shared Memory MCP, unified learning
4. **Adding new topic is simple** - ~50 lines of config
5. **Different schedules per topic** - AI every 15min, sports hourly

### Adding a New Topic

```python
# syndicates/sports_news/syndicate.py
class SportsNewsSyndicate(NewsSyndicate):
    topic = "sports-news"

    feeds = [
        FeedConfig("ESPN", "https://www.espn.com/espn/rss/news"),
        FeedConfig("The Athletic", "https://theathletic.com/rss/"),
    ]

    analysis_prompt = "prompts/sports-news-analysis.md"

    categories = ["scores", "trades", "injuries", "analysis", "rumors"]

    sections = [
        SectionConfig("trade-alerts", "Trade Alerts", filter="category=trades"),
        SectionConfig("injury-report", "Injury Report", filter="category=injuries"),
    ]

    channels = {
        "digest": "sports-news",
        "breaking": "sports-breaking",
    }

    schedule = {
        "collection": "*/30 * * * *",
        "morning_digest": "0 6 * * *",
    }
```

---

## 4. Agents

### Agent Naming Convention

Agents are named for WHAT they do, not WHERE they're used:

| Name | Purpose | Reusable For |
|------|---------|--------------|
| **FeedCollector** | Collect from RSS/Atom/API feeds | Any feed-based ingestion |
| **ArticleAnalyst** | LLM analysis of article-shaped content | News, blog posts, papers |
| **DigestComposer** | Compose sections into digests | Any multi-item summary |
| **DiscordPublisher** | Format and publish to Discord | Any Discord bot |

### FeedCollector (Existing, Enhanced)

**Location:** `kubani/agents/feed_collector/`

**Skills Used:**
- `collect-feeds` with reference: `rss-parsing.md`

**Changes from current:**
- Accept feeds as parameter, not hardcoded
- Return structured `Article` objects
- Support topic tagging

```python
class FeedCollector(KubaniAgent):
    """Collects articles from RSS/Atom/API feeds."""

    SKILLS = ["collect-feeds"]

    async def collect(
        self,
        feeds: list[FeedConfig],
        max_age_hours: int = 24,
        deduplicate: bool = True,
    ) -> list[Article]:
        """
        Collect articles from configured feeds.

        Uses skill for RSS parsing, this method handles orchestration.
        Note: Collection is mostly deterministic, skill provides parsing guidance.
        """
        skill = self.get_skill("collect-feeds")

        all_articles = []
        for feed in feeds:
            articles = await self.execute_skill(
                skill,
                context={"feed": feed, "max_age_hours": max_age_hours},
                reference=skill.get_reference("rss-parsing.md"),
            )
            all_articles.extend(articles)

        if deduplicate:
            all_articles = self._deduplicate_by_url(all_articles)

        return all_articles
```

### ArticleAnalyst (Renamed from ContentAnalyst)

**Location:** `kubani/agents/article_analyst/`

**Skills Used:**
- `analyze-article` with references: `news-article.md`, `research-paper.md`, `company-announcement.md`
- `detect-trends`

**Changes from current:**
- Select skill reference based on `source_category`
- Skills define categories, entity types, importance criteria
- Breaking news criteria defined in skill references

```python
class ArticleAnalyst(KubaniAgent):
    """Analyzes articles using skills with content-type-specific references."""

    SKILLS = ["analyze-article", "detect-trends"]

    async def analyze(self, article: Article) -> AnalyzedArticle:
        """
        Analyze a single article using appropriate skill reference.

        Selects reference based on source_category:
        - research → references/research-paper.md
        - company_blog → references/company-announcement.md
        - other → references/news-article.md
        """
        skill = self.get_skill("analyze-article")

        # Select reference based on content type
        reference_map = {
            "research": "research-paper.md",
            "company_blog": "company-announcement.md",
        }
        reference = reference_map.get(article.source_category, "news-article.md")

        return await self.execute_skill(
            skill,
            context={"article": article},
            reference=skill.get_reference(reference),
        )

    async def detect_trends(
        self,
        articles: list[AnalyzedArticle],
        min_sources: int = 2,
    ) -> list[Trend]:
        """Detect trending topics across articles."""
        skill = self.get_skill("detect-trends")
        return await self.execute_skill(
            skill,
            context={"articles": articles, "min_sources": min_sources},
        )
```

### DigestComposer (New)

**Location:** `kubani/agents/digest_composer/`

**Skills Used:**
- `compose-digest-section` with references: `executive-brief.md`, `research-deep-dive.md`, `tool-spotlight.md`, `company-roundup.md`, `trends.md`

**Purpose:** Compose rich digest sections from analyzed articles using section-specific references.

```python
class DigestComposer(KubaniAgent):
    """Composes digest sections using skills with section-type references."""

    SKILLS = ["compose-digest-section"]

    async def compose_section(
        self,
        articles: list[AnalyzedArticle],
        section_type: str,
    ) -> DigestSection:
        """
        Compose a single digest section.

        Selects reference based on section_type:
        - executive-brief → references/executive-brief.md
        - research-deep-dive → references/research-deep-dive.md
        - tool-spotlight → references/tool-spotlight.md
        - company-roundup → references/company-roundup.md
        - trends → references/trends.md
        """
        skill = self.get_skill("compose-digest-section")

        return await self.execute_skill(
            skill,
            context={"articles": articles, "section_type": section_type},
            reference=skill.get_reference(f"{section_type}.md"),
        )

    async def compose_digest(
        self,
        sections: list[DigestSection],
        trends: list[Trend],
        digest_type: str,
    ) -> Digest:
        """
        Assemble full digest from sections.

        This is procedural assembly, not LLM-driven.
        Adds header, combines sections, adds footer with metadata.
        """
        return Digest(
            digest_type=digest_type,
            sections=sections,
            trends=trends,
            created_at=datetime.now(UTC),
        )
```

### DiscordPublisher (Renamed from DigestPublisher)

**Location:** `kubani/agents/discord_publisher/`

**Skills Used:**
- `publish-to-discord` with references: `digest-format.md`, `breaking-format.md`
- `process-feedback` with reference: `feedback-signals.md`

**Changes from current:**
- Explicit Discord focus in name
- Skills define message formatting via references
- Feedback reactions defined in skill reference

```python
class DiscordPublisher(KubaniAgent):
    """Publishes content to Discord using format-specific skill references."""

    SKILLS = ["publish-to-discord", "process-feedback"]

    async def publish_digest(
        self,
        digest: Digest,
        channel_name: str,
    ) -> PublishResult:
        """
        Publish a digest to Discord.

        Uses references/digest-format.md for formatting guidance.
        Automatically adds feedback reactions from feedback-signals.md.
        """
        skill = self.get_skill("publish-to-discord")

        result = await self.execute_skill(
            skill,
            context={"content": digest, "channel": channel_name},
            reference=skill.get_reference("digest-format.md"),
        )

        # Add feedback reactions
        await self._add_feedback_reactions(result.message_id, result.channel_id)

        return result

    async def publish_breaking(
        self,
        article: AnalyzedArticle,
        channel_name: str,
    ) -> PublishResult:
        """
        Publish breaking news alert with embed.

        Uses references/breaking-format.md for embed formatting.
        """
        skill = self.get_skill("publish-to-discord")

        return await self.execute_skill(
            skill,
            context={"content": article, "channel": channel_name, "mention": "@here"},
            reference=skill.get_reference("breaking-format.md"),
        )

    async def _add_feedback_reactions(
        self,
        message_id: str,
        channel_id: str,
    ) -> None:
        """Add feedback reactions defined in skill reference."""
        skill = self.get_skill("process-feedback")
        signals = skill.get_reference("feedback-signals.md")
        # Reactions defined in reference: 🔥 👍 👎 ❌ 📖 ✂️ ⚡ 🕐 🔧
```

---

## 5. Workflows

### Workflow Structure

All topic workflows share the same structure, parameterized by topic config.

### CollectionWorkflow

**Trigger:** Temporal Schedule (e.g., every 15 minutes)

```python
@workflow.defn
class CollectionWorkflow:
    """Collect and analyze articles from feeds."""

    @workflow.run
    async def run(self, topic_config: TopicConfig) -> CollectionResult:
        # Step 1: Collect from feeds
        articles = await workflow.execute_activity(
            collect_feeds,
            args=[topic_config.feeds, topic_config.max_age_hours],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # Step 2: Analyze articles (parallel)
        analyzed = await asyncio.gather(*[
            workflow.execute_activity(
                analyze_article,
                args=[article, topic_config.analysis_prompt, topic_config.categories],
                start_to_close_timeout=timedelta(minutes=2),
            )
            for article in articles
        ])

        # Step 3: Store in Memory MCP
        await workflow.execute_activity(
            store_articles,
            args=[analyzed, topic_config.topic],
        )

        # Step 4: Check for breaking news
        breaking = [a for a in analyzed if a.is_breaking]
        for article in breaking:
            await workflow.start_child_workflow(
                BreakingWorkflow.run,
                args=[article, topic_config],
            )

        return CollectionResult(
            collected=len(articles),
            analyzed=len(analyzed),
            breaking=len(breaking),
        )
```

### DigestWorkflow

**Trigger:** Temporal Schedule (e.g., 7am, 3pm)

```python
@workflow.defn
class DigestWorkflow:
    """Compose and publish a digest."""

    @workflow.run
    async def run(self, topic_config: TopicConfig, digest_type: str) -> DigestResult:
        # Step 1: Query recent articles from Memory
        articles = await workflow.execute_activity(
            query_recent_articles,
            args=[topic_config.topic, hours=12],
        )

        # Step 2: Detect trends
        trends = await workflow.execute_activity(
            detect_trends,
            args=[articles],
        )

        # Step 3: Compose sections
        sections = []
        for section_config in topic_config.sections:
            section = await workflow.execute_activity(
                compose_section,
                args=[articles, section_config],
            )
            sections.append(section)

        # Step 4: Assemble digest
        digest = await workflow.execute_activity(
            compose_digest,
            args=[sections, trends, digest_type],
        )

        # Step 5: Publish to Discord
        result = await workflow.execute_activity(
            publish_digest,
            args=[digest, topic_config.channels["digest"]],
        )

        # Step 6: Record for feedback tracking
        await workflow.execute_activity(
            record_digest_published,
            args=[result.message_id, topic_config.topic],
        )

        return DigestResult(
            message_id=result.message_id,
            sections=len(sections),
            articles=len(articles),
        )
```

### BreakingWorkflow

**Trigger:** Signal from CollectionWorkflow or manual

```python
@workflow.defn
class BreakingWorkflow:
    """Publish breaking news immediately."""

    @workflow.run
    async def run(self, article: AnalyzedArticle, topic_config: TopicConfig) -> PublishResult:
        # Publish with @here mention
        result = await workflow.execute_activity(
            publish_breaking,
            args=[article, topic_config.channels["breaking"]],
        )

        # Record for feedback
        await workflow.execute_activity(
            record_breaking_published,
            args=[result.message_id, article.url],
        )

        return result
```

### FeedbackWorkflow

**Trigger:** Discord reaction event via event bus

```python
@workflow.defn
class FeedbackWorkflow:
    """Process user feedback from Discord reactions."""

    @workflow.run
    async def run(self, feedback: FeedbackEvent) -> None:
        # Map emoji to feedback type
        feedback_type = EMOJI_TO_FEEDBACK.get(feedback.emoji)

        # Store feedback in Memory
        await workflow.execute_activity(
            store_feedback,
            args=[feedback.message_id, feedback_type, feedback.user_id],
        )

        # Special handling for bug reports
        if feedback_type == FeedbackType.BROKEN:
            await workflow.execute_activity(
                create_incident,
                args=[feedback.message_id, feedback.channel_id],
            )
```

---

## 6. Skills

### Skills-First Architecture

Skills drive agent behavior. Agents select and execute skills based on context. Each skill follows the [Open Agent Skill Standard](https://agentskills.io/specification).

**Key Pattern:** Skills use `references/` directories for content-type-specific guidance, enabling a single skill to handle multiple variants without code duplication.

### Skill Organization

```
kubani/skills/
├── news/
│   ├── collection/
│   │   └── collect-feeds/
│   │       ├── SKILL.md              # Core collection procedure
│   │       └── references/
│   │           └── rss-parsing.md    # RSS/Atom parsing details
│   │
│   ├── analysis/
│   │   ├── analyze-article/
│   │   │   ├── SKILL.md              # Core analysis procedure
│   │   │   └── references/
│   │   │       ├── news-article.md   # News/blog post guidance
│   │   │       ├── research-paper.md # Arxiv/academic guidance
│   │   │       └── company-announcement.md  # Official blog guidance
│   │   │
│   │   └── detect-trends/
│   │       └── SKILL.md              # Cross-article pattern detection
│   │
│   ├── composition/
│   │   └── compose-digest-section/
│   │       ├── SKILL.md              # Core section composition
│   │       └── references/
│   │           ├── executive-brief.md     # Top-line summary guidance
│   │           ├── research-deep-dive.md  # Research analysis guidance
│   │           ├── tool-spotlight.md      # Product feature guidance
│   │           ├── company-roundup.md     # Business news guidance
│   │           └── trends.md              # Trends section guidance
│   │
│   └── publishing/
│       └── publish-to-discord/
│           ├── SKILL.md              # Core publishing procedure
│           └── references/
│               ├── digest-format.md  # Digest message formatting
│               └── breaking-format.md # Breaking news embed format
│
└── learning/
    └── process-feedback/
        ├── SKILL.md                  # Feedback handling procedure
        └── references/
            └── feedback-signals.md   # Emoji meanings and actions
```

### Core Skills

| Skill | Purpose | References Used |
|-------|---------|-----------------|
| `collect-feeds` | Fetch and parse RSS/API feeds | `rss-parsing.md` |
| `analyze-article` | LLM categorization, scoring, entity extraction | Selected by `source_category`: `news-article.md`, `research-paper.md`, or `company-announcement.md` |
| `detect-trends` | Find patterns across multiple articles | None (self-contained) |
| `compose-digest-section` | Generate a single digest section | Selected by `section_type`: `executive-brief.md`, `research-deep-dive.md`, etc. |
| `publish-to-discord` | Format and send to Discord | Selected by `publish_type`: `digest-format.md` or `breaking-format.md` |
| `process-feedback` | Handle user emoji reactions | `feedback-signals.md` |

### How Agents Use Skills with References

**ArticleAnalyst selecting analysis reference:**
```python
class ArticleAnalyst(KubaniAgent):
    async def analyze(self, article: Article) -> AnalyzedArticle:
        # Load the base skill
        skill = self.get_skill("analyze-article")

        # Select appropriate reference based on content type
        if article.source_category == "research":
            reference = skill.get_reference("research-paper.md")
        elif article.source_category == "company_blog":
            reference = skill.get_reference("company-announcement.md")
        else:
            reference = skill.get_reference("news-article.md")

        # Execute skill with selected reference
        return await self.execute_skill(
            skill,
            context={"article": article},
            reference=reference,
        )
```

**DigestComposer selecting section reference:**
```python
class DigestComposer(KubaniAgent):
    async def compose_section(
        self,
        articles: list[AnalyzedArticle],
        section_type: str,
    ) -> DigestSection:
        skill = self.get_skill("compose-digest-section")

        # Reference file matches section type
        reference = skill.get_reference(f"{section_type}.md")

        return await self.execute_skill(
            skill,
            context={"articles": articles, "section_type": section_type},
            reference=reference,
        )
```

### Example Skill: analyze-article

**SKILL.md:**
```markdown
---
name: analyze-article
description: Analyze news articles, research papers, or announcements for categorization, importance scoring, and entity extraction. Select appropriate reference based on content type.
metadata:
  domain: news
  category: analysis
---

# Analyze Article

## Purpose
Analyze a single article to extract structured insights for digest composition and breaking news detection.

## Procedure

1. **Load Reference**: Select reference file based on `source_category`:
   - research → references/research-paper.md
   - company_blog → references/company-announcement.md
   - other → references/news-article.md

2. **Prepare Content**: Format article title and summary for LLM

3. **Call LLM**: Using guidance from selected reference, extract:
   - Category (from reference-defined list)
   - Entities (types defined in reference)
   - Importance score (1-10, criteria in reference)
   - Breaking flag (criteria in reference)
   - Summary (style guidance in reference)

4. **Apply Boosters**: Per reference guidance (e.g., official blogs get +2 importance)

5. **Return Result**: Structured AnalyzedArticle

## Success Criteria
- Category is valid for content type
- Importance score is 1-10
- At least one entity extracted if names mentioned
- Summary is concise (2-3 sentences)
```

**references/research-paper.md:**
```markdown
# Research Paper Analysis

## Categories
- ml (machine learning)
- nlp (natural language processing)
- cv (computer vision)
- rl (reinforcement learning)
- theory (theoretical)
- safety (AI safety/alignment)
- other

## Entity Types
- Authors (names)
- Institutions (universities, labs)
- Techniques (transformer, RLHF, etc.)
- Datasets (ImageNet, MMLU, etc.)
- Benchmarks (scores, comparisons)

## Importance Criteria
- 9-10: State-of-the-art results, breakthrough methodology
- 7-8: Significant improvement, novel approach
- 5-6: Incremental progress, interesting findings
- 1-4: Minor contribution, replication study

## Breaking Criteria
- Claims state-of-the-art on major benchmark
- From top lab (DeepMind, OpenAI, Anthropic, Google, Meta AI)
- Addresses critical safety concern
- Introduces paradigm-shifting technique

## Summary Style
Technical but accessible. Focus on: What they did, why it matters, key result.
```

**references/news-article.md:**
```markdown
# News Article Analysis

## Categories
- business (funding, acquisitions, partnerships)
- product (launches, features, updates)
- security (vulnerabilities, breaches, patches)
- policy (regulation, governance, ethics)
- general (other AI news)

## Entity Types
- Companies (OpenAI, Google, startups)
- Products (ChatGPT, Claude, models)
- People (executives, researchers)
- Technologies (transformers, RAG, agents)

## Importance Criteria
- 9-10: Major industry impact, paradigm shift
- 7-8: Significant news, notable development
- 5-6: Interesting update, worth noting
- 1-4: Minor news, incremental update

## Breaking Criteria
- Major model release from top company
- Significant acquisition (>$100M or strategic)
- Critical security vulnerability
- Major policy/regulatory announcement

## Summary Style
Clear, concise, business-focused. Lead with the "so what?"
```

### Benefits of References Pattern

1. **Single skill, multiple variants** - One `analyze-article` skill handles news and research
2. **Progressive disclosure** - SKILL.md loaded on activation, references on-demand
3. **Easy to extend** - New content type = new reference file, no code changes
4. **Topic-specific customization** - AI news and sports news can have different references
5. **Testable** - Each reference can be validated independently

---

## 7. MCP Integration

### Required MCP Servers

| Server | Purpose | Status |
|--------|---------|--------|
| **Memory MCP** | Article storage, feedback, learnings | Existing |
| **Qdrant MCP** | Semantic search, deduplication | Existing |
| **Discord MCP** | Message publishing, reactions | Existing |
| **Temporal MCP** | Workflow management | Existing |

### Memory MCP Usage

```python
# Store analyzed article
await mcp.memory.store(
    namespace="news",
    key=f"{topic}/{article.url_hash}",
    value={
        "article": article.to_dict(),
        "analyzed_at": datetime.now().isoformat(),
        "topic": topic,
    },
    ttl_days=30,
)

# Query recent articles
articles = await mcp.memory.query(
    namespace="news",
    filter={"topic": topic, "analyzed_at": {"$gt": cutoff}},
    sort="-importance_score",
    limit=100,
)

# Store feedback
await mcp.memory.store(
    namespace="feedback",
    key=f"{message_id}/{user_id}",
    value={
        "type": feedback_type,
        "timestamp": datetime.now().isoformat(),
        "article_url": article_url,
    },
)
```

### Qdrant MCP Usage

```python
# Check for semantic duplicates
similar = await mcp.qdrant.search(
    collection="news-articles",
    query_vector=article.embedding,
    filter={"topic": topic},
    limit=5,
    score_threshold=0.95,  # Very similar = duplicate
)

# Find related articles for trends
related = await mcp.qdrant.search(
    collection="news-articles",
    query_vector=entity_embedding,
    filter={"topic": topic, "analyzed_at": {"$gt": cutoff}},
    limit=20,
)
```

### Discord MCP Usage

```python
# Publish digest
result = await mcp.discord.send_message(
    channel_name=channel,
    content=digest.formatted_content,
)

# Add feedback reactions
for emoji in FEEDBACK_EMOJIS:
    await mcp.discord.add_reaction(
        channel_id=result.channel_id,
        message_id=result.message_id,
        emoji=emoji,
    )

# Listen for reactions
async for event in mcp.discord.subscribe_reactions(channel_id):
    if event.emoji in FEEDBACK_EMOJIS:
        await process_feedback(event)
```

---

## 8. Feedback & Learning System

### Feedback Vocabulary

| Emoji | Meaning | Learning Signal | Action |
|-------|---------|-----------------|--------|
| `fire` | Excellent | High value content | Boost similar articles |
| `thumbs_up` | Good | Appropriate content | Baseline positive |
| `thumbs_down` | Not relevant | Filtering too loose | Tighten category matching |
| `x` | Irrelevant | Bad categorization | Review analysis prompt |
| `open_book` | More detail | Summary too brief | Increase summary length |
| `scissors` | Less detail | Too verbose | Decrease summary length |
| `zap` | Should be breaking | Urgency detection off | Lower breaking threshold |
| `clock` | Already knew / slow | Timeliness issue | Prioritize faster sources |
| `wrench` | Broken / unexpected | Operational issue | Create incident |

### Feedback Flow

```
1. User reacts to message with emoji
       |
       v
2. Discord MCP detects reaction event
       |
       v
3. Event published to bus: FEEDBACK_RECEIVED
       |
       v
4. FeedbackWorkflow triggered
       |
       v
5. Feedback stored in Memory MCP with:
   - message_id (links to original article/digest)
   - feedback_type (mapped from emoji)
   - user_id
   - timestamp
       |
       v
6. Special handling:
   - wrench -> create incident
   - zap -> flag for breaking threshold review
```

### Learning Integration (Hybrid Approach)

**Local Learning (per topic):**
- Track feedback ratios per category
- Track feedback ratios per source
- Adjust analysis prompts based on patterns

**Cross-Topic Learning (VoyagerSyndicate, future):**
- Aggregate feedback patterns across topics
- Propose skill improvements
- Identify cross-cutting insights (e.g., "company blog posts are more important")

### Metrics to Track

```python
# Per-digest metrics
digest_feedback = {
    "message_id": "...",
    "topic": "ai-news",
    "published_at": "...",
    "feedback": {
        "fire": 3,
        "thumbs_up": 8,
        "thumbs_down": 1,
        "x": 0,
    },
    "feedback_ratio": 0.92,  # (fire + thumbs_up) / total
}

# Per-source metrics
source_metrics = {
    "source": "TechCrunch",
    "articles_30d": 45,
    "avg_importance": 6.2,
    "feedback_ratio": 0.85,
}

# Per-category metrics
category_metrics = {
    "category": "research",
    "articles_30d": 120,
    "breaking_detected": 5,
    "breaking_confirmed": 4,  # User didn't react with clock
}
```

---

## 9. Discord Channel Strategy

### Channel Structure

```
AI News Server
├── #ai-news              <- Scheduled digests (morning, afternoon)
├── #ai-breaking-news     <- Breaking news alerts (@here)
├── #ai-research-deep-dive <- Research-focused content (future)
└── #ai-feedback          <- Bug reports, suggestions (future)
```

### Digest Sections (AI News)

| Section | Emoji | Filter | Frequency |
|---------|-------|--------|-----------|
| Executive Brief | `newspaper` | Top 5-6 by importance | Every digest |
| Research Deep Dive | `books` | category=research, importance>=7 | When available |
| Tool Spotlight | `wrench` | category=product, importance>=6 | When available |
| Company News | `newspaper` | category=business | When available |
| Patterns | `dart` | Emerging themes from trends | When 2+ trends |
| Trends | `chart_increasing` | Topic momentum | Every digest |

### Message Formatting

```markdown
# AI News Digest - January 24, 2026 (Morning)

**Executive Brief**

[Narrative summary with inline citations...]

---

**Research Deep Dive**

[Detailed analysis of top research paper...]

---

**Tool Spotlight**

[New tool announcement with details...]

---

**Trending Topics:**
- Reasoning Models (covered by 5 sources)
- AI Safety (covered by 3 sources)

---
*42 articles from 15 sources | React to provide feedback*
```

---

## 10. Error Handling

### Temporal Retry Policies

```python
# Feed collection - retry network errors
feed_retry = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    non_retryable_error_types=["ValueError"],  # Bad config = don't retry
)

# LLM analysis - retry API errors
llm_retry = RetryPolicy(
    maximum_attempts=5,
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=2),
)

# Discord publishing - retry rate limits
discord_retry = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=30),  # Respect rate limits
)
```

### Fallback Behaviors

| Failure | Fallback |
|---------|----------|
| LLM analysis fails | Use original summary, category=general, importance=5 |
| Feed unavailable | Skip feed, log warning, continue with others |
| Discord rate limited | Queue and retry with backoff |
| Memory MCP down | Log to local file, alert, continue without persistence |
| Qdrant down | Skip deduplication, continue |

### Alerting

```python
# Critical failures alert to Discord
if workflow_failed and attempts_exhausted:
    await mcp.discord.send_message(
        channel_name="ops-alerts",
        content=f"@here News workflow failed: {error}",
    )
```

---

## 11. Testing Strategy

### Test Levels

```
tests/
├── unit/
│   ├── agents/
│   │   ├── test_feed_collector.py
│   │   ├── test_article_analyst.py
│   │   ├── test_digest_composer.py
│   │   └── test_discord_publisher.py
│   └── workflows/
│       ├── test_collection_workflow.py
│       ├── test_digest_workflow.py
│       └── test_feedback_workflow.py
├── integration/
│   ├── test_mcp_integration.py
│   └── test_temporal_integration.py
└── e2e/
    └── test_full_pipeline.py
```

### Unit Tests

```python
# Test article analysis
class TestArticleAnalyst:
    def test_analyze_returns_structured_result(self):
        analyst = ArticleAnalyst()
        result = await analyst.analyze(
            article=sample_article,
            prompt_template=AI_ANALYSIS_PROMPT,
            categories=AI_CATEGORIES,
            breaking_criteria=AI_BREAKING_CRITERIA,
        )

        assert result.category in AI_CATEGORIES
        assert 1 <= result.importance_score <= 10
        assert isinstance(result.is_breaking, bool)

    def test_analyze_handles_llm_failure(self):
        # Should return fallback result, not raise
        ...
```

### Workflow Tests

```python
# Test collection workflow with mocked activities
@pytest.mark.asyncio
async def test_collection_workflow():
    async with WorkflowEnvironment.start_local() as env:
        async with Worker(
            env.client,
            task_queue="test",
            workflows=[CollectionWorkflow],
            activities=[collect_feeds, analyze_article, store_articles],
        ):
            result = await env.client.execute_workflow(
                CollectionWorkflow.run,
                args=[test_topic_config],
                task_queue="test",
            )

            assert result.collected > 0
            assert result.analyzed == result.collected
```

### Integration Tests

```python
# Test with real MCP servers (in test environment)
@pytest.mark.integration
async def test_memory_mcp_storage():
    client = await get_mcp_client()

    await client.memory.store(
        namespace="test-news",
        key="test-article",
        value={"title": "Test"},
    )

    result = await client.memory.get(
        namespace="test-news",
        key="test-article",
    )

    assert result["title"] == "Test"
```

---

## 12. Implementation Plan

### Phase 1: Foundation (Week 1-2)

**Goal:** Get basic collection -> analysis -> publish working with Temporal

| Task | Description | Files |
|------|-------------|-------|
| 1.1 | Create `NewsSyndicate` base class | `syndicates/_base/news.py` |
| 1.2 | Create `NewsWorkflows` with collection, digest, breaking | `syndicates/_base/workflows.py` |
| 1.3 | Refactor `FeedCollector` to accept feeds as parameter | `agents/feed_collector/` |
| 1.4 | Rename/refactor `ContentAnalyst` to `ArticleAnalyst` | `agents/article_analyst/` |
| 1.5 | Create `DigestComposer` agent | `agents/digest_composer/` |
| 1.6 | Rename/refactor `DigestPublisher` to `DiscordPublisher` | `agents/discord_publisher/` |
| 1.7 | Create `AINewsSyndicate` extending `NewsSyndicate` | `syndicates/ai_news/` |
| 1.8 | Register Temporal schedules on startup | `syndicates/ai_news/worker.py` |
| 1.9 | Unit tests for all agents | `tests/unit/agents/` |
| 1.10 | Workflow tests with mocked activities | `tests/unit/workflows/` |

**Success Criteria:**
- Digests publish to Discord on schedule via Temporal
- Breaking news publishes immediately
- All tests pass

### Phase 2: Memory & Deduplication (Week 3)

**Goal:** Add persistence and avoid duplicate articles

| Task | Description | Files |
|------|-------------|-------|
| 2.1 | Integrate Memory MCP for article storage | `agents/article_analyst/` |
| 2.2 | Add Qdrant MCP for semantic deduplication | `agents/feed_collector/` |
| 2.3 | Query recent articles for digest composition | `agents/digest_composer/` |
| 2.4 | Store published digests for feedback tracking | `agents/discord_publisher/` |
| 2.5 | Integration tests for MCP servers | `tests/integration/` |

**Success Criteria:**
- Articles persisted in Memory MCP
- Duplicate articles filtered
- Digests reference stored articles

### Phase 3: Feedback System (Week 4)

**Goal:** Capture and store user feedback

| Task | Description | Files |
|------|-------------|-------|
| 3.1 | Add feedback reactions to published messages | `agents/discord_publisher/` |
| 3.2 | Create `FeedbackWorkflow` | `syndicates/_base/workflows.py` |
| 3.3 | Subscribe to Discord reaction events | `syndicates/ai_news/syndicate.py` |
| 3.4 | Store feedback in Memory MCP | `workflows/feedback.py` |
| 3.5 | Create incident on `wrench` reaction | `workflows/feedback.py` |
| 3.6 | Dashboard for feedback metrics (basic) | `ui/` or Discord command |

**Success Criteria:**
- All messages have feedback reactions
- Reactions are captured and stored
- `wrench` creates alerts

### Phase 4: Rich Sections (Week 5)

**Goal:** Restore rich digest sections

| Task | Description | Files |
|------|-------------|-------|
| 4.1 | Define section configurations for AI news | `syndicates/ai_news/config.yaml` |
| 4.2 | Implement section composition logic | `agents/digest_composer/` |
| 4.3 | Executive Brief section | `skills/news/composition/` |
| 4.4 | Research Deep Dive section | `skills/news/composition/` |
| 4.5 | Tool Spotlight section | `skills/news/composition/` |
| 4.6 | Trends section | `skills/news/composition/` |
| 4.7 | Update Discord formatting | `agents/discord_publisher/` |

**Success Criteria:**
- Digests have multiple sections
- Sections are conditionally included based on content
- Formatting matches design spec

### Phase 5: Learning Loop (Week 6)

**Goal:** Use feedback to improve analysis

| Task | Description | Files |
|------|-------------|-------|
| 5.1 | Aggregate feedback metrics per source | Background job |
| 5.2 | Aggregate feedback metrics per category | Background job |
| 5.3 | Surface metrics in logs/dashboard | Observability |
| 5.4 | Document manual tuning process | `docs/` |
| 5.5 | (Future) Auto-adjust based on feedback | VoyagerSyndicate |

**Success Criteria:**
- Feedback metrics visible
- Clear process for tuning based on feedback

### Phase 6: Production Hardening (Week 7)

**Goal:** Ready for production deployment

| Task | Description | Files |
|------|-------------|-------|
| 6.1 | Error handling and fallbacks | All agents |
| 6.2 | Alerting for failures | `syndicates/ai_news/` |
| 6.3 | E2E tests | `tests/e2e/` |
| 6.4 | Deployment manifests | `infrastructure/gitops/` |
| 6.5 | Runbook documentation | `docs/operations/` |
| 6.6 | Load testing | Manual |

**Success Criteria:**
- Graceful degradation on failures
- Alerts for critical issues
- Documented operations

---

## Appendix A: Configuration Schema

### TopicConfig

```python
@dataclass
class TopicConfig:
    topic: str  # Unique identifier
    feeds: list[FeedConfig]
    analysis_prompt: str  # Path to prompt file
    categories: list[str]
    breaking_criteria: BreakingCriteria
    sections: list[SectionConfig]
    channels: dict[str, str]  # type -> channel_name
    schedule: dict[str, str]  # type -> cron expression
```

### FeedConfig

```python
@dataclass
class FeedConfig:
    name: str
    url: str
    category: str = "general"  # For filtering
    priority: int = 5  # 1-10, higher = check first
```

### SectionConfig

```python
@dataclass
class SectionConfig:
    id: str
    title: str
    emoji: str
    filter: str  # e.g., "category=research AND importance>=7"
    max_articles: int = 3
    composition_prompt: str  # Path to LLM prompt
```

### BreakingCriteria

```python
@dataclass
class BreakingCriteria:
    min_importance: int = 8
    require_is_breaking_flag: bool = True
    source_overrides: dict[str, int] = field(default_factory=dict)
    # e.g., {"OpenAI Blog": 7} - lower threshold for official sources
```

---

## Appendix B: Event Types

```python
# News events (add to framework/events/types.py)
NEWS_ARTICLE_COLLECTED = "news:article_collected"
NEWS_ARTICLE_ANALYZED = "news:article_analyzed"
NEWS_BREAKING_DETECTED = "news:breaking_detected"
NEWS_DIGEST_PUBLISHED = "news:digest_published"
NEWS_FEEDBACK_RECEIVED = "news:feedback_received"
NEWS_INCIDENT_CREATED = "news:incident_created"
```

---

## Appendix C: Migration from Current Code

### Files to Keep (Enhanced)
- `kubani/agents/feed_collector/` - Refactor to accept feeds parameter
- `kubani/agents/content_analyst/` - Rename to `article_analyst`, add parameters
- `kubani/agents/digest_publisher/` - Rename to `discord_publisher`
- `kubani/syndicates/news_digest/` - Refactor to `ai_news`, inherit from `NewsSyndicate`

### Files to Create
- `kubani/syndicates/_base/news.py` - Base class for topic syndicates
- `kubani/syndicates/_base/workflows.py` - Shared workflow definitions
- `kubani/agents/digest_composer/` - New agent for section composition
- `kubani/syndicates/ai_news/` - AI news topic syndicate

### Files to Remove
- None (all current code is refactored, not deleted)

### Breaking Changes
- Syndicate `run()` no longer uses asyncio loops
- Workflows registered with Temporal, not run inline
- Agents require configuration parameters, not hardcoded values

---

## Appendix D: Glossary

| Term | Definition |
|------|------------|
| **Topic** | A content domain (ai-news, sports-news) |
| **Syndicate** | Orchestration layer for a topic |
| **Agent** | Reusable component with specific capability |
| **Workflow** | Temporal workflow defining execution order |
| **Activity** | Temporal activity wrapping agent method |
| **Section** | Part of a digest (Research Deep Dive, etc.) |
| **Breaking** | High-urgency article requiring immediate publish |
| **Feedback** | User reaction to published content |

---

## Document History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-24 | Claude + Human | Initial design |
