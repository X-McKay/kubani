# News Syndicate Skills-Centric Migration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate all 6 news syndicate agents to the skills-centric architecture defined in ADR-007, enabling end-to-end testing of the new pattern.

**Architecture:** Agents become thin orchestrators (~100-150 LOC) that discover skills and delegate work via Strands SDK. Domain logic moves to portable skills following Agent Skills standard. Skills are loaded progressively (metadata first, full content on demand).

**Tech Stack:** Strands SDK, agentskills package, existing kubani.framework.skills module

---

## Overview

### Agents to Migrate (4,282 total LOC)

| Agent | Current LOC | Target LOC | Skills Needed |
|-------|-------------|------------|---------------|
| FeedCollectorAgent | 313 | ~100 | fetch-rss-feeds, filter-ai-relevant, deduplicate-articles |
| ContentAnalystAgent | 776 | ~120 | analyze-article, detect-trends, identify-breaking-news |
| ResearchCollectorAgent | 653 | ~100 | fetch-arxiv-papers, fetch-github-trending |
| ResearchAnalystAgent | 702 | ~120 | analyze-arxiv-paper, analyze-github-repo |
| TrendAnalystAgent | 539 | ~100 | analyze-trends-historical |
| DigestPublisherAgent | 1,299 | ~150 | compose-digest, compose-executive-digest, publish-to-discord |

### Existing Skills (from branch)

**Collection:**
- `kubani/skills/news/collection/fetch-rss-feeds/` ✅
- `kubani/skills/news/collection/filter-ai-relevant/` ✅
- `kubani/skills/news/collection/deduplicate-articles/` ✅
- `kubani/skills/news/collection/fetch-arxiv-papers/` ✅
- `kubani/skills/news/collection/fetch-github-trending/` ✅

**Analysis/Diagnostic:**
- `kubani/skills/news/analysis/analyze-article/` ✅
- `kubani/skills/news/analysis/detect-trends/` ✅
- `kubani/skills/news/analysis/identify-breaking-news/` ✅
- `kubani/skills/news/diagnostic/analyze-arxiv-paper/` ✅
- `kubani/skills/news/diagnostic/analyze-github-repo/` ✅
- `kubani/skills/news/diagnostic/analyze-trends-historical/` ✅

**Publishing:**
- `kubani/skills/news/publishing/compose-digest/` ✅
- `kubani/skills/news/action/compose-executive-digest/` ✅
- `kubani/skills/news/action/publish-to-discord/` ✅

---

## Task 1: Fix YAML Parsing Errors in Existing Skills

**Files:**
- Fix: `kubani/skills/news/diagnostic/analyze-arxiv-paper/SKILL.md`
- Fix: `kubani/skills/news/action/compose-executive-digest/SKILL.md`

**Step 1: Read and identify YAML issues**

The YAML frontmatter has unescaped quotes in description fields that break parsing.

**Step 2: Fix analyze-arxiv-paper SKILL.md**

Change line 20-21 from:
```yaml
    description: "standard" for digest inclusion, "deep" for featured research spotlight
```

To:
```yaml
    description: standard for digest inclusion, deep for featured research spotlight
```

**Step 3: Fix compose-executive-digest SKILL.md**

Change line 36 from:
```yaml
    description: "daily", "weekly", or "breaking"
```

To:
```yaml
    description: daily, weekly, or breaking
```

**Step 4: Verify fixes**

Run:
```bash
uv run python -c "
from kubani.framework.skills import discover_kubani_skills
from pathlib import Path
skills = discover_kubani_skills(Path('kubani/skills'))
print(f'Discovered {len(skills)} skills without errors')
"
```
Expected: No YAML parsing errors in output

**Step 5: Commit**

```bash
git add kubani/skills/news/diagnostic/analyze-arxiv-paper/SKILL.md
git add kubani/skills/news/action/compose-executive-digest/SKILL.md
git commit -m "fix: escape YAML quotes in skill frontmatter"
```

---

## Task 2: Create SkillsOrchestrator Base Class

**Files:**
- Create: `kubani/agents/_base/skills_orchestrator.py`
- Modify: `kubani/agents/_base/__init__.py`

