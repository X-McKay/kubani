# Kubani UI Redesign — Master Plan

**Date:** 2026-01-28
**Status:** Draft
**Branch:** feature/ui-redesign
**Supersedes:** [2026-01-27 Design System Overhaul (Idea)](../ideas/2026-01-27-kubani-ui-design-system-overhaul.md)

---

## Executive Summary

Complete redesign of the Kubani UI from a monitoring dashboard with chat into a **unified control plane** for the entire Kubani ecosystem. The new UI serves as the primary interface for:

1. **Real-time activity monitoring** — Live feed of syndicate outputs, agent activity, and system events (replacing Discord notifications)
2. **Intelligent agent interaction** — Natural language interface with automatic routing to the appropriate syndicate/agent
3. **Human-in-the-loop approvals** — Review and approve proposed skills, agents, and actions from the learning system
4. **Temporal workflow management** — Monitor, signal, and manage Temporal workflows
5. **Registry browsing** — Discover and manage syndicates, agents, skills, and MCP servers
6. **Cluster monitoring** — Infrastructure health, nodes, pods, services

---

## Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary view | Activity Feed | System awareness is the primary daily use case |
| Navigation model | Sidebar with 6 views | Clear separation of concerns, each view has distinct purpose |
| Agent interaction | Smart routing to syndicates | User shouldn't need to know which agent handles what |
| Detail levels | Toggleable (clean/debug) | Clean default for daily use, debug for development |
| Feed structure | Unified + filters | Cross-syndicate awareness without per-syndicate isolation |
| Approvals | Inline in feed + dedicated queue | Actionable in context AND batchable in dedicated view |
| Notifications | Replace Discord with in-UI | Single pane of glass, richer content rendering |
| Real-time | WebSocket (replacing polling/SSE-only) | Bidirectional, lower latency, connection state management |
| Backend | Rust (Axum) — extend existing | Proven performance, already battle-tested |
| Frontend | React 19 + shadcn/ui + Tailwind | Keep proven stack, rebuild pages/components |
| Visual aesthetic | Refined dark (Factory.ai inspired) | Matte surfaces, subtle borders, away from heavy glassmorphism |
| Persistence | DuckDB (sessions, approvals, feed) | Embedded OLAP, native JSON, fast analytics queries |
| Multi-agent | Sessions show all syndicate agents | Transparent orchestration visibility |
| Testing | MCP-based (Playwright MCP server) | Automated visual verification throughout implementation |

---

