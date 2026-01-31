# Phase 2: Activity Feed

**Parent:** [UI Redesign Master Plan](./2026-01-28-ui-redesign-master-plan.md)
**Status:** Draft
**Dependencies:** Phase 0 (Design System), Phase 1 (Backend Foundation)
**Estimated scope:** ~8 new frontend files, ~2 new backend files

---

## Overview

The Activity Feed is the landing page and primary view of the redesigned Kubani UI. It displays a unified, real-time stream of all activity across the Kubani cluster — syndicate outputs, agent activity, workflow state changes, approval requests, learning events, and system notifications. This replaces Discord as the primary output channel.

---

## Goals

1. Real-time feed of all cluster activity via WebSocket
2. Rich content rendering (markdown, tables, code blocks)
3. Filter chips for source, event type, and severity
4. Inline approval actions on approval-type feed items
5. Side panel for detailed view without leaving the feed
6. Unread indicators and mark-as-read support
7. Smooth entry animations for new items

---

## 1. Frontend Architecture

### Feature Directory Structure

```
client/src/features/activity-feed/
├── ActivityFeed.tsx          # Main page component
├── FeedItem.tsx              # Individual feed item card
├── FeedItemDetail.tsx        # Side panel detail view
├── FeedFilters.tsx           # Filter chips component
├── RichContent.tsx           # Markdown/table/code renderer
├── InlineApprovalActions.tsx # Approve/reject buttons for feed items
├── hooks/
│   └── useActivityFeed.ts   # WebSocket subscription + REST fallback
└── types.ts                 # TypeScript types for feed data
```

### Data Types

```typescript
// types.ts

export interface ActivityEvent {
  id: string;
  source: string;          // 'news-digest', 'k8s-monitor', 'learning-system', 'system'
  event_type: string;       // 'syndicate_output', 'agent_activity', 'alert', 'approval', 'workflow', 'learning', 'system'
  title: string;
  content: string;          // Rich markdown content
  metadata: Record<string, unknown>;
  severity: 'info' | 'warning' | 'error' | 'success';
  created_at: string;       // ISO 8601
  read: boolean;
}

export type FeedFilter = {
  source?: string;
  event_type?: string;
  severity?: string;
};

// Event type display configuration
export const EVENT_TYPE_CONFIG: Record<string, { label: string; icon: string; color: string }> = {
  syndicate_output: { label: 'Output', icon: 'FileText', color: 'text-accent' },
  agent_activity:   { label: 'Agent', icon: 'Bot', color: 'text-primary' },
  alert:            { label: 'Alert', icon: 'AlertTriangle', color: 'text-warning' },
  approval:         { label: 'Approval', icon: 'ShieldCheck', color: 'text-warning' },
  workflow:         { label: 'Workflow', icon: 'Workflow', color: 'text-info' },
  learning:         { label: 'Learning', icon: 'Brain', color: 'text-accent' },
  system:           { label: 'System', icon: 'Settings', color: 'text-muted-foreground' },
};

// Source display configuration
export const SOURCE_CONFIG: Record<string, { label: string; shortLabel: string }> = {
  'k8s-monitor':      { label: 'Kubernetes Monitor', shortLabel: 'k8s' },
  'news-digest':      { label: 'News Digest', shortLabel: 'news' },
  'learning-system':  { label: 'Learning System', shortLabel: 'learn' },
  'system':           { label: 'System', shortLabel: 'sys' },
};
```

### Hook: useActivityFeed