**Step 1: Write failing test**

Create `tests/unit/agents/test_skills_orchestrator.py`:

```python
"""Tests for SkillsOrchestrator base class."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from kubani.agents._base.skills_orchestrator import SkillsOrchestrator


class TestSkillsOrchestrator:
    """Test the SkillsOrchestrator base class."""

    def test_orchestrator_inherits_kubani_agent(self):
        """SkillsOrchestrator should inherit from KubaniAgent."""
        from kubani.agents._base import KubaniAgent
        assert issubclass(SkillsOrchestrator, KubaniAgent)

    def test_orchestrator_discovers_skills(self):
        """Orchestrator should discover skills on init."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock_discover:
            mock_discover.return_value = []

            class TestOrchestrator(SkillsOrchestrator):
                AGENT_DIR = Path(__file__).parent
                async def on_skill_complete(self, skill_name, result):
                    pass

            orchestrator = TestOrchestrator()
            mock_discover.assert_called()

    def test_orchestrator_generates_skills_prompt(self):
        """Orchestrator should generate skills catalog for prompt."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock_discover:
            from kubani.framework.skills import KubaniSkill
            mock_discover.return_value = [
                KubaniSkill(
                    name="test-skill",
                    description="A test skill",
                    skill_path=Path("/test"),
                    license="MIT",
                    compatibility="None",
                    domain="news",
                    category="collection",
                )
            ]

            class TestOrchestrator(SkillsOrchestrator):
                AGENT_DIR = Path(__file__).parent
                async def on_skill_complete(self, skill_name, result):
                    pass

            orchestrator = TestOrchestrator()
            prompt = orchestrator._generate_skills_prompt()

            assert "test-skill" in prompt
            assert "A test skill" in prompt
```

**Step 2: Run test to verify it fails**

```bash
uv run python -m pytest tests/unit/agents/test_skills_orchestrator.py -v --override-ini="addopts="
```
Expected: FAIL with "No module named 'kubani.agents._base.skills_orchestrator'"

**Step 3: Implement SkillsOrchestrator**

Create `kubani/agents/_base/skills_orchestrator.py`:

```python
"""
Skills Orchestrator - Base class for skills-centric agents.

Extends KubaniAgent with skills discovery and progressive disclosure.
Agents extending this class are thin orchestrators that delegate to skills.
"""

import logging
from pathlib import Path
from typing import Any

from kubani.framework.skills import (
    KubaniSkill,
    discover_kubani_skills,
    generate_skills_catalog,
)

from .agent import KubaniAgent

logger = logging.getLogger(__name__)


class SkillsOrchestrator(KubaniAgent):
    """
    Base class for skills-centric agents.

    Discovers skills based on domain/category filters and generates
    a skills catalog for the system prompt. Skills are loaded progressively:
    - Phase 1: Metadata only (name, description) in system prompt
    - Phase 2: Full SKILL.md content loaded on demand via file_read tool

    Subclasses should:
    1. Set SKILLS_DOMAIN and SKILLS_CATEGORY class attributes
    2. Override _get_task_prompt() to generate task-specific prompts
    3. Implement on_skill_complete() for learning integration
    """

    # Override in subclass to filter skills
    SKILLS_DOMAIN: str | None = None
    SKILLS_CATEGORY: str | None = None
    SKILLS_ROOT: Path | None = None  # Defaults to kubani/skills

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the orchestrator with skill discovery."""
        super().__init__(agent_dir)

        # Discover skills
        self._skills: list[KubaniSkill] = []
        self._discover_skills()

    def _discover_skills(self) -> None:
        """Discover skills based on domain/category filters."""
        skills_root = self.SKILLS_ROOT
        if skills_root is None:
            # Default to kubani/skills relative to agent
            skills_root = self._agent_dir.parent.parent / "skills"

        if not skills_root.exists():
            logger.warning(f"Skills root not found: {skills_root}")
            return

        self._skills = discover_kubani_skills(
            skills_root,
            domain=self.SKILLS_DOMAIN,
            category=self.SKILLS_CATEGORY,
        )

        logger.info(
            f"Discovered {len(self._skills)} skills for {self.name} "
            f"(domain={self.SKILLS_DOMAIN}, category={self.SKILLS_CATEGORY})"
        )

    @property
    def skills(self) -> list[KubaniSkill]:
        """Get discovered skills."""
        return self._skills

    def _generate_skills_prompt(self) -> str:
        """
        Generate skills catalog for system prompt (Phase 1 disclosure).

        Returns metadata-only catalog to minimize token usage.
        Full skill content is loaded on demand via file_read tool.
        """
        if not self._skills:
            return "\n## No Skills Available\n"

        return generate_skills_catalog(self._skills)

    @property
    def prompt(self) -> str:
        """Get system prompt with skills catalog appended."""
        base_prompt = super().prompt
        skills_prompt = self._generate_skills_prompt()

        # Add instructions for using skills
        usage_instructions = """

## Using Skills

When you need to perform a task, check the available skills above.
To use a skill:
1. Read the full SKILL.md file to understand the detailed instructions
2. Follow the steps in the skill exactly
3. Report results in the format specified by the skill

Use the file_read tool to read skill files when needed.
"""

        return base_prompt + skills_prompt + usage_instructions

    def get_skill_path(self, skill_name: str) -> Path | None:
        """Get the path to a skill's SKILL.md file."""
        for skill in self._skills:
            if skill.name == skill_name:
                return skill.skill_path / "SKILL.md"
        return None

    def _get_task_prompt(self, **kwargs) -> str:
        """
        Generate a task-specific prompt for the agent.

        Override in subclass to create prompts for specific operations.

        Args:
            **kwargs: Task-specific parameters

        Returns:
            Prompt string for the task
        """
        return "Execute the task using available skills."
```