## Information Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ Kubani UI                                                      │
├──────────┬─────────────────────────────────────────────────────┤
│          │                                                     │
│ SIDEBAR  │  MAIN CONTENT AREA                                  │
│          │                                                     │
│ [Feed]   │  ┌─────────────────────────────────────────────┐   │
│ [Agent]  │  │                                             │   │
│ [Approv] │  │  Active View                                │   │
│ [Workfl] │  │  (one of 6 views)                           │   │
│ [Regist] │  │                                             │   │
│ [Cluste] │  │  + Optional side panel                      │   │
│          │  │    (detail, context, debug)                  │   │
│ ──────── │  │                                             │   │
│ [Cmd+K]  │  └─────────────────────────────────────────────┘   │
│ [Settin] │                                                     │
└──────────┴─────────────────────────────────────────────────────┘
```

### Navigation Structure

| View | Path | Purpose | Badge |
|------|------|---------|-------|
| **Activity Feed** | `/` | Real-time event stream, syndicate outputs | Unread count |
| **Agent Sessions** | `/sessions` | Direct agent/syndicate interaction | Active sessions |
| **Approvals** | `/approvals` | Pending skill/agent/action approvals | Pending count |
| **Workflows** | `/workflows` | Temporal workflow monitoring | Running count |
| **Registry** | `/registry` | Syndicates, agents, skills, MCP servers | — |
| **Cluster** | `/cluster` | Infrastructure health monitoring | — |

### Cross-Cutting Features

- **Command Palette (Cmd+K)** — Quick navigation, agent launch, search
- **WebSocket connection** — Real-time push for all views
- **Side panel pattern** — Detail/context panels slide in from right on any view
- **Notification badges** — Live counts on Approvals and Activity Feed
- **Global search** — Search across agents, skills, workflows, activity

---

## Phase Overview

Each phase has its own detailed design and implementation document.

| Phase | Document | Scope | Dependencies |
|-------|----------|-------|--------------|
| **Phase 0** | [Visual Design System](./2026-01-28-ui-redesign-phase-0-design-system.md) | Design tokens, surfaces, animations, typography | None |
| **Phase 1** | [Backend Foundation](./2026-01-28-ui-redesign-phase-1-backend.md) | WebSocket, event bus, persistence, shared state | None |
| **Phase 2** | [Activity Feed](./2026-01-28-ui-redesign-phase-2-activity-feed.md) | Feed UI, real-time events, rich content, side panel | Phase 0, 1 |
| **Phase 3** | [Agent Sessions](./2026-01-28-ui-redesign-phase-3-agent-sessions.md) | Smart routing, multi-agent sessions, toggleable debug | Phase 0, 1 |
| **Phase 4** | [Approvals System](./2026-01-28-ui-redesign-phase-4-approvals.md) | Approval queue, inline actions, state machine | Phase 0, 1, 2 |
| **Phase 5** | [Workflows View](./2026-01-28-ui-redesign-phase-5-workflows.md) | Temporal workflow monitoring, detail panel | Phase 0, 1 |
| **Phase 6** | [Registry View](./2026-01-28-ui-redesign-phase-6-registry.md) | Syndicate/agent/skill/MCP browser, actions | Phase 0 |
| **Phase 7** | [Cluster View](./2026-01-28-ui-redesign-phase-7-cluster.md) | Node/pod/service monitoring, charts | Phase 0 |

### Dependency Graph

```
Phase 0 (Design System) ──┬──→ Phase 2 (Activity Feed) ──→ Phase 4 (Approvals)
                           ├──→ Phase 3 (Agent Sessions)
Phase 1 (Backend) ────────┤──→ Phase 5 (Workflows)
                           ├──→ Phase 6 (Registry)
                           └──→ Phase 7 (Cluster)
```

**Recommended execution order:**
1. Phase 0 + Phase 1 (parallel — no dependencies)
2. Phase 6 + Phase 7 (parallel — only need Phase 0)
3. Phase 2 (needs Phase 0 + 1)
4. Phase 3 (needs Phase 0 + 1)
5. Phase 5 (needs Phase 0 + 1)
6. Phase 4 (needs Phase 2)

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (React 19)                        │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Activity  │ │ Sessions │ │Approvals │ │Workflows │ │ Registry │ │
│  │ Feed     │ │          │ │          │ │          │ │ +Cluster │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ │
│       │            │            │            │            │        │
│  ┌────┴────────────┴────────────┴────────────┴────────────┴────┐  │
│  │                   WebSocket Client                          │  │
│  │  - Connection management (auto-reconnect, heartbeat)        │  │
│  │  - Subscription model (subscribe to event types/filters)    │  │
│  │  - State synchronization                                    │  │
│  └─────────────────────────┬───────────────────────────────────┘  │
│                             │                                      │
│  ┌──────────────────────────┴──────────────────────────────────┐  │
│  │                   REST API Client                           │  │
│  │  - Session CRUD, Approval actions, Registry queries         │  │
│  │  - Retained for non-streaming operations                    │  │
│  └─────────────────────────┬───────────────────────────────────┘  │
└─────────────────────────────┼──────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │   Rust Backend    │
                    │   (Axum 0.7)     │
                    ├───────────────────┤
                    │                   │
                    │ ┌───────────────┐ │
                    │ │ WebSocket Hub │ │    ← tokio broadcast channels
                    │ │ (real-time)   │ │
                    │ └───────┬───────┘ │
                    │         │         │
                    │ ┌───────┴───────┐ │
                    │ │ Event         │ │    ← Redis Streams consumer
                    │ │ Aggregator    │ │    ← Syndicates publish here
                    │ └───────┬───────┘ │
                    │         │         │
                    │ ┌───────┴───────┐ │
                    │ │ Session Mgr   │ │    ← DuckDB persistence
                    │ │ (chat state)  │ │
                    │ └───────────────┘ │
                    │                   │
                    │ ┌───────────────┐ │
                    │ │ Router Agent  │ │    ← Intent classification
                    │ │ (dispatch)    │ │    ← Routes to syndicates
                    │ └───────────────┘ │
                    │                   │
                    │ ┌───────────────┐ │
                    │ │ Approval Svc  │ │    ← State machine
                    │ │ (CRUD)        │ │    ← DuckDB persistence
                    │ └───────────────┘ │
                    │                   │
                    │ ┌───────────────┐ │
                    │ │ MCP Client    │ │    ← Existing, expanded
                    │ │ Pool          │ │
                    │ └───────────────┘ │
                    │                   │
                    │ ┌───────────────┐ │
                    │ │ REST API      │ │    ← Existing endpoints
                    │ │ (monitoring,  │ │    ← + new CRUD endpoints
                    │ │  registry)    │ │
                    │ └───────────────┘ │
                    └───────┬───────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
        ┌─────┴─────┐ ┌────┴────┐ ┌──────┴──────┐
        │ Redis     │ │ DuckDB  │ │ External    │
        │ Streams   │ │ (local) │ │ Services    │
        │ (events)  │ │         │ │             │
        └───────────┘ └─────────┘ │ - vLLM      │
                                   │ - Temporal  │
                                   │ - K8s MCP   │
                                   │ - Registry  │
                                   │ - Qdrant    │
                                   └─────────────┘
```