```typescript
// hooks/useActivityFeed.ts

import { useState, useEffect, useCallback, useRef } from 'react';
import { ActivityEvent, FeedFilter } from '../types';

interface UseActivityFeedOptions {
  filters?: FeedFilter;
  pageSize?: number;
}

interface UseActivityFeedResult {
  events: ActivityEvent[];
  isLoading: boolean;
  hasMore: boolean;
  unreadCount: number;
  loadMore: () => void;
  markAsRead: (ids: string[]) => void;
  refresh: () => void;
}

export function useActivityFeed(options: UseActivityFeedOptions = {}): UseActivityFeedResult {
  const { filters, pageSize = 50 } = options;
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasMore, setHasMore] = useState(true);
  const [unreadCount, setUnreadCount] = useState(0);
  const offsetRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);

  // Initial load from REST API
  const loadEvents = useCallback(async (offset: number = 0) => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters?.source) params.set('source', filters.source);
      if (filters?.event_type) params.set('event_type', filters.event_type);
      params.set('limit', String(pageSize));
      params.set('offset', String(offset));

      const response = await fetch(`/api/activity?${params}`);
      const data: ActivityEvent[] = await response.json();

      if (offset === 0) {
        setEvents(data);
      } else {
        setEvents(prev => [...prev, ...data]);
      }
      setHasMore(data.length === pageSize);
      offsetRef.current = offset + data.length;
    } catch (error) {
      console.error('Failed to load activity events:', error);
    } finally {
      setIsLoading(false);
    }
  }, [filters, pageSize]);

  // Load unread count
  const loadUnreadCount = useCallback(async () => {
    try {
      const response = await fetch('/api/activity/unread-count');
      const data = await response.json();
      setUnreadCount(data.count);
    } catch {
      // Ignore errors
    }
  }, []);

  // WebSocket for real-time updates
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'activity_item') {
          // Apply client-side filter
          const matchesFilter = (!filters?.source || data.source === filters.source)
            && (!filters?.event_type || data.event_type === filters.event_type);

          if (matchesFilter) {
            setEvents(prev => [{
              id: data.id,
              source: data.source,
              event_type: data.event_type,
              title: data.title,
              content: data.content,
              metadata: data.metadata,
              severity: 'info',
              created_at: data.timestamp,
              read: false,
            }, ...prev]);
          }

          setUnreadCount(prev => prev + 1);
        }

        if (data.type === 'new_approval') {
          // Also add approvals to the feed
          setEvents(prev => [{
            id: data.id,
            source: data.source,
            event_type: 'approval',
            title: data.title,
            content: data.summary,
            metadata: { approval_type: data.approval_type },
            severity: 'warning',
            created_at: data.timestamp,
            read: false,
          }, ...prev]);
          setUnreadCount(prev => prev + 1);
        }
      } catch {
        // Ignore parse errors
      }
    };

    ws.onclose = () => {
      // Auto-reconnect after 3 seconds
      setTimeout(() => {
        // Reconnect logic (re-run this effect)
      }, 3000);
    };

    return () => {
      ws.close();
    };
  }, [filters]);

  // Initial data load
  useEffect(() => {
    loadEvents(0);
    loadUnreadCount();
  }, [loadEvents, loadUnreadCount]);

  const loadMore = useCallback(() => {
    loadEvents(offsetRef.current);
  }, [loadEvents]);

  const markAsRead = useCallback(async (ids: string[]) => {
    try {
      await fetch('/api/activity/mark-read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids }),
      });
      setEvents(prev => prev.map(e =>
        ids.includes(e.id) ? { ...e, read: true } : e
      ));
      setUnreadCount(prev => Math.max(0, prev - ids.length));
    } catch {
      // Ignore errors
    }
  }, []);

  const refresh = useCallback(() => {
    offsetRef.current = 0;
    loadEvents(0);
    loadUnreadCount();
  }, [loadEvents, loadUnreadCount]);

  return { events, isLoading, hasMore, unreadCount, loadMore, markAsRead, refresh };
}
```

---

## 2. Main Components

### ActivityFeed.tsx (Page Component)

