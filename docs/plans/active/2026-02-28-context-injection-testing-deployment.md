# Context Injection: Testing and Deployment Plan

**Date**: 2026-02-28
**Status**: Active
**Related ADR**: [ADR-008: Context Injection for Pipeline Testability](../../adr/008-context-injection-for-pipeline-testability.md)
**Branch**: `feature/manus-temporal-context-inj`

---

## Overview

This plan covers the testing strategy and deployment process for the Context Injection refactoring of the news_digest ingest workflows. The refactoring introduces a `PipelineContext` protocol, a shared `run_ingest_pipeline` function, and two context implementations (`TemporalContext` and `LocalContext`).

---

## 1. Testing Strategy

### 1.1 Test Layers

The Context Injection architecture creates three distinct, independently testable layers:

| Layer | What It Tests | Test File | Temporal Required | Speed |
|-------|--------------|-----------|-------------------|-------|
| **Pipeline Logic** | The shared `run_ingest_pipeline` function against mock contexts | `test_ingest_pipeline.py` | No | ~0.07s |
| **LocalContext** | The `LocalContext` class: default behaviors, custom callables, observability recording | `test_local_context.py` | No | ~0.04s |
| **Workflow Dataclasses** | Input/output dataclasses, model conversion functions, workflow initialization | `test_ingest_workflows.py` | No | ~0.05s |
| **Models** | Pure functions (`make_dedup_key`, `compute_content_hash`, converters) and `dedup_key` property | `test_models.py` | No | ~0.12s |
| **Integration (Temporal)** | Full workflow execution with a Temporal test server | *(future)* | Yes | ~5-10s |

### 1.2 Pipeline Logic Tests (17 tests)

These are the most important tests. They validate the core business logic using `LocalContext` with injected mock callables.

**Test Matrix:**

| Test | Source | Scenario | Validates |
|------|--------|----------|-----------|
| `test_happy_path` | RSS | 3 articles, 0 duplicates | Full pipeline flow, correct counts |
| `test_empty_fetch` | RSS | 0 articles returned | Early exit, no dedup/store calls |
| `test_all_duplicates` | RSS | 3 articles, all duplicates | Dedup filtering, no store call |
| `test_partial_duplicates` | RSS | 3 articles, 1 duplicate | Correct filtering, partial store |
| `test_fetch_failure` | RSS | Fetcher raises exception | Error propagation, result.error set |
| `test_store_failure` | RSS | Storer raises exception | Error propagation after dedup |
| `test_paused_before_dedup` | RSS | Pause signal before dedup | Early exit with success=True |
| `test_happy_path` | arXiv | 2 papers, 0 duplicates | arXiv-specific fetch/convert |
| `test_with_duplicates` | arXiv | 2 papers, 1 duplicate | arXiv dedup filtering |
| `test_happy_path` | GitHub | 2 repos, 0 duplicates | GitHub-specific fetch/convert |
| `test_with_duplicates` | GitHub | 2 repos, 1 duplicate | GitHub dedup filtering |
| `test_status_phases` | RSS | Normal run | Correct status phase sequence |
| `test_events_logged` | RSS | Normal run | Correct event kinds logged |
| `test_empty_fetch_status` | RSS | Empty fetch | Status shows "No documents found" |
| `test_to_dict` | — | IngestResult serialization | All fields present in dict |
| `test_to_dict_with_extra` | — | IngestResult with extra fields | Extra fields merged into dict |
| `test_default_values` | — | IngestResult defaults | Correct zero/True/None defaults |

### 1.3 LocalContext Tests (12 tests)

These validate the `LocalContext` class itself — its default no-op behaviors, custom callable injection, and observability recording.

**Test Matrix:**

| Test | Category | Validates |
|------|----------|-----------|
| `test_default_fetch_returns_empty` | Defaults | Default fetcher returns `[]` |
| `test_default_dedup_returns_all_new` | Defaults | Default checker returns all `False` |
| `test_default_store_returns_count` | Defaults | Default storer returns `len(docs)` |
| `test_default_trigger_is_noop` | Defaults | Default trigger does not raise |
| `test_wait_if_paused_returns_false` | Defaults | Always returns `False` locally |
| `test_custom_fetcher` | Custom | Injected fetcher is called |
| `test_custom_checker` | Custom | Injected checker is called |
| `test_custom_storer` | Custom | Injected storer is called |
| `test_set_status_records` | Observability | Statuses are recorded and inspectable |
| `test_log_event_records` | Observability | Events are recorded and inspectable |
| `test_get_events_by_kind` | Observability | Event filtering by kind works |
| `test_events_and_statuses_are_copies` | Observability | Properties return copies, not refs |

### 1.4 Running Tests Locally

```bash
# From the repository root:

# Run all news_digest tests (excluding worker tests that need uv workspace)
PYTHONPATH=. python -m pytest kubani/syndicates/news_digest/tests/ -v \
    --ignore=kubani/syndicates/news_digest/tests/test_worker.py

# Run only the new pipeline tests
PYTHONPATH=. python -m pytest kubani/syndicates/news_digest/tests/test_ingest_pipeline.py -v

# Run only the LocalContext tests
PYTHONPATH=. python -m pytest kubani/syndicates/news_digest/tests/test_local_context.py -v

# Run with coverage (requires pytest-cov)
PYTHONPATH=. python -m pytest kubani/syndicates/news_digest/tests/ -v \
    --ignore=kubani/syndicates/news_digest/tests/test_worker.py \
    --cov=kubani.syndicates.news_digest.pipeline
```

