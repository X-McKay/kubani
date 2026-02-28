"""GitHub Trending Repos Ingest Workflow.

Collects trending AI/ML repositories from GitHub via the research-collector
agent, deduplicates by repository URL, and stores raw documents in Memory MCP.

Designed to run infrequently (every 6-12 hours) since GitHub trending repos
change slowly and the signal is more about weekly momentum than hourly updates.

Dedup strategy: SHA-256 hash of the full repository URL, checked via
batch cache lookup. Repos that were already seen are skipped entirely.
"""

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
class GitHubIngestInput:
    """Input for a GitHub ingest run.

    Attributes:
        max_results: Maximum number of repos to fetch.
        correlation_id: Optional tracking ID.
    """

    max_results: int = 20
    correlation_id: str | None = None


@dataclass
class GitHubIngestResult:
    """Result of a GitHub ingest run.

    Attributes:
        repos_collected: Total repos returned by the agent.
        repos_new: Repos that passed deduplication.
        repos_stored: Repos successfully stored in Memory MCP.
        success: Whether the workflow completed without fatal errors.
        error: Error message if the workflow failed.
    """

    repos_collected: int = 0
    repos_new: int = 0
    repos_stored: int = 0
    success: bool = True
    error: str | None = None


# =============================================================================
# Retry Policies
# =============================================================================

AGENT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
    non_retryable_error_types=["RateLimitError"],
)

STORAGE_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=2,
)


# =============================================================================
# Workflow
# =============================================================================


