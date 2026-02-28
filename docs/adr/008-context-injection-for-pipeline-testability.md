# ADR-008: Context Injection for Pipeline Testability

## Status
Accepted

## Date
2026-02-28

## Context

The news_digest syndicate implements a three-stage pipeline (Ingest → Analyze → Digest) using Temporal workflows. While the Temporal-based architecture provides durability, retries, and observability, it created several development friction points:

1. **Untestable pipeline logic.** The core business logic (fetch → convert → dedup → store → trigger) was embedded directly inside Temporal workflow `run()` methods. Testing required either a full Temporal test environment or extensive mocking of Temporal internals (`workflow.execute_activity`, `workflow.start_child_workflow`, etc.).

2. **Code duplication across source types.** The three ingest workflows (RSS, arXiv, GitHub) each contained nearly identical orchestration logic — the same fetch → dedup → store → trigger flow — differing only in how documents were fetched and converted. This duplication made changes error-prone.

3. **No local iteration path.** Developers could not run the ingest pipeline locally to inspect intermediate outputs, test with mock data, or iterate on logic without a running Temporal server. This slowed development velocity significantly.

4. **Observability was coupled to Temporal.** Status reporting (`_set_status`), event logging (`_log_event`), and pause/resume (`_wait_if_paused`) were only available inside Temporal workflows, making it impossible to observe pipeline behavior during local testing.

Several alternative approaches were evaluated during the design process:

- **Service Layer with Dependency Injection**: Extract activities into a service class with injected dependencies. Improved testability of individual activities but did not address the workflow orchestration logic or observability coupling.

- **Command/State Machine Pattern**: Extract workflow logic into a pure state machine that returns command objects. The workflow would execute commands and feed results back. This was overly complex for the use case — the pipeline is a simple linear sequence, not a state machine.

- **Ports and Adapters (Hexagonal Architecture)**: Define ports for each I/O boundary and source-specific adapters. Architecturally clean but created a regression in Temporal observability (the generic pipeline became a black box to the workflow) and added significant boilerplate for a system with only three source types.

## Decision

We adopted the **Context Injection** pattern: a single `PipelineContext` protocol that encapsulates all I/O operations *and* all observability/control-flow operations. The pipeline logic is written as a plain async function against this protocol. Concrete context implementations provide the actual behavior.

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    PipelineContext (Protocol)                  │
│                                                                │
│  I/O:           fetch_documents, check_duplicates,            │
│                 store_documents, trigger_analysis              │
│                                                                │
│  Observability: set_status, log_event                         │
│                                                                │
│  Control:       wait_if_paused                                │
└──────────────────────────────────────────────────────────────┘
                    ▲                        ▲
                    │                        │
        ┌───────────┴──────────┐  ┌─────────┴──────────┐
        │   TemporalContext    │  │    LocalContext     │
        │                      │  │                    │
        │ - Temporal activities│  │ - Injectable fns   │
        │ - ObservableMixin    │  │ - Print/log output │
        │ - Signals & queries  │  │ - Event recording  │
        └──────────────────────┘  └────────────────────┘
                    ▲                        ▲
                    │                        │
        ┌───────────┴──────────┐  ┌─────────┴──────────┐
        │  Temporal Workflows  │  │   Local Runner /   │
        │  (thin shells)       │  │   Unit Tests       │
        └──────────────────────┘  └────────────────────┘
