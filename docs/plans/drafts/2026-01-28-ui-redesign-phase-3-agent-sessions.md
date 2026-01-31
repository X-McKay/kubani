# Phase 3: Agent Sessions

**Parent:** [UI Redesign Master Plan](./2026-01-28-ui-redesign-master-plan.md)
**Status:** Draft
**Dependencies:** Phase 0 (Design System), Phase 1 (Backend Foundation)
**Estimated scope:** ~10 new frontend files, ~4 new/modified backend files

---

## Overview

The Agent Sessions view replaces the current Chat page with an intelligent agent interaction interface. Users type natural language queries and the system automatically routes them to the appropriate syndicate or agent. Multi-agent sessions show all participating agents and their orchestration. A toggleable detail level switches between a clean default view and a full debug mode.

---

## Goals

1. Smart routing: classify user intent and dispatch to the right syndicate/agent
2. Multi-agent visibility: show which agents in a syndicate are active
3. Toggleable detail levels (clean vs. debug)
4. Session persistence (survives page refresh)
5. Session list with history
6. Streaming responses with real-time tool execution visibility

---

## 1. Routing Architecture

### How Routing Works

When a user sends a message, the backend classifies the intent and routes to the appropriate handler:

```
User message → Router Agent (LLM-based classification)
  → Match: "k8s-monitor" → k8s-monitor syndicate agents + tools
  → Match: "news-digest" → news-digest syndicate agents + tools
  → Match: "learning"    → learning system syndicate agents + tools
  → No match             → General agent with basic MCP tools
```

### Router Agent Implementation

The router uses a lightweight LLM call with a classification prompt. It does NOT need to be a full agent — just a single LLM inference.

```rust
// backend/src/api/router.rs (NEW)

use serde::{Deserialize, Serialize};
use serde_json::json;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoutingDecision {
    pub syndicate_id: Option<String>,
    pub agent_id: Option<String>,
    pub confidence: f32,
    pub reasoning: String,
}

/// Available syndicates for routing
const SYNDICATE_DESCRIPTIONS: &str = r#"
Available syndicates:
1. "k8s-monitor" — Kubernetes cluster monitoring, pod health, node status, resource usage, crash investigation, remediation
2. "news-digest" — News aggregation, article collection, digest generation, content analysis
3. "learning-system" — Skill evaluation, reflection, skill synthesis, agent learning, continuous improvement
"#;

const ROUTER_PROMPT: &str = r#"You are a routing agent. Given a user's message, determine which syndicate should handle it.

{syndicates}

Respond in JSON format:
{
  "syndicate_id": "<syndicate-name>" or null,
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>"
}

If the message doesn't clearly match any syndicate, set syndicate_id to null. This will route to a general-purpose agent.

Only set a syndicate if you're >0.6 confident. Prefer null over a wrong match."#;

pub async fn classify_intent(message: &str) -> RoutingDecision {
    let vllm_url = std::env::var("VLLM_URL")
        .unwrap_or_else(|_| "http://llm-api.vllm.svc.cluster.local:8000/v1".to_string());
    let model_name = std::env::var("MODEL_NAME")
        .unwrap_or_else(|_| "Qwen/Qwen3-14B".to_string());

    let prompt = ROUTER_PROMPT.replace("{syndicates}", SYNDICATE_DESCRIPTIONS);

    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/chat/completions", vllm_url))
        .json(&json!({
            "model": model_name,
            "messages": [
                { "role": "system", "content": prompt },
                { "role": "user", "content": message }
            ],
            "temperature": 0.1,
            "max_tokens": 200,
            "response_format": { "type": "json_object" }
        }))
        .send()
        .await;

    match response {
        Ok(resp) if resp.status().is_success() => {
            if let Ok(body) = resp.json::<serde_json::Value>().await {
                if let Some(content) = body["choices"][0]["message"]["content"].as_str() {
                    if let Ok(decision) = serde_json::from_str::<RoutingDecision>(content) {
                        return decision;
                    }
                }
            }
        }
        _ => {}
    }

    // Default: no syndicate match
    RoutingDecision {
        syndicate_id: None,
        agent_id: None,
        confidence: 0.0,
        reasoning: "Failed to classify intent, defaulting to general agent".to_string(),
    }
}
```

