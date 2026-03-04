"""News Digest Composition Workflow.

Composes and publishes a structured news digest by querying analyzed documents
from Memory MCP. This is the final stage of the three-stage pipeline:

    Ingest → Analyze → **Digest**

The digest is composed using a **topic-clustered approach** to stay within the
32k context window of the cluster LLM:

1. Query all analyzed documents for the lookback window.
2. Cluster documents by their most common topics (e.g., "AI agents",
   "security", "open source") using frequency-based grouping.
3. Generate each digest section independently via separate LLM calls,
   one per topic cluster.
4. Compose the final digest from sections using a template (no LLM).
5. Publish to Discord via webhook and the UI activity feed.

Each LLM call receives only the data for its section (~1-2k tokens),
keeping every call well under the 32k limit.
"""

import json
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
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
            "url": a.get("source_uri", ""),
            "summary": a.get("summary", ""),
            "source_name": a.get("source_name", ""),
            "importance_score": a.get("importance_score", 5),
            "entities": a.get("entities", [])[:5],
            "topics": a.get("topics", [])[:3],
        }
        for a in articles[:MAX_ARTICLES]
    ]
    return sorted(condensed, key=lambda x: x.get("importance_score", 0), reverse=True)


# =============================================================================
# Topic-Based Clustering
# =============================================================================

MAX_TOPIC_SECTIONS = 4
MIN_DOCS_PER_CLUSTER = 2