**Step 4: Update __init__.py**

Add to `kubani/agents/_base/__init__.py`:

```python
from .skills_orchestrator import SkillsOrchestrator

__all__ = ["KubaniAgent", "SkillsOrchestrator"]
```

**Step 5: Run test to verify it passes**

```bash
uv run python -m pytest tests/unit/agents/test_skills_orchestrator.py -v --override-ini="addopts="
```
Expected: PASS

**Step 6: Commit**

```bash
git add kubani/agents/_base/skills_orchestrator.py
git add kubani/agents/_base/__init__.py
git add tests/unit/agents/test_skills_orchestrator.py
git commit -m "feat: add SkillsOrchestrator base class for skills-centric agents"
```

---

## Task 3: Migrate FeedCollectorAgent

**Files:**
- Modify: `kubani/agents/feed_collector/agent.py`
- Keep: `kubani/agents/feed_collector/feeds.py` (configuration data)
- Test: `tests/unit/agents/test_feed_collector_skills.py`

**Step 1: Write failing test**

Create `tests/unit/agents/test_feed_collector_skills.py`:

```python
"""Tests for skills-centric FeedCollectorAgent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock


class TestFeedCollectorSkills:
    """Test FeedCollectorAgent with skills-centric architecture."""

    def test_inherits_skills_orchestrator(self):
        """FeedCollectorAgent should inherit from SkillsOrchestrator."""
        from kubani.agents.feed_collector import FeedCollectorAgent
        from kubani.agents._base import SkillsOrchestrator
        assert issubclass(FeedCollectorAgent, SkillsOrchestrator)

    def test_discovers_collection_skills(self):
        """Agent should discover news/collection skills."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock:
            mock.return_value = []
            from kubani.agents.feed_collector import FeedCollectorAgent
            agent = FeedCollectorAgent()

            # Verify it filters by news domain and collection category
            call_args = mock.call_args
            assert call_args.kwargs.get('domain') == 'news'
            assert call_args.kwargs.get('category') == 'collection'

    def test_has_collect_method(self):
        """Agent should have collect() method that delegates to skills."""
        from kubani.agents.feed_collector import FeedCollectorAgent
        agent = FeedCollectorAgent()
        assert hasattr(agent, 'collect')
        assert callable(agent.collect)

    @pytest.mark.asyncio
    async def test_collect_generates_task_prompt(self):
        """collect() should generate appropriate task prompt."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.feed_collector import FeedCollectorAgent
            agent = FeedCollectorAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(return_value='{"articles": [], "stats": {}}')

            await agent.collect(max_age_hours=24)

            # Verify run was called with a task prompt
            agent.run.assert_called_once()
            prompt = agent.run.call_args[0][0]
            assert 'collect' in prompt.lower() or 'fetch' in prompt.lower()
```