### 1.5 Using the Local Runner

The local runner (`scripts/run_ingest_local.py`) executes the full pipeline with mock data, allowing developers to inspect the pipeline's behavior interactively.

```bash
# Run with RSS source (default)
PYTHONPATH=. python kubani/syndicates/news_digest/scripts/run_ingest_local.py --source rss

# Run with arXiv source
PYTHONPATH=. python kubani/syndicates/news_digest/scripts/run_ingest_local.py --source arxiv

# Run with GitHub source
PYTHONPATH=. python kubani/syndicates/news_digest/scripts/run_ingest_local.py --source github

# Simulate duplicates
PYTHONPATH=. python kubani/syndicates/news_digest/scripts/run_ingest_local.py --source rss --with-duplicates
```

The local runner outputs:
- Status updates at each pipeline phase
- Event logs with structured data
- A summary of all statuses and events
- The final `IngestResult` as JSON

---

## 2. Deployment Plan

### 2.1 Pre-Deployment Checklist

| Step | Action | Owner | Status |
|------|--------|-------|--------|
| 1 | All 151 tests pass locally | Automated | Done |
| 2 | Local runner works for all 3 source types | Manual | Done |
| 3 | Local runner works with `--with-duplicates` flag | Manual | Done |
| 4 | ADR-008 reviewed and accepted | Team | Done |
| 5 | Code review on feature branch | Team | Pending |
| 6 | Temporal integration test (with test server) | Manual | Pending |
| 7 | Worker registration verified (workflows still register correctly) | Manual | Pending |

### 2.2 Deployment Sequence

**Phase 1: Merge and Monitor (Low Risk)**

The refactoring is backward-compatible in terms of Temporal workflow behavior:
- Workflow class names are unchanged (`RSSIngestWorkflow`, `ArxivIngestWorkflow`, `GitHubIngestWorkflow`)
- Input dataclasses are unchanged (`RSSIngestInput`, `ArxivIngestInput`, `GitHubIngestInput`)
- Temporal task queue and workflow IDs are unchanged
- Activity calls use the same activities with the same retry policies

Steps:
1. Merge `feature/manus-temporal-context-inj` into `main`
2. Deploy the updated worker
3. Monitor the first scheduled run of each ingest workflow in the Temporal UI
4. Verify status updates appear correctly in the Temporal UI
5. Verify documents are stored and analysis is triggered

**Phase 2: Validate Observability**

After the first successful run:
1. Check that `get_ingest_stats` query returns correct data
2. Check that `get_status` query returns correct phase information
3. Verify pause/resume signals still work (send pause signal, verify workflow pauses, send resume signal)

**Phase 3: Extend Pattern (Future)**

Once the ingest workflows are stable:
1. Apply Context Injection to the `AnalyzeDocumentWorkflow`
2. Apply Context Injection to the `DigestWorkflow`
3. Create `AnalyzeContext` and `DigestContext` protocols as needed

### 2.3 Rollback Plan

If issues are discovered after deployment:
1. Revert the merge commit on `main`
2. Redeploy the previous worker version
3. Temporal will automatically pick up the old workflow definitions
4. No data migration is needed — the refactoring does not change data formats

---

## 3. Known Limitations

### 3.1 `test_worker.py` Failures

The 5 failures in `test_worker.py` are a **pre-existing issue** unrelated to this refactoring. They fail because `news_digest_syndicate` is a `uv` workspace package that is not installed in the flat `PYTHONPATH` test environment. These tests pass when run via `uv run pytest` inside the workspace.

### 3.2 TemporalContext Not Directly Testable

The `TemporalContext` class cannot be unit-tested in isolation because it calls `workflow.execute_activity` and other Temporal APIs that require a running workflow context. It is tested indirectly through:
- The Temporal integration tests (future, requires test server)
- The fact that the pipeline logic is fully tested via `LocalContext`
- The fact that the `TemporalContext` is a thin delegation layer with minimal logic

### 3.3 `collect_feeds_activity` Redundancy

The framework's `collect_feeds_activity` performs both fetching and conversion internally. The `TemporalContext._fetch_rss()` method uses the activity's `raw_documents` output directly (already converted). This means the conversion logic in `models.py` is not exercised during RSS ingest via Temporal — it is only used by the arXiv and GitHub contexts, and by the local runner. This is a known redundancy that can be cleaned up in a future iteration by refactoring `collect_feeds_activity` to return raw entries only.

---

## 4. Future Work

| Item | Priority | Description |
|------|----------|-------------|
| Temporal integration tests | High | Add tests using `temporalio.testing.WorkflowEnvironment` |
| Apply to analyze workflow | Medium | Create `AnalyzeContext` protocol and refactor `AnalyzeDocumentWorkflow` |
| Apply to digest workflow | Medium | Create `DigestContext` protocol and refactor `DigestWorkflow` |
| Refactor `collect_feeds_activity` | Low | Strip conversion from the activity; let the pipeline handle it |
| Add real local fetchers | Low | Create `LocalContext` fetchers that call real RSS/arXiv/GitHub APIs |