### Event Flow: Syndicate Output → UI

```
1. Syndicate (Python) completes work
2. Publishes event to Redis Stream: "kubani:activity"
   {
     "source": "news-digest",
     "type": "syndicate_output",
     "title": "Daily AI News Digest Generated",
     "content": "## Top Stories\n1. ...",  // Rich markdown
     "metadata": { "articles_processed": 12, "high_relevance": 3 }
   }
3. Rust backend Redis consumer picks up event
4. Stores in DuckDB activity_events table
5. Broadcasts via WebSocket to all connected clients
6. Frontend Activity Feed renders new item with slide-in animation
```

### Event Flow: User Chat → Syndicate Routing

```
1. User types: "What's happening with pod crashes in production?"
2. Frontend sends to /api/sessions/{id}/message via WebSocket
3. Router Agent classifies intent → "k8s-monitor" syndicate
4. Backend creates/resumes session with k8s-monitor syndicate
5. Syndicate agents (event-classifier, remediator) work in sequence
6. Each agent step streams back via WebSocket:
   - router_decision: { syndicate: "k8s-monitor", confidence: 0.92 }
   - agent_start: { agent: "event-classifier", step: 1 }
   - tool_call: { name: "pods_list", args: {...} }
   - tool_result: { ... }
   - content: "I found 3 pods in CrashLoopBackOff..."
   - agent_complete: { agent: "event-classifier" }
7. Frontend renders multi-agent session with activity panel
```

### Event Flow: Approval Request

```
1. Learning system's SkillSynthesizer proposes a new skill
2. Publishes to Redis Stream: "kubani:approvals"
   {
     "type": "skill_proposal",
     "source": "learning-system/skill-synthesizer",
     "data": { name, description, triggers, category, confidence, spec_markdown }
   }
3. Backend stores in DuckDB approvals table (status: "pending")
4. Broadcasts via WebSocket: new_approval event
5. Frontend shows:
   - Badge increment on Approvals nav item
   - New card in Activity Feed (if syndicate filter matches)
   - New item in Approvals queue
6. User clicks "Approve" → POST /api/approvals/{id}/approve
7. Backend updates status, publishes approval event to Redis
8. Learning system picks up approval, deploys skill
```

---

## Technical Decisions

### Why DuckDB for Persistence

The UI backend needs persistent storage for sessions, approvals, and activity history. Options considered:

| Option | Pros | Cons |
|--------|------|------|
| **DuckDB** | Embedded OLAP, native JSON type, fast analytics (counts/aggregations), great Rust support | Single-writer (fine for single backend instance) |
| SQLite | Simple, widely used | JSON as TEXT only, no columnar storage |
| PostgreSQL | Full ACID, concurrent writes, rich queries | Requires external service, operational overhead |
| Redis only | Already in stack, fast | No relational queries, persistence complexity |