**Step 2: Run test to verify it fails**

```bash
uv run python -m pytest tests/unit/agents/test_feed_collector_skills.py -v --override-ini="addopts="
```
Expected: FAIL

**Step 3: Refactor FeedCollectorAgent**

Replace `kubani/agents/feed_collector/agent.py`:

```python
"""
Feed Collector Agent - Skills-centric RSS feed collection.

Thin orchestrator that delegates to collection skills:
- fetch-rss-feeds: Fetch articles from RSS/Atom feeds
- filter-ai-relevant: Filter for AI/ML relevance
- deduplicate-articles: Remove duplicates using Redis

Usage:
    from kubani.agents.feed_collector import FeedCollectorAgent

    agent = FeedCollectorAgent()
    result = await agent.collect(max_age_hours=24)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kubani.agents._base import SkillsOrchestrator

from .feeds import get_enabled_feeds

logger = logging.getLogger(__name__)


@dataclass
class RawArticle:
    """Raw article from RSS feed."""

    title: str
    url: str
    source: str
    published_date: str
    summary: str = ""
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    source_category: str = ""


@dataclass
class CollectionResult:
    """Result from running collection."""

    articles: list[RawArticle] = field(default_factory=list)
    total_collected: int = 0
    seen_filtered: int = 0
    sources_fetched: int = 0
    failed_feeds: int = 0


class FeedCollectorAgent(SkillsOrchestrator):
    """
    Skills-centric feed collector.

    Discovers and delegates to news/collection skills:
    - fetch-rss-feeds
    - filter-ai-relevant
    - deduplicate-articles
    """

    AGENT_DIR = Path(__file__).parent
    SKILLS_DOMAIN = "news"
    SKILLS_CATEGORY = "collection"

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Feed Collector agent."""
        super().__init__(agent_dir)

        # Collector-specific configuration
        collector_config = self.config.get("collector", {})
        self.default_max_age_hours = collector_config.get("max_age_hours", 24)
        self.default_filter_ai = collector_config.get("filter_ai_relevant", True)

    async def collect(
        self,
        max_age_hours: int | None = None,
        filter_ai_relevant: bool | None = None,
    ) -> CollectionResult:
        """
        Collect articles from RSS feeds using skills.

        Args:
            max_age_hours: Maximum article age (default from config)
            filter_ai_relevant: Whether to filter for AI relevance

        Returns:
            CollectionResult with articles and stats
        """
        max_age = max_age_hours or self.default_max_age_hours
        filter_ai = filter_ai_relevant if filter_ai_relevant is not None else self.default_filter_ai

        # Get feed configuration
        feeds = get_enabled_feeds()
        feeds_info = [
            {"name": f.name, "url": f.url, "category": f.category.value}
            for f in feeds
        ]

        # Generate task prompt
        task_prompt = self._get_task_prompt(
            feeds=feeds_info,
            max_age_hours=max_age,
            filter_ai_relevant=filter_ai,
        )

        # Delegate to LLM with skills
        try:
            response = await self.run(task_prompt)
            result = self._parse_collection_result(response)
            await self.on_skill_complete("collect", {"total": result.total_collected})
            return result
        except Exception as e:
            logger.error(f"Collection failed: {e}")
            await self.on_error(e, {"task": "collect"})
            return CollectionResult()

    def _get_task_prompt(
        self,
        feeds: list[dict],
        max_age_hours: int,
        filter_ai_relevant: bool,
    ) -> str:
        """Generate task prompt for collection."""
        feeds_json = json.dumps(feeds[:5], indent=2)  # Show sample feeds

        return f"""Collect articles from RSS feeds.

## Task Parameters
- Maximum article age: {max_age_hours} hours
- Filter for AI relevance: {filter_ai_relevant}
- Total feeds to process: {len(feeds)}

## Sample Feeds (first 5)
```json
{feeds_json}
```

## Instructions

Use the available skills to:

1. **Fetch RSS feeds** using the fetch-rss-feeds skill
   - Process all {len(feeds)} configured feeds
   - Extract title, URL, source, published_date, summary from each entry
   - Handle feed errors gracefully (log and continue)

2. **Filter by age**
   - Skip articles older than {max_age_hours} hours

3. **Filter AI relevance** (if enabled: {filter_ai_relevant})
   - Use the filter-ai-relevant skill for general_tech category feeds
   - Keep all articles from ai_focused, company_blogs, research categories

4. **Deduplicate articles** using the deduplicate-articles skill
   - Remove duplicates by URL within this run
   - Mark URLs as seen for future runs (7-day TTL)

## Output Format

Return a JSON object:
```json
{{
  "articles": [
    {{
      "title": "Article title",
      "url": "https://...",
      "source": "Feed name",
      "published_date": "ISO datetime",
      "summary": "Article summary",
      "author": "Author name or null",
      "tags": ["tag1", "tag2"],
      "source_category": "ai_focused"
    }}
  ],
  "stats": {{
    "total_collected": 42,
    "seen_filtered": 10,
    "sources_fetched": 18,
    "failed_feeds": 2
  }}
}}
```

Read the SKILL.md files for detailed instructions on each skill."""

    def _parse_collection_result(self, response: str) -> CollectionResult:
        """Parse LLM response into CollectionResult."""
        try:
            # Try to extract JSON from response
            data = self._extract_json(response)

            articles = [
                RawArticle(
                    title=a.get("title", ""),
                    url=a.get("url", ""),
                    source=a.get("source", ""),
                    published_date=a.get("published_date", ""),
                    summary=a.get("summary", ""),
                    author=a.get("author"),
                    tags=a.get("tags", []),
                    source_category=a.get("source_category", ""),
                )
                for a in data.get("articles", [])
            ]

            stats = data.get("stats", {})

            return CollectionResult(
                articles=articles,
                total_collected=stats.get("total_collected", len(articles)),
                seen_filtered=stats.get("seen_filtered", 0),
                sources_fetched=stats.get("sources_fetched", 0),
                failed_feeds=stats.get("failed_feeds", 0),
            )
        except Exception as e:
            logger.warning(f"Failed to parse collection result: {e}")
            return CollectionResult()

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from text, handling markdown code blocks."""
        import re

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        match = re.search(r'```(?:json)?\n(.*?)\n```', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        raise ValueError("No valid JSON found in response")

    async def collect_as_dicts(self) -> list[dict[str, Any]]:
        """Collect articles and return as serializable dicts."""
        result = await self.collect()
        return [
            {
                "title": a.title,
                "url": a.url,
                "source": a.source,
                "published_date": a.published_date,
                "summary": a.summary,
                "author": a.author,
                "tags": a.tags,
                "source_category": a.source_category,
            }
            for a in result.articles
        ]

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("total", 0) > 0
        await self.record_outcome(skill_name, result, success=success)
```