```

### Key Design Decisions

**The context includes observability, not just I/O.** This is the critical difference from a standard ports-and-adapters approach. By including `set_status`, `log_event`, and `wait_if_paused` in the protocol, the pipeline logic can report progress and respond to control signals regardless of execution environment. The `TemporalContext` delegates these to `ObservableWorkflowMixin`; the `LocalContext` prints to stdout and records events for test assertions.

**Fetch and convert are bundled together in the context.** Both fetching and converting are source-specific concerns. RSS entries have different fields than arXiv papers. Rather than forcing the shared pipeline to know about source-specific conversion, `fetch_documents()` returns already-converted `RawDocument` dicts. Everything from dedup onward is generic.

**Dedup operates on batches, not individual documents.** The `check_duplicates` method accepts a list of dedup keys and returns a dict of results. This preserves the existing batched activity call pattern, avoiding the performance regression of one-activity-per-document.

**Separate workflow classes per source type are retained.** Although the pipeline logic is unified, each source type keeps its own workflow class (`RSSIngestWorkflow`, `ArxivIngestWorkflow`, `GitHubIngestWorkflow`). This allows independent scheduling, separate Temporal workflow IDs, and source-specific input dataclasses.

**The `TemporalContext` holds a reference to the workflow instance.** It is instantiated inside the workflow's `run()` method with `TemporalContext(workflow_mixin=self, source_type="rss")`. This gives it full access to `_set_status`, `_log_event`, `_wait_if_paused`, and all Temporal workflow APIs.

### File Structure

```
kubani/syndicates/news_digest/
├── pipeline/                          # NEW: Core pipeline module
│   ├── __init__.py                    # Exports PipelineContext, run_ingest_pipeline, IngestResult
│   ├── context.py                     # PipelineContext protocol definition
│   ├── ingest.py                      # Shared pipeline logic (single source of truth)
│   └── contexts/
│       ├── __init__.py                # Exports TemporalContext, LocalContext
│       ├── temporal_context.py        # Temporal-backed context implementation
│       └── local_context.py           # Local/mock context for testing
├── scripts/
│   └── run_ingest_local.py            # NEW: CLI for running pipeline locally
├── workflows/
│   ├── ingest_rss.py                  # MODIFIED: Thin shell using Context Injection
│   ├── ingest_arxiv.py                # MODIFIED: Thin shell using Context Injection
│   └── ingest_github.py               # MODIFIED: Thin shell using Context Injection
├── tests/
│   ├── test_ingest_pipeline.py        # NEW: 17 tests for shared pipeline logic
│   ├── test_local_context.py          # NEW: 12 tests for LocalContext
│   ├── test_ingest_workflows.py       # MODIFIED: Updated for new workflow structure
│   └── test_models.py                 # MODIFIED: Added dedup_key property tests
└── models.py                          # MODIFIED: Added dedup_key property to RawDocument
```

## Consequences

### Positive

**Full local testability.** The entire ingest pipeline can be tested without Temporal. Unit tests run in ~0.2 seconds and cover all pipeline paths (happy path, empty fetch, all duplicates, partial duplicates, fetch failure, store failure, pause handling).

**Zero code duplication.** The pipeline logic exists in exactly one place (`pipeline/ingest.py`). All three source types use the same function. Bug fixes and improvements apply to all sources automatically.

**Preserved Temporal features.** The `TemporalContext` retains full access to `ObservableWorkflowMixin` features: status reporting, event logging, pause/resume signals, batched activities, retry policies, and child workflow triggering.

**Local runner for rapid iteration.** The `scripts/run_ingest_local.py` CLI allows developers to run the full pipeline locally with mock data, inspect intermediate outputs, and test with or without simulated duplicates.

**Clear separation of concerns.** The pipeline logic knows nothing about Temporal. The Temporal workflows know nothing about pipeline logic. The context is the only bridge between them.

**Incremental adoption.** The pattern can be applied to the analyze and digest workflows independently, without requiring a big-bang migration.

### Negative

**Additional indirection.** Developers must understand the Context Injection pattern to trace execution flow. The call path is: `Workflow.run()` → `TemporalContext` → `run_ingest_pipeline()` → `ctx.method()` → Temporal activity.

**More files.** The `pipeline/` module adds 6 new Python files. This is offset by the fact that the three workflow files are now significantly simpler.

**Context must be kept in sync with pipeline.** If the pipeline needs a new I/O capability, both the protocol and all context implementations must be updated.

### Risks

**Context bloat.** As the pipeline evolves, the `PipelineContext` protocol could accumulate too many methods. Mitigation: Keep the protocol focused on the ingest pipeline; create separate protocols for analyze and digest if needed.

**TemporalContext correctness.** The `TemporalContext` wraps Temporal APIs in a non-standard way. If Temporal's sandbox restrictions change, the context may need updating. Mitigation: All Temporal-specific imports use `workflow.unsafe.imports_passed_through()`.

## Alternatives Considered

### Keep Temporal Workflows As-Is
Rejected because: No local testability, duplicated logic across three workflows, slow development iteration.

### Service Layer with Dependency Injection
Rejected because: Improved activity testability but did not address workflow orchestration logic or observability coupling.

### Command/State Machine Pattern
Rejected because: Over-engineered for a linear pipeline. Added complexity (command dataclasses, state objects, match statements) without proportional benefit.

### Ports and Adapters (Hexagonal Architecture)
Rejected because: Created a regression in Temporal observability. The generic pipeline became a black box to the workflow, losing status reporting and pause/resume. Adding a `ProgressReporter` port to fix this essentially converged on the Context Injection pattern.

## References

- [ADR-006: Dual-Pattern Syndicate Architecture](006-dual-pattern-syndicate-architecture.md)
- [Temporal Workflow Testing Guide](https://docs.temporal.io/develop/python/testing-suite)
- [Ports and Adapters / Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/)
