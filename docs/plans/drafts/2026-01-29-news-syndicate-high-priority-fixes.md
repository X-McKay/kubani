# News Syndicate High Priority Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three critical gaps in the news syndicate: breaking news Discord notifications, GitHub repo persistence, and date filtering for article queries.

**Architecture:** Each fix is isolated to specific files with minimal dependencies. Task 1 adds a Discord notification activity and integrates it into the collection workflow. Task 2 adds repo storage using the existing knowledge activity pattern. Task 3 adds proper date post-filtering to the article query activity.

**Tech Stack:** Python 3.11+, Temporal workflows/activities, MCP client (Memory, Discord), pytest

---

## Task 1: Implement Breaking News Discord Notifications

**Problem:** The `_notify_breaking_news()` method only logs events but never actually sends Discord notifications.

**Files:**
- Create: `kubani/framework/temporal/discord.py` (Discord activities)
- Modify: `kubani/syndicates/news_digest/workflows/collection.py:409-417`
- Modify: `kubani/framework/temporal/__init__.py` (export new activity)
- Test: `tests/workflows/syndicates/test_breaking_news_notification.py`

### Step 1: Write failing test for Discord notification activity

Create test file that verifies the activity sends to Discord MCP.

```python
# tests/workflows/syndicates/test_breaking_news_notification.py
"""Tests for breaking news Discord notification."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestSendBreakingNewsActivity:
    """Tests for send_breaking_news_activity."""

    @pytest.mark.asyncio
    async def test_sends_embed_to_discord(self):
        """Test that breaking news sends an embed to Discord."""
        from kubani.framework.temporal.discord import send_breaking_news_activity

        mock_client = MagicMock()
        mock_discord = AsyncMock()
        mock_discord.send_message_to_channel_name.return_value = MagicMock(
            success=True,
            data={"message_id": "123456", "channel_id": "789"},
        )
        mock_client.discord = mock_discord

        with patch(
            "kubani.framework.temporal.discord._get_mcp_client",
            return_value=mock_client,
        ):
            result = await send_breaking_news_activity(
                channel_name="ai-news-breaking",
                articles=[
                    {
                        "title": "OpenAI Releases GPT-5",
                        "url": "https://example.com/gpt5",
                        "reason": "Major model release",
                        "urgency": 9,
                    }
                ],
            )

        assert result["success"] is True
        assert result["message_id"] == "123456"
        mock_discord.send_message_to_channel_name.assert_called_once()

    @pytest.mark.asyncio
    async def test_formats_multiple_articles(self):
        """Test that multiple breaking articles are formatted correctly."""
        from kubani.framework.temporal.discord import send_breaking_news_activity

        mock_client = MagicMock()
        mock_discord = AsyncMock()
        mock_discord.send_message_to_channel_name.return_value = MagicMock(
            success=True,
            data={"message_id": "123456"},
        )
        mock_client.discord = mock_discord

        with patch(
            "kubani.framework.temporal.discord._get_mcp_client",
            return_value=mock_client,
        ):
            result = await send_breaking_news_activity(
                channel_name="ai-news-breaking",
                articles=[
                    {"title": "Article 1", "url": "https://a.com", "reason": "R1", "urgency": 9},
                    {"title": "Article 2", "url": "https://b.com", "reason": "R2", "urgency": 8},
                ],
            )

        assert result["success"] is True
        assert result["articles_notified"] == 2

    @pytest.mark.asyncio
    async def test_returns_failure_on_discord_error(self):
        """Test that Discord errors are handled gracefully."""
        from kubani.framework.temporal.discord import send_breaking_news_activity

        mock_client = MagicMock()
        mock_discord = AsyncMock()
        mock_discord.send_message_to_channel_name.return_value = MagicMock(
            success=False,
            error="Channel not found",
        )
        mock_client.discord = mock_discord

        with patch(
            "kubani.framework.temporal.discord._get_mcp_client",
            return_value=mock_client,
        ):
            result = await send_breaking_news_activity(
                channel_name="nonexistent-channel",
                articles=[{"title": "Test", "url": "https://test.com", "reason": "Test", "urgency": 8}],
            )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_skips_empty_articles_list(self):
        """Test that empty articles list returns early without calling Discord."""
        from kubani.framework.temporal.discord import send_breaking_news_activity

        mock_client = MagicMock()
        mock_discord = AsyncMock()
        mock_client.discord = mock_discord

        with patch(
            "kubani.framework.temporal.discord._get_mcp_client",
            return_value=mock_client,
        ):
            result = await send_breaking_news_activity(
                channel_name="ai-news-breaking",
                articles=[],
            )

        assert result["success"] is True
        assert result["articles_notified"] == 0
        mock_discord.send_message_to_channel_name.assert_not_called()
```