**Step 4: Run test to verify it passes**

```bash
uv run python -m pytest tests/unit/agents/test_feed_collector_skills.py -v --override-ini="addopts="
```
Expected: PASS

**Step 5: Commit**

```bash
git add kubani/agents/feed_collector/agent.py
git add tests/unit/agents/test_feed_collector_skills.py
git commit -m "refactor(feed_collector): migrate to skills-centric architecture"
```

---

## Task 4: Migrate ContentAnalystAgent

**Files:**
- Modify: `kubani/agents/content_analyst/agent.py`
- Keep: `kubani/agents/content_analyst/models.py`
- Test: `tests/unit/agents/test_content_analyst_skills.py`

**Step 1: Write failing test**

Create `tests/unit/agents/test_content_analyst_skills.py`:

```python
"""Tests for skills-centric ContentAnalystAgent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch


class TestContentAnalystSkills:
    """Test ContentAnalystAgent with skills-centric architecture."""

    def test_inherits_skills_orchestrator(self):
        """ContentAnalystAgent should inherit from SkillsOrchestrator."""
        from kubani.agents.content_analyst import ContentAnalystAgent
        from kubani.agents._base import SkillsOrchestrator
        assert issubclass(ContentAnalystAgent, SkillsOrchestrator)

    def test_discovers_analysis_skills(self):
        """Agent should discover news/analysis skills."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock:
            mock.return_value = []
            from kubani.agents.content_analyst import ContentAnalystAgent
            agent = ContentAnalystAgent()

            call_args = mock.call_args
            assert call_args.kwargs.get('domain') == 'news'
            assert call_args.kwargs.get('category') == 'analysis'

    def test_has_analyze_methods(self):
        """Agent should have analysis methods."""
        from kubani.agents.content_analyst import ContentAnalystAgent
        agent = ContentAnalystAgent()
        assert hasattr(agent, 'analyze_articles')
        assert hasattr(agent, 'detect_breaking_news')
        assert hasattr(agent, 'analyze_trends')
```