def cluster_by_topics(documents: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Cluster documents by their most common topics.

    Groups documents into meaningful sections based on topic metadata.
    Each document is assigned to its highest-ranked matching topic cluster.
    Documents that don't fit any cluster go to a catch-all section.

    Args:
        documents: List of AnalyzedDocument dicts with 'topics' field.

    Returns:
        Dict mapping section name to list of documents, sorted by importance.
    """
    if not documents:
        return {}

    # Count topic frequency across all documents
    topic_counts: Counter[str] = Counter()
    for doc in documents:
        for topic in doc.get("topics", []):
            topic_counts[topic] += 1

    # Pick top topics that have at least MIN_DOCS_PER_CLUSTER documents
    top_topics = [
        topic for topic, count in topic_counts.most_common() if count >= MIN_DOCS_PER_CLUSTER
    ][:MAX_TOPIC_SECTIONS]

    if not top_topics:
        # No topic has enough docs — put everything in one section
        section_name = _topic_to_section_name(
            topic_counts.most_common(1)[0][0] if topic_counts else "Notable Developments"
        )
        return {
            section_name: sorted(
                documents, key=lambda d: d.get("importance_score", 0), reverse=True
            )
        }

    # Assign each document to its highest-ranked matching topic
    clusters: dict[str, list[dict[str, Any]]] = {}
    unclustered: list[dict[str, Any]] = []

    for doc in documents:
        doc_topics = doc.get("topics", [])
        assigned = False
        for topic in top_topics:
            if topic in doc_topics:
                section_name = _topic_to_section_name(topic)
                clusters.setdefault(section_name, []).append(doc)
                assigned = True
                break
        if not assigned:
            unclustered.append(doc)

    # Add unclustered docs to catch-all if any
    if unclustered:
        clusters["Notable Mentions"] = unclustered

    # Sort each cluster by importance
    return {
        name: sorted(docs, key=lambda d: d.get("importance_score", 0), reverse=True)
        for name, docs in clusters.items()
    }


def _topic_to_section_name(topic: str) -> str:
    """Convert a raw topic string to a readable section header."""
    return topic.strip().title()


def _section_instructions(section_name: str) -> str:
    """Generate section-specific writing instructions."""
    return (
        f"Summarize the most important developments in '{section_name}'. "
        "For each story, write 2-4 sentences: what happened, why it matters, "
        "and any broader implications for the AI/tech ecosystem. "
        "Note connections between related stories if they exist. "
        "Prioritize significance over recency."
    )


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

    return f"""Write the "{section_name}" section of an AI news digest.

{section_instructions}

Data ({len(items)} items):
{json.dumps(items, indent=2)}

Rules:
- For each story, write 2-4 sentences: what happened, why it matters, and broader implications.
- Start each bullet with **[Story Title](url)** using the `url` field from the data. If `url` is empty, use **Story Title** in bold instead.
- Note connections between related stories if any exist.
- Use Discord markdown formatting (bold titles, bullet points).
- Do NOT include a section header — just the content.
- Up to 10 bullet points.
- Prioritize significance over recency.
- Write for a technical audience who wants insights, not just headlines.
- Return ONLY the section text, no JSON, no code fences, no reasoning."""


def compose_digest(
    sections: dict[str, str],
    digest_type: str,
    lookback_hours: int,
    total_documents: int = 0,
) -> str:
    """Compose a complete digest from pre-written sections.

    Formats the sections into a clean Discord-ready digest with title,
    section headers, and footer. No LLM call — the section content is
    already high quality from the per-section agent calls.

    Args:
        sections: Dict mapping section names to their generated text.
        digest_type: Type of digest (daily, scheduled, morning, evening).
        lookback_hours: How many hours the digest covers.
        total_documents: Total documents included (for footer).

    Returns:
        A formatted digest string ready for Discord publishing.
    """
    parts = [f"# AI News Digest — {digest_type.title()}"]

    for name, content in sections.items():
        if content:
            parts.append(f"\n## {name}\n{content}")

    section_count = len([c for c in sections.values() if c])
    parts.append(
        f"\n---\n*{total_documents} sources across {section_count} topics · Last {lookback_hours}h*"
    )
    return "\n".join(parts)


# =============================================================================
# Workflow
# =============================================================================


@workflow.defn
class NewsDigestWorkflow(ObservableWorkflowMixin):
    """Compose and publish a news digest from analyzed documents.

    Pipeline:
    1. Query analyzed documents from Memory MCP for the lookback window.
    2. Cluster documents by topic frequency (via cluster_by_topics).
    3. Generate each section independently (one LLM call per topic cluster).
    4. Compose the final digest from sections (template, no LLM).
    5. Publish to Discord via webhook and the UI activity feed.

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

            # Step 2: Count source types for result stats
            for doc in documents:
                st = doc.get("source_type", "rss")
                if st == "rss":
                    self._result.articles_included += 1
                elif st == "arxiv":
                    self._result.papers_included += 1
                elif st == "github":
                    self._result.repos_included += 1
            self._result.total_documents = len(documents)

            if await self._wait_if_paused():
                return self._build_result()

            # Step 3: Cluster by topics and generate sections
            clusters = cluster_by_topics(documents)
            sections = await self._generate_sections(clusters)

            if not any(sections.values()):
                self._set_status(
                    WorkflowStatus.COMPLETED,
                    "No sections could be generated",
                )
                return self._build_result()

            if await self._wait_if_paused():
                return self._build_result()

            # Step 4: Compose and publish
            await self._compose_and_publish(sections, input)

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

    async def _generate_sections(self, clusters: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
        """Generate each digest section from topic clusters.

        Each cluster becomes a section, generated by its own agent call
        with only the data relevant to that section.

        Args:
            clusters: Documents grouped by topic (from cluster_by_topics).

        Returns:
            Dict mapping section name to generated text (empty string on failure).
        """
        from kubani.framework.temporal import run_agent_activity

        sections: dict[str, str] = {}

        for section_name, docs in clusters.items():
            self._set_status(
                WorkflowStatus.RUNNING,
                f"Generating section: {section_name}",
                phase="compose_sections",
            )

            # Prepare condensed context for this cluster
            items = prepare_articles_context(docs)
            prompt = build_section_prompt(section_name, _section_instructions(section_name), items)

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

        self._result.sections_generated = len([s for s in sections.values() if s])
        return sections

    async def _compose_and_publish(
        self,
        sections: dict[str, str],
        input: DigestInput,
    ) -> None:
        """Compose the final digest from sections and publish.

        Composes directly from a template — no LLM synthesis step.
        The section content is already high quality from the per-section
        LLM calls, so we just format and publish.

        Args:
            sections: Dict mapping section names to generated text.
            input: Digest configuration.
        """
        self._set_status(
            WorkflowStatus.RUNNING,
            "Composing final digest",
            phase="compose",
        )

        digest_text = compose_digest(
            sections=sections,
            digest_type=input.digest_type,
            lookback_hours=input.lookback_hours,
            total_documents=self._result.total_documents,
        )

        # Publish to Discord
        await self._publish_to_discord(digest_text, input)

        # Publish to UI activity feed (non-critical)
        await self._publish_to_ui(input, digest_text)

    async def _publish_to_discord(self, digest_text: str, input: DigestInput) -> None:
        """Publish the final digest to Discord via webhook.

        Uses a direct HTTP webhook call — no LLM in the loop.

        Args:
            digest_text: The formatted digest text.
            input: Digest configuration with notify_channel.
        """
        from kubani.syndicates.news_digest.activities import publish_digest_to_discord_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Publishing to #{input.notify_channel}",
            phase="publish",
        )

        result = await workflow.execute_activity(
            publish_digest_to_discord_activity,
            args=[digest_text],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=PUBLISH_RETRY_POLICY,
        )

        if result.get("success"):
            self._result.message_id = result.get("message_id")
            self._log_event(
                "digest_published",
                f"Published digest to #{input.notify_channel}",
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
