"""News Digest Workflow - Scheduled digest composition and publishing.

This workflow runs on a schedule (2x/day) to:
1. Query collected articles from Memory MCP (last 12 hours)
2. Analyze articles for trends and insights
3. Analyze research papers for digest inclusion
4. Analyze repos for tool spotlights
5. Compose and publish executive digest to Discord

The digest workflow queries data that was collected by NewsCollectionWorkflow,
enabling richer analysis with historical context.
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
class DigestInput:
    """Input for digest composition.

    Attributes:
        digest_type: Type of digest (morning, afternoon, on-demand)
        lookback_hours: Hours to look back for articles (default: 12)
        notify_channel: Discord channel for digest
        include_research: Whether to include research papers
        include_repos: Whether to include tool spotlights
        correlation_id: Optional ID for tracking
    """

    digest_type: str = "scheduled"
    lookback_hours: int = 12
    notify_channel: str = "ai-news"
    include_research: bool = True
    include_repos: bool = True
    correlation_id: str | None = None


@dataclass
class DigestResult:
    """Result of digest composition.

    Attributes:
        articles_included: Number of articles in digest
        papers_included: Number of papers included
        repos_included: Number of repos included
        trends_identified: Number of trends identified
        message_id: Discord message ID if published
        success: Whether composition succeeded
        error: Error message if failed
    """

    articles_included: int = 0
    papers_included: int = 0
    repos_included: int = 0
    trends_identified: int = 0
    message_id: str | None = None
    success: bool = True
    error: str | None = None


# =============================================================================
# Activity Retry Policies
# =============================================================================


ANALYSIS_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
)

PUBLISH_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=5,
)


# =============================================================================
# Workflow Definition
# =============================================================================


@workflow.defn
class NewsDigestWorkflow(ObservableWorkflowMixin):
    """Scheduled news digest composition workflow.

    Queries collected articles from Memory MCP, analyzes them,
    and publishes executive digests to Discord.

    Architecture:
    - Queries articles via query_articles_activity (Memory MCP)
    - Uses run_agent_activity to execute ContentAnalyst, ResearchAnalyst
    - Stores trend snapshots via store_trend_snapshot_activity
    - Publishes via DigestPublisher agent

    Status queries and pause/resume signals are inherited from
    ObservableWorkflowMixin for full observability.
    """

    def __init__(self) -> None:
        """Initialize the workflow."""
        self._init_observability("NewsDigestWorkflow")
        self._result = DigestResult()
        self._articles: list[dict[str, Any]] = []
        self._papers: list[dict[str, Any]] = []
        self._repos: list[dict[str, Any]] = []
        self._trends: list[dict[str, Any]] = []

    @workflow.run
    async def run(self, input: DigestInput | None = None) -> dict[str, Any]:
        """Execute digest composition.

        Args:
            input: Digest configuration (optional, uses defaults if not provided)

        Returns:
            DigestResult as dict
        """
        if input is None:
            input = DigestInput()
        self._set_status(
            WorkflowStatus.RUNNING,
            f"Starting {input.digest_type} digest",
            phase="init",
        )

        try:
            # Phase 1: Query collected articles
            await self._query_articles(input.lookback_hours)

            if not self._articles:
                self._set_status(WorkflowStatus.COMPLETED, "No articles to process")
                return self._build_result()

            # Check for pause/cancel
            if await self._wait_if_paused():
                return self._build_result()

            # Phase 2: Analyze articles for trends
            await self._analyze_articles()

            if await self._wait_if_paused():
                return self._build_result()

            # Phase 3: Analyze research papers (optional)
            if input.include_research:
                await self._analyze_papers()

            if await self._wait_if_paused():
                return self._build_result()

            # Phase 4: Analyze repos for spotlights (optional)
            if input.include_repos:
                await self._analyze_repos()

            if await self._wait_if_paused():
                return self._build_result()

            # Phase 5: Compose and publish digest
            await self._compose_and_publish(input.digest_type, input.notify_channel)

            # Phase 6: Store trend snapshot for future comparisons
            await self._store_trend_snapshot()

            self._set_status(WorkflowStatus.COMPLETED, "Digest published successfully")
            self._result.success = True

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"Digest failed: {e}")
            self._result.success = False
            self._result.error = str(e)
            raise  # Re-raise to mark workflow as Failed in Temporal

        return self._build_result()

    async def _query_articles(self, lookback_hours: int) -> None:
        """Query articles from Memory MCP."""
        from kubani.framework.temporal import query_articles_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Querying articles from last {lookback_hours} hours",
            phase="query_articles",
        )

        # Calculate time range (use workflow.now() for Temporal determinism)
        end_date = workflow.now()
        start_date = end_date - timedelta(hours=lookback_hours)

        result = await workflow.execute_activity(
            query_articles_activity,
            args=[
                start_date.isoformat(),
                end_date.isoformat(),
                None,  # source filter
                None,  # entity filter
                None,  # category filter
                0,  # min_importance
                200,  # limit
            ],
            start_to_close_timeout=timedelta(minutes=2),
        )

        if result.get("success"):
            self._articles = result.get("articles", [])
            self._result.articles_included = len(self._articles)
            self._log_event("articles_queried", f"Found {len(self._articles)} articles")
        else:
            self._log_event("error", f"Query failed: {result.get('error')}")

    async def _analyze_articles(self) -> None:
        """Analyze articles for trends and insights."""
        from kubani.framework.temporal import run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Analyzing {len(self._articles)} articles",
            phase="analyze_articles",
        )

        # Build analysis prompt with article data
        articles_summary = "\n".join(
            f"- {a.get('title', 'Unknown')} ({a.get('source', 'Unknown')})"
            for a in self._articles[:50]  # Limit to avoid token overflow
        )

        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "content-analyst",
                f"""Analyze these articles for trends and insights:

{articles_summary}

Identify:
1. Major themes and trends (with frequency)
2. Emerging topics (new in last 24h)
3. Key company updates
4. Notable research developments

Return JSON with:
- trends: array of {{topic, mention_count, momentum, description}}
- emerging: array of topic names
- company_updates: array of {{company, update, url}}
- research_highlights: array of {{title, significance}}""",
            ],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=ANALYSIS_RETRY_POLICY,
        )

        if result.get("success"):
            analysis = self._parse_json_from_result(result.get("result", ""))
            self._trends = analysis.get("trends", [])
            self._result.trends_identified = len(self._trends)
            self._log_event("analysis_complete", f"Identified {len(self._trends)} trends")

    async def _analyze_papers(self) -> None:
        """Analyze research papers for digest inclusion."""
        from kubani.framework.temporal import query_knowledge_activity, run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Analyzing research papers",
            phase="analyze_papers",
        )

        # Query papers from Memory MCP
        result = await workflow.execute_activity(
            query_knowledge_activity,
            args=[
                "recent AI/ML research papers",
                20,  # limit
            ],
            start_to_close_timeout=timedelta(minutes=1),
        )

        if not result.get("success") or not result.get("knowledge"):
            return

        papers = result.get("knowledge", [])

        # Analyze for digest worthiness
        papers_summary = "\n".join(
            f"- {p.get('topic', 'Unknown')}: {p.get('content', '')[:200]}..." for p in papers[:10]
        )

        analysis_result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "research-analyst",
                f"""Evaluate these papers for digest inclusion:

{papers_summary}

For each paper, determine:
- digest_worthy: boolean (significant enough for executive digest)
- significance: brief explanation
- category: foundational, applied, tool, benchmark

Return JSON array with paper evaluations.""",
            ],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=ANALYSIS_RETRY_POLICY,
        )

        if analysis_result.get("success"):
            self._papers = self._parse_json_array_from_result(analysis_result.get("result", ""))
            self._result.papers_included = sum(1 for p in self._papers if p.get("digest_worthy"))
            self._log_event(
                "papers_analyzed",
                f"Found {self._result.papers_included} digest-worthy papers",
            )

    async def _analyze_repos(self) -> None:
        """Analyze repos for tool spotlights.

        Queries stored repos from Memory MCP (collected by NewsCollectionWorkflow),
        then uses research-analyst agent to evaluate for digest inclusion.
        """
        from kubani.framework.temporal import query_knowledge_activity, run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Analyzing repos for spotlights",
            phase="analyze_repos",
        )

        # Query repos from Memory MCP
        result = await workflow.execute_activity(
            query_knowledge_activity,
            args=[
                "trending AI/ML GitHub repositories",
                20,  # limit
            ],
            start_to_close_timeout=timedelta(minutes=1),
        )

        if not result.get("success") or not result.get("knowledge"):
            return

        repos = result.get("knowledge", [])

        # Analyze for spotlight worthiness
        repos_summary = "\n".join(
            f"- {r.get('topic', 'Unknown')}: {r.get('content', '')[:200]}..." for r in repos[:10]
        )

        analysis_result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "research-analyst",
                f"""Review these trending AI/ML repositories for tool spotlight inclusion.

{repos_summary}

Criteria for spotlight:
- Practical utility for AI practitioners
- Active development and community
- Novel approach or significant improvement
- Good documentation

For each repo, determine:
- spotlight_worthy: boolean
- category: tool, library, dataset, model
- highlight: brief description of why it's noteworthy