**Step 2: Run test to verify it fails**

```bash
uv run python -m pytest tests/unit/agents/test_content_analyst_skills.py -v --override-ini="addopts="
```
Expected: FAIL

**Step 3: Refactor ContentAnalystAgent**

Replace `kubani/agents/content_analyst/agent.py` with skills-centric version (~120 lines):

```python
"""
Content Analyst Agent - Skills-centric article analysis.

Thin orchestrator that delegates to analysis skills:
- analyze-article: Extract insights, entities, importance
- detect-trends: Identify trending topics
- identify-breaking-news: Flag breaking stories

Usage:
    from kubani.agents.content_analyst import ContentAnalystAgent

    agent = ContentAnalystAgent()
    result = await agent.full_analysis(articles)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from kubani.agents._base import SkillsOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class ProcessedArticle:
    """Article after LLM analysis."""
    url: str
    title: str
    source: str
    source_category: str
    published_at: datetime | None
    original_summary: str
    ai_summary: str
    category: str
    entities: list[str]
    importance_score: int
    is_breaking: bool
    breaking_reason: str | None
    content_hash: str
    processed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TrendingTopic:
    """Topic trending across multiple sources."""
    entity: str
    article_count: int
    sources: list[str]
    status: str  # HOT, RISING, STABLE
    momentum: float


@dataclass
class AnalysisResult:
    """Result from full analysis."""
    processed_articles: list[ProcessedArticle] = field(default_factory=list)
    breaking_articles: list[ProcessedArticle] = field(default_factory=list)
    trends: list[TrendingTopic] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


class ContentAnalystAgent(SkillsOrchestrator):
    """
    Skills-centric content analyst.

    Discovers and delegates to news/analysis skills:
    - analyze-article
    - detect-trends
    - identify-breaking-news
    """

    AGENT_DIR = Path(__file__).parent
    SKILLS_DOMAIN = "news"
    SKILLS_CATEGORY = "analysis"

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Content Analyst agent."""
        super().__init__(agent_dir)

        # Analyst-specific configuration
        analyst_config = self.config.get("analyst", {})
        self.min_importance = analyst_config.get("min_breaking_importance", 8)
        self.max_workers = analyst_config.get("max_workers", 8)

    async def analyze_articles(self, articles: list[dict]) -> list[ProcessedArticle]:
        """Analyze articles using analyze-article skill."""
        task_prompt = f"""Analyze these {len(articles)} articles.

Use the analyze-article skill to:
1. Generate concise summaries
2. Categorize by topic (research, business, product, security, policy)
3. Extract key entities
4. Assign importance scores (1-10)
5. Flag breaking news

Articles to analyze:
```json
{json.dumps(articles[:10], indent=2)}
```
{"..." if len(articles) > 10 else ""}

Return JSON array of processed articles."""

        response = await self.run(task_prompt)
        return self._parse_processed_articles(response)

    async def detect_breaking_news(
        self, articles: list[ProcessedArticle]
    ) -> list[ProcessedArticle]:
        """Filter breaking news using identify-breaking-news skill."""
        task_prompt = f"""Identify breaking news from these analyzed articles.

Use the identify-breaking-news skill to filter articles that:
- Have importance_score >= {self.min_importance}
- Are flagged as is_breaking = true
- Represent major announcements or events

Articles:
```json
{json.dumps([a.__dict__ for a in articles[:20]], indent=2, default=str)}
```

Return JSON array of breaking articles only."""

        response = await self.run(task_prompt)
        return self._parse_processed_articles(response)

    async def analyze_trends(
        self, articles: list[ProcessedArticle]
    ) -> list[TrendingTopic]:
        """Detect trends using detect-trends skill."""
        task_prompt = f"""Analyze trends across these {len(articles)} articles.

Use the detect-trends skill to:
1. Extract entities from all articles
2. Group by entity occurrence
3. Identify HOT topics (3+ sources)
4. Identify RISING topics (2 sources)
5. Calculate momentum

Articles:
```json
{json.dumps([{"title": a.title, "entities": a.entities, "source": a.source} for a in articles], indent=2)}
```

Return JSON array of trending topics."""

        response = await self.run(task_prompt)
        return self._parse_trends(response)

    async def full_analysis(self, articles: list[dict]) -> AnalysisResult:
        """Run complete analysis pipeline."""
        processed = await self.analyze_articles(articles)
        breaking = await self.detect_breaking_news(processed)
        trends = await self.analyze_trends(processed)

        await self.on_skill_complete("full_analysis", {
            "processed": len(processed),
            "breaking": len(breaking),
            "trends": len(trends),
        })

        return AnalysisResult(
            processed_articles=processed,
            breaking_articles=breaking,
            trends=trends,
            stats={
                "total_processed": len(processed),
                "breaking_count": len(breaking),
                "trend_count": len(trends),
            },
        )

    def _parse_processed_articles(self, response: str) -> list[ProcessedArticle]:
        """Parse LLM response into ProcessedArticles."""
        try:
            data = self._extract_json(response)
            articles = data if isinstance(data, list) else data.get("articles", [])
            return [
                ProcessedArticle(
                    url=a.get("url", ""),
                    title=a.get("title", ""),
                    source=a.get("source", ""),
                    source_category=a.get("source_category", ""),
                    published_at=None,
                    original_summary=a.get("original_summary", ""),
                    ai_summary=a.get("ai_summary", ""),
                    category=a.get("category", "general"),
                    entities=a.get("entities", []),
                    importance_score=a.get("importance_score", 5),
                    is_breaking=a.get("is_breaking", False),
                    breaking_reason=a.get("breaking_reason"),
                    content_hash=a.get("content_hash", ""),
                )
                for a in articles
            ]
        except Exception as e:
            logger.warning(f"Failed to parse articles: {e}")
            return []

    def _parse_trends(self, response: str) -> list[TrendingTopic]:
        """Parse LLM response into TrendingTopics."""
        try:
            data = self._extract_json(response)
            trends = data if isinstance(data, list) else data.get("trends", [])
            return [
                TrendingTopic(
                    entity=t.get("entity", ""),
                    article_count=t.get("article_count", 0),
                    sources=t.get("sources", []),
                    status=t.get("status", "STABLE"),
                    momentum=t.get("momentum", 0.0),
                )
                for t in trends
            ]
        except Exception as e:
            logger.warning(f"Failed to parse trends: {e}")
            return []

    def _extract_json(self, text: str) -> dict | list:
        """Extract JSON from text."""
        import re
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'```(?:json)?\n(.*?)\n```', text, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("processed", 0) > 0 or result.get("total", 0) > 0
        await self.record_outcome(skill_name, result, success=success)
```

