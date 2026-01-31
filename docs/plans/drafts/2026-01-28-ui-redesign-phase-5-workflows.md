# Phase 5: Workflows View

**Parent:** [UI Redesign Master Plan](./2026-01-28-ui-redesign-master-plan.md)
**Status:** Draft
**Dependencies:** Phase 0 (Design System), Phase 1 (Backend Foundation)
**Estimated scope:** ~6 new frontend files, ~2 new/modified backend files

---

## Overview

Dedicated view for monitoring Temporal workflows. Displays running, completed, and failed workflows with filtering, detail panels showing execution history, and actions (signal, cancel, retry).

---

## Goals

1. Workflow list with status tabs (Running, Completed, Failed, All)
2. Filtering by syndicate, workflow type, time range
3. Detail side panel with step-by-step execution history
4. Actions: signal, cancel, retry failed workflows
5. Real-time status updates via WebSocket
6. Link workflows to their source syndicate and Activity Feed events

---

## 1. Backend: Temporal Integration

### Current State

The existing `api/workflows.rs` is a placeholder returning mock data. The Temporal MCP server exists at `temporal-mcp.ai-agents.svc.cluster.local:8081` but is optionally connected.

### Enhanced Workflow Endpoint

```rust
// backend/src/api/workflows.rs (UPDATED)

use axum::{extract::{State, Path, Query}, Json};
use std::sync::Arc;
use crate::state::AppState;
use serde::Deserialize;

#[derive(Deserialize)]
pub struct WorkflowListParams {
    status: Option<String>,         // "running", "completed", "failed", "all"
    syndicate: Option<String>,      // Filter by syndicate
    limit: Option<u32>,
    next_page_token: Option<String>,
}

pub async fn get_workflows(
    Query(params): Query<WorkflowListParams>,
) -> Json<serde_json::Value> {
    // Try to fetch from Temporal MCP
    let temporal_url = std::env::var("TEMPORAL_MCP_URL")
        .unwrap_or_else(|_| "http://temporal-mcp.ai-agents.svc.cluster.local:8081".to_string());

    // Call Temporal MCP tool: list_workflows
    match crate::mcp::call_tool_at(
        &temporal_url,
        "list_workflows",
        serde_json::json!({
            "status": params.status.unwrap_or_else(|| "all".to_string()),
            "namespace": params.syndicate.as_deref().unwrap_or("default"),
            "limit": params.limit.unwrap_or(50),
        }),
    ).await {
        Ok(result) => Json(serde_json::from_str(&result).unwrap_or(serde_json::json!([]))),
        Err(e) => {
            tracing::warn!("Failed to fetch workflows from Temporal: {}", e);
            Json(serde_json::json!([]))
        }
    }
}

pub async fn get_workflow_detail(
    Path(workflow_id): Path<String>,
) -> Json<serde_json::Value> {
    let temporal_url = std::env::var("TEMPORAL_MCP_URL")
        .unwrap_or_else(|_| "http://temporal-mcp.ai-agents.svc.cluster.local:8081".to_string());

    match crate::mcp::call_tool_at(
        &temporal_url,
        "get_workflow_execution",
        serde_json::json!({ "workflow_id": workflow_id }),
    ).await {
        Ok(result) => Json(serde_json::from_str(&result).unwrap_or(serde_json::json!({}))),
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}

pub async fn signal_workflow(
    Path(workflow_id): Path<String>,
    Json(request): Json<serde_json::Value>,
) -> Json<serde_json::Value> {
    let temporal_url = std::env::var("TEMPORAL_MCP_URL")
        .unwrap_or_else(|_| "http://temporal-mcp.ai-agents.svc.cluster.local:8081".to_string());

    match crate::mcp::call_tool_at(
        &temporal_url,
        "signal_workflow",
        serde_json::json!({
            "workflow_id": workflow_id,
            "signal_name": request.get("signal_name").and_then(|v| v.as_str()).unwrap_or("pause"),
            "input": request.get("input"),
        }),
    ).await {
        Ok(_) => Json(serde_json::json!({ "status": "signaled" })),
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}

pub async fn cancel_workflow(
    Path(workflow_id): Path<String>,
) -> Json<serde_json::Value> {
    let temporal_url = std::env::var("TEMPORAL_MCP_URL")
        .unwrap_or_else(|_| "http://temporal-mcp.ai-agents.svc.cluster.local:8081".to_string());

    match crate::mcp::call_tool_at(
        &temporal_url,
        "cancel_workflow",
        serde_json::json!({ "workflow_id": workflow_id }),
    ).await {
        Ok(_) => Json(serde_json::json!({ "status": "cancelled" })),
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}
```