### Syndicate-Specific Agent Configs

```rust
// backend/src/api/syndicate_configs.rs (NEW)

use crate::api::chat_executor::AgentConfig;
use serde_json::json;

/// Get the agent configuration for a syndicate
pub async fn get_syndicate_config(syndicate_id: &str) -> AgentConfig {
    match syndicate_id {
        "k8s-monitor" => AgentConfig {
            system_prompt: Some(K8S_MONITOR_SYSTEM_PROMPT.to_string()),
            tools: crate::api::chat_executor::get_dynamic_tools().await,
        },
        "news-digest" => AgentConfig {
            system_prompt: Some(NEWS_DIGEST_SYSTEM_PROMPT.to_string()),
            tools: vec![],  // News digest doesn't need MCP tools
        },
        "learning-system" => AgentConfig {
            system_prompt: Some(LEARNING_SYSTEM_PROMPT.to_string()),
            tools: vec![],  // Learning system doesn't need MCP tools directly
        },
        _ => {
            // General agent with dynamic tools
            AgentConfig {
                system_prompt: Some(crate::api::chat_executor::DYNAMIC_AGENT_PROMPT.to_string()),
                tools: crate::api::chat_executor::get_dynamic_tools().await,
            }
        }
    }
}

const K8S_MONITOR_SYSTEM_PROMPT: &str = r#"You are the Kubernetes Monitor syndicate, specialized in cluster health monitoring, diagnostics, and remediation.

Your capabilities:
- Detecting and diagnosing pod failures, crashes, and resource issues
- Monitoring resource utilization across nodes
- Identifying potential issues before they become critical
- Providing remediation suggestions and taking action

When investigating:
1. Gather current state using tools
2. Analyze for anomalies
3. Provide clear diagnosis with actionable recommendations

Be proactive about related issues."#;

const NEWS_DIGEST_SYSTEM_PROMPT: &str = r#"You are the News Digest syndicate, focused on news aggregation and content analysis.

Your capabilities:
- Summarizing recent news and articles
- Analyzing trends and patterns in news content
- Generating digests on specific topics
- Providing context on current events in AI/tech

Provide clear, well-structured summaries."#;

const LEARNING_SYSTEM_PROMPT: &str = r#"You are the Learning System syndicate, managing continuous improvement.

Your capabilities:
- Evaluating agent execution quality
- Synthesizing insights from cross-agent patterns
- Proposing new skills based on identified patterns
- Managing the skill approval workflow

Provide clear analysis of learning patterns and skill proposals."#;
```

---

## 2. Updated Session Message Flow

### File: `backend/src/api/sessions.rs` (UPDATED from Phase 1)

The `send_message` endpoint now includes routing:

```rust
pub async fn send_message(
    State(state): State<Arc<AppState>>,
    Path(id): Path<String>,
    Json(request): Json<SendMessageRequest>,
) -> Result<Sse<impl Stream<Item = Result<axum::response::sse::Event, Infallible>>>, StatusCode> {
    // 1. Load session
    let session = {
        let db = state.db.lock().await;
        match crate::db::sessions::get_by_id(&db, &id) {
            Ok(Some(s)) => s,
            _ => return Err(StatusCode::NOT_FOUND),
        }
    };

    // 2. Add user message to session
    let mut messages: Vec<ChatMessage> = serde_json::from_value(session.messages.clone())
        .unwrap_or_default();
    messages.push(ChatMessage {
        role: "user".to_string(),
        content: request.content.clone(),
        tool_calls: None,
        tool_call_id: None,
    });

    // 3. Route if this is a new session (no syndicate yet)
    let syndicate_id = if session.syndicate_id.is_some() {
        session.syndicate_id.clone()
    } else {
        let decision = crate::api::router::classify_intent(&request.content).await;

        // Update session with routing decision
        if let Some(ref sid) = decision.syndicate_id {
            let db = state.db.lock().await;
            let _ = crate::db::sessions::update_syndicate(&db, &id, sid);
        }

        decision.syndicate_id
    };

    // 4. Get agent config based on routing
    let config = match syndicate_id.as_deref() {
        Some(sid) => crate::api::syndicate_configs::get_syndicate_config(sid).await,
        None => crate::api::syndicate_configs::get_syndicate_config("general").await,
    };

    // 5. Create streaming response (reuse existing agentic loop)
    let event_stream = crate::api::chat_executor::create_agentic_stream(messages.clone(), config);

    // 6. Save messages (in background, after stream completes)
    let state_clone = state.clone();
    let session_id = id.clone();
    tokio::spawn(async move {
        // TODO: Collect final messages from stream and save
        // This will be more sophisticated in the multi-agent version
    });

    Ok(Sse::new(event_stream).keep_alive(KeepAlive::default()))
}
```