```tsx
// ActivityFeed.tsx

import { useState, useCallback } from 'react';
import { useActivityFeed } from './hooks/useActivityFeed';
import { FeedItem } from './FeedItem';
import { FeedItemDetail } from './FeedItemDetail';
import { FeedFilters } from './FeedFilters';
import { ActivityEvent, FeedFilter } from './types';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { RefreshCw } from 'lucide-react';

export function ActivityFeed() {
  const [filters, setFilters] = useState<FeedFilter>({});
  const [selectedEvent, setSelectedEvent] = useState<ActivityEvent | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const { events, isLoading, hasMore, unreadCount, loadMore, markAsRead, refresh } =
    useActivityFeed({ filters });

  const handleItemClick = useCallback((event: ActivityEvent) => {
    setSelectedEvent(event);
    setDetailOpen(true);
    if (!event.read) {
      markAsRead([event.id]);
    }
  }, [markAsRead]);

  return (
    <div className="page-padding h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-heading-1">Activity Feed</h1>
          {unreadCount > 0 && (
            <p className="text-caption mt-1">
              {unreadCount} unread {unreadCount === 1 ? 'event' : 'events'}
            </p>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={refresh}
          className="gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <FeedFilters
        activeFilters={filters}
        onFilterChange={setFilters}
        className="mb-4"
      />

      {/* Feed items */}
      <div className="flex-1 overflow-y-auto scrollbar-thin section-gap">
        {isLoading && events.length === 0 ? (
          // Skeleton loading
          <div className="stack-md">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="surface rounded-xl p-4">
                <div className="animate-shimmer h-4 w-1/3 rounded mb-2" />
                <div className="animate-shimmer h-3 w-2/3 rounded mb-1" />
                <div className="animate-shimmer h-3 w-1/2 rounded" />
              </div>
            ))}
          </div>
        ) : events.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <p>No activity events found.</p>
            <p className="text-caption mt-1">Events from syndicates and agents will appear here.</p>
          </div>
        ) : (
          <>
            {events.map((event) => (
              <FeedItem
                key={event.id}
                event={event}
                onClick={() => handleItemClick(event)}
                className="animate-fade-in-up"
              />
            ))}

            {hasMore && (
              <div className="flex justify-center py-4">
                <Button variant="ghost" onClick={loadMore} disabled={isLoading}>
                  {isLoading ? 'Loading...' : 'Load more'}
                </Button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Detail side panel */}
      <Sheet open={detailOpen} onOpenChange={setDetailOpen}>
        <SheetContent side="right" className="surface-elevated w-full sm:w-[480px] p-0">
          {selectedEvent && (
            <FeedItemDetail
              event={selectedEvent}
              onClose={() => setDetailOpen(false)}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
```

### FeedItem.tsx (Feed Card)

```tsx
// FeedItem.tsx

import { cn } from '@/lib/utils';
import { ActivityEvent, EVENT_TYPE_CONFIG, SOURCE_CONFIG } from './types';
import { RichContent } from './RichContent';
import { InlineApprovalActions } from './InlineApprovalActions';
import { Badge } from '@/components/ui/badge';
import { formatDistanceToNow } from 'date-fns';
import * as Icons from 'lucide-react';

interface FeedItemProps {
  event: ActivityEvent;
  onClick: () => void;
  className?: string;
}

export function FeedItem({ event, onClick, className }: FeedItemProps) {
  const typeConfig = EVENT_TYPE_CONFIG[event.event_type] || EVENT_TYPE_CONFIG.system;
  const sourceConfig = SOURCE_CONFIG[event.source] || { label: event.source, shortLabel: event.source };
  const Icon = (Icons as Record<string, React.ComponentType<{ className?: string }>>)[typeConfig.icon] || Icons.Activity;

  const severityBadgeVariant = {
    info: 'info' as const,
    warning: 'warning' as const,
    error: 'destructive' as const,
    success: 'success' as const,
  }[event.severity] || 'secondary' as const;

  const timeAgo = formatDistanceToNow(new Date(event.created_at), { addSuffix: true });

  return (
    <div
      className={cn(
        "surface-interactive cursor-pointer card-padding-compact",
        !event.read && "border-l-2 border-l-primary",
        className
      )}
      onClick={onClick}
    >
      {/* Header row */}
      <div className="flex items-center gap-2 mb-2">
        <Badge variant={severityBadgeVariant} className="gap-1">
          <Icon className="w-3 h-3" />
          {typeConfig.label}
        </Badge>
        <span className="text-caption">{sourceConfig.label}</span>
        <span className="text-caption ml-auto">{timeAgo}</span>
      </div>

      {/* Title */}
      <h3 className="text-body font-medium text-foreground mb-1">
        {event.title}
      </h3>

      {/* Content preview (truncated) */}
      {event.content && (
        <div className="text-caption line-clamp-3">
          <RichContent content={event.content} truncate maxLength={200} />
        </div>
      )}

      {/* Metadata chips */}
      {event.metadata && Object.keys(event.metadata).length > 0 && (
        <div className="flex gap-2 mt-2 flex-wrap">
          {Object.entries(event.metadata).slice(0, 3).map(([key, value]) => (
            <span key={key} className="text-mono text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
              {key}: {String(value)}
            </span>
          ))}
        </div>
      )}

      {/* Inline approval actions (if this is an approval event) */}
      {event.event_type === 'approval' && (
        <InlineApprovalActions
          approvalId={event.id}
          className="mt-3"
        />
      )}
    </div>
  );
}
```