### Step 2: Run test to verify it fails

Run: `pytest tests/workflows/syndicates/test_breaking_news_notification.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'kubani.framework.temporal.discord'"

### Step 3: Create Discord activities module

```python
# kubani/framework/temporal/discord.py
"""Discord MCP integration for Temporal workflows.

This module provides Temporal activities for Discord notifications,
specifically designed for breaking news alerts and digest publishing.
"""

import logging
from datetime import datetime
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


def _get_mcp_client():
    """Get MCP client for Discord operations."""
    from kubani.framework.mcp import get_mcp_client

    return get_mcp_client()


def _format_breaking_news_embed(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Format breaking news articles as a Discord embed.

    Args:
        articles: List of breaking news articles with title, url, reason, urgency

    Returns:
        Discord embed dict ready for sending
    """
    # Sort by urgency (highest first)
    sorted_articles = sorted(articles, key=lambda a: a.get("urgency", 0), reverse=True)

    # Build embed fields for each article
    fields = []
    for article in sorted_articles[:5]:  # Limit to 5 articles per embed
        urgency = article.get("urgency", 0)
        urgency_indicator = "🔴" if urgency >= 9 else "🟠" if urgency >= 7 else "🟡"

        fields.append({
            "name": f"{urgency_indicator} {article.get('title', 'Unknown')}",
            "value": f"{article.get('reason', 'Breaking news')}\n[Read more]({article.get('url', '')})",
            "inline": False,
        })

    return {
        "title": "🚨 Breaking AI News",
        "description": f"**{len(articles)} breaking {'story' if len(articles) == 1 else 'stories'}** detected",
        "color": 0xFF4444,  # Red color for breaking news
        "fields": fields,
        "footer": f"Kubani News Monitor • {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "timestamp": datetime.utcnow().isoformat(),
    }


@activity.defn
async def send_breaking_news_activity(
    channel_name: str,
    articles: list[dict[str, Any]],
) -> dict[str, Any]:
    """Send breaking news notification to Discord.

    Args:
        channel_name: Discord channel name (without #)
        articles: List of breaking articles with title, url, reason, urgency

    Returns:
        Dict with success status, message_id, and articles_notified count
    """
    if not articles:
        logger.info("send_breaking_news_activity: No articles to notify")
        return {
            "success": True,
            "message_id": None,
            "articles_notified": 0,
        }

    logger.info(f"send_breaking_news_activity: Sending {len(articles)} breaking articles to #{channel_name}")

    try:
        client = _get_mcp_client()

        # Format articles as embed
        embed = _format_breaking_news_embed(articles)

        # Send to Discord via MCP
        response = await client.discord.send_message_to_channel_name(
            channel_name=channel_name,
            content=None,  # No plain text, just embed
            embed=embed,
        )

        if not response.success:
            logger.error(f"send_breaking_news_activity: Discord error: {response.error}")
            return {
                "success": False,
                "error": response.error,
                "articles_notified": 0,
            }

        message_id = response.data.get("message_id") if response.data else None
        logger.info(f"send_breaking_news_activity: Sent notification, message_id={message_id}")

        return {
            "success": True,
            "message_id": message_id,
            "channel_name": channel_name,
            "articles_notified": len(articles),
        }

    except Exception as e:
        logger.error(f"send_breaking_news_activity: Failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "articles_notified": 0,
        }


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "send_breaking_news_activity",
]
```

### Step 4: Run test to verify it passes

Run: `pytest tests/workflows/syndicates/test_breaking_news_notification.py -v`

Expected: All 4 tests PASS

### Step 5: Export the activity from temporal module

Modify `kubani/framework/temporal/__init__.py` to add the import and export:

```python
# Add to imports section (after line 82):
from .discord import (
    send_breaking_news_activity,
)

# Add to __all__ list (after line 196):
    # Discord Activities
    "send_breaking_news_activity",
```

### Step 6: Write test for workflow integration

```python
# Add to tests/workflows/syndicates/test_breaking_news_notification.py

class TestNewsCollectionWorkflowBreakingIntegration:
    """Tests for breaking news integration in NewsCollectionWorkflow."""

    def test_notify_method_exists(self):
        """Test that _notify_breaking_news method exists."""
        from kubani.syndicates.news_digest.workflows.collection import NewsCollectionWorkflow

        workflow = NewsCollectionWorkflow()
        assert hasattr(workflow, "_notify_breaking_news")
        assert callable(workflow._notify_breaking_news)

    def test_breaking_articles_list_stored(self):
        """Test that workflow stores breaking articles list, not just count."""
        from kubani.syndicates.news_digest.workflows.collection import NewsCollectionWorkflow

        workflow = NewsCollectionWorkflow()
        # After initialization, should have a place to store breaking articles
        assert hasattr(workflow, "_breaking_articles") or hasattr(workflow, "_result")
```

### Step 7: Run integration test to verify it fails

Run: `pytest tests/workflows/syndicates/test_breaking_news_notification.py::TestNewsCollectionWorkflowBreakingIntegration -v`

Expected: FAIL (workflow doesn't have `_breaking_articles` attribute yet)

### Step 8: Update workflow to store breaking articles and call Discord activity

Modify `kubani/syndicates/news_digest/workflows/collection.py`:

```python
# In __init__ (after line 109), add:
        self._breaking_articles: list[dict[str, Any]] = []

# Replace _notify_breaking_news method (lines 409-417) with:
    async def _notify_breaking_news(self, breaking: list[dict[str, Any]], channel: str) -> None:
        """Send breaking news notifications to Discord."""
        from kubani.framework.temporal import send_breaking_news_activity

        if not breaking:
            return

        self._breaking_articles = breaking

        result = await workflow.execute_activity(
            send_breaking_news_activity,
            args=[channel, breaking],
            start_to_close_timeout=timedelta(seconds=30),
        )

        if result.get("success"):
            self._log_event(
                "breaking_notification_sent",
                f"Notified {result.get('articles_notified', 0)} breaking articles to #{channel}",
                message_id=result.get("message_id"),
            )
        else:
            self._log_event(
                "breaking_notification_failed",
                f"Failed to notify breaking news: {result.get('error')}",
            )
```

### Step 9: Run tests to verify they pass

Run: `pytest tests/workflows/syndicates/test_breaking_news_notification.py -v`

Expected: All tests PASS

### Step 10: Update worker to register the new activity

Modify `kubani/syndicates/news_digest/src/news_digest_syndicate/worker.py` to include the new activity in `get_activities()`:

```python
# In get_activities function, add:
from kubani.framework.temporal import send_breaking_news_activity

# Add to the returned list:
    send_breaking_news_activity,
```

### Step 11: Commit Task 1

```bash
git add kubani/framework/temporal/discord.py \
        kubani/framework/temporal/__init__.py \
        kubani/syndicates/news_digest/workflows/collection.py \
        kubani/syndicates/news_digest/src/news_digest_syndicate/worker.py \
        tests/workflows/syndicates/test_breaking_news_notification.py
git commit -m "$(cat <<'EOF'
feat(news-syndicate): implement breaking news Discord notifications

- Add send_breaking_news_activity for Discord MCP integration
- Update _notify_breaking_news to actually send to Discord
- Store breaking articles list for debugging/observability
- Format breaking news as rich embeds with urgency indicators

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Persist GitHub Repos in Memory MCP

**Problem:** The `_collect_repos()` method collects repos but never stores them, unlike papers which are stored via `store_knowledge_activity()`.

**Files:**
- Modify: `kubani/syndicates/news_digest/workflows/collection.py:269-303`
- Modify: `kubani/framework/temporal/memory.py` (add store_repo_activity)
- Modify: `kubani/framework/temporal/__init__.py` (export new activity)
- Test: `tests/workflows/syndicates/test_repo_storage.py`

### Step 1: Write failing test for repo storage activity

```python
# tests/workflows/syndicates/test_repo_storage.py
"""Tests for GitHub repo storage in Memory MCP."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestStoreRepoActivity:
    """Tests for store_repo_activity."""

    @pytest.mark.asyncio
    async def test_stores_repo_as_knowledge(self):
        """Test that repo is stored as knowledge entry."""
        from kubani.framework.temporal.memory import store_repo_activity

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.store_knowledge.return_value = {"knowledge_id": "repo:abc123"}
        mock_memory.cache_set.return_value = {"success": True}
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            result = await store_repo_activity(
                repo_url="https://github.com/openai/gpt-4",
                name="gpt-4",
                description="GPT-4 model implementation",
                stars=50000,
                language="Python",
                topics=["ai", "llm", "gpt"],
                ttl_days=14,
            )

        assert result["success"] is True
        assert result["repo_id"] is not None
        mock_memory.store_knowledge.assert_called_once()

    @pytest.mark.asyncio
    async def test_repo_topic_format(self):
        """Test that repo uses correct topic format."""
        from kubani.framework.temporal.memory import store_repo_activity

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.store_knowledge.return_value = {"knowledge_id": "repo:test"}
        mock_memory.cache_set.return_value = {"success": True}
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            await store_repo_activity(
                repo_url="https://github.com/user/repo",
                name="repo",
                description="Test repo",
                stars=100,
                language="Python",
                topics=["test"],
            )

        # Verify topic format is "repo:{owner}/{name}"
        call_kwargs = mock_memory.store_knowledge.call_args[1]
        assert call_kwargs["topic"].startswith("repo:")

    @pytest.mark.asyncio
    async def test_dedup_cache_set(self):
        """Test that deduplication cache is set."""
        from kubani.framework.temporal.memory import store_repo_activity

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.store_knowledge.return_value = {"knowledge_id": "repo:test"}
        mock_memory.cache_set.return_value = {"success": True}
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            await store_repo_activity(
                repo_url="https://github.com/user/repo",
                name="repo",
                description="Test repo",
                stars=100,
                language="Python",
                topics=["test"],
                ttl_days=14,
            )

        # Verify cache_set was called for deduplication
        mock_memory.cache_set.assert_called_once()
        call_kwargs = mock_memory.cache_set.call_args[1]
        assert call_kwargs["key"].startswith("repo:dedup:")
        assert call_kwargs["ttl_seconds"] == 14 * 86400


class TestCheckRepoExistsActivity:
    """Tests for check_repo_exists_activity."""

    @pytest.mark.asyncio
    async def test_returns_exists_true_when_cached(self):
        """Test that existing repo returns exists=True."""
        from kubani.framework.temporal.memory import check_repo_exists_activity

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.cache_get.return_value = {"found": True, "value": {"url": "test"}}
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            result = await check_repo_exists_activity("https://github.com/user/repo")

        assert result["exists"] is True

    @pytest.mark.asyncio
    async def test_returns_exists_false_when_not_cached(self):
        """Test that non-existing repo returns exists=False."""
        from kubani.framework.temporal.memory import check_repo_exists_activity

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.cache_get.return_value = {"found": False}
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            result = await check_repo_exists_activity("https://github.com/user/new-repo")

        assert result["exists"] is False
```

### Step 2: Run test to verify it fails

Run: `pytest tests/workflows/syndicates/test_repo_storage.py -v`

Expected: FAIL with "ImportError: cannot import name 'store_repo_activity'"

### Step 3: Add repo storage activities to memory.py

Add to `kubani/framework/temporal/memory.py` (after line 425, before the Trend Activities section):

```python
# =============================================================================
# Repo Activities
# =============================================================================


def _repo_url_hash(url: str) -> str:
    """Create a short hash of a repo URL for cache keys."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


@activity.defn
async def store_repo_activity(
    repo_url: str,
    name: str,
    description: str,
    stars: int,
    language: str | None = None,
    topics: list[str] | None = None,
    forks: int = 0,
    trending_score: float = 0.0,
    ttl_days: int = 14,
) -> dict[str, Any]:
    """Store a GitHub repository using generic Memory MCP tools.

    Strategy:
    1. Store repo as knowledge entry with topic="repo:{owner/name}"
    2. Set cache key for URL deduplication

    Args:
        repo_url: Full GitHub repo URL
        name: Repository name
        description: Repository description
        stars: Star count
        language: Primary programming language
        topics: GitHub topics/tags
        forks: Fork count
        trending_score: Calculated trending score
        ttl_days: Days to retain in cache

    Returns:
        Dict with repo_id (knowledge_id) and status
    """
    logger.info(f"store_repo_activity: Storing '{name}' ({stars} stars)")

    try:
        client = _get_memory_client()
        url_hash = _repo_url_hash(repo_url)

        # Extract owner/repo from URL for topic
        # https://github.com/owner/repo -> owner/repo
        repo_path = repo_url.replace("https://github.com/", "").rstrip("/")

        # Build content string for knowledge storage
        content_parts = [
            f"# {name}",
            f"URL: {repo_url}",
            f"Stars: {stars} | Forks: {forks}",
        ]
        if language:
            content_parts.append(f"Language: {language}")
        if description:
            content_parts.append(f"\n{description}")

        content = "\n".join(content_parts)

        # Build metadata
        metadata = {
            "url": repo_url,
            "name": name,
            "stars": stars,
            "forks": forks,
            "language": language,
            "topics": topics or [],
            "trending_score": trending_score,
        }

        # Store as knowledge entry
        knowledge_result = await client.memory.store_knowledge(
            topic=f"repo:{repo_path}",
            content=content,
            source="github",
            related_topics=[f"topic:{t}" for t in (topics or [])[:5]],
            metadata=metadata,
        )

        # Set cache key for deduplication (TTL in seconds)
        await client.memory.cache_set(
            key=f"repo:dedup:{url_hash}",
            value={"url": repo_url, "stored_at": datetime.utcnow().isoformat()},
            ttl_seconds=ttl_days * 86400,
        )

        return {
            "success": True,
            "repo_id": knowledge_result.get("knowledge_id"),
            "url": repo_url,
        }

    except Exception as e:
        logger.error(f"store_repo_activity: Failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@activity.defn
async def check_repo_exists_activity(
    repo_url: str,
) -> dict[str, Any]:
    """Check if a repository already exists using cache lookup.

    Args:
        repo_url: Repository URL to check

    Returns:
        Dict with exists status
    """
    if not repo_url:
        return {"success": True, "exists": False, "repo_id": None}

    try:
        client = _get_memory_client()
        url_hash = _repo_url_hash(repo_url)

        result = await client.memory.cache_get(key=f"repo:dedup:{url_hash}")

        exists = result.get("found", False)
        return {
            "success": True,
            "exists": exists,
            "repo_id": f"repo:{url_hash}" if exists else None,
        }

    except Exception as e:
        logger.error(f"check_repo_exists_activity: Failed: {e}")
        return {
            "success": False,
            "exists": False,
            "error": str(e),
        }
```

### Step 4: Update memory.py exports

Add to the `__all__` list in `kubani/framework/temporal/memory.py`:

```python
    # Repo activities
    "store_repo_activity",
    "check_repo_exists_activity",
```

### Step 5: Run test to verify it passes

Run: `pytest tests/workflows/syndicates/test_repo_storage.py -v`

Expected: All tests PASS

### Step 6: Export from temporal __init__.py

Add to `kubani/framework/temporal/__init__.py`:

```python
# In imports (after check_article_exists_activity):
from .memory import (
    # ... existing imports ...
    store_repo_activity,
    check_repo_exists_activity,
)

# In __all__ (after query_articles_activity):
    # Memory Repo Activities
    "store_repo_activity",
    "check_repo_exists_activity",
```

### Step 7: Write test for workflow integration

```python
# Add to tests/workflows/syndicates/test_repo_storage.py

class TestNewsCollectionWorkflowRepoStorage:
    """Tests for repo storage in NewsCollectionWorkflow."""

    def test_store_repos_method_exists(self):
        """Test that _store_repos method exists."""
        from kubani.syndicates.news_digest.workflows.collection import NewsCollectionWorkflow

        workflow = NewsCollectionWorkflow()
        assert hasattr(workflow, "_store_repos")

    def test_repos_stored_count_in_result(self):
        """Test that CollectionResult has repos_stored field."""
        from kubani.syndicates.news_digest.workflows.collection import CollectionResult

        result = CollectionResult()
        assert hasattr(result, "repos_stored")
```

### Step 8: Run integration test to verify it fails

Run: `pytest tests/workflows/syndicates/test_repo_storage.py::TestNewsCollectionWorkflowRepoStorage -v`

Expected: FAIL (workflow doesn't have `_store_repos` method)

### Step 9: Update workflow to store repos

Modify `kubani/syndicates/news_digest/workflows/collection.py`:

First, update CollectionResult dataclass (after line 64):

```python
    repos_stored: int = 0
```

Then, replace `_collect_repos` method (lines 269-303) with:

```python
    async def _collect_repos(self) -> str | None:
        """Collect trending repos from GitHub.

        Returns:
            Error message if collection failed, None on success.
        """
        from kubani.framework.temporal import run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Collecting trending repos from GitHub",
            phase="collect_repos",
        )
        self._log_event("phase_start", "Starting GitHub collection")

        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "research-collector",
                "Fetch trending AI/ML repositories from GitHub. Return a JSON array with repo_url, name, description, stars, forks, language, and topics fields.",
            ],
            start_to_close_timeout=timedelta(minutes=3),
            heartbeat_timeout=timedelta(minutes=1),
            retry_policy=COLLECTION_RETRY_POLICY,
        )

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            self._log_event("error", f"Repo collection failed: {error}")
            return error

        repos = self._parse_repos_from_result(result.get("result", ""))
        self._result.repos_collected = len(repos)
        self._log_event("repos_collected", f"Collected {len(repos)} repos")

        # Store repos in Memory MCP
        stored = await self._store_repos(repos)
        self._result.repos_stored = stored
        return None

    async def _store_repos(self, repos: list[dict[str, Any]]) -> int:
        """Store repos in Memory MCP with deduplication.

        Returns:
            Number of new repos stored
        """
        from kubani.framework.temporal import (
            check_repo_exists_activity,
            store_repo_activity,
        )

        stored_count = 0

        for repo in repos:
            repo_url = repo.get("repo_url") or repo.get("url", "")
            if not repo_url:
                continue

            # Check if repo already exists
            exists_result = await workflow.execute_activity(
                check_repo_exists_activity,
                args=[repo_url],
                start_to_close_timeout=timedelta(seconds=10),
            )

            if exists_result.get("exists"):
                continue

            # Store the repo
            store_result = await workflow.execute_activity(
                store_repo_activity,
                args=[
                    repo_url,
                    repo.get("name", ""),
                    repo.get("description", ""),
                    repo.get("stars", 0),
                    repo.get("language"),
                    repo.get("topics", []),
                    repo.get("forks", 0),
                    repo.get("trending_score", 0.0),
                    14,  # ttl_days
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )

            if store_result.get("success"):
                stored_count += 1

        self._log_event("repos_stored", f"Stored {stored_count} new repos")
        return stored_count
```

Also update `_build_result` to include `repos_stored`:

```python
    def _build_result(self) -> dict[str, Any]:
        """Build result dictionary."""
        return {
            "articles_collected": self._result.articles_collected,
            "papers_collected": self._result.papers_collected,
            "repos_collected": self._result.repos_collected,
            "articles_stored": self._result.articles_stored,
            "repos_stored": self._result.repos_stored,
            "breaking_detected": self._result.breaking_detected,
            "success": self._result.success,
            "error": self._result.error,
        }
```

### Step 10: Run tests to verify they pass

Run: `pytest tests/workflows/syndicates/test_repo_storage.py -v`

Expected: All tests PASS

### Step 11: Update worker to register new activities

Modify `kubani/syndicates/news_digest/src/news_digest_syndicate/worker.py`:

```python
# In imports:
from kubani.framework.temporal import (
    # ... existing imports ...
    store_repo_activity,
    check_repo_exists_activity,
)

# In get_activities(), add:
    store_repo_activity,
    check_repo_exists_activity,
```

### Step 12: Commit Task 2

```bash
git add kubani/framework/temporal/memory.py \
        kubani/framework/temporal/__init__.py \
        kubani/syndicates/news_digest/workflows/collection.py \
        kubani/syndicates/news_digest/src/news_digest_syndicate/worker.py \
        tests/workflows/syndicates/test_repo_storage.py
git commit -m "$(cat <<'EOF'
feat(news-syndicate): persist GitHub repos in Memory MCP

- Add store_repo_activity and check_repo_exists_activity
- Update _collect_repos to store repos with deduplication
- Add repos_stored to CollectionResult for observability
- Use repo:{owner/repo} topic format for consistent querying

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Fix Date Filtering in Article Queries

**Problem:** The `query_articles_activity` uses semantic search with date text, which doesn't filter by date precisely. Articles older than the lookback window may be included.

**Files:**
- Modify: `kubani/framework/temporal/memory.py:467-568`
- Test: `tests/workflows/syndicates/test_article_date_filtering.py`

### Step 1: Write failing test for date filtering

```python
# tests/workflows/syndicates/test_article_date_filtering.py
"""Tests for article date filtering in Memory MCP queries."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


class TestQueryArticlesDateFiltering:
    """Tests for date filtering in query_articles_activity."""

    @pytest.mark.asyncio
    async def test_filters_articles_by_start_date(self):
        """Test that articles before start_date are filtered out."""
        from kubani.framework.temporal.memory import query_articles_activity

        now = datetime.utcnow()
        old_date = (now - timedelta(days=5)).isoformat()
        recent_date = (now - timedelta(hours=6)).isoformat()
        start_date = (now - timedelta(hours=12)).isoformat()

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        # Return mix of old and recent articles
        mock_memory.query_knowledge.return_value = [
            {
                "knowledge_id": "article:old",
                "topic": "article:abc123",
                "content": "# Old Article\nSource: Test",
                "source": "test",
                "metadata": {
                    "url": "https://old.com",
                    "source": "test",
                    "category": "general",
                    "importance_score": 7,
                    "published_at": old_date,
                },
            },
            {
                "knowledge_id": "article:recent",
                "topic": "article:def456",
                "content": "# Recent Article\nSource: Test",
                "source": "test",
                "metadata": {
                    "url": "https://recent.com",
                    "source": "test",
                    "category": "general",
                    "importance_score": 8,
                    "published_at": recent_date,
                },
            },
        ]
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            result = await query_articles_activity(
                start_date=start_date,
                end_date=now.isoformat(),
                min_importance=0,
                limit=100,
            )

        assert result["success"] is True
        # Should only return the recent article
        assert result["count"] == 1
        assert result["articles"][0]["url"] == "https://recent.com"

    @pytest.mark.asyncio
    async def test_filters_articles_by_end_date(self):
        """Test that articles after end_date are filtered out."""
        from kubani.framework.temporal.memory import query_articles_activity

        now = datetime.utcnow()
        old_date = (now - timedelta(hours=24)).isoformat()
        future_date = (now + timedelta(hours=1)).isoformat()  # Future (shouldn't exist but test edge case)
        end_date = (now - timedelta(hours=6)).isoformat()

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.query_knowledge.return_value = [
            {
                "knowledge_id": "article:old",
                "topic": "article:abc123",
                "content": "# Old Article\nSource: Test",
                "source": "test",
                "metadata": {
                    "url": "https://old.com",
                    "source": "test",
                    "category": "general",
                    "importance_score": 7,
                    "published_at": old_date,
                },
            },
        ]
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            result = await query_articles_activity(
                start_date=(now - timedelta(days=2)).isoformat(),
                end_date=end_date,
                min_importance=0,
                limit=100,
            )

        assert result["success"] is True
        # Old article is before end_date, should be included
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_handles_missing_published_at(self):
        """Test that articles without published_at are included."""
        from kubani.framework.temporal.memory import query_articles_activity

        now = datetime.utcnow()

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.query_knowledge.return_value = [
            {
                "knowledge_id": "article:no-date",
                "topic": "article:abc123",
                "content": "# No Date Article\nSource: Test",
                "source": "test",
                "metadata": {
                    "url": "https://nodate.com",
                    "source": "test",
                    "category": "general",
                    "importance_score": 7,
                    # No published_at
                },
            },
        ]
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            result = await query_articles_activity(
                start_date=(now - timedelta(hours=12)).isoformat(),
                min_importance=0,
                limit=100,
            )

        assert result["success"] is True
        # Article without date should still be included (can't filter it)
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_handles_invalid_published_at(self):
        """Test that articles with invalid dates are included."""
        from kubani.framework.temporal.memory import query_articles_activity

        now = datetime.utcnow()

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.query_knowledge.return_value = [
            {
                "knowledge_id": "article:bad-date",
                "topic": "article:abc123",
                "content": "# Bad Date Article\nSource: Test",
                "source": "test",
                "metadata": {
                    "url": "https://baddate.com",
                    "source": "test",
                    "category": "general",
                    "importance_score": 7,
                    "published_at": "not-a-date",
                },
            },
        ]
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            result = await query_articles_activity(
                start_date=(now - timedelta(hours=12)).isoformat(),
                min_importance=0,
                limit=100,
            )

        assert result["success"] is True
        # Article with invalid date should still be included
        assert result["count"] == 1
```

### Step 2: Run test to verify it fails

Run: `pytest tests/workflows/syndicates/test_article_date_filtering.py -v`

Expected: FAIL (date filtering not implemented, old articles included)

### Step 3: Update query_articles_activity with date post-filtering

Replace the `query_articles_activity` function in `kubani/framework/temporal/memory.py` (lines 467-568):

```python
def _parse_iso_date(date_str: str | None) -> datetime | None:
    """Parse ISO format date string, returning None on failure."""
    if not date_str:
        return None
    try:
        # Handle various ISO formats
        if "T" in date_str:
            # Full ISO format with time
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"
            return datetime.fromisoformat(date_str.replace("+00:00", ""))
        else:
            # Date only
            return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


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
    """Query stored articles using generic knowledge query with date post-filtering.

    Date filtering is done post-query since Qdrant semantic search doesn't support
    date-indexed queries. Articles without valid published_at dates are included
    (can't determine if they match the date range).

    Args:
        start_date: ISO format start date (filters out articles before this)
        end_date: ISO format end date (filters out articles after this)
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

        # Parse date boundaries
        start_dt = _parse_iso_date(start_date)
        end_dt = _parse_iso_date(end_date)

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

        # Query knowledge entries - over-fetch to account for date filtering
        fetch_limit = limit * 3 if (start_dt or end_dt) else limit * 2
        entries = await client.memory.query_knowledge(
            query=query,
            limit=fetch_limit,
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

            # Filter by importance
            if importance < min_importance:
                continue

            # Filter by date range
            published_at_str = metadata.get("published_at")
            published_dt = _parse_iso_date(published_at_str)

            # Only filter if we can parse the date
            if published_dt:
                if start_dt and published_dt < start_dt:
                    continue
                if end_dt and published_dt > end_dt:
                    continue

            articles.append(
                {
                    "article_id": entry.get("knowledge_id"),
                    "url": metadata.get("url", ""),
                    "title": entry.get("content", "").split("\n")[0].lstrip("# "),
                    "source": metadata.get("source", entry.get("source", "")),
                    "published_at": published_at_str,
                    "category": metadata.get("category", "general"),
                    "importance_score": importance,
                    "entities": metadata.get("entities", []),
                }
            )

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

### Step 4: Run tests to verify they pass

Run: `pytest tests/workflows/syndicates/test_article_date_filtering.py -v`

Expected: All 4 tests PASS

### Step 5: Run existing workflow tests to ensure no regression

Run: `pytest tests/workflows/syndicates/test_news_workflows.py -v`

Expected: All existing tests PASS

### Step 6: Commit Task 3

```bash
git add kubani/framework/temporal/memory.py \
        tests/workflows/syndicates/test_article_date_filtering.py
git commit -m "$(cat <<'EOF'
fix(news-syndicate): add proper date filtering for article queries

- Add post-query date filtering to query_articles_activity
- Filter articles by start_date and end_date using published_at
- Include articles with missing/invalid dates (can't determine range)
- Over-fetch from semantic search to account for date filtering

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Final Verification

### Step 1: Run all new tests

```bash
pytest tests/workflows/syndicates/test_breaking_news_notification.py \
       tests/workflows/syndicates/test_repo_storage.py \
       tests/workflows/syndicates/test_article_date_filtering.py -v
```

Expected: All tests PASS

### Step 2: Run existing news workflow tests

```bash
pytest tests/workflows/syndicates/test_news_workflows.py -v
```

Expected: All existing tests PASS

### Step 3: Run full test suite

```bash
just test
```

Expected: No regressions

---

## Summary of Changes

| Task | Files Modified | Key Changes |
|------|----------------|-------------|
| 1. Breaking News | `temporal/discord.py` (new), `collection.py`, `__init__.py`, `worker.py` | Added Discord notification activity, integrated into workflow |
| 2. Repo Storage | `temporal/memory.py`, `collection.py`, `__init__.py`, `worker.py` | Added repo storage/dedup activities, integrated into workflow |
| 3. Date Filtering | `temporal/memory.py` | Added date post-filtering to query_articles_activity |

**Total new files:** 1 (discord.py)
**Total test files:** 3
**Total modified files:** 5