---

## 3. Frontend Architecture

### Feature Directory Structure

```
client/src/features/sessions/
├── SessionsView.tsx          # Main page with session list + active session
├── SessionList.tsx           # Left sidebar session list
├── SessionChat.tsx           # Chat message area
├── SessionInput.tsx          # Message input with send button
├── SessionMessage.tsx        # Individual message bubble
├── ToolCallBlock.tsx         # Tool call visualization
├── RoutingIndicator.tsx      # Shows which syndicate/agent was selected
├── DetailToggle.tsx          # Clean/Debug toggle switch
├── DebugPanel.tsx            # Debug event stream panel
├── NewSessionDialog.tsx      # Dialog for starting new session
├── hooks/
│   ├── useSession.ts         # Single session state + streaming
│   └── useSessions.ts        # Session list management
└── types.ts                  # TypeScript types
```

### Data Types

```typescript
// types.ts

export interface Session {
  id: string;
  title: string | null;
  agent_id: string | null;
  syndicate_id: string | null;
  status: 'active' | 'completed' | 'failed';
  created_at: string;
  updated_at: string;
}

export interface SessionDetail extends Session {
  messages: SessionMessage[];
  metadata: Record<string, unknown>;
}

export interface SessionMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  timestamp?: string;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  status?: 'pending' | 'running' | 'complete' | 'error';
  result?: string;
  error?: string;
  duration_ms?: number;
}

export interface RoutingDecision {
  syndicate_id: string | null;
  confidence: number;
  reasoning: string;
}

export type DetailLevel = 'clean' | 'debug';

export interface StreamEvent {
  type: 'content' | 'tool_call' | 'tool_start' | 'tool_complete' | 'tool_error' | 'routing' | 'done' | 'error';
  // ... fields vary by type
  [key: string]: unknown;
}
```

### SessionsView.tsx (Main Page)

```tsx
// SessionsView.tsx

import { useState, useCallback } from 'react';
import { SessionList } from './SessionList';
import { SessionChat } from './SessionChat';
import { NewSessionDialog } from './NewSessionDialog';
import { DetailToggle } from './DetailToggle';
import { DebugPanel } from './DebugPanel';
import { useSessions } from './hooks/useSessions';
import { useSession } from './hooks/useSession';
import { DetailLevel, StreamEvent } from './types';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable';
import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';

export function SessionsView() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [detailLevel, setDetailLevel] = useState<DetailLevel>('clean');
  const [showNewSession, setShowNewSession] = useState(false);
  const [debugEvents, setDebugEvents] = useState<StreamEvent[]>([]);

  const { sessions, isLoading: sessionsLoading, refresh: refreshSessions } = useSessions();
  const { session, messages, isStreaming, sendMessage } = useSession(activeSessionId);

  const handleNewSession = useCallback(async (agentId?: string, title?: string) => {
    try {
      const response = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId, title }),
      });
      const data = await response.json();
      setActiveSessionId(data.id);
      refreshSessions();
      setShowNewSession(false);
    } catch (error) {
      console.error('Failed to create session:', error);
    }
  }, [refreshSessions]);

  const handleSendMessage = useCallback(async (content: string) => {
    if (!activeSessionId) {
      // Auto-create session
      const response = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: content.slice(0, 50) }),
      });
      const data = await response.json();
      setActiveSessionId(data.id);
      refreshSessions();

      // Then send message
      await sendMessage(content, (event) => {
        setDebugEvents(prev => [...prev, event]);
      });
    } else {
      await sendMessage(content, (event) => {
        setDebugEvents(prev => [...prev, event]);
      });
    }
  }, [activeSessionId, sendMessage, refreshSessions]);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle">
        <h1 className="text-heading-2">Agent Sessions</h1>
        <div className="flex items-center gap-3">
          <DetailToggle level={detailLevel} onChange={setDetailLevel} />
          <Button size="sm" onClick={() => setShowNewSession(true)} className="gap-1">
            <Plus className="w-4 h-4" />
            New Session
          </Button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-hidden">
        <ResizablePanelGroup direction="horizontal">
          {/* Session list */}
          <ResizablePanel defaultSize={20} minSize={15} maxSize={30}>
            <SessionList
              sessions={sessions}
              activeSessionId={activeSessionId}
              onSelect={setActiveSessionId}
              onNew={() => setShowNewSession(true)}
            />
          </ResizablePanel>

          <ResizableHandle />

          {/* Chat area */}
          <ResizablePanel defaultSize={detailLevel === 'debug' ? 50 : 80}>
            <SessionChat
              session={session}
              messages={messages}
              isStreaming={isStreaming}
              detailLevel={detailLevel}
              onSendMessage={handleSendMessage}
            />
          </ResizablePanel>

          {/* Debug panel (only in debug mode) */}
          {detailLevel === 'debug' && (
            <>
              <ResizableHandle />
              <ResizablePanel defaultSize={30} minSize={20}>
                <DebugPanel events={debugEvents} />
              </ResizablePanel>
            </>
          )}
        </ResizablePanelGroup>
      </div>

      {/* New session dialog */}
      <NewSessionDialog
        open={showNewSession}
        onOpenChange={setShowNewSession}
        onCreateSession={handleNewSession}
      />
    </div>
  );
}
```