### FeedFilters.tsx

```tsx
// FeedFilters.tsx

import { cn } from '@/lib/utils';
import { FeedFilter, SOURCE_CONFIG, EVENT_TYPE_CONFIG } from './types';
import { Button } from '@/components/ui/button';

interface FeedFiltersProps {
  activeFilters: FeedFilter;
  onFilterChange: (filters: FeedFilter) => void;
  className?: string;
}

export function FeedFilters({ activeFilters, onFilterChange, className }: FeedFiltersProps) {
  const sources = Object.entries(SOURCE_CONFIG);
  const eventTypes = Object.entries(EVENT_TYPE_CONFIG);

  const toggleSource = (source: string) => {
    onFilterChange({
      ...activeFilters,
      source: activeFilters.source === source ? undefined : source,
    });
  };

  const toggleEventType = (eventType: string) => {
    onFilterChange({
      ...activeFilters,
      event_type: activeFilters.event_type === eventType ? undefined : eventType,
    });
  };

  const clearAll = () => onFilterChange({});

  const hasActiveFilters = activeFilters.source || activeFilters.event_type;

  return (
    <div className={cn("flex flex-wrap gap-2 items-center", className)}>
      {/* All chip */}
      <Button
        variant={!hasActiveFilters ? "default" : "outline"}
        size="sm"
        onClick={clearAll}
        className="h-7 text-xs"
      >
        All
      </Button>

      {/* Divider */}
      <div className="w-px h-5 bg-border-subtle" />

      {/* Source filters */}
      {sources.map(([key, config]) => (
        <Button
          key={key}
          variant={activeFilters.source === key ? "default" : "outline"}
          size="sm"
          onClick={() => toggleSource(key)}
          className="h-7 text-xs"
        >
          {config.shortLabel}
        </Button>
      ))}

      {/* Divider */}
      <div className="w-px h-5 bg-border-subtle" />

      {/* Event type filters */}
      {eventTypes.map(([key, config]) => (
        <Button
          key={key}
          variant={activeFilters.event_type === key ? "default" : "outline"}
          size="sm"
          onClick={() => toggleEventType(key)}
          className="h-7 text-xs"
        >
          {config.label}
        </Button>
      ))}
    </div>
  );
}
```

### RichContent.tsx

