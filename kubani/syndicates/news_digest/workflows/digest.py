"""News Digest Composition Workflow.

Composes and publishes a structured news digest by querying analyzed documents
from Memory MCP. This is the final stage of the three-stage pipeline:

    Ingest → Analyze → **Digest**

The digest is composed using a **section-based approach** to stay within the
32k context window of the cluster LLM:

1. Query all analyzed documents for the lookback window.
2. Group documents by source type (rss, arxiv, github).
3. Generate each digest section independently via separate LLM calls:
   - "Top Stories" from RSS articles
   - "Research Spotlight" from arXiv papers
   - "Tool Spotlight" from GitHub repos
4. Synthesize the sections into a final digest with an Executive Summary.
5. Publish to Discord and the UI activity feed.

Each LLM call receives only the data for its section (~1-2k tokens), and the
final synthesis call receives only the rendered section text (~2-3k tokens).
This keeps every call well under the 32k limit.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from kubani.framework.temporal.workflows import ObservableWorkflowMixin, WorkflowStatus


# =============================================================================
# Input / Output
# =============================================================================


@dataclass
class DigestInput:
    """Input for a digest composition run.

    Attributes:
        digest_type: Type of digest (scheduled, morning, evening, on_demand).
        lookback_hours: How far back to look for analyzed documents.
        notify_channel: Discord channel to publish the digest to.
        min_importance: Minimum importance score to include (1-10).
        correlation_id: Optional tracking ID.
    """

    digest_type: str = "scheduled"
    lookback_hours: int = 12
    notify_channel: str = "ai-news"
    min_importance: int = 3
    correlation_id: str | None = None


@dataclass
class DigestResult:
    """Result of a digest composition run.

    Attributes:
        articles_included: Number of RSS articles included.
        papers_included: Number of arXiv papers included.
        repos_included: Number of GitHub repos included.
        total_documents: Total documents included in the digest.
        sections_generated: Number of sections successfully generated.
        message_id: Discord message ID if published.
        success: Whether the workflow completed without fatal errors.
        error: Error message if the workflow failed.
    """

    articles_included: int = 0
    papers_included: int = 0
    repos_included: int = 0
    total_documents: int = 0
    sections_generated: int = 0
    message_id: str | None = None
    success: bool = True
    error: str | None = None


# =============================================================================
# Retry Policies
# =============================================================================

QUERY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)

SECTION_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=2,
)

PUBLISH_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
)


# =============================================================================
# Section Configuration
# =============================================================================

# Maximum items per section to keep LLM calls small
MAX_ARTICLES = 15
MAX_PAPERS = 5
MAX_REPOS = 5


# =============================================================================
# Pure Functions for Section Data Preparation
# =============================================================================


def prepare_articles_context(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepare RSS article data for the Top Stories section.

    Strips each article to only the fields needed for section generation,
    keeping the payload small and predictable.

    Args:
        articles: List of AnalyzedDocument dicts with source_type='rss'.

    Returns:
        List of condensed article dicts, sorted by importance descending.
    """
    condensed = [
        {
            "title": a.get("title", ""),
            "summary": a.get("summary", ""),
            "source_name": a.get("source_name", ""),
            "importance_score": a.get("importance_score", 5),
            "entities": a.get("entities", [])[:5],
            "topics": a.get("topics", [])[:3],
        }
        for a in articles[:MAX_ARTICLES]
    ]
    return sorted(condensed, key=lambda x: x.get("importance_score", 0), reverse=True)