### DetailToggle.tsx

```tsx
// DetailToggle.tsx

import { DetailLevel } from './types';
import { Button } from '@/components/ui/button';
import { Eye, Bug } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DetailToggleProps {
  level: DetailLevel;
  onChange: (level: DetailLevel) => void;
}

export function DetailToggle({ level, onChange }: DetailToggleProps) {
  return (
    <div className="flex items-center bg-muted/50 rounded-lg p-0.5">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onChange('clean')}
        className={cn(
          "h-7 px-3 gap-1.5 rounded-md text-xs",
          level === 'clean' && "bg-card shadow-sm text-foreground",
          level !== 'clean' && "text-muted-foreground"
        )}
      >
        <Eye className="w-3.5 h-3.5" />
        Clean
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onChange('debug')}
        className={cn(
          "h-7 px-3 gap-1.5 rounded-md text-xs",
          level === 'debug' && "bg-card shadow-sm text-foreground",
          level !== 'debug' && "text-muted-foreground"
        )}
      >
        <Bug className="w-3.5 h-3.5" />
        Debug
      </Button>
    </div>
  );
}
```

### ToolCallBlock.tsx

```tsx
// ToolCallBlock.tsx — Shows tool calls in clean or debug mode

import { useState } from 'react';
import { ToolCall } from './types';
import { DetailLevel } from './types';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { ChevronRight, Check, X, Loader2 } from 'lucide-react';

interface ToolCallBlockProps {
  toolCall: ToolCall;
  detailLevel: DetailLevel;
}

export function ToolCallBlock({ toolCall, detailLevel }: ToolCallBlockProps) {
  const [expanded, setExpanded] = useState(detailLevel === 'debug');

  const statusIcon = {
    pending: <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />,
    running: <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />,
    complete: <Check className="w-3.5 h-3.5 text-success" />,
    error: <X className="w-3.5 h-3.5 text-error" />,
  }[toolCall.status || 'pending'];

  if (detailLevel === 'clean') {
    return (
      <div
        className="surface-inset rounded-lg px-3 py-2 flex items-center gap-2 cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {statusIcon}
        <span className="text-mono text-xs text-muted-foreground">{toolCall.name}</span>
        {toolCall.duration_ms && (
          <span className="text-caption ml-auto">{toolCall.duration_ms}ms</span>
        )}
        <ChevronRight className={cn("w-3.5 h-3.5 transition-transform", expanded && "rotate-90")} />

        {expanded && (
          <div className="w-full mt-2 pt-2 border-t border-border-subtle">
            {toolCall.result && (
              <pre className="text-mono text-xs whitespace-pre-wrap max-h-40 overflow-y-auto">
                {toolCall.result.slice(0, 500)}
                {toolCall.result.length > 500 && '...'}
              </pre>
            )}
            {toolCall.error && (
              <p className="text-error text-xs">{toolCall.error}</p>
            )}
          </div>
        )}
      </div>
    );
  }

  // Debug mode: always expanded, show full details
  return (
    <div className="surface-inset rounded-lg p-3 stack-sm">
      <div className="flex items-center gap-2">
        {statusIcon}
        <span className="text-mono text-xs font-medium">{toolCall.name}</span>
        <Badge variant="secondary" className="text-xs">{toolCall.id}</Badge>
        {toolCall.duration_ms && (
          <span className="text-caption ml-auto">{toolCall.duration_ms}ms</span>
        )}
      </div>

      <div>
        <p className="text-label mb-1">Arguments</p>
        <pre className="text-mono text-xs bg-background/50 p-2 rounded overflow-x-auto">
          {JSON.stringify(toolCall.arguments, null, 2)}
        </pre>
      </div>

      {toolCall.result && (
        <div>
          <p className="text-label mb-1">Result</p>
          <pre className="text-mono text-xs bg-background/50 p-2 rounded max-h-60 overflow-y-auto whitespace-pre-wrap">
            {toolCall.result}
          </pre>
        </div>
      )}

      {toolCall.error && (
        <div>
          <p className="text-label mb-1 text-error">Error</p>
          <pre className="text-mono text-xs text-error bg-error/5 p-2 rounded">
            {toolCall.error}
          </pre>
        </div>
      )}
    </div>
  );
}
```