**Decision: DuckDB.** The UI backend is a single instance. DuckDB excels at the analytics queries needed for dashboards (counts by status, aggregations over time). Native JSON type means no serialization overhead. No external dependency to manage.

### Why WebSocket (Not Just SSE)

| Feature | SSE | WebSocket |
|---------|-----|-----------|
| Server → Client | Yes | Yes |
| Client → Server | No (needs separate HTTP) | Yes |
| Connection state | Simple | Rich (open/close/error handlers) |
| Reconnection | Auto (EventSource) | Manual (but standard pattern) |
| Subscriptions | Not native | Easy to implement |
| Binary data | No | Yes |

**Decision: WebSocket.** The UI needs bidirectional communication for session interaction and subscription management. SSE is retained only for the existing chat streaming endpoint (backward compatibility).

### Why Keep React + shadcn/ui

The existing frontend has 40+ shadcn components already configured. Switching to SolidJS or Svelte would require rewriting every component. The redesign changes page structure and adds new views but can reuse primitives (Button, Card, Badge, Tabs, Dialog, Sheet, Tooltip, etc.).

---

## New Dependencies

### Backend (Rust)

```toml
# Add to Cargo.toml [dependencies]
duckdb = { version = "1.0", features = ["bundled"] }  # DuckDB (embedded OLAP)
redis = { version = "0.25", features = ["tokio-comp", "streams"] }  # Redis Streams
```

Note: `axum` already has `ws` feature enabled in existing Cargo.toml.

### Frontend (npm)

```json
{
  "dependencies": {
    "react-markdown": "^9.0.0",    // Rich markdown rendering in feed
    "remark-gfm": "^4.0.0",        // GitHub-flavored markdown
    "rehype-highlight": "^7.0.0",  // Code syntax highlighting
    "date-fns": "^3.6.0"           // Date formatting (lightweight)
  }
}
```

---

## Migration Strategy

The redesign is additive, not destructive. Existing pages continue to work during development.

1. **Phase 0 + 1** — New design system and backend capabilities. Existing pages unaffected.
2. **Phase 2-7** — New pages added alongside existing ones. Old routes remain.
3. **Cutover** — Once all new views are functional, update navigation and remove old pages.
4. **Cleanup** — Remove unused old components and routes.

### File Organization

```
client/src/
├── app/                    # NEW: App shell, routing, providers
│   ├── App.tsx
│   ├── Router.tsx
│   └── providers.tsx
├── features/               # NEW: Feature-based organization
│   ├── activity-feed/
│   │   ├── ActivityFeed.tsx
│   │   ├── FeedItem.tsx
│   │   ├── FeedFilters.tsx
│   │   └── hooks/
│   ├── sessions/
│   │   ├── SessionsView.tsx
│   │   ├── SessionChat.tsx
│   │   ├── SessionList.tsx
│   │   └── hooks/
│   ├── approvals/
│   │   ├── ApprovalsView.tsx
│   │   ├── ApprovalCard.tsx
│   │   └── hooks/
│   ├── workflows/
│   │   ├── WorkflowsView.tsx
│   │   ├── WorkflowDetail.tsx
│   │   └── hooks/
│   ├── registry/
│   │   ├── RegistryView.tsx
│   │   ├── SyndicateCard.tsx
│   │   ├── AgentCard.tsx
│   │   └── hooks/
│   └── cluster/
│       ├── ClusterView.tsx
│       ├── NodeDetail.tsx
│       └── hooks/
├── shared/                 # NEW: Shared components and utilities
│   ├── components/
│   │   ├── Layout.tsx          # New DashboardLayout
│   │   ├── SidePanel.tsx       # Reusable side panel
│   │   ├── CommandPalette.tsx  # Cmd+K
│   │   ├── RichContent.tsx     # Markdown/table renderer
│   │   └── StatusBadge.tsx
│   ├── hooks/
│   │   ├── useWebSocket.ts     # WebSocket connection
│   │   ├── useActivityFeed.ts  # Feed subscription
│   │   └── useApprovals.ts     # Approval state
│   └── lib/
│       ├── api.ts              # REST client (extended)
│       ├── ws.ts               # WebSocket client
│       └── types.ts            # Shared TypeScript types
├── components/             # EXISTING: shadcn/ui (keep as-is)
│   └── ui/
├── contexts/               # EXISTING: Theme (keep)
├── pages/                  # EXISTING: Old pages (remove after cutover)
└── lib/                    # EXISTING: Utils (keep)
```

