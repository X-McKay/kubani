# Phase 6: Registry View

**Parent:** [UI Redesign Master Plan](./2026-01-28-ui-redesign-master-plan.md)
**Status:** Draft
**Dependencies:** Phase 0 (Design System)
**Estimated scope:** ~8 new frontend files, ~1 modified backend file

---

## Overview

Consolidated browser for all registered components in the Kubani ecosystem. Tabs for Syndicates, Agents, Skills, and MCP Servers. Each entity shows status, capabilities, and provides contextual actions.

---

## Goals

1. Four tabs: Syndicates, Agents, Skills, MCP Servers
2. Searchable, filterable lists
3. Detail side panels with full configuration
4. Contextual actions (Start Session, View Workflows, etc.)
5. Status indicators for health monitoring
6. Syndicates tab shows member agents and active workflows

---

## 1. Key Design Change: Syndicates as First-Class

The current Registry page has Agents, MCP, Skills, Models tabs. The redesign elevates **Syndicates** to the first tab and removes the Models tab (models are implementation details, not user-facing).

### Syndicate Data

Syndicates are fetched from the metadata registry. Each syndicate includes:
- Name, description, status
- Member agents (list with status)
- Active workflows (count from Temporal)
- Recent activity (last N feed events)

### Backend: Syndicate Endpoint

```rust
// Add to backend/src/api/registry.rs

pub async fn get_syndicates() -> Json<serde_json::Value> {
    // Fetch from metadata registry
    let registry_url = std::env::var("REGISTRY_URL")
        .unwrap_or_else(|_| "http://metadata-registry.ai-agents.svc.cluster.local:8000".to_string());

    let client = reqwest::Client::new();
    match client.get(format!("{}/api/syndicates", registry_url)).send().await {
        Ok(resp) if resp.status().is_success() => {
            Json(resp.json().await.unwrap_or(serde_json::json!([])))
        }
        _ => {
            // Fallback: construct from known syndicates
            Json(serde_json::json!([
                {
                    "id": "k8s-monitor",
                    "name": "Kubernetes Monitor",
                    "description": "Kubernetes monitoring and auto-remediation",
                    "status": "healthy",
                    "agents": ["event-classifier", "remediator", "escalation"],
                    "namespace": "k8s-monitor"
                },
                {
                    "id": "news-digest",
                    "name": "News Digest",
                    "description": "News aggregation and digest generation",
                    "status": "healthy",
                    "agents": ["feed-collector", "content-analyst"],
                    "namespace": "news-digest"
                },
                {
                    "id": "learning-system",
                    "name": "Learning System",
                    "description": "Continuous learning with Critic, Reflection, and Synthesizer",
                    "status": "healthy",
                    "agents": ["critic", "reflection", "skill-synthesizer"],
                    "namespace": "learning-system"
                }
            ]))
        }
    }
}
```

---

## 2. Frontend Architecture

### Feature Directory Structure

```
client/src/features/registry/
├── RegistryView.tsx         # Main page with tabs
├── SyndicatesTab.tsx        # Syndicates list
├── SyndicateCard.tsx        # Syndicate card with member agents
├── AgentsTab.tsx            # Agents list
├── AgentCard.tsx            # Agent card
├── SkillsTab.tsx            # Skills list with search
├── McpServersTab.tsx        # MCP servers list
├── RegistryDetail.tsx       # Shared side panel for any entity detail
├── hooks/
│   └── useRegistry.ts      # Data fetching for all tabs
└── types.ts                # TypeScript types
```

### Data Types

```typescript
export interface Syndicate {
  id: string;
  name: string;
  description: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  agents: string[];
  namespace: string;
  active_workflows?: number;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  status: 'ready' | 'busy' | 'offline' | 'healthy';
  version?: string;
  capabilities: string[];
  syndicate_id?: string;
}

export interface Skill {
  id: string;
  name: string;
  domain: string;
  category: string;
  confidence: number;
  success_count: number;
  failure_count: number;
  status: string;
  triggers?: string[];
}

export interface McpServer {
  id: string;
  name: string;
  description: string;
  transport: 'http' | 'sse' | 'stdio';
  status: 'connected' | 'disconnected' | 'error';
  tools: number;
  capabilities: string[];
}

export type RegistryTab = 'syndicates' | 'agents' | 'skills' | 'mcp-servers';
```

### SyndicateCard.tsx