### DebugPanel.tsx

```tsx
// DebugPanel.tsx — Right panel showing raw event stream

import { StreamEvent } from './types';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Copy, Trash2 } from 'lucide-react';
import { useRef, useEffect } from 'react';

interface DebugPanelProps {
  events: StreamEvent[];
  onClear?: () => void;
}

export function DebugPanel({ events, onClear }: DebugPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  const copyAllJson = () => {
    navigator.clipboard.writeText(JSON.stringify(events, null, 2));
  };

  const eventColor: Record<string, string> = {
    content: 'text-foreground',
    tool_call: 'text-warning',
    tool_start: 'text-info',
    tool_complete: 'text-success',
    tool_error: 'text-error',
    routing: 'text-accent',
    done: 'text-success',
    error: 'text-error',
  };

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <span className="text-label">Events</span>
          <Badge variant="secondary" className="text-xs">{events.length}</Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={copyAllJson}>
            <Copy className="w-3.5 h-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onClear}>
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* Event list */}
      <ScrollArea className="flex-1" ref={scrollRef}>
        <div className="p-2 stack-xs">
          {events.map((event, i) => (
            <div
              key={i}
              className="surface-inset rounded p-2 hover-row cursor-pointer"
              onClick={() => {
                // Toggle expand
              }}
            >
              <div className="flex items-center gap-2 mb-1">
                <Badge
                  variant="secondary"
                  className={`text-xs ${eventColor[event.type] || 'text-foreground'}`}
                >
                  {event.type.toUpperCase()}
                </Badge>
                <span className="text-caption">#{i}</span>
                <span className="text-caption ml-auto">seq {i}</span>
              </div>
              <pre className="text-mono text-xs text-muted-foreground whitespace-pre-wrap max-h-20 overflow-hidden">
                {JSON.stringify(event, null, 2).slice(0, 200)}
              </pre>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
```

### RoutingIndicator.tsx

```tsx
// RoutingIndicator.tsx — Shows which syndicate was selected

import { RoutingDecision } from './types';
import { Badge } from '@/components/ui/badge';
import { ArrowRight, Bot } from 'lucide-react';

interface RoutingIndicatorProps {
  decision: RoutingDecision;
}

const SYNDICATE_LABELS: Record<string, string> = {
  'k8s-monitor': 'Kubernetes Monitor',
  'news-digest': 'News Digest',
  'learning-system': 'Learning System',
};

export function RoutingIndicator({ decision }: RoutingIndicatorProps) {
  const label = decision.syndicate_id
    ? SYNDICATE_LABELS[decision.syndicate_id] || decision.syndicate_id
    : 'General Agent';

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-muted-foreground">
      <ArrowRight className="w-3 h-3" />
      <span>Routed to</span>
      <Badge variant="secondary" className="gap-1">
        <Bot className="w-3 h-3" />
        {label}
      </Badge>
      <span className="text-caption">
        ({Math.round(decision.confidence * 100)}% confidence)
      </span>
    </div>
  );
}
```

