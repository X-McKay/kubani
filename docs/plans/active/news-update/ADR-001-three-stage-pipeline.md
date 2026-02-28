# ADR-001: Three-Stage Pipeline Architecture for News Digest

## Status

Accepted

## Date

2026-02-27

## Context

The original `news_digest` syndicate used a monolithic two-workflow design:

- **NewsCollectionWorkflow**: A single workflow that collected from all three sources (RSS, arXiv, GitHub) sequentially, performed per-item deduplication checks, and stored results using source-specific storage activities.
- **NewsDigestWorkflow**: A complex workflow that queried articles, ran trend analysis via an agent, composed a digest via another agent, and published to Discord.

This design had several pain points:

1. **Tight coupling**: All three source types were collected in a single workflow, making it impossible to tune schedules or test sources independently.
2. **Chatty deduplication**: Each item was checked individually against the cache, resulting in N network round-trips per collection run.
3. **No analysis stage**: The collection workflow stored raw content, and the digest workflow had to perform analysis (trend detection, summarization) at query time, making digests slow and unrepeatable.
4. **Unused graph capabilities**: The Memory MCP server supports Neo4j graph storage with relationship creation, but the original design never leveraged it for news content.
5. **Fragile agent parsing**: Both workflows relied on parsing JSON from agent text output, with parsing logic duplicated across workflows.

## Decision

Refactor the syndicate into a **three-stage pipeline**:

### Stage 1 — Ingest (Source-Specific)

Three independent workflows, each with its own schedule tuned to the source's update frequency:

| Workflow | Source | Schedule | Dedup Strategy |
|:---|:---|:---|:---|
| `RSSIngestWorkflow` | RSS feeds | Every 30 min | URI hash via `make_dedup_key` |
| `ArxivIngestWorkflow` | arXiv API | Every 4 hours | arXiv ID hash |
| `GitHubIngestWorkflow` | GitHub trending | Every 6 hours | Repo URL hash |

Each workflow:
1. Collects raw data from its source.
2. Converts entries to a standardized `RawDocument` dataclass.
3. Performs **batch** deduplication (one activity call for all keys).
4. Stores new documents and sets dedup cache keys.
5. Triggers `AnalyzeDocumentWorkflow` as a child workflow for the new batch.

### Stage 2 — Analyze

A single `AnalyzeDocumentWorkflow` that processes each new document:
1. Calls the `content-analyst` agent for entity extraction, topic classification, importance scoring, and summarization.
2. Stores the enriched `AnalyzedDocument` in Qdrant with analysis metadata.
3. Creates graph relationships in Neo4j (MENTIONS entities, DISCUSSES topics).

### Stage 3 — Digest (Section-Based Composition)

A simplified `NewsDigestWorkflow` that uses **section-based composition** to stay within the 32k context window of the cluster LLM:

1. Queries analyzed documents from a time window using `query_analyzed_documents_activity`.
2. Groups documents by source type (rss, arxiv, github).
3. Prepares condensed context for each section using **pure functions** (`prepare_articles_context`, `prepare_papers_context`, `prepare_repos_context`) that strip unnecessary fields, sort by importance, and cap item counts.
4. Generates each section independently via separate LLM calls (~1-2k tokens each):
   - "Top Stories" from RSS articles (via `content-analyst` agent)
   - "Research Spotlight" from arXiv papers (via `content-analyst` agent)
   - "Tool Spotlight" from GitHub repos (via `content-analyst` agent)
5. Synthesizes the sections into a final digest with an Executive Summary (via `digest-publisher` agent, ~2-3k tokens input).
6. Falls back to a pure-function concatenation if synthesis fails.
7. Publishes to Discord and the UI activity feed.

This approach ensures that no single LLM call exceeds ~5k tokens, well within the 32k limit.

### Shared Components

- **`models.py`**: Pure dataclasses (`RawDocument`, `AnalyzedDocument`) and pure utility functions (`compute_content_hash`, `make_dedup_key`, `parse_json_array_from_text`, etc.).
- **`activities.py`**: New Temporal activities (`batch_check_duplicates_activity`, `store_raw_documents_activity`, `store_analyzed_document_activity`, `query_analyzed_documents_activity`, `analyze_document_activity`).

## Consequences

### Positive

- **Independent testability**: Each source can be tested, deployed, and debugged independently.
- **Tuned schedules**: RSS runs every 30 min (fast-moving), arXiv every 4 hours (daily batches), GitHub every 6 hours (slow-moving).
- **32k-safe digest**: Section-based composition keeps every LLM call under 5k tokens, with a pure-function fallback if synthesis fails.
- **Batch deduplication**: One activity call checks all keys, reducing N round-trips to 1.
- **Reusable analysis**: Documents are analyzed once and stored with enrichment metadata, making digests a simple query.
- **Graph integration**: Neo4j relationships are created during analysis, enabling future graph-based features (related topics, entity networks).
- **Pure data models**: `RawDocument` and `AnalyzedDocument` are plain dataclasses with `to_dict`/`from_dict` for Temporal serialization, making them easy to test.
- **Centralized parsing**: JSON parsing utilities are in `models.py`, eliminating duplication.

### Negative

- **More workflow files**: Five workflow files instead of two, though each is simpler and more focused.
- **Child workflow overhead**: Each ingest triggers an analyze child workflow, adding a small amount of Temporal overhead.
- **Migration required**: Existing scheduled workflows need to be replaced with the new ones.

### Neutral

- **Old collection.py removed**: The monolithic `NewsCollectionWorkflow` is replaced by three ingest workflows. The old file is deleted.
- **Breaking news removed**: The breaking news detection feature (which relied on per-article importance checks during collection) is removed in favor of the analysis stage's importance scoring. High-importance items can be surfaced in digests or via a future alerting workflow.

## Files Changed

| File | Action | Description |
|:---|:---|:---|
| `models.py` | **New** | RawDocument, AnalyzedDocument, pure utility functions |
| `activities.py` | **New** | Pipeline-specific Temporal activities |
| `workflows/ingest_rss.py` | **New** | RSS ingest workflow |
| `workflows/ingest_arxiv.py` | **New** | arXiv ingest workflow |
| `workflows/ingest_github.py` | **New** | GitHub ingest workflow |
| `workflows/analyze.py` | **New** | Document analysis workflow |
| `workflows/digest.py` | **Rewritten** | Simplified digest workflow |
| `workflows/collection.py` | **Deleted** | Replaced by three ingest workflows |
| `workflows/__init__.py` | **Updated** | Exports new workflows |
| `__init__.py` | **Updated** | Exports new workflows |
| `config.yaml` | **Updated** | New pipeline description and config |
| `pyproject.toml` | **Updated** | Version bump to 2.0.0 |
| `src/.../worker.py` | **Updated** | New schedules and activity registration |
| `tests/conftest.py` | **Updated** | New fixtures for pipeline stages |
| `tests/test_models.py` | **New** | Tests for data models and utilities |
| `tests/test_ingest_workflows.py` | **New** | Tests for all three ingest workflows |
| `tests/test_analyze_workflow.py` | **New** | Tests for analyze workflow |
| `tests/test_digest_workflow.py` | **Rewritten** | Tests for simplified digest workflow |
| `tests/test_worker.py` | **New** | Tests for worker registration |
| `tests/test_collection_workflow.py` | **Deleted** | Replaced by ingest tests |