Return JSON array with repo evaluations.""",
            ],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=ANALYSIS_RETRY_POLICY,
        )

        if analysis_result.get("success"):
            self._repos = self._parse_json_array_from_result(analysis_result.get("result", ""))
            self._result.repos_included = sum(1 for r in self._repos if r.get("spotlight_worthy"))
            self._log_event(
                "repos_analyzed",
                f"Found {self._result.repos_included} spotlight-worthy repos",
            )

    async def _compose_and_publish(self, digest_type: str, channel: str) -> None:
        """Compose and publish the executive digest."""
        from kubani.framework.temporal import run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Composing executive digest",
            phase="compose_publish",
        )

        # Build context for digest composition
        import json

        context = {
            "articles": self._articles[:20],  # Top articles
            "trends": self._trends,
            "papers": [p for p in self._papers if p.get("digest_worthy")],
            "repos": [r for r in self._repos if r.get("spotlight_worthy")],
            "digest_type": digest_type,
        }

        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "digest-publisher",
                f"""Compose and publish an executive AI news digest.

Context:
{json.dumps(context, indent=2)}

Create a professional digest with:
1. Executive Summary (key developments in 2-3 sentences)
2. Top Stories (3-5 most important articles with brief analysis)
3. Trend Analysis (what's gaining momentum)
4. Research Spotlight (1-2 notable papers if available)
5. Tool Spotlight (1-2 notable repos if available)
6. Company Updates (major announcements)

Format for Discord with proper markdown.
Publish to channel: {channel}

Return JSON with: message_id, chunks_sent, success""",
            ],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=PUBLISH_RETRY_POLICY,
        )

        if result.get("success"):
            publish_result = self._parse_json_from_result(result.get("result", ""))
            self._result.message_id = publish_result.get("message_id")
            self._log_event(
                "digest_published",
                f"Published digest to {channel}",
                message_id=self._result.message_id,
            )

            # Publish digest to UI activity feed
            try:
                from kubani.framework.temporal.activities import publish_ui_activity

                await workflow.execute_activity(
                    publish_ui_activity,
                    args=[
                        "news-digest",
                        "syndicate_output",
                        f"AI News Digest — {digest_type.title()}",
                        result.get("result", "")[:2000],
                        "info",
                        {
                            "digest_type": digest_type,
                            "articles_analyzed": len(self._articles),
                            "trends": len(self._trends),
                            "message_id": self._result.message_id,
                        },
                    ],
                    start_to_close_timeout=timedelta(seconds=10),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
            except Exception:
                pass  # UI publishing is non-critical
        else:
            self._log_event("error", f"Publish failed: {result.get('error')}")

    async def _store_trend_snapshot(self) -> None:
        """Store trend snapshot for historical comparison."""
        from kubani.framework.temporal import store_trend_snapshot_activity

        if not self._trends:
            return

        # Identify emerging and declining topics
        emerging = [t.get("topic") for t in self._trends if t.get("momentum", 0) > 0.5]
        declining = [t.get("topic") for t in self._trends if t.get("momentum", 0) < -0.3]

        await workflow.execute_activity(
            store_trend_snapshot_activity,
            args=[
                self._trends,
                emerging,
                declining,
                len(self._articles),
                30,  # ttl_days
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

        self._log_event(
            "trend_snapshot_stored",
            f"Stored snapshot with {len(self._trends)} trends",
        )

    # =========================================================================
    # Result Parsing Helpers
    # =========================================================================

    def _parse_json_from_result(self, result: str) -> dict[str, Any]:
        """Parse JSON object from agent result."""
        import json

        try:
            start = result.find("{")
            end = result.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(result[start:end])
        except json.JSONDecodeError:
            pass
        return {}

    def _parse_json_array_from_result(self, result: str) -> list[dict[str, Any]]:
        """Parse JSON array from agent result."""
        import json

        try:
            start = result.find("[")
            end = result.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(result[start:end])
        except json.JSONDecodeError:
            pass
        return []

    def _build_result(self) -> dict[str, Any]:
        """Build result dictionary."""
        return {
            "articles_included": self._result.articles_included,
            "papers_included": self._result.papers_included,
            "repos_included": self._result.repos_included,
            "trends_identified": self._result.trends_identified,
            "message_id": self._result.message_id,
            "success": self._result.success,
            "error": self._result.error,
        }

    # =========================================================================
    # Additional Queries
    # =========================================================================

    @workflow.query
    def get_digest_stats(self) -> dict[str, Any]:
        """Query current digest statistics."""
        return {
            "articles_included": self._result.articles_included,
            "papers_included": self._result.papers_included,
            "repos_included": self._result.repos_included,
            "trends_identified": self._result.trends_identified,
            "trends": self._trends[:5],  # Top 5 trends
        }

    @workflow.query
    def get_top_trends(self) -> list[dict[str, Any]]:
        """Query top trends identified."""
        return sorted(self._trends, key=lambda t: t.get("mention_count", 0), reverse=True)[:10]