---

## 4. Implementation Checklist

### Backend

- [ ] Create `backend/src/api/router.rs` -- Intent classification with LLM
- [ ] Create `backend/src/api/syndicate_configs.rs` -- Per-syndicate agent configs
- [ ] Update `backend/src/api/sessions.rs` -- Add routing to `send_message`, return SSE stream
- [ ] Update `backend/src/api/mod.rs` -- Add router, syndicate_configs modules
- [ ] Add `update_syndicate` function to `db/sessions` module
- [ ] Test routing with sample queries for each syndicate

### Frontend

- [ ] Create `client/src/features/sessions/` directory
- [ ] Create `types.ts` with Session, SessionMessage, ToolCall, RoutingDecision, DetailLevel, StreamEvent
- [ ] Create `hooks/useSessions.ts` -- List sessions from API
- [ ] Create `hooks/useSession.ts` -- Single session state, message sending, streaming
- [ ] Create `SessionList.tsx` -- Left sidebar with session list
- [ ] Create `SessionChat.tsx` -- Main chat area with messages
- [ ] Create `SessionInput.tsx` -- Text input with send button
- [ ] Create `SessionMessage.tsx` -- Message bubble component
- [ ] Create `ToolCallBlock.tsx` -- Tool call visualization (clean/debug modes)
- [ ] Create `RoutingIndicator.tsx` -- Shows routing decision
- [ ] Create `DetailToggle.tsx` -- Clean/Debug toggle
- [ ] Create `DebugPanel.tsx` -- Raw event stream panel
- [ ] Create `NewSessionDialog.tsx` -- New session creation dialog
- [ ] Create `SessionsView.tsx` -- Main page component
- [ ] Add route `/sessions` in Router
- [ ] Update DashboardLayout navigation

### Verification

- [ ] New session can be created
- [ ] Typing a k8s-related question routes to k8s-monitor
- [ ] Typing a news-related question routes to news-digest
- [ ] General questions route to default agent
- [ ] Routing decision is shown in the UI
- [ ] Tool calls display in clean mode (collapsed, name + status)
- [ ] Tool calls display in debug mode (expanded, full args/results)
- [ ] Debug panel shows raw event stream
- [ ] Toggle between clean and debug mode
- [ ] Session list shows all sessions with status
- [ ] Session history persists on page refresh
- [ ] Streaming responses render incrementally
- [ ] Session auto-creates when typing without selecting one

---

## Files Summary

| File | Status | Purpose |
|------|--------|---------|
| `backend/src/api/router.rs` | NEW | Intent classification |
| `backend/src/api/syndicate_configs.rs` | NEW | Per-syndicate configs |
| `backend/src/api/sessions.rs` | MODIFIED | Add routing + SSE streaming |
| `backend/src/api/mod.rs` | MODIFIED | New module declarations |
| `client/src/features/sessions/SessionsView.tsx` | NEW | Main page |
| `client/src/features/sessions/SessionList.tsx` | NEW | Session list sidebar |
| `client/src/features/sessions/SessionChat.tsx` | NEW | Chat area |
| `client/src/features/sessions/SessionInput.tsx` | NEW | Message input |
| `client/src/features/sessions/SessionMessage.tsx` | NEW | Message bubble |
| `client/src/features/sessions/ToolCallBlock.tsx` | NEW | Tool call viz |
| `client/src/features/sessions/RoutingIndicator.tsx` | NEW | Routing display |
| `client/src/features/sessions/DetailToggle.tsx` | NEW | Detail level toggle |
| `client/src/features/sessions/DebugPanel.tsx` | NEW | Debug event stream |
| `client/src/features/sessions/NewSessionDialog.tsx` | NEW | New session dialog |
| `client/src/features/sessions/hooks/useSession.ts` | NEW | Session state hook |
| `client/src/features/sessions/hooks/useSessions.ts` | NEW | Sessions list hook |
| `client/src/features/sessions/types.ts` | NEW | TypeScript types |

**Total: 13 new frontend files, 2 new backend files, 2 modified backend files**