```tsx
import { Syndicate } from './types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { MessageSquare, Workflow, Users } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SyndicateCardProps {
  syndicate: Syndicate;
  onSelect: () => void;
}

export function SyndicateCard({ syndicate, onSelect }: SyndicateCardProps) {
  const statusVariant = {
    healthy: 'success' as const,
    degraded: 'warning' as const,
    unhealthy: 'destructive' as const,
  }[syndicate.status];

  return (
    <div className="surface-interactive card-padding cursor-pointer" onClick={onSelect}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-body font-medium">{syndicate.name}</h3>
          <p className="text-caption mt-0.5">{syndicate.description}</p>
        </div>
        <Badge variant={statusVariant}>
          <span className="status-dot status-dot-${syndicate.status === 'healthy' ? 'success' : syndicate.status === 'degraded' ? 'warning' : 'error'} mr-1.5" />
          {syndicate.status}
        </Badge>
      </div>

      {/* Member agents */}
      <div className="flex items-center gap-2 mb-3">
        <Users className="w-3.5 h-3.5 text-muted-foreground" />
        <span className="text-caption">{syndicate.agents.length} agents:</span>
        <div className="flex gap-1 flex-wrap">
          {syndicate.agents.map(agent => (
            <Badge key={agent} variant="secondary" className="text-xs">{agent}</Badge>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
        <Button size="sm" variant="outline" className="gap-1" asChild>
          <a href={`/sessions?syndicate=${syndicate.id}`}>
            <MessageSquare className="w-3.5 h-3.5" />
            Start Session
          </a>
        </Button>
        <Button size="sm" variant="outline" className="gap-1" asChild>
          <a href={`/workflows?syndicate=${syndicate.id}`}>
            <Workflow className="w-3.5 h-3.5" />
            Workflows
            {syndicate.active_workflows != null && syndicate.active_workflows > 0 && (
              <Badge variant="secondary" className="ml-1 text-xs">{syndicate.active_workflows}</Badge>
            )}
          </a>
        </Button>
      </div>
    </div>
  );
}
```

### SkillsTab.tsx

Skills are the most searchable entity. This tab includes:
- Search input for name/category/trigger matching
- Sort by confidence, usage count, or name
- Cards showing: name, domain/category, confidence score (as progress bar), success/failure counts, triggers as chips
- Detail panel shows full skill specification

---

## 3. Implementation Checklist

### Backend
- [ ] Add `get_syndicates` endpoint to `backend/src/api/registry.rs`
- [ ] Add `/api/registry/syndicates` route to main.rs

### Frontend
- [ ] Create `client/src/features/registry/` directory
- [ ] Create `types.ts`
- [ ] Create `hooks/useRegistry.ts`
- [ ] Create `SyndicateCard.tsx`
- [ ] Create `SyndicatesTab.tsx`
- [ ] Create `AgentsTab.tsx` and `AgentCard.tsx`
- [ ] Create `SkillsTab.tsx`
- [ ] Create `McpServersTab.tsx`
- [ ] Create `RegistryDetail.tsx` (shared side panel)
- [ ] Create `RegistryView.tsx` (main page)
- [ ] Add route `/registry` in Router

### Verification
- [ ] Syndicates tab shows all registered syndicates with member agents
- [ ] Agents tab shows all agents with capabilities
- [ ] Skills tab is searchable, filterable, sortable
- [ ] MCP Servers tab shows status and tool count
- [ ] "Start Session" on syndicate navigates to Sessions with pre-selected syndicate
- [ ] "Workflows" on syndicate navigates to Workflows filtered by syndicate
- [ ] Detail side panel shows full entity information
- [ ] Status indicators are accurate

---

## Files Summary

| File | Status | Purpose |
|------|--------|---------|
| `backend/src/api/registry.rs` | MODIFIED | Add syndicates endpoint |
| `client/src/features/registry/RegistryView.tsx` | NEW | Main page |
| `client/src/features/registry/SyndicatesTab.tsx` | NEW | Syndicates list |
| `client/src/features/registry/SyndicateCard.tsx` | NEW | Syndicate card |
| `client/src/features/registry/AgentsTab.tsx` | NEW | Agents list |
| `client/src/features/registry/SkillsTab.tsx` | NEW | Skills list |
| `client/src/features/registry/McpServersTab.tsx` | NEW | MCP servers list |
| `client/src/features/registry/RegistryDetail.tsx` | NEW | Shared detail panel |
| `client/src/features/registry/hooks/useRegistry.ts` | NEW | Data hook |
| `client/src/features/registry/types.ts` | NEW | Types |

**Total: 9 new frontend files, 1 modified backend file**