### New Routes in main.rs

```rust
.route("/api/workflows", get(api::workflows::get_workflows))
.route("/api/workflows/:id", get(api::workflows::get_workflow_detail))
.route("/api/workflows/:id/signal", post(api::workflows::signal_workflow))
.route("/api/workflows/:id/cancel", post(api::workflows::cancel_workflow))
```

---

## 2. Frontend Architecture

### Feature Directory Structure

```
client/src/features/workflows/
├── WorkflowsView.tsx        # Main page with tabs + list
├── WorkflowRow.tsx          # Table row component
├── WorkflowDetail.tsx       # Side panel with execution history
├── WorkflowActions.tsx      # Signal/cancel/retry buttons
├── hooks/
│   └── useWorkflows.ts     # Data fetching + WebSocket subscription
└── types.ts                # TypeScript types
```

### Data Types

```typescript
export interface Workflow {
  workflow_id: string;
  workflow_type: string;
  namespace: string;         // Temporal namespace (maps to syndicate)
  status: 'RUNNING' | 'COMPLETED' | 'FAILED' | 'TERMINATED' | 'CANCELED' | 'TIMED_OUT';
  start_time: string;
  close_time?: string;
  execution_time?: string;   // Duration string
  task_queue: string;
}

export interface WorkflowDetail extends Workflow {
  history: WorkflowEvent[];
  input?: unknown;
  output?: unknown;
  failure_message?: string;
}

export interface WorkflowEvent {
  event_id: number;
  event_type: string;
  timestamp: string;
  details: Record<string, unknown>;
}

export type WorkflowTab = 'running' | 'completed' | 'failed' | 'all';
```

### WorkflowsView.tsx

Main page component with:
- Status tabs (Running with count, Completed, Failed, All)
- Filter dropdown for syndicate
- Sortable table: Workflow ID, Type, Syndicate, Status, Started, Duration
- Rows are clickable → opens side panel
- Real-time: running workflows update status via WebSocket

### WorkflowDetail.tsx

Side panel showing:
- Workflow header (ID, type, status, syndicate)
- Timeline of workflow events (ActivityStarted, ActivityCompleted, etc.)
- Input/output data (JSON formatted)
- Failure message (if failed)
- Action buttons (Signal, Cancel, Retry)

---

## 3. Implementation Checklist

### Backend
- [ ] Update `backend/src/api/workflows.rs` — Replace placeholder with Temporal MCP calls
- [ ] Add workflow detail endpoint
- [ ] Add signal/cancel endpoints
- [ ] Add routes to main.rs

### Frontend
- [ ] Create `client/src/features/workflows/` directory
- [ ] Create `types.ts`
- [ ] Create `hooks/useWorkflows.ts`
- [ ] Create `WorkflowRow.tsx`
- [ ] Create `WorkflowDetail.tsx`
- [ ] Create `WorkflowActions.tsx`
- [ ] Create `WorkflowsView.tsx`
- [ ] Add route `/workflows` in Router
- [ ] Update DashboardLayout navigation with running count badge

### Verification
- [ ] Running workflows displayed with live status
- [ ] Completed/Failed tabs filter correctly
- [ ] Workflow detail shows execution history timeline
- [ ] Signal workflow sends signal to Temporal
- [ ] Cancel workflow terminates execution
- [ ] Syndicate filter narrows results
- [ ] Graceful fallback when Temporal MCP is unavailable

---

## Files Summary

| File | Status | Purpose |
|------|--------|---------|
| `backend/src/api/workflows.rs` | MODIFIED | Temporal MCP integration |
| `backend/src/main.rs` | MODIFIED | New workflow routes |
| `client/src/features/workflows/WorkflowsView.tsx` | NEW | Main page |
| `client/src/features/workflows/WorkflowRow.tsx` | NEW | Table row |
| `client/src/features/workflows/WorkflowDetail.tsx` | NEW | Side panel |
| `client/src/features/workflows/WorkflowActions.tsx` | NEW | Action buttons |
| `client/src/features/workflows/hooks/useWorkflows.ts` | NEW | Data hook |
| `client/src/features/workflows/types.ts` | NEW | Types |

**Total: 6 new frontend files, 2 modified backend files**