---

## Testing Strategy: MCP-Based Verification

Throughout implementation, use MCP servers (particularly Playwright MCP) to verify that UI components look and function correctly. This enables automated visual testing and validation at each phase.

### Playwright MCP Server Integration

The Playwright MCP server provides browser automation tools that can be used to:

1. **Visual Verification** — Screenshot pages after each phase, compare against expected layouts
2. **Functional Testing** — Click buttons, fill forms, verify responses
3. **Real-time Testing** — Test WebSocket connections, verify events appear in feed
4. **Responsive Testing** — Verify layouts at different viewport sizes

### Per-Phase Testing Checklist

Each phase should include Playwright MCP verification:

| Phase | Tests |
|-------|-------|
| **Phase 0** | Screenshot base styles, verify color tokens render correctly |
| **Phase 1** | Test WebSocket connection establishment, verify health endpoints |
| **Phase 2** | Verify feed loads, test filter interactions, check rich content rendering |
| **Phase 3** | Test session creation, verify routing indicator appears, check tool call display |
| **Phase 4** | Test approve/reject buttons, verify status updates, check batch selection |
| **Phase 5** | Verify workflow list loads, test detail panel opens, check action buttons |
| **Phase 6** | Test tab switching, verify search/filter, check syndicate card actions |
| **Phase 7** | Verify node metrics display, test charts render, check side panel |

### Example Playwright MCP Usage

```
# After implementing Activity Feed (Phase 2):

1. Use playwright_navigate to open http://localhost:5173/
2. Use playwright_screenshot to capture feed state
3. Use playwright_click to test filter chips
4. Use playwright_screenshot to verify filtered state
5. Publish test event to Redis
6. Use playwright_screenshot to verify new event appears
7. Use playwright_click on event to open side panel
8. Use playwright_screenshot to verify side panel content
```

### Automated Verification Points

After each implementation step, verify:

1. **No visual regressions** — Compare screenshots to previous phase
2. **Interactive elements work** — Buttons, links, inputs respond correctly
3. **Real-time updates work** — WebSocket events trigger UI updates
4. **Error states handled** — Error messages display correctly
5. **Loading states work** — Skeletons/spinners show during data fetch

This MCP-based testing approach ensures quality throughout the implementation and catches issues early before they compound.

---

## Success Criteria

### Functional
- [ ] Activity Feed shows real-time syndicate outputs within 1 second of publication
- [ ] Agent Sessions routes queries to correct syndicate with >90% accuracy
- [ ] Approvals can be processed (approve/reject/modify) from both feed and dedicated view
- [ ] Workflows view shows accurate Temporal workflow state
- [ ] Registry displays all registered syndicates, agents, skills, MCP servers
- [ ] Cluster view shows node/pod/service health with resource metrics
- [ ] Command palette provides quick access to all primary actions

### Non-Functional
- [ ] WebSocket reconnects automatically within 3 seconds
- [ ] Feed items render rich markdown, tables, and code blocks
- [ ] Toggle between clean and debug detail levels in agent sessions
- [ ] Mobile-responsive layout for all views
- [ ] Page load under 2 seconds
- [ ] Smooth animations at 60fps

### Qualitative
- [ ] Daily use replaces need to check Discord for syndicate outputs
- [ ] Approval workflow is faster than Discord reaction-based approval
- [ ] Agent interaction feels like talking to one unified system, not selecting specific agents

---

## Open Questions

1. **Authentication** — Should we add auth now, or defer? Currently no auth on the UI.
2. **Multi-user** — If multiple users are connected, should they see each other's sessions?
3. **Notification sound/browser notifications** — Should approval requests trigger browser notifications?
4. **Dark/light mode** — The previous plan included light theme. Keep or defer?
5. **Agent session persistence** — How long should sessions be retained? 7 days? 30 days?

---

## Related Documents

- [Previous idea: Design System Overhaul](../ideas/2026-01-27-kubani-ui-design-system-overhaul.md) — Visual polish plan (superseded by this broader redesign)
- Phase documents (linked in Phase Overview above)