```tsx
// RichContent.tsx

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { cn } from '@/lib/utils';

interface RichContentProps {
  content: string;
  truncate?: boolean;
  maxLength?: number;
  className?: string;
}

export function RichContent({ content, truncate, maxLength = 200, className }: RichContentProps) {
  const displayContent = truncate && content.length > maxLength
    ? content.slice(0, maxLength) + '...'
    : content;

  if (truncate) {
    // Simple text rendering for truncated previews
    return (
      <span className={cn("text-muted-foreground", className)}>
        {displayContent.replace(/[#*_`~\[\]]/g, '')}
      </span>
    );
  }

  return (
    <div className={cn("prose prose-invert prose-sm max-w-none", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          // Custom renderers for better styling
          table: ({ children }) => (
            <div className="overflow-x-auto my-3">
              <table className="w-full border-collapse">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="text-left text-label p-2 border-b border-border-subtle">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="text-body p-2 border-b border-border-subtle/50">
              {children}
            </td>
          ),
          code: ({ className, children, ...props }) => {
            const isInline = !className;
            if (isInline) {
              return (
                <code className="text-mono bg-muted/50 px-1 py-0.5 rounded" {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code className={cn("block surface-inset p-3 rounded-lg overflow-x-auto", className)} {...props}>
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="surface-inset p-0 rounded-lg overflow-x-auto my-3">
              {children}
            </pre>
          ),
        }}
      />
    </div>
  );
}
```

### FeedItemDetail.tsx (Side Panel)

```tsx
// FeedItemDetail.tsx

import { ActivityEvent, EVENT_TYPE_CONFIG, SOURCE_CONFIG } from './types';
import { RichContent } from './RichContent';
import { InlineApprovalActions } from './InlineApprovalActions';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { X, ExternalLink } from 'lucide-react';
import { formatDistanceToNow, format } from 'date-fns';

interface FeedItemDetailProps {
  event: ActivityEvent;
  onClose: () => void;
}

export function FeedItemDetail({ event, onClose }: FeedItemDetailProps) {
  const typeConfig = EVENT_TYPE_CONFIG[event.event_type] || EVENT_TYPE_CONFIG.system;
  const sourceConfig = SOURCE_CONFIG[event.source] || { label: event.source };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border-subtle">
        <div>
          <Badge variant="secondary" className="mb-1">
            {typeConfig.label}
          </Badge>
          <h2 className="text-heading-3">{event.title}</h2>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="w-4 h-4" />
        </Button>
      </div>

      {/* Metadata */}
      <div className="px-4 py-3 border-b border-border-subtle text-caption flex flex-wrap gap-x-4 gap-y-1">
        <span>Source: <strong>{sourceConfig.label}</strong></span>
        <span>Time: <strong>{format(new Date(event.created_at), 'PPp')}</strong></span>
        <span>({formatDistanceToNow(new Date(event.created_at), { addSuffix: true })})</span>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1 p-4">
        <RichContent content={event.content} />

        {/* Full metadata */}
        {event.metadata && Object.keys(event.metadata).length > 0 && (
          <div className="mt-6">
            <h4 className="text-label mb-2">Metadata</h4>
            <div className="surface-inset p-3 rounded-lg">
              <pre className="text-mono text-xs whitespace-pre-wrap">
                {JSON.stringify(event.metadata, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </ScrollArea>

      {/* Actions footer */}
      {event.event_type === 'approval' && (
        <div className="p-4 border-t border-border-subtle">
          <InlineApprovalActions approvalId={event.id} expanded />
        </div>
      )}
    </div>
  );
}
```

### InlineApprovalActions.tsx

```tsx
// InlineApprovalActions.tsx

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Check, X, Edit } from 'lucide-react';
import { cn } from '@/lib/utils';

interface InlineApprovalActionsProps {
  approvalId: string;
  expanded?: boolean;
  className?: string;
}

export function InlineApprovalActions({ approvalId, expanded, className }: InlineApprovalActionsProps) {
  const [status, setStatus] = useState<'pending' | 'approved' | 'rejected' | 'loading'>('pending');

  const handleApprove = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setStatus('loading');
    try {
      await fetch(`/api/approvals/${approvalId}/approve`, { method: 'POST' });
      setStatus('approved');
    } catch {
      setStatus('pending');
    }
  };

  const handleReject = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setStatus('loading');
    try {
      await fetch(`/api/approvals/${approvalId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: null }),
      });
      setStatus('rejected');
    } catch {
      setStatus('pending');
    }
  };

  if (status === 'approved') {
    return <span className="text-success text-sm font-medium">Approved</span>;
  }
  if (status === 'rejected') {
    return <span className="text-error text-sm font-medium">Rejected</span>;
  }

  return (
    <div className={cn("flex gap-2", className)} onClick={(e) => e.stopPropagation()}>
      <Button
        variant="outline"
        size="sm"
        onClick={handleApprove}
        disabled={status === 'loading'}
        className="gap-1 text-success border-success/30 hover:bg-success/10"
      >
        <Check className="w-3.5 h-3.5" />
        {expanded && 'Approve'}
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={handleReject}
        disabled={status === 'loading'}
        className="gap-1 text-error border-error/30 hover:bg-error/10"
      >
        <X className="w-3.5 h-3.5" />
        {expanded && 'Reject'}
      </Button>
      {expanded && (
        <Button variant="outline" size="sm" className="gap-1">
          <Edit className="w-3.5 h-3.5" />
          Modify
        </Button>
      )}
    </div>
  );
}
```

---

## 3. Backend Additions

### Redis Stream Schema for Syndicate Publishing

Syndicates publish to `kubani:activity` stream with these fields:

```
XADD kubani:activity *
  source "news-digest"
  type "syndicate_output"
  title "Daily AI News Digest — January 28, 2026"
  content "## Top Stories\n\n1. **OpenAI releases GPT-5** — The new model shows...\n\n2. ..."
  severity "info"
  metadata '{"articles_processed": 12, "high_relevance": 3, "digest_id": "2026-01-28"}'
```

Required fields: `source`, `type`, `title`
Optional fields: `content` (default: ""), `severity` (default: "info"), `metadata` (default: "{}")

### Python Helper for Syndicates

Add a helper function to the framework so syndicates can easily publish:

```python
# kubani/framework/ui_events.py

import json
import redis.asyncio as redis
from kubani.framework.config import get_config

ACTIVITY_STREAM = "kubani:activity"
APPROVALS_STREAM = "kubani:approvals"

async def publish_activity(
    source: str,
    event_type: str,
    title: str,
    content: str = "",
    severity: str = "info",
    metadata: dict | None = None,
) -> str:
    """Publish an activity event to the UI feed.

    Args:
        source: Syndicate/agent name (e.g., 'news-digest')
        event_type: Event category (e.g., 'syndicate_output', 'alert')
        title: Short title for the feed card
        content: Rich markdown content for detail view
        severity: 'info', 'warning', 'error', 'success'
        metadata: Additional structured data

    Returns:
        Redis stream entry ID
    """
    config = get_config()
    r = redis.from_url(f"redis://{config.redis.host}:{config.redis.port}")

    entry = {
        "source": source,
        "type": event_type,
        "title": title,
        "content": content,
        "severity": severity,
        "metadata": json.dumps(metadata or {}),
    }

    entry_id = await r.xadd(ACTIVITY_STREAM, entry)
    await r.aclose()
    return entry_id


async def publish_approval(
    approval_type: str,
    source: str,
    title: str,
    summary: str,
    spec: str = "",
    metadata: dict | None = None,
) -> str:
    """Publish an approval request to the UI.

    Args:
        approval_type: 'skill_proposal', 'agent_proposal', 'action_request'
        source: Origin (e.g., 'learning-system/skill-synthesizer')
        title: Short title
        summary: Brief description for the approval card
        spec: Full specification markdown
        metadata: Structured data (confidence, triggers, etc.)

    Returns:
        Redis stream entry ID
    """
    config = get_config()
    r = redis.from_url(f"redis://{config.redis.host}:{config.redis.port}")

    entry = {
        "type": approval_type,
        "source": source,
        "title": title,
        "summary": summary,
        "spec": spec,
        "metadata": json.dumps(metadata or {}),
    }

    entry_id = await r.xadd(APPROVALS_STREAM, entry)
    await r.aclose()
    return entry_id
```

### Integration Example (News Digest Syndicate)

```python
# In news_digest syndicate, after generating a digest:
from kubani.framework.ui_events import publish_activity

await publish_activity(
    source="news-digest",
    event_type="syndicate_output",
    title=f"Daily AI News Digest — {date.today().strftime('%B %d, %Y')}",
    content=digest_markdown,  # Full markdown content
    severity="info",
    metadata={
        "articles_processed": len(articles),
        "high_relevance": high_relevance_count,
        "digest_id": digest_id,
    },
)
```

---

## 4. npm Dependencies

Add to `package.json`:

```json
{
  "dependencies": {
    "react-markdown": "^9.0.0",
    "remark-gfm": "^4.0.0",
    "rehype-highlight": "^7.0.0",
    "date-fns": "^3.6.0"
  }
}
```

---

## 5. Implementation Checklist

### Frontend

- [ ] Create `client/src/features/activity-feed/` directory
- [ ] Create `types.ts` with ActivityEvent, FeedFilter, config maps
- [ ] Create `hooks/useActivityFeed.ts` with WebSocket + REST integration
- [ ] Create `RichContent.tsx` with markdown rendering
- [ ] Create `FeedItem.tsx` with card layout, badges, preview
- [ ] Create `FeedFilters.tsx` with filter chips
- [ ] Create `InlineApprovalActions.tsx` with approve/reject buttons
- [ ] Create `FeedItemDetail.tsx` with side panel layout
- [ ] Create `ActivityFeed.tsx` main page component
- [ ] Add route `/` pointing to ActivityFeed in Router
- [ ] Update DashboardLayout navigation to include Activity Feed
- [ ] Install `react-markdown`, `remark-gfm`, `rehype-highlight`, `date-fns`

### Backend

- [ ] Create `kubani/framework/ui_events.py` with publish helpers
- [ ] Update news-digest syndicate to publish activity events
- [ ] Update k8s-monitor syndicate to publish activity events
- [ ] Update learning system to publish approval events

### Verification

- [ ] Activity Feed loads and shows existing events from REST API
- [ ] New events appear in real-time via WebSocket
- [ ] Filter chips correctly filter events
- [ ] Rich markdown renders (headers, lists, tables, code blocks)
- [ ] Side panel opens with full event detail
- [ ] Inline approval buttons work (approve/reject)
- [ ] Unread count badge appears on navigation
- [ ] Load more pagination works
- [ ] Empty state shows when no events
- [ ] Skeleton loading state shows during initial load
- [ ] New items animate in with fade-in-up

---

## Files Summary

| File | Status | Purpose |
|------|--------|---------|
| `client/src/features/activity-feed/ActivityFeed.tsx` | NEW | Main page component |
| `client/src/features/activity-feed/FeedItem.tsx` | NEW | Feed card component |
| `client/src/features/activity-feed/FeedItemDetail.tsx` | NEW | Side panel detail |
| `client/src/features/activity-feed/FeedFilters.tsx` | NEW | Filter chips |
| `client/src/features/activity-feed/RichContent.tsx` | NEW | Markdown renderer |
| `client/src/features/activity-feed/InlineApprovalActions.tsx` | NEW | Approval buttons |
| `client/src/features/activity-feed/hooks/useActivityFeed.ts` | NEW | Data hook |
| `client/src/features/activity-feed/types.ts` | NEW | TypeScript types |
| `kubani/framework/ui_events.py` | NEW | Python publish helpers |
| `client/src/App.tsx` | MODIFIED | Add Activity Feed route |
| `client/src/components/DashboardLayout.tsx` | MODIFIED | Update navigation |

**Total: 9 new files, 2 modified files**