def prepare_papers_context(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepare arXiv paper data for the Research Spotlight section.

    Args:
        papers: List of AnalyzedDocument dicts with source_type='arxiv'.

    Returns:
        List of condensed paper dicts, sorted by importance descending.
    """
    condensed = [
        {
            "title": p.get("title", ""),
            "summary": p.get("summary", ""),
            "importance_score": p.get("importance_score", 5),
            "topics": p.get("topics", [])[:3],
        }
        for p in papers[:MAX_PAPERS]
    ]
    return sorted(condensed, key=lambda x: x.get("importance_score", 0), reverse=True)


def prepare_repos_context(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepare GitHub repo data for the Tool Spotlight section.

    Args:
        repos: List of AnalyzedDocument dicts with source_type='github'.

    Returns:
        List of condensed repo dicts, sorted by importance descending.
    """
    condensed = [
        {
            "title": r.get("title", ""),
            "summary": r.get("summary", ""),
            "importance_score": r.get("importance_score", 5),
            "metadata": {
                k: r.get("metadata", {}).get(k)
                for k in ["stars", "language", "trending_score"]
                if r.get("metadata", {}).get(k) is not None
            },
        }
        for r in repos[:MAX_REPOS]
    ]
    return sorted(condensed, key=lambda x: x.get("importance_score", 0), reverse=True)


def build_section_prompt(
    section_name: str,
    section_instructions: str,
    items: list[dict[str, Any]],
) -> str:
    """Build a prompt for generating a single digest section.

    This is a pure function that produces a deterministic prompt string
    from the section configuration and data.

    Args:
        section_name: Human-readable section name (e.g., "Top Stories").
        section_instructions: Specific instructions for this section.
        items: List of condensed item dicts for this section.

    Returns:
        A prompt string ready to send to the agent.
    """
    import json

    return f"""Write the "{section_name}" section of an AI news digest.

{section_instructions}

Data ({len(items)} items):
{json.dumps(items, indent=2)}

Rules:
- Write in professional, concise style suitable for a Discord message.
- Use Discord markdown formatting (bold, bullet points).
- Do NOT include a section header — just the content.
- Keep the section to 3-8 bullet points maximum.
- Focus on the most significant items.
- Return ONLY the section text, no JSON, no code fences."""


def build_synthesis_prompt(
    sections: dict[str, str],
    digest_type: str,
    lookback_hours: int,
) -> str:
    """Build the synthesis prompt that combines sections into a final digest.

    Args:
        sections: Dict mapping section names to their generated text.
        digest_type: Type of digest (scheduled, morning, evening).
        lookback_hours: How many hours the digest covers.

    Returns:
        A prompt string for the synthesis LLM call.
    """
    sections_text = ""
    for name, content in sections.items():
        if content:
            sections_text += f"\n### {name}\n{content}\n"

    return f"""Synthesize the following pre-written sections into a complete AI news digest.

Digest type: {digest_type}
Period: Last {lookback_hours} hours

Pre-written sections:
{sections_text}

Your task:
1. Write a 2-3 sentence **Executive Summary** that captures the most important
   developments across ALL sections.
2. Combine the Executive Summary with the pre-written sections into a single
   cohesive digest.
3. Format the final output for Discord with proper markdown:
   - Use "# AI News Digest" as the title
   - Use "## " for each section header
   - Add a brief footer with the period covered

Rules:
- Do NOT rewrite the section content — use it as-is.
- Do NOT add items that are not in the sections.
- The Executive Summary should reference specific items from the sections.
- Return ONLY the final formatted digest text, no JSON, no code fences."""


# =============================================================================
# Workflow
# =============================================================================


@workflow.defn
class NewsDigestWorkflow(ObservableWorkflowMixin):
    """Compose and publish a news digest from analyzed documents.

    Pipeline:
    1. Query analyzed documents from Memory MCP for the lookback window.
    2. Group documents by source type (rss, arxiv, github).
    3. Generate each section independently (separate LLM calls).
    4. Synthesize sections into a final digest with Executive Summary.
    5. Publish to Discord and the UI activity feed.

    Each LLM call is kept small (~1-3k tokens) to stay well within the
    32k context window of the cluster LLM.
    """

    def __init__(self) -> None:
        self._init_observability("NewsDigestWorkflow")
        self._result = DigestResult()
        self._documents: list[dict[str, Any]] = []

    @workflow.run
    async def run(self, input: DigestInput | None = None) -> dict[str, Any]:
        """Execute a digest composition run."""
        if input is None:
            input = DigestInput()

        self._set_status(WorkflowStatus.RUNNING, "Starting digest composition", phase="init")

        try:
            # Step 1: Query analyzed documents
            documents = await self._query_documents(input)
            self._documents = documents

            if not documents:
                self._set_status(
                    WorkflowStatus.COMPLETED,
                    "No documents found for digest period",
                )
                return self._build_result()

            if await self._wait_if_paused():
                return self._build_result()

            # Step 2: Group by source type and count
            grouped = self._group_documents(documents)

            if await self._wait_if_paused():
                return self._build_result()

            # Step 3: Generate sections independently
            sections = await self._generate_sections(grouped)
            self._result.sections_generated = len(
                [s for s in sections.values() if s]
            )

            if not any(sections.values()):
                self._set_status(
                    WorkflowStatus.COMPLETED,
                    "No sections could be generated",
                )
                return self._build_result()

            if await self._wait_if_paused():
                return self._build_result()

            # Step 4: Synthesize and publish
            await self._synthesize_and_publish(sections, input)

            self._set_status(
                WorkflowStatus.COMPLETED,
                f"Published digest with {self._result.total_documents} documents "
                f"across {self._result.sections_generated} sections",
            )
            return self._build_result()

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"Digest failed: {e}")
            self._result.success = False
            self._result.error = str(e)
            raise

    # =========================================================================
    # Pipeline Steps
    # =========================================================================

    async def _query_documents(self, input: DigestInput) -> list[dict[str, Any]]:
        """Query analyzed documents for the digest time window.

        Args:
            input: Digest configuration with lookback_hours and min_importance.

        Returns:
            List of AnalyzedDocument dicts sorted by importance.
        """
        from kubani.syndicates.news_digest.activities import query_analyzed_documents_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Querying documents from last {input.lookback_hours} hours",
            phase="query",
        )

        # Calculate the start date for the lookback window
        # Note: workflow.now() is the deterministic Temporal time
        now = workflow.now()
        start_date = (now - timedelta(hours=input.lookback_hours)).isoformat()

        result = await workflow.execute_activity(
            query_analyzed_documents_activity,
            args=[
                start_date,  # start_date
                None,  # end_date (now)
                None,  # source_type (all)
                input.min_importance,  # min_importance
                None,  # topics_filter
                100,  # limit
            ],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=QUERY_RETRY_POLICY,
        )

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            self._log_event("error", f"Document query failed: {error}")
            raise RuntimeError(f"Document query failed: {error}")

        documents = result.get("documents", [])
        self._log_event("documents_queried", f"Found {len(documents)} analyzed documents")
        return documents

    def _group_documents(
        self, documents: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Group documents by source type and update result counts.

        This is a pure function with no side effects beyond updating
        the result counters.

        Args:
            documents: List of AnalyzedDocument dicts.

        Returns:
            Dict mapping source_type to list of documents.
        """
        grouped: dict[str, list[dict[str, Any]]] = {
            "rss": [],
            "arxiv": [],
            "github": [],
        }

        for doc in documents:
            source_type = doc.get("source_type", "rss")
            if source_type in grouped:
                grouped[source_type].append(doc)
            else:
                grouped["rss"].append(doc)  # Default to rss

        self._result.articles_included = len(grouped["rss"])
        self._result.papers_included = len(grouped["arxiv"])
        self._result.repos_included = len(grouped["github"])
        self._result.total_documents = len(documents)

        self._log_event(
            "documents_grouped",
            f"Articles: {self._result.articles_included}, "
            f"Papers: {self._result.papers_included}, "
            f"Repos: {self._result.repos_included}",
        )
        return grouped

    async def _generate_sections(
        self, grouped: dict[str, list[dict[str, Any]]]
    ) -> dict[str, str]:
        """Generate each digest section independently via separate LLM calls.

        Each section is generated by its own agent call with only the data
        relevant to that section. This keeps each call small and focused.
        If a section fails, the others are unaffected.

        Args:
            grouped: Documents grouped by source type.

        Returns:
            Dict mapping section name to generated text (empty string on failure).
        """
        from kubani.framework.temporal import run_agent_activity

        sections: dict[str, str] = {}

        # Define section configurations
        section_configs = []

        # Top Stories (RSS articles)
        rss_articles = grouped.get("rss", [])
        if rss_articles:
            articles_context = prepare_articles_context(rss_articles)
            section_configs.append((
                "Top Stories",
                build_section_prompt(
                    "Top Stories",
                    "Summarize the most important AI/ML news articles. "
                    "For each notable story, include the title, a brief insight, "
                    "and why it matters. Prioritize by importance_score.",
                    articles_context,
                ),
            ))

        # Research Spotlight (arXiv papers)
        arxiv_papers = grouped.get("arxiv", [])
        if arxiv_papers:
            papers_context = prepare_papers_context(arxiv_papers)
            section_configs.append((
                "Research Spotlight",
                build_section_prompt(
                    "Research Spotlight",
                    "Highlight the most notable research papers. "
                    "For each paper, explain the key contribution and its "
                    "potential impact in accessible language.",
                    papers_context,
                ),
            ))

        # Tool Spotlight (GitHub repos)
        github_repos = grouped.get("github", [])
        if github_repos:
            repos_context = prepare_repos_context(github_repos)
            section_configs.append((
                "Tool Spotlight",
                build_section_prompt(
                    "Tool Spotlight",
                    "Highlight trending GitHub repositories and tools. "
                    "For each tool, explain what it does and why it's gaining "
                    "traction. Include star counts and languages where available.",
                    repos_context,
                ),
            ))

        # Generate each section sequentially
        # (Could be parallelized in future if Temporal supports it cleanly)
        for section_name, prompt in section_configs:
            self._set_status(
                WorkflowStatus.RUNNING,
                f"Generating section: {section_name}",
                phase="compose_sections",
            )

            try:
                result = await workflow.execute_activity(
                    run_agent_activity,
                    args=["content-analyst", prompt],
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=SECTION_RETRY_POLICY,
                )

                if result.get("success"):
                    section_text = result.get("result", "").strip()
                    sections[section_name] = section_text
                    self._log_event(
                        "section_generated",
                        f"Generated '{section_name}' ({len(section_text)} chars)",
                    )
                else:
                    sections[section_name] = ""
                    self._log_event(
                        "section_failed",
                        f"Failed to generate '{section_name}': {result.get('error', '')}",
                    )

            except Exception as e:
                sections[section_name] = ""
                self._log_event(
                    "section_error",
                    f"Error generating '{section_name}': {e}",
                )

        return sections

    async def _synthesize_and_publish(
        self,
        sections: dict[str, str],
        input: DigestInput,
    ) -> None:
        """Synthesize sections into a final digest and publish.

        The synthesis LLM call receives only the pre-rendered section text
        (not raw data), keeping the payload small. It adds an Executive
        Summary and formats the final output.

        Args:
            sections: Dict mapping section names to generated text.
            input: Digest configuration.
        """
        from kubani.framework.temporal import run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Synthesizing final digest",
            phase="synthesize",
        )

        # Build the synthesis prompt
        prompt = build_synthesis_prompt(
            sections=sections,
            digest_type=input.digest_type,
            lookback_hours=input.lookback_hours,
        )

        # Synthesize
        result = await workflow.execute_activity(
            run_agent_activity,
            args=["digest-publisher", prompt],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=SECTION_RETRY_POLICY,
        )

        if not result.get("success"):
            self._log_event("error", f"Synthesis failed: {result.get('error')}")
            # Fall back to concatenating sections directly
            digest_text = self._fallback_digest(sections, input)
        else:
            digest_text = result.get("result", "").strip()

        if not digest_text:
            self._log_event("warning", "Empty digest text, using fallback")
            digest_text = self._fallback_digest(sections, input)

        # Publish to Discord
        await self._publish_to_discord(digest_text, input)

        # Publish to UI activity feed (non-critical)
        await self._publish_to_ui(input, digest_text)

    def _fallback_digest(
        self, sections: dict[str, str], input: DigestInput
    ) -> str:
        """Build a fallback digest by concatenating sections directly.

        Used when the synthesis LLM call fails. This is a pure function
        that produces a valid digest without any LLM involvement.

        Args:
            sections: Dict mapping section names to generated text.
            input: Digest configuration.

        Returns:
            A formatted digest string.
        """
        parts = [f"# AI News Digest\n"]
        parts.append(f"*{input.digest_type.title()} — Last {input.lookback_hours} hours*\n")

        for name, content in sections.items():
            if content:
                parts.append(f"\n## {name}\n{content}")

        parts.append(
            f"\n---\n*{self._result.total_documents} documents from "
            f"{self._result.sections_generated} sections*"
        )
        return "\n".join(parts)

    async def _publish_to_discord(
        self, digest_text: str, input: DigestInput
    ) -> None:
        """Publish the final digest to Discord.

        Args:
            digest_text: The formatted digest text.
            input: Digest configuration with notify_channel.
        """
        from kubani.framework.temporal import run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Publishing to #{input.notify_channel}",
            phase="publish",
        )

        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "digest-publisher",
                f"""Publish the following digest to Discord channel #{input.notify_channel}.

{digest_text}

Use the publish-discord skill to send this content.
Return JSON with: message_id, chunks_sent, success""",
            ],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=PUBLISH_RETRY_POLICY,
        )

        if result.get("success"):
            from kubani.syndicates.news_digest.models import parse_json_object_from_text

            publish_result = parse_json_object_from_text(result.get("result", ""))
            self._result.message_id = publish_result.get("message_id")
            self._log_event(
                "digest_published",
                f"Published digest to {input.notify_channel}",
                message_id=self._result.message_id,
            )
        else:
            self._log_event("error", f"Publish failed: {result.get('error')}")

    async def _publish_to_ui(self, input: DigestInput, digest_text: str) -> None:
        """Publish digest summary to the UI activity feed.

        This is a non-critical operation; failures are silently ignored.
        """
        try:
            from kubani.framework.temporal.activities import publish_ui_activity

            await workflow.execute_activity(
                publish_ui_activity,
                args=[
                    "news-digest",
                    "syndicate_output",
                    f"AI News Digest — {input.digest_type.title()}",
                    digest_text[:2000],
                    "info",
                    {
                        "digest_type": input.digest_type,
                        "articles_included": self._result.articles_included,
                        "papers_included": self._result.papers_included,
                        "repos_included": self._result.repos_included,
                        "total_documents": self._result.total_documents,
                        "sections_generated": self._result.sections_generated,
                        "message_id": self._result.message_id,
                    },
                ],
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception:
            pass  # UI publishing is non-critical

    # =========================================================================
    # Result Building & Queries
    # =========================================================================

    def _build_result(self) -> dict[str, Any]:
        """Build the result dictionary."""
        return {
            "articles_included": self._result.articles_included,
            "papers_included": self._result.papers_included,
            "repos_included": self._result.repos_included,
            "total_documents": self._result.total_documents,
            "sections_generated": self._result.sections_generated,
            "message_id": self._result.message_id,
            "success": self._result.success,
            "error": self._result.error,
        }

    @workflow.query
    def get_digest_stats(self) -> dict[str, Any]:
        """Query current digest statistics."""
        return {
            "articles_included": self._result.articles_included,
            "papers_included": self._result.papers_included,
            "repos_included": self._result.repos_included,
            "total_documents": self._result.total_documents,
            "sections_generated": self._result.sections_generated,
        }

    @workflow.query
    def get_top_documents(self) -> list[dict[str, Any]]:
        """Query top documents by importance score."""
        return sorted(
            self._documents,
            key=lambda d: d.get("importance_score", 0),
            reverse=True,
        )[:10]