**Step 4: Run test to verify it passes**

```bash
uv run python -m pytest tests/unit/agents/test_content_analyst_skills.py -v --override-ini="addopts="
```
Expected: PASS

**Step 5: Commit**

```bash
git add kubani/agents/content_analyst/agent.py
git add tests/unit/agents/test_content_analyst_skills.py
git commit -m "refactor(content_analyst): migrate to skills-centric architecture"
```

---

## Task 5: Migrate ResearchCollectorAgent

Similar pattern - create thin orchestrator delegating to:
- fetch-arxiv-papers
- fetch-github-trending

**Files:**
- Modify: `kubani/agents/research_collector/agent.py`
- Test: `tests/unit/agents/test_research_collector_skills.py`

Follow same test-first pattern as Tasks 3-4. Target ~100 lines.

---

## Task 6: Migrate ResearchAnalystAgent

Similar pattern - create thin orchestrator delegating to:
- analyze-arxiv-paper
- analyze-github-repo

**Files:**
- Modify: `kubani/agents/research_analyst/agent.py`
- Test: `tests/unit/agents/test_research_analyst_skills.py`

Follow same test-first pattern. Target ~120 lines.

---

## Task 7: Migrate TrendAnalystAgent

Similar pattern - create thin orchestrator delegating to:
- analyze-trends-historical

