# Phase 7: Cluster View

**Parent:** [UI Redesign Master Plan](./2026-01-28-ui-redesign-master-plan.md)
**Status:** Draft
**Dependencies:** Phase 0 (Design System)
**Estimated scope:** ~6 new frontend files, 0 new backend files (reuses existing endpoints)

---

## Overview

Infrastructure monitoring view showing Kubernetes cluster health. This is a redesign of the existing Monitoring page to use the new design system and component patterns. The backend endpoints already exist — this phase is frontend-only.

---

## Goals

1. Rebuild monitoring page with new design system
2. Better visual hierarchy with the refined dark aesthetic
3. Consistent side panel pattern for node/pod details
4. Resource utilization charts with improved styling
5. Live event feed integrated into the view
6. Mobile-responsive layout

---

## 1. Existing Backend Endpoints (No Changes)

| Endpoint | Returns |
|----------|---------|
| `GET /api/monitoring/nodes` | Node list with CPU/memory/pod counts |
| `GET /api/monitoring/namespaces` | Namespace overview with pod counts |
| `GET /api/monitoring/events` | Recent Kubernetes events (50 max) |
| `GET /api/monitoring/services` | Service status and readiness |

These endpoints use the existing Moka cache (5-second TTL) and MCP tool calls. No backend changes needed.

---

## 2. Frontend Architecture

### Feature Directory Structure

```
client/src/features/cluster/
├── ClusterView.tsx          # Main page with tabs
├── OverviewTab.tsx          # Health summary cards + charts
├── NodesTab.tsx             # Node list with resource metrics
├── ServicesTab.tsx          # Service status table
├── EventsTab.tsx            # Kubernetes event feed
├── NodeDetail.tsx           # Side panel for node details
├── hooks/
│   └── useCluster.ts       # Data fetching with auto-refresh
└── types.ts                # TypeScript types
```

### Data Types

```typescript
export interface ClusterNode {
  name: string;
  status: string;
  role: string;
  cpu: number;         // Percentage
  memory: number;      // Percentage
  pods: number;
  ip: string;
}

export interface Namespace {
  name: string;
  running: number;
  total: number;
  status: string;
}

export interface ClusterEvent {
  namespace: string;
  lastSeen: string;
  type: string;         // 'Normal' | 'Warning'
  reason: string;
  object: string;
  message: string;
}

export interface Service {
  name: string;
  namespace: string;
  ready: string;
  status: string;
  type: string;
}

export type ClusterTab = 'overview' | 'nodes' | 'services' | 'events';
```

### OverviewTab.tsx

Summary cards showing:
- **Total Nodes**: count + healthy/unhealthy breakdown
- **Total Pods**: running/total across all namespaces
- **CPU Utilization**: average across nodes, with mini chart
- **Memory Utilization**: average across nodes, with mini chart

Uses Recharts for sparkline charts in the summary cards.

Below the cards: Namespace grid showing each namespace as a card with pod count bar chart.

### NodesTab.tsx

Table showing all nodes:
- Name, Status (with status-dot), Role
- CPU usage (progress bar + percentage)
- Memory usage (progress bar + percentage)
- Pod count
- IP address

Clicking a row opens the NodeDetail side panel.

### NodeDetail.tsx

Side panel showing:
- Node name, status, role, IP
- CPU and Memory as larger gauge charts
- Pod list for this node
- Recent events for this node
- Labels and annotations (collapsible)

### ServicesTab.tsx

Table showing all services:
- Name, Namespace, Type, Ready replicas, Status
- Status badge (color-coded)
- Click for detail panel

### EventsTab.tsx

List of recent Kubernetes events:
- Type badge (Normal = info, Warning = warning)
- Reason, Object, Namespace
- Message
- Time (relative + absolute on hover)
- Auto-refresh indicator

---

## 3. Design Patterns

### Resource Utilization Bars

```tsx
// Reusable resource bar component
function ResourceBar({ value, max = 100, label, color }: {
  value: number;
  max?: number;
  label: string;
  color: 'primary' | 'accent' | 'warning' | 'error';
}) {
  const percentage = Math.min(100, (value / max) * 100);
  const colorClass = {
    primary: 'bg-primary',
    accent: 'bg-accent',
    warning: 'bg-warning',
    error: 'bg-error',
  }[color];

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono">{Math.round(percentage)}%</span>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-500", colorClass)}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
```

### Auto-Refresh Hook

```typescript
function useAutoRefresh(callback: () => void, intervalMs: number = 30000) {
  useEffect(() => {
    const interval = setInterval(callback, intervalMs);
    return () => clearInterval(interval);
  }, [callback, intervalMs]);
}
```

---

## 4. Implementation Checklist

### Frontend
- [ ] Create `client/src/features/cluster/` directory
- [ ] Create `types.ts`
- [ ] Create `hooks/useCluster.ts` (fetches all monitoring endpoints, auto-refreshes every 30s)
- [ ] Create `OverviewTab.tsx` with summary cards and namespace grid
- [ ] Create `NodesTab.tsx` with node table and resource bars
- [ ] Create `NodeDetail.tsx` side panel
- [ ] Create `ServicesTab.tsx` with service table
- [ ] Create `EventsTab.tsx` with event list
- [ ] Create `ClusterView.tsx` main page with tabs
- [ ] Add route `/cluster` in Router
- [ ] Update DashboardLayout navigation

### Verification
- [ ] Overview shows correct node/pod/CPU/memory summaries
- [ ] Namespace cards show accurate pod counts
- [ ] Node table shows resource utilization with progress bars
- [ ] Node detail panel shows per-node data
- [ ] Services table shows readiness status
- [ ] Events list shows recent events with correct type badges
- [ ] Auto-refresh updates data every 30 seconds
- [ ] Mobile layout is usable
- [ ] All cards use new surface treatment from Phase 0
- [ ] Transitions and hover states are smooth

---

## 5. Migration from Existing Monitoring Page

The current `client/src/pages/Monitoring.tsx` will be replaced by `client/src/features/cluster/ClusterView.tsx`. During the transition:

1. Both routes exist: `/monitoring` (old) and `/cluster` (new)
2. When new view is verified, update Router to point `/` to Activity Feed and `/cluster` to ClusterView
3. Remove old `Monitoring.tsx` after cutover

---

## Files Summary

| File | Status | Purpose |
|------|--------|---------|
| `client/src/features/cluster/ClusterView.tsx` | NEW | Main page |
| `client/src/features/cluster/OverviewTab.tsx` | NEW | Summary cards |
| `client/src/features/cluster/NodesTab.tsx` | NEW | Node table |
| `client/src/features/cluster/NodeDetail.tsx` | NEW | Node detail panel |
| `client/src/features/cluster/ServicesTab.tsx` | NEW | Services table |
| `client/src/features/cluster/EventsTab.tsx` | NEW | Events list |
| `client/src/features/cluster/hooks/useCluster.ts` | NEW | Data hook |
| `client/src/features/cluster/types.ts` | NEW | Types |

**Total: 8 new frontend files, 0 backend changes**
