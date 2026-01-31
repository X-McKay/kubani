# Phase 4: Approvals System

**Parent:** [UI Redesign Master Plan](./2026-01-28-ui-redesign-master-plan.md)
**Status:** Draft
**Dependencies:** Phase 0 (Design System), Phase 1 (Backend Foundation), Phase 2 (Activity Feed)
**Estimated scope:** ~6 new frontend files, backend already built in Phase 1

---

## Overview

Dedicated approvals queue for managing human-in-the-loop decisions. Skills, agents, and actions proposed by the learning system are presented for review with full context. Approvals also appear inline in the Activity Feed (Phase 2). This phase builds the dedicated queue view.

---

## Goals

1. Dedicated queue view with pending/approved/rejected/all tabs
2. Rich approval cards with full specification
3. Approve, reject, and request-modification actions
4. Side panel for full spec review
5. Batch selection for bulk approve/reject
6. Real-time updates via WebSocket (new approvals appear, status changes)

---

## 1. Frontend Architecture

### Feature Directory Structure

```
client/src/features/approvals/
├── ApprovalsView.tsx        # Main page with tabs + list
├── ApprovalCard.tsx         # Approval item card
├── ApprovalDetail.tsx       # Side panel detail view
├── ApprovalActions.tsx      # Full action buttons (approve/reject/modify)
├── hooks/
│   └── useApprovals.ts     # Data fetching + WebSocket subscription
└── types.ts                # TypeScript types
```

### Data Types

```typescript
// types.ts

export interface Approval {
  id: string;
  approval_type: 'skill_proposal' | 'agent_proposal' | 'action_request';
  source: string;
  title: string;
  summary: string;
  spec: string;           // Full markdown specification
  metadata: {
    confidence?: number;
    triggers?: string[];
    category?: string;
    based_on?: number;    // Number of observations
    [key: string]: unknown;
  };
  status: 'pending' | 'approved' | 'rejected' | 'modified';
  feedback?: string;
  created_at: string;
  updated_at: string;
}

export type ApprovalTab = 'pending' | 'approved' | 'rejected' | 'all';
```

### ApprovalsView.tsx