**Files:**
- Modify: `kubani/agents/trend_analyst/agent.py`
- Test: `tests/unit/agents/test_trend_analyst_skills.py`

Follow same test-first pattern. Target ~100 lines.

---

## Task 8: Migrate DigestPublisherAgent

Most complex migration due to multiple responsibilities. Create thin orchestrator delegating to:
- compose-digest
- compose-executive-digest
- publish-to-discord

**Files:**
- Modify: `kubani/agents/digest_publisher/agent.py`
- Test: `tests/unit/agents/test_digest_publisher_skills.py`

Follow same test-first pattern. Target ~150 lines.

---

## Task 9: Integration Test - End-to-End News Workflow

**Files:**
- Create: `tests/integration/test_news_syndicate_e2e.py`

```python
"""End-to-end test for skills-centric news syndicate."""

import pytest
from unittest.mock import AsyncMock, patch

from kubani.agents.feed_collector import FeedCollectorAgent
from kubani.agents.content_analyst import ContentAnalystAgent
from kubani.agents.digest_publisher import DigestPublisherAgent


@pytest.mark.asyncio
async def test_news_syndicate_e2e():
    """Test full news collection → analysis → publish flow."""

    # Mock LLM responses for deterministic testing
    with patch.object(FeedCollectorAgent, 'run') as mock_collect, \
         patch.object(ContentAnalystAgent, 'run') as mock_analyze, \
         patch.object(DigestPublisherAgent, 'run') as mock_publish:

        # Setup mock responses
        mock_collect.return_value = '{"articles": [{"title": "Test", "url": "https://test.com"}], "stats": {}}'
        mock_analyze.return_value = '{"articles": [{"title": "Test", "importance_score": 8}]}'
        mock_publish.return_value = '{"success": true, "message_id": "123"}'

        # Run pipeline
        collector = FeedCollectorAgent()
        collection_result = await collector.collect()
        assert collection_result.total_collected >= 0

        analyst = ContentAnalystAgent()
        analysis_result = await analyst.full_analysis([])
        assert analysis_result is not None

        publisher = DigestPublisherAgent()
        # Publisher test would go here

        print("E2E test passed - skills-centric architecture working")
```

**Run:**
```bash
uv run python -m pytest tests/integration/test_news_syndicate_e2e.py -v --override-ini="addopts="
```

---

## Task 10: Update News Syndicate Worker

**Files:**
- Modify: `kubani/syndicates/news_digest/src/news_digest_syndicate/worker.py`

Verify that Temporal activities still work with the new agent interfaces. The activity wrappers should remain compatible since the public API (collect(), analyze_articles(), etc.) is preserved.

---

## Success Criteria

1. All 6 agents migrated to SkillsOrchestrator pattern
2. Each agent reduced to ~100-150 lines (from 300-1300)
3. All unit tests passing
4. Integration test passing
5. Temporal worker compatible
6. Skills discoverable and documented

## Metrics to Measure

| Metric | Before | After |
|--------|--------|-------|
| Total agent LOC | 4,282 | ~750 |
| Test coverage | TBD | TBD |
| Token usage (startup) | TBD | TBD |

---

## Rollback Plan

If migration causes issues:
1. Git revert the agent changes
2. Skills remain available for future use
3. Original agents restored

The skills and SkillsOrchestrator base class can coexist with original agents.