@workflow.defn
class GitHubIngestWorkflow(ObservableWorkflowMixin):
    """Ingest trending repos from GitHub.

    Pipeline:
    1. Call research-collector agent to fetch trending repos.
    2. Parse the agent response into repo dicts.
    3. Convert to RawDocument dicts.
    4. Batch-check dedup keys against Memory MCP cache.
    5. Store new documents and set dedup cache keys.
    """

    def __init__(self) -> None:
        self._init_observability("GitHubIngestWorkflow")
        self._result = GitHubIngestResult()

    @workflow.run
    async def run(self, input: GitHubIngestInput | None = None) -> dict[str, Any]:
        """Execute a GitHub ingest run."""
        if input is None:
            input = GitHubIngestInput()

        self._set_status(WorkflowStatus.RUNNING, "Starting GitHub ingest", phase="init")

        try:
            # Step 1: Fetch repos via agent
            repos = await self._fetch_repos(input)
            self._result.repos_collected = len(repos)

            if not repos:
                self._set_status(WorkflowStatus.COMPLETED, "No repos found")
                return self._build_result()

            if await self._wait_if_paused():
                return self._build_result()

            # Step 2: Convert to RawDocument dicts
            raw_docs = self._convert_to_raw_documents(repos)

            # Step 3: Batch dedup
            new_docs = await self._batch_dedup(raw_docs)
            self._result.repos_new = len(new_docs)

            if not new_docs:
                self._set_status(WorkflowStatus.COMPLETED, "All repos already seen")
                return self._build_result()

            if await self._wait_if_paused():
                return self._build_result()

            # Step 4: Store new documents
            stored = await self._store_documents(new_docs)
            self._result.repos_stored = stored

            # Step 5: Trigger analysis for new documents (fire-and-forget)
            await self._trigger_analysis(new_docs)

            self._set_status(
                WorkflowStatus.COMPLETED,
                f"Stored {stored} new repos",
            )
            return self._build_result()

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"GitHub ingest failed: {e}")
            self._result.success = False
            self._result.error = str(e)
            raise

    # =========================================================================
    # Pipeline Steps
    # =========================================================================

    async def _fetch_repos(self, input: GitHubIngestInput) -> list[dict[str, Any]]:
        """Fetch trending repos from GitHub via the research-collector agent."""
        from kubani.framework.temporal import run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Fetching trending repos from GitHub",
            phase="fetch",
        )

        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "research-collector",
                f"""Fetch the top {input.max_results} trending AI/ML repositories from GitHub.

Focus on repositories that are:
- Actively maintained and recently updated
- Related to AI, ML, LLMs, or data science
- Gaining significant traction (stars, forks)

Return ONLY a JSON array where each element has these fields:
- repo_url: string (full GitHub URL)
- name: string (repo name)
- description: string
- stars: integer
- language: string (primary language)
- topics: array of strings
- forks: integer
- trending_score: float (0.0 to 1.0, your estimate of trending momentum)""",
            ],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=AGENT_RETRY_POLICY,
        )

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            self._log_event("error", f"Repo fetch failed: {error}")
            raise RuntimeError(f"Repo fetch failed: {error}")

        from kubani.syndicates.news_digest.models import parse_json_array_from_text

        repos = parse_json_array_from_text(result.get("result", ""))
        self._log_event("repos_fetched", f"Fetched {len(repos)} repos")
        return repos

    def _convert_to_raw_documents(self, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert GitHub repo dicts to RawDocument dicts."""
        from kubani.syndicates.news_digest.models import raw_document_from_github_repo

        docs = []
        for repo in repos:
            try:
                doc = raw_document_from_github_repo(repo)
                docs.append(doc.to_dict())
            except Exception as e:
                self._log_event("warning", f"Failed to convert repo: {e}")
        return docs

    async def _batch_dedup(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter out repos that have already been stored."""
        from kubani.syndicates.news_digest.activities import batch_check_duplicates_activity
        from kubani.syndicates.news_digest.models import make_dedup_key

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Checking {len(documents)} repos for duplicates",
            phase="dedup",
        )

        key_to_doc: dict[str, dict[str, Any]] = {}
        for doc in documents:
            key = make_dedup_key(doc["source_type"], doc["source_uri"])
            key_to_doc[key] = doc

        result = await workflow.execute_activity(
            batch_check_duplicates_activity,
            args=[list(key_to_doc.keys())],
            start_to_close_timeout=timedelta(minutes=2),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=STORAGE_RETRY_POLICY,
        )

        if not result.get("success"):
            self._log_event("warning", "Dedup check failed, passing all documents through")
            return documents

        duplicates = result.get("duplicates", {})
        new_docs = [doc for key, doc in key_to_doc.items() if not duplicates.get(key, False)]

        dup_count = len(documents) - len(new_docs)
        self._log_event("dedup_complete", f"{len(new_docs)} new, {dup_count} duplicates filtered")
        return new_docs

    async def _trigger_analysis(self, documents: list[dict[str, Any]]) -> None:
        """Start the AnalyzeDocumentWorkflow as a child workflow.

        Fire-and-forget: the ingest workflow does not wait for analysis.

        Args:
            documents: List of RawDocument dicts to analyze.
        """
        from kubani.syndicates.news_digest.workflows.analyze import (
            AnalyzeDocumentWorkflow,
            AnalyzeInput,
        )

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Triggering analysis for {len(documents)} documents",
            phase="trigger_analyze",
        )

        try:
            run_id = workflow.info().run_id[:8]
            await workflow.start_child_workflow(
                AnalyzeDocumentWorkflow.run,
                args=[
                    AnalyzeInput(
                        documents=documents,
                        max_documents=len(documents),
                    )
                ],
                id=f"analyze-github-{run_id}",
                task_queue=workflow.info().task_queue,
                parent_close_policy=workflow.ParentClosePolicy.ABANDON,
            )
            self._log_event(
                "analysis_triggered",
                f"Started analysis for {len(documents)} documents",
            )
        except Exception as e:
            self._log_event(
                "analysis_trigger_error",
                f"Failed to trigger analysis: {e}",
            )

    async def _store_documents(self, documents: list[dict[str, Any]]) -> int:
        """Store new raw documents in Memory MCP."""
        from kubani.syndicates.news_digest.activities import store_raw_documents_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Storing {len(documents)} new repos",
            phase="store",
        )

        result = await workflow.execute_activity(
            store_raw_documents_activity,
            args=[documents],
            start_to_close_timeout=timedelta(minutes=5),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=STORAGE_RETRY_POLICY,
        )

        stored = result.get("stored_count", 0)
        self._log_event("documents_stored", f"Stored {stored} documents")
        return stored

    # =========================================================================
    # Result Building & Queries
    # =========================================================================

    def _build_result(self) -> dict[str, Any]:
        """Build the result dictionary."""
        return {
            "repos_collected": self._result.repos_collected,
            "repos_new": self._result.repos_new,
            "repos_stored": self._result.repos_stored,
            "success": self._result.success,
            "error": self._result.error,
        }

    @workflow.query
    def get_ingest_stats(self) -> dict[str, Any]:
        """Query current ingest statistics."""
        return {
            "repos_collected": self._result.repos_collected,
            "repos_new": self._result.repos_new,
            "repos_stored": self._result.repos_stored,
        }