```tsx
import { useState, useCallback } from 'react';
import { useApprovals } from './hooks/useApprovals';
import { ApprovalCard } from './ApprovalCard';
import { ApprovalDetail } from './ApprovalDetail';
import { Approval, ApprovalTab } from './types';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { CheckCheck, XCircle } from 'lucide-react';

export function ApprovalsView() {
  const [activeTab, setActiveTab] = useState<ApprovalTab>('pending');
  const [selectedApproval, setSelectedApproval] = useState<Approval | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const { approvals, pendingCount, isLoading, refresh } = useApprovals(activeTab);

  const handleSelect = useCallback((approval: Approval) => {
    setSelectedApproval(approval);
    setDetailOpen(true);
  }, []);

  const toggleSelection = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleBulkApprove = async () => {
    for (const id of selectedIds) {
      await fetch(`/api/approvals/${id}/approve`, { method: 'POST' });
    }
    setSelectedIds(new Set());
    refresh();
  };

  const handleBulkReject = async () => {
    for (const id of selectedIds) {
      await fetch(`/api/approvals/${id}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Bulk rejected' }),
      });
    }
    setSelectedIds(new Set());
    refresh();
  };

  return (
    <div className="page-padding h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-heading-1">Approvals</h1>
          {pendingCount > 0 && (
            <p className="text-caption mt-1">{pendingCount} pending approval{pendingCount !== 1 ? 's' : ''}</p>
          )}
        </div>

        {/* Bulk actions (show when items selected) */}
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">{selectedIds.size} selected</span>
            <Button size="sm" variant="outline" onClick={handleBulkApprove} className="gap-1 text-success">
              <CheckCheck className="w-4 h-4" />
              Approve All
            </Button>
            <Button size="sm" variant="outline" onClick={handleBulkReject} className="gap-1 text-error">
              <XCircle className="w-4 h-4" />
              Reject All
            </Button>
          </div>
        )}
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as ApprovalTab)} className="mb-4">
        <TabsList>
          <TabsTrigger value="pending" className="gap-1.5">
            Pending
            {pendingCount > 0 && <Badge variant="default" className="ml-1 text-xs">{pendingCount}</Badge>}
          </TabsTrigger>
          <TabsTrigger value="approved">Approved</TabsTrigger>
          <TabsTrigger value="rejected">Rejected</TabsTrigger>
          <TabsTrigger value="all">All</TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Approval list */}
      <div className="flex-1 overflow-y-auto scrollbar-thin stack-md">
        {isLoading ? (
          <div className="stack-md">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="surface rounded-xl p-4">
                <div className="animate-shimmer h-5 w-1/3 rounded mb-3" />
                <div className="animate-shimmer h-4 w-2/3 rounded mb-2" />
                <div className="animate-shimmer h-4 w-1/2 rounded" />
              </div>
            ))}
          </div>
        ) : approvals.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <p>No {activeTab === 'all' ? '' : activeTab} approvals.</p>
          </div>
        ) : (
          approvals.map(approval => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              selected={selectedIds.has(approval.id)}
              onSelect={() => handleSelect(approval)}
              onToggleSelection={() => toggleSelection(approval.id)}
              onApprove={() => { /* inline approve */ }}
              onReject={() => { /* inline reject */ }}
            />
          ))
        )}
      </div>

      {/* Detail side panel */}
      <Sheet open={detailOpen} onOpenChange={setDetailOpen}>
        <SheetContent side="right" className="surface-elevated w-full sm:w-[560px] p-0">
          {selectedApproval && (
            <ApprovalDetail
              approval={selectedApproval}
              onClose={() => setDetailOpen(false)}
              onAction={refresh}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
```

### ApprovalCard.tsx

```tsx
import { Approval } from './types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Check, X, Sparkles, Bot, ShieldCheck } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { cn } from '@/lib/utils';

interface ApprovalCardProps {
  approval: Approval;
  selected: boolean;
  onSelect: () => void;
  onToggleSelection: () => void;
  onApprove: () => void;
  onReject: () => void;
}

const TYPE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  skill_proposal: Sparkles,
  agent_proposal: Bot,
  action_request: ShieldCheck,
};

const TYPE_LABELS: Record<string, string> = {
  skill_proposal: 'Skill Proposal',
  agent_proposal: 'Agent Proposal',
  action_request: 'Action Request',
};

export function ApprovalCard({ approval, selected, onSelect, onToggleSelection, onApprove, onReject }: ApprovalCardProps) {
  const Icon = TYPE_ICONS[approval.approval_type] || ShieldCheck;
  const typeLabel = TYPE_LABELS[approval.approval_type] || approval.approval_type;
  const timeAgo = formatDistanceToNow(new Date(approval.created_at), { addSuffix: true });

  const statusBadge = {
    pending: <Badge variant="warning">Pending</Badge>,
    approved: <Badge variant="success">Approved</Badge>,
    rejected: <Badge variant="destructive">Rejected</Badge>,
    modified: <Badge variant="info">Modification Requested</Badge>,
  }[approval.status];

  return (
    <div
      className={cn(
        "surface-interactive card-padding cursor-pointer",
        selected && "ring-2 ring-primary/50"
      )}
      onClick={onSelect}
    >
      <div className="flex items-start gap-3">
        {/* Checkbox for bulk selection */}
        {approval.status === 'pending' && (
          <Checkbox
            checked={selected}
            onCheckedChange={() => onToggleSelection()}
            onClick={(e) => e.stopPropagation()}
            className="mt-1"
          />
        )}

        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-center gap-2 mb-2">
            <Badge variant="secondary" className="gap-1">
              <Icon className="w-3 h-3" />
              {typeLabel}
            </Badge>
            {statusBadge}
            <span className="text-caption ml-auto">{timeAgo}</span>
          </div>

          {/* Title */}
          <h3 className="text-body font-medium mb-1">{approval.title}</h3>

          {/* Summary */}
          <p className="text-caption line-clamp-2">{approval.summary}</p>

          {/* Metadata */}
          <div className="flex items-center gap-3 mt-2">
            <span className="text-caption">Source: {approval.source}</span>
            {approval.metadata.confidence && (
              <span className="text-caption">
                Confidence: {Math.round(approval.metadata.confidence * 100)}%
              </span>
            )}
            {approval.metadata.based_on && (
              <span className="text-caption">
                Based on: {approval.metadata.based_on} observations
              </span>
            )}
          </div>

          {/* Inline actions (pending only) */}
          {approval.status === 'pending' && (
            <div className="flex gap-2 mt-3" onClick={(e) => e.stopPropagation()}>
              <Button size="sm" variant="outline" onClick={onApprove}
                className="gap-1 text-success border-success/30 hover:bg-success/10">
                <Check className="w-3.5 h-3.5" /> Approve
              </Button>
              <Button size="sm" variant="outline" onClick={onReject}
                className="gap-1 text-error border-error/30 hover:bg-error/10">
                <X className="w-3.5 h-3.5" /> Reject
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

### ApprovalDetail.tsx

Full side panel with complete specification, metadata, and action buttons. Uses RichContent from Phase 2 to render the spec markdown. Shows full metadata table, action buttons at the bottom, and a text input for modification feedback.

### useApprovals.ts

Hook that:
- Fetches approvals from `/api/approvals?status={tab}` on tab change
- Subscribes to WebSocket for `new_approval` and `approval_updated` events
- Tracks `pendingCount` separately
- Provides `refresh()` function

---

## 2. Implementation Checklist

### Frontend
- [ ] Create `client/src/features/approvals/` directory
- [ ] Create `types.ts`
- [ ] Create `hooks/useApprovals.ts`
- [ ] Create `ApprovalCard.tsx`
- [ ] Create `ApprovalDetail.tsx` (side panel with full spec)
- [ ] Create `ApprovalActions.tsx` (approve/reject/modify with feedback input)
- [ ] Create `ApprovalsView.tsx` (main page)
- [ ] Add route `/approvals` in Router
- [ ] Update DashboardLayout navigation with badge count

### Verification
- [ ] Pending tab shows pending approvals
- [ ] Approved/Rejected tabs show historical items
- [ ] Approve button changes status to approved
- [ ] Reject button changes status to rejected (with optional reason)
- [ ] Modify button shows feedback input, sends modification request
- [ ] Side panel shows full specification in markdown
- [ ] Batch selection works (select multiple, bulk approve/reject)
- [ ] New approvals appear in real-time via WebSocket
- [ ] Badge count on nav updates in real-time
- [ ] Inline approval actions in Activity Feed (from Phase 2) still work

---

## Files Summary

| File | Status | Purpose |
|------|--------|---------|
| `client/src/features/approvals/ApprovalsView.tsx` | NEW | Main page |
| `client/src/features/approvals/ApprovalCard.tsx` | NEW | Approval card |
| `client/src/features/approvals/ApprovalDetail.tsx` | NEW | Side panel detail |
| `client/src/features/approvals/ApprovalActions.tsx` | NEW | Action buttons |
| `client/src/features/approvals/hooks/useApprovals.ts` | NEW | Data hook |
| `client/src/features/approvals/types.ts` | NEW | Types |

**Total: 6 new files**
