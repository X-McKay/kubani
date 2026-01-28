"""News Collection Workflow - Continuous ambient article collection.

This workflow runs continuously (every 15 minutes) to:
1. Collect articles from RSS feeds
2. Collect research papers from arXiv
3. Collect trending repos from GitHub
4. Store everything in Memory MCP for later digest composition
5. Detect breaking news for immediate notification

The collection is separate from digest composition to enable:
- Breaking news detection (requires continuous monitoring)
- Cross-day deduplication (articles stored with TTL)
- Richer trend analysis (historical data available)
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from kubani.framework.temporal.workflows import ObservableWorkflowMixin, WorkflowStatus


# =============================================================================
# Input/Output Types
# =============================================================================


@dataclass
class CollectionInput:
    """Input for a collection run.

    Attributes:
        check_breaking: Whether to check for breaking news
        notify_channel: Discord channel for breaking news notifications
        correlation_id: Optional ID for tracking related operations
    """

    check_breaking: bool = True
    notify_channel: str = "ai-news-breaking"
    correlation_id: str | None = None


@dataclass
class CollectionResult:
    """Result of a collection run.

    Attributes:
        articles_collected: Number of articles collected
        papers_collected: Number of papers collected
        repos_collected: Number of repos collected
        articles_stored: Number of new articles stored (after deduplication)
        breaking_detected: Number of breaking news articles detected
        success: Whether the collection succeeded
        error: Error message if failed
    """

    articles_collected: int = 0
    papers_collected: int = 0
    repos_collected: int = 0
    articles_stored: int = 0
    breaking_detected: int = 0
    success: bool = True
    error: str | None = None


# =============================================================================
# Activity Imports (deferred)
# =============================================================================


# Retry policy for collection activities
COLLECTION_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
    non_retryable_error_types=["RateLimitError"],
)


# =============================================================================
# Workflow Definition
# =============================================================================


@workflow.defn
class NewsCollectionWorkflow(ObservableWorkflowMixin):
    """Continuous news collection workflow.

    Collects articles from various sources and stores them in Memory MCP.
    This workflow is designed to run on a schedule (every 15 minutes).

    Architecture:
    - Uses run_agent_activity to execute FeedCollector and ResearchCollector
    - Stores articles via store_article_activity (Memory MCP)
    - Checks for duplicates via check_article_exists_activity
    - Notifies on breaking news via Discord MCP

    Status queries and pause/resume signals are inherited from
    ObservableWorkflowMixin for full observability.
    """

    def __init__(self) -> None:
        """Initialize the workflow."""
        self._init_observability("NewsCollectionWorkflow")
        self._result = CollectionResult()

    @workflow.run
    async def run(self, input: CollectionInput) -> dict[str, Any]:
        """Execute a collection run.

        Args:
            input: Collection configuration

        Returns:
            CollectionResult as dict
        """
        self._set_status(WorkflowStatus.RUNNING, "Starting collection", phase="init")

        try:
            # Phase 1: Collect from RSS feeds
            await self._collect_articles()

            # Check for pause/cancel
            if await self._wait_if_paused():
                return self._build_result()

            # Phase 2: Collect research papers
            await self._collect_papers()

            if await self._wait_if_paused():
                return self._build_result()

            # Phase 3: Collect trending repos
            await self._collect_repos()

            if await self._wait_if_paused():
                return self._build_result()

            # Phase 4: Check for breaking news
            if input.check_breaking:
                await self._check_breaking_news(input.notify_channel)

            self._set_status(WorkflowStatus.COMPLETED, "Collection complete")
            self._result.success = True

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"Collection failed: {e}")
            self._result.success = False
            self._result.error = str(e)

        return self._build_result()

    async def _collect_articles(self) -> None:
        """Collect articles from RSS feeds."""
        from kubani.framework.temporal import run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Collecting articles from RSS feeds",
            phase="collect_articles",
        )
        self._log_event("phase_start", "Starting RSS collection")

        # Run feed collector agent
        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "feed-collector",
                "Collect articles from all configured RSS feeds. Return a JSON array of articles with url, title, source, published_at, and summary fields.",
            ],
            start_to_close_timeout=timedelta(minutes=5),
            heartbeat_timeout=timedelta(minutes=1),
            retry_policy=COLLECTION_RETRY_POLICY,
        )

        if not result.get("success"):
            self._log_event("error", f"Feed collection failed: {result.get('error')}")
            return

        # Parse articles from result
        articles = self._parse_articles_from_result(result.get("result", ""))
        self._result.articles_collected = len(articles)
        self._log_event("articles_collected", f"Collected {len(articles)} articles")

        # Store articles in Memory MCP
        stored = await self._store_articles(articles)
        self._result.articles_stored = stored

    async def _collect_papers(self) -> None:
        """Collect papers from arXiv."""
        from kubani.framework.temporal import run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Collecting papers from arXiv",
            phase="collect_papers",
        )
        self._log_event("phase_start", "Starting arXiv collection")

        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "research-collector",
                "Fetch recent AI/ML papers from arXiv. Return a JSON array with arxiv_id, title, authors, abstract, categories, and published_at fields.",
            ],
            start_to_close_timeout=timedelta(minutes=5),
            heartbeat_timeout=timedelta(minutes=1),
            retry_policy=COLLECTION_RETRY_POLICY,
        )

        if not result.get("success"):
            self._log_event("error", f"Paper collection failed: {result.get('error')}")
            return

        papers = self._parse_papers_from_result(result.get("result", ""))
        self._result.papers_collected = len(papers)
        self._log_event("papers_collected", f"Collected {len(papers)} papers")

        # Store papers in Memory MCP
        await self._store_papers(papers)

    async def _collect_repos(self) -> None:
        """Collect trending repos from GitHub."""
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
                "Fetch trending AI/ML repositories from GitHub. Return a JSON array with repo_url, name, description, stars, language, and topics fields.",
            ],
            start_to_close_timeout=timedelta(minutes=3),
            heartbeat_timeout=timedelta(minutes=1),
            retry_policy=COLLECTION_RETRY_POLICY,
        )

        if not result.get("success"):
            self._log_event("error", f"Repo collection failed: {result.get('error')}")
            return

        repos = self._parse_repos_from_result(result.get("result", ""))
        self._result.repos_collected = len(repos)
        self._log_event("repos_collected", f"Collected {len(repos)} repos")

    async def _store_articles(self, articles: list[dict[str, Any]]) -> int:
        """Store articles in Memory MCP with deduplication.

        Returns:
            Number of new articles stored
        """
        from kubani.framework.temporal import (
            check_article_exists_activity,
            store_article_activity,
        )

        stored_count = 0

        for article in articles:
            # Check if article already exists
            exists_result = await workflow.execute_activity(
                check_article_exists_activity,
                args=[article.get("url")],
                start_to_close_timeout=timedelta(seconds=10),
            )

            if exists_result.get("exists"):
                continue

            # Store the article
            store_result = await workflow.execute_activity(
                store_article_activity,
                args=[
                    article.get("url", ""),
                    article.get("title", ""),
                    article.get("source", ""),
                    article.get("published_at"),
                    article.get("summary", ""),
                    article.get("entities", []),
                    article.get("importance_score", 5),
                    article.get("category", "general"),
                    "",  # content_hash
                    14,  # ttl_days
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )

            if store_result.get("success"):
                stored_count += 1

        self._log_event("articles_stored", f"Stored {stored_count} new articles")
        return stored_count

    async def _store_papers(self, papers: list[dict[str, Any]]) -> None:
        """Store papers in Memory MCP."""
        from kubani.framework.temporal import store_knowledge_activity

        for paper in papers:
            await workflow.execute_activity(
                store_knowledge_activity,
                args=[
                    f"research/arxiv/{paper.get('arxiv_id', 'unknown')}",
                    f"{paper.get('title', '')}\n\n{paper.get('abstract', '')}",
                    "arxiv",
                    paper.get("categories", []),
                    {"authors": paper.get("authors", []), "arxiv_id": paper.get("arxiv_id")},
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )

    async def _check_breaking_news(self, notify_channel: str) -> None:
        """Check collected articles for breaking news."""
        from kubani.framework.temporal import run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Checking for breaking news",
            phase="check_breaking",
        )

        # Use content analyst to detect breaking news
        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "content-analyst",
                """Analyze the most recently collected articles for breaking news.
Breaking news criteria:
- Major product launches from leading AI companies
- Significant research breakthroughs
- Important regulatory announcements
- Security incidents affecting AI systems

Return a JSON array of breaking articles with: url, title, reason (why it's breaking), urgency (1-10).
Return empty array if no breaking news.""",
            ],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=COLLECTION_RETRY_POLICY,
        )

        if not result.get("success"):
            return

        breaking = self._parse_breaking_from_result(result.get("result", ""))
        self._result.breaking_detected = len(breaking)

        if breaking:
            self._log_event("breaking_detected", f"Detected {len(breaking)} breaking articles")
            await self._notify_breaking_news(breaking, notify_channel)

    async def _notify_breaking_news(self, breaking: list[dict[str, Any]], channel: str) -> None:
        """Send breaking news notifications to Discord."""
        # Import Discord activity (would be in discord MCP activities)
        # For now, log the intent
        self._log_event(
            "breaking_notification",
            f"Would notify {len(breaking)} breaking articles to {channel}",
            articles=[b.get("title") for b in breaking],
        )

    # =========================================================================
    # Result Parsing Helpers
    # =========================================================================

    def _parse_articles_from_result(self, result: str) -> list[dict[str, Any]]:
        """Parse articles from agent result."""
        import json

        try:
            # Try to find JSON array in result
            start = result.find("[")
            end = result.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(result[start:end])
        except json.JSONDecodeError:
            pass
        return []

    def _parse_papers_from_result(self, result: str) -> list[dict[str, Any]]:
        """Parse papers from agent result."""
        return self._parse_articles_from_result(result)

    def _parse_repos_from_result(self, result: str) -> list[dict[str, Any]]:
        """Parse repos from agent result."""
        return self._parse_articles_from_result(result)

    def _parse_breaking_from_result(self, result: str) -> list[dict[str, Any]]:
        """Parse breaking news from agent result."""
        return self._parse_articles_from_result(result)

    def _build_result(self) -> dict[str, Any]:
        """Build result dictionary."""
        return {
            "articles_collected": self._result.articles_collected,
            "papers_collected": self._result.papers_collected,
            "repos_collected": self._result.repos_collected,
            "articles_stored": self._result.articles_stored,
            "breaking_detected": self._result.breaking_detected,
            "success": self._result.success,
            "error": self._result.error,
        }

    # =========================================================================
    # Additional Queries
    # =========================================================================

    @workflow.query
    def get_collection_stats(self) -> dict[str, int]:
        """Query current collection statistics."""
        return {
            "articles_collected": self._result.articles_collected,
            "papers_collected": self._result.papers_collected,
            "repos_collected": self._result.repos_collected,
            "articles_stored": self._result.articles_stored,
            "breaking_detected": self._result.breaking_detected,
        }
