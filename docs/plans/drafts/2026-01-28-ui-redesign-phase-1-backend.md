# Phase 1: Backend Foundation

**Parent:** [UI Redesign Master Plan](./2026-01-28-ui-redesign-master-plan.md)
**Status:** Draft
**Dependencies:** None (can be built in parallel with Phase 0)
**Estimated scope:** ~12 new files, ~3 modified files

---

## Overview

Build the backend infrastructure required by all subsequent phases: WebSocket server, Redis Streams event consumption, DuckDB persistence layer, and shared application state. This phase adds no new user-facing features but provides the foundation for real-time updates, session persistence, and approval workflows.

---

## Goals

1. Add WebSocket endpoint with subscription model
2. Connect to Redis Streams to consume syndicate/agent events
3. Add DuckDB database for sessions, approvals, and activity history
4. Create shared application state (AppState) accessible across all handlers
5. Maintain backward compatibility with all existing REST/SSE endpoints

---

## 1. New Dependencies

### Add to `backend/Cargo.toml`

```toml
[dependencies]
# ... existing dependencies ...

# DuckDB (embedded OLAP database, excellent for analytics queries)
duckdb = { version = "1.0", features = ["bundled"] }

# Redis (with tokio async and streams support)
redis = { version = "0.25", features = ["tokio-comp", "streams"] }
```

**Why DuckDB over SQLite:**
- **Columnar storage** — Better for analytics queries on activity/event data
- **Faster aggregations** — Counts, groupings for dashboard stats
- **JSON support** — Native JSON type, no need for string serialization
- **Modern SQL** — Window functions, CTEs work great
- **Embedded** — Same deployment model as SQLite (single file, no external service)
- **Rust support** — `duckdb-rs` provides async-compatible API

**Why `bundled`:** Bundles the DuckDB library directly into the binary, avoiding external dependency. Increases compile time but eliminates deployment issues.

---

## 2. Application State

### File: `backend/src/state.rs` (NEW)

```rust
use std::sync::Arc;
use tokio::sync::broadcast;
use duckdb::Connection;
use tokio::sync::Mutex;

/// Events broadcast to WebSocket clients
#[derive(Debug, Clone, serde::Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum WsEvent {
    /// New activity feed item
    ActivityItem {
        id: String,
        source: String,
        event_type: String,
        title: String,
        content: String,
        metadata: serde_json::Value,
        timestamp: String,
    },

    /// New approval request
    NewApproval {
        id: String,
        approval_type: String,
        source: String,
        title: String,
        summary: String,
        timestamp: String,
    },

    /// Approval status changed
    ApprovalUpdated {
        id: String,
        status: String,
        updated_by: String,
    },

    /// Agent session event (for active sessions)
    SessionEvent {
        session_id: String,
        event: serde_json::Value,
    },

    /// Workflow state change
    WorkflowUpdate {
        workflow_id: String,
        status: String,
        details: serde_json::Value,
    },

    /// Connection established (sent on connect)
    Connected {
        pending_approvals: u32,
        active_sessions: u32,
    },

    /// Heartbeat (every 30s)
    Ping {
        timestamp: String,
    },
}

/// Shared application state
pub struct AppState {
    /// Broadcast channel for WebSocket events
    pub ws_tx: broadcast::Sender<WsEvent>,

    /// DuckDB database connection (wrapped in Mutex for thread safety)
    pub db: Mutex<Connection>,

    /// Redis connection for streams
    pub redis_url: String,
}

impl AppState {
    pub async fn new() -> anyhow::Result<Arc<Self>> {
        // Initialize broadcast channel (buffer 1000 events)
        let (ws_tx, _) = broadcast::channel(1000);

        // Initialize DuckDB
        let db_path = std::env::var("DB_PATH")
            .unwrap_or_else(|_| "/data/kubani-ui.duckdb".to_string());
        let db = Connection::open(&db_path)?;

        // Run migrations
        crate::db::run_migrations(&db)?;

        let redis_url = std::env::var("REDIS_URL")
            .unwrap_or_else(|_| "redis://redis.almckay.io:6379".to_string());

        Ok(Arc::new(Self {
            ws_tx,
            db: Mutex::new(db),
            redis_url,
        }))
    }
}
```

### Important Design Decisions

1. **`Mutex<Connection>` for DuckDB:** DuckDB supports concurrent reads but serializes writes. Using a Mutex ensures safe access. For read-heavy workloads, consider multiple read connections in the future. For the expected load (dozens of concurrent requests), a single Mutex is fine.

2. **`broadcast::channel` for WebSocket:** Allows multiple WebSocket clients to receive the same events. Each client gets its own `broadcast::Receiver`. Buffer of 1000 prevents slow clients from blocking the channel.

3. **Redis URL from env:** Follows existing pattern of env-based configuration.

---

## 3. Database Schema

### File: `backend/src/db.rs` (NEW)

```rust
use duckdb::{Connection, Result};

/// Run all database migrations
pub fn run_migrations(db: &Connection) -> Result<()> {
    // DuckDB supports standard SQL with some enhanced features
    // Using JSON type natively instead of TEXT for metadata
    db.execute_batch("
        -- Activity feed events
        CREATE TABLE IF NOT EXISTS activity_events (
            id VARCHAR PRIMARY KEY,
            source VARCHAR NOT NULL,          -- e.g., 'news-digest', 'k8s-monitor', 'system'
            event_type VARCHAR NOT NULL,      -- e.g., 'syndicate_output', 'agent_activity', 'alert'
            title VARCHAR NOT NULL,
            content VARCHAR NOT NULL DEFAULT '',  -- Rich markdown content
            metadata JSON NOT NULL DEFAULT '{}',  -- Native JSON type
            severity VARCHAR NOT NULL DEFAULT 'info',  -- 'info', 'warning', 'error', 'success'
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            read BOOLEAN NOT NULL DEFAULT false
        );

        CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_activity_source ON activity_events(source);
        CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_activity_read ON activity_events(read);

        -- Approval items
        CREATE TABLE IF NOT EXISTS approvals (
            id VARCHAR PRIMARY KEY,
            approval_type VARCHAR NOT NULL,     -- 'skill_proposal', 'agent_proposal', 'action_request'
            source VARCHAR NOT NULL,            -- e.g., 'learning-system/skill-synthesizer'
            title VARCHAR NOT NULL,
            summary VARCHAR NOT NULL,
            spec VARCHAR NOT NULL DEFAULT '',   -- Full specification (markdown)
            metadata JSON NOT NULL DEFAULT '{}',  -- Native JSON (confidence, triggers, category, etc.)
            status VARCHAR NOT NULL DEFAULT 'pending',  -- 'pending', 'approved', 'rejected', 'modified'
            feedback VARCHAR,                   -- Optional feedback on reject/modify
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
        CREATE INDEX IF NOT EXISTS idx_approvals_created ON approvals(created_at DESC);

        -- Agent sessions
        CREATE TABLE IF NOT EXISTS sessions (
            id VARCHAR PRIMARY KEY,
            title VARCHAR,                      -- Auto-generated or user-set title
            agent_id VARCHAR,                   -- Routed agent/syndicate ID
            syndicate_id VARCHAR,               -- If routed to a syndicate
            status VARCHAR NOT NULL DEFAULT 'active',  -- 'active', 'completed', 'failed'
            messages JSON NOT NULL DEFAULT '[]',  -- Native JSON array of messages
            metadata JSON NOT NULL DEFAULT '{}',  -- Native JSON (model, tools used, etc.)
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
        CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);

        -- WebSocket subscription tracking (for reconnection state)
        -- This is optional — can be done in-memory only
    ")?;

    Ok(())
}

/// Activity event queries
pub mod activity {
    use duckdb::{Connection, params, Result};
    use serde_json::Value;

    pub struct ActivityEvent {
        pub id: String,
        pub source: String,
        pub event_type: String,
        pub title: String,
        pub content: String,
        pub metadata: Value,
        pub severity: String,
        pub created_at: String,
        pub read: bool,
    }

    /// Insert a new activity event
    pub fn insert(db: &Connection, event: &ActivityEvent) -> Result<()> {
        db.execute(
            "INSERT INTO activity_events (id, source, event_type, title, content, metadata, severity, created_at)
             VALUES ($1, $2, $3, $4, $5, $6::JSON, $7, $8::TIMESTAMPTZ)",
            params![
                event.id,
                event.source,
                event.event_type,
                event.title,
                event.content,
                event.metadata.to_string(),
                event.severity,
                event.created_at,
            ],
        )?;
        Ok(())
    }

    /// List activity events with filtering and pagination
    pub fn list(
        db: &Connection,
        source_filter: Option<&str>,
        event_type_filter: Option<&str>,
        limit: u32,
        offset: u32,
    ) -> Result<Vec<ActivityEvent>> {
        // DuckDB supports prepared statements with named/positional params
        let mut sql = String::from(
            "SELECT id, source, event_type, title, content, metadata::VARCHAR, severity, created_at::VARCHAR, read
             FROM activity_events WHERE 1=1"
        );

        if source_filter.is_some() {
            sql.push_str(" AND source = $1");
        }
        if event_type_filter.is_some() {
            sql.push_str(" AND event_type = $2");
        }

        sql.push_str(" ORDER BY created_at DESC LIMIT $3 OFFSET $4");

        let mut stmt = db.prepare(&sql)?;
        let rows = stmt.query_map(
            params![
                source_filter.unwrap_or(""),
                event_type_filter.unwrap_or(""),
                limit,
                offset
            ],
            |row| {
                let metadata_str: String = row.get(5)?;
                Ok(ActivityEvent {
                    id: row.get(0)?,
                    source: row.get(1)?,
                    event_type: row.get(2)?,
                    title: row.get(3)?,
                    content: row.get(4)?,
                    metadata: serde_json::from_str(&metadata_str).unwrap_or_default(),
                    severity: row.get(6)?,
                    created_at: row.get(7)?,
                    read: row.get(8)?,
                })
            }
        )?;

        rows.collect()
    }

    /// Count unread events
    pub fn unread_count(db: &Connection) -> Result<u32> {
        db.query_row(
            "SELECT COUNT(*)::INTEGER FROM activity_events WHERE read = false",
            [],
            |row| row.get(0),
        )
    }

    /// Mark events as read
    pub fn mark_read(db: &Connection, ids: &[String]) -> Result<()> {
        // DuckDB supports UPDATE with IN clause
        let placeholders: String = ids.iter()
            .map(|id| format!("'{}'", id.replace("'", "''")))
            .collect::<Vec<_>>()
            .join(",");
        let sql = format!(
            "UPDATE activity_events SET read = true WHERE id IN ({})",
            placeholders
        );
        db.execute(&sql, [])?;
        Ok(())
    }
}

/// Approval queries
pub mod approvals {
    use duckdb::{Connection, params, Result};
    use serde_json::Value;

    pub struct Approval {
        pub id: String,
        pub approval_type: String,
        pub source: String,
        pub title: String,
        pub summary: String,
        pub spec: String,
        pub metadata: Value,
        pub status: String,
        pub feedback: Option<String>,
        pub created_at: String,
        pub updated_at: String,
    }

    pub fn insert(db: &Connection, approval: &Approval) -> Result<()> {
        db.execute(
            "INSERT INTO approvals (id, approval_type, source, title, summary, spec, metadata, status, created_at)
             VALUES ($1, $2, $3, $4, $5, $6, $7::JSON, $8, $9::TIMESTAMPTZ)",
            params![
                approval.id,
                approval.approval_type,
                approval.source,
                approval.title,
                approval.summary,
                approval.spec,
                approval.metadata.to_string(),
                approval.status,
                approval.created_at,
            ],
        )?;
        Ok(())
    }

    pub fn update_status(
        db: &Connection,
        id: &str,
        status: &str,
        feedback: Option<&str>,
    ) -> Result<()> {
        db.execute(
            "UPDATE approvals SET status = $1, feedback = $2, updated_at = now() WHERE id = $3",
            params![status, feedback.unwrap_or(""), id],
        )?;
        Ok(())
    }

    pub fn list_by_status(db: &Connection, status: &str, limit: u32) -> Result<Vec<Approval>> {
        let mut stmt = db.prepare(
            "SELECT id, approval_type, source, title, summary, spec, metadata::VARCHAR, status, feedback, created_at::VARCHAR, updated_at::VARCHAR
             FROM approvals WHERE status = $1 ORDER BY created_at DESC LIMIT $2"
        )?;

        let rows = stmt.query_map(params![status, limit], |row| {
            let metadata_str: String = row.get(6)?;
            Ok(Approval {
                id: row.get(0)?,
                approval_type: row.get(1)?,
                source: row.get(2)?,
                title: row.get(3)?,
                summary: row.get(4)?,
                spec: row.get(5)?,
                metadata: serde_json::from_str(&metadata_str).unwrap_or_default(),
                status: row.get(7)?,
                feedback: row.get(8)?,
                created_at: row.get(9)?,
                updated_at: row.get(10)?,
            })
        })?;

        rows.collect()
    }

    pub fn pending_count(db: &Connection) -> Result<u32> {
        db.query_row(
            "SELECT COUNT(*)::INTEGER FROM approvals WHERE status = 'pending'",
            [],
            |row| row.get(0),
        )
    }

    pub fn get_by_id(db: &Connection, id: &str) -> Result<Option<Approval>> {
        let mut stmt = db.prepare(
            "SELECT id, approval_type, source, title, summary, spec, metadata::VARCHAR, status, feedback, created_at::VARCHAR, updated_at::VARCHAR
             FROM approvals WHERE id = $1"
        )?;

        let mut rows = stmt.query_map(params![id], |row| {
            let metadata_str: String = row.get(6)?;
            Ok(Approval {
                id: row.get(0)?,
                approval_type: row.get(1)?,
                source: row.get(2)?,
                title: row.get(3)?,
                summary: row.get(4)?,
                spec: row.get(5)?,
                metadata: serde_json::from_str(&metadata_str).unwrap_or_default(),
                status: row.get(7)?,
                feedback: row.get(8)?,
                created_at: row.get(9)?,
                updated_at: row.get(10)?,
            })
        })?;

        Ok(rows.next().transpose()?)
    }
}

/// Session queries
pub mod sessions {
    use duckdb::{Connection, params, Result};
    use serde_json::Value;

    pub struct Session {
        pub id: String,
        pub title: Option<String>,
        pub agent_id: Option<String>,
        pub syndicate_id: Option<String>,
        pub status: String,
        pub messages: Value,
        pub metadata: Value,
        pub created_at: String,
        pub updated_at: String,
    }

    pub fn create(db: &Connection, session: &Session) -> Result<()> {
        db.execute(
            "INSERT INTO sessions (id, title, agent_id, syndicate_id, status, messages, metadata)
             VALUES ($1, $2, $3, $4, $5, $6::JSON, $7::JSON)",
            params![
                session.id,
                session.title.as_deref().unwrap_or(""),
                session.agent_id.as_deref().unwrap_or(""),
                session.syndicate_id.as_deref().unwrap_or(""),
                session.status,
                session.messages.to_string(),
                session.metadata.to_string(),
            ],
        )?;
        Ok(())
    }

    pub fn update_messages(db: &Connection, id: &str, messages: &Value) -> Result<()> {
        db.execute(
            "UPDATE sessions SET messages = $1::JSON, updated_at = now() WHERE id = $2",
            params![messages.to_string(), id],
        )?;
        Ok(())
    }

    pub fn update_status(db: &Connection, id: &str, status: &str) -> Result<()> {
        db.execute(
            "UPDATE sessions SET status = $1, updated_at = now() WHERE id = $2",
            params![status, id],
        )?;
        Ok(())
    }

    pub fn list_recent(db: &Connection, limit: u32) -> Result<Vec<Session>> {
        let mut stmt = db.prepare(
            "SELECT id, title, agent_id, syndicate_id, status, messages::VARCHAR, metadata::VARCHAR, created_at::VARCHAR, updated_at::VARCHAR
             FROM sessions ORDER BY updated_at DESC LIMIT $1"
        )?;

        let rows = stmt.query_map(params![limit], |row| {
            let messages_str: String = row.get(5)?;
            let metadata_str: String = row.get(6)?;
            Ok(Session {
                id: row.get(0)?,
                title: row.get(1)?,
                agent_id: row.get(2)?,
                syndicate_id: row.get(3)?,
                status: row.get(4)?,
                messages: serde_json::from_str(&messages_str).unwrap_or_default(),
                metadata: serde_json::from_str(&metadata_str).unwrap_or_default(),
                created_at: row.get(7)?,
                updated_at: row.get(8)?,
            })
        })?;

        rows.collect()
    }

    pub fn get_by_id(db: &Connection, id: &str) -> Result<Option<Session>> {
        let mut stmt = db.prepare(
            "SELECT id, title, agent_id, syndicate_id, status, messages::VARCHAR, metadata::VARCHAR, created_at::VARCHAR, updated_at::VARCHAR
             FROM sessions WHERE id = $1"
        )?;

        let mut rows = stmt.query_map(params![id], |row| {
            let messages_str: String = row.get(5)?;
            let metadata_str: String = row.get(6)?;
            Ok(Session {
                id: row.get(0)?,
                title: row.get(1)?,
                agent_id: row.get(2)?,
                syndicate_id: row.get(3)?,
                status: row.get(4)?,
                messages: serde_json::from_str(&messages_str).unwrap_or_default(),
                metadata: serde_json::from_str(&metadata_str).unwrap_or_default(),
                created_at: row.get(7)?,
                updated_at: row.get(8)?,
            })
        })?;

        Ok(rows.next().transpose()?)
    }
}
```

---

## 4. WebSocket Handler

### File: `backend/src/api/ws.rs` (NEW)

```rust
use axum::{
    extract::{State, ws::{Message, WebSocket, WebSocketUpgrade}},
    response::IntoResponse,
};
use std::sync::Arc;
use crate::state::{AppState, WsEvent};
use futures::{SinkExt, StreamExt};
use tokio::sync::broadcast;

/// WebSocket upgrade handler
pub async fn ws_handler(
    ws: WebSocketUpgrade,
    State(state): State<Arc<AppState>>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_socket(socket, state))
}

/// Handle a single WebSocket connection
async fn handle_socket(socket: WebSocket, state: Arc<AppState>) {
    let (mut sender, mut receiver) = socket.split();

    // Subscribe to broadcast channel
    let mut rx = state.ws_tx.subscribe();

    // Send initial connection event with counts
    let pending_approvals = {
        let db = state.db.lock().await;
        crate::db::approvals::pending_count(&db).unwrap_or(0)
    };

    let connected = WsEvent::Connected {
        pending_approvals,
        active_sessions: 0, // TODO: count from db
    };

    if let Ok(json) = serde_json::to_string(&connected) {
        let _ = sender.send(Message::Text(json)).await;
    }

    // Spawn task to forward broadcast events to this client
    let mut send_task = tokio::spawn(async move {
        loop {
            tokio::select! {
                // Forward broadcast events
                result = rx.recv() => {
                    match result {
                        Ok(event) => {
                            if let Ok(json) = serde_json::to_string(&event) {
                                if sender.send(Message::Text(json)).await.is_err() {
                                    break; // Client disconnected
                                }
                            }
                        }
                        Err(broadcast::error::RecvError::Lagged(n)) => {
                            tracing::warn!("WebSocket client lagged, missed {} events", n);
                            // Continue — client will get next events
                        }
                        Err(broadcast::error::RecvError::Closed) => {
                            break; // Channel closed
                        }
                    }
                }
            }
        }
    });

    // Receive task: handle incoming messages from client
    let mut recv_task = tokio::spawn(async move {
        while let Some(Ok(msg)) = receiver.next().await {
            match msg {
                Message::Text(text) => {
                    // Handle client messages (subscriptions, pings, etc.)
                    tracing::debug!("WS received: {}", text);
                    // Future: handle subscription filter changes
                }
                Message::Ping(data) => {
                    // Pong is handled automatically by axum
                    tracing::trace!("WS ping received, {} bytes", data.len());
                }
                Message::Close(_) => {
                    break;
                }
                _ => {}
            }
        }
    });

    // Wait for either task to finish (client disconnect or channel close)
    tokio::select! {
        _ = &mut send_task => {
            recv_task.abort();
        }
        _ = &mut recv_task => {
            send_task.abort();
        }
    }

    tracing::debug!("WebSocket connection closed");
}
```

---

## 5. Redis Streams Consumer

### File: `backend/src/events.rs` (NEW)

```rust
use std::sync::Arc;
use crate::state::{AppState, WsEvent};
use crate::db;
use redis::AsyncCommands;

/// Redis stream names
const ACTIVITY_STREAM: &str = "kubani:activity";
const APPROVALS_STREAM: &str = "kubani:approvals";
const CONSUMER_GROUP: &str = "ui-backend";
const CONSUMER_NAME: &str = "ui-backend-1";

/// Start consuming Redis Streams events
/// This runs as a background task for the lifetime of the application
pub async fn start_event_consumer(state: Arc<AppState>) {
    // Try to connect to Redis. If it fails, log and retry.
    loop {
        match run_consumer(state.clone()).await {
            Ok(()) => {
                tracing::info!("Event consumer exited cleanly");
                break;
            }
            Err(e) => {
                tracing::error!("Event consumer error: {}. Reconnecting in 5s...", e);
                tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
            }
        }
    }
}

async fn run_consumer(state: Arc<AppState>) -> anyhow::Result<()> {
    let client = redis::Client::open(state.redis_url.as_str())?;
    let mut conn = client.get_multiplexed_async_connection().await?;

    // Create consumer groups (ignore error if already exists)
    for stream in [ACTIVITY_STREAM, APPROVALS_STREAM] {
        let result: redis::RedisResult<()> = redis::cmd("XGROUP")
            .arg("CREATE")
            .arg(stream)
            .arg(CONSUMER_GROUP)
            .arg("$")  // Start from new messages
            .arg("MKSTREAM")
            .query_async(&mut conn)
            .await;

        match result {
            Ok(()) => tracing::info!("Created consumer group for {}", stream),
            Err(e) if e.to_string().contains("BUSYGROUP") => {
                tracing::debug!("Consumer group already exists for {}", stream);
            }
            Err(e) => {
                tracing::warn!("Failed to create consumer group for {}: {}", stream, e);
            }
        }
    }

    tracing::info!("Event consumer started, listening on {} and {}", ACTIVITY_STREAM, APPROVALS_STREAM);

    // Read loop
    loop {
        // XREADGROUP with 5-second block timeout
        let results: redis::RedisResult<redis::streams::StreamReadReply> = redis::cmd("XREADGROUP")
            .arg("GROUP")
            .arg(CONSUMER_GROUP)
            .arg(CONSUMER_NAME)
            .arg("COUNT")
            .arg(10)
            .arg("BLOCK")
            .arg(5000)  // 5 second block timeout
            .arg("STREAMS")
            .arg(ACTIVITY_STREAM)
            .arg(APPROVALS_STREAM)
            .arg(">")  // Only new messages
            .arg(">")
            .query_async(&mut conn)
            .await;

        match results {
            Ok(reply) => {
                for stream_key in reply.keys {
                    for entry in stream_key.ids {
                        let stream_name = &stream_key.key;
                        let entry_id = &entry.id;

                        // Extract fields from the stream entry
                        let fields: std::collections::HashMap<String, String> = entry.map
                            .iter()
                            .filter_map(|(k, v)| {
                                if let redis::Value::BulkString(bytes) = v {
                                    Some((k.clone(), String::from_utf8_lossy(bytes).to_string()))
                                } else {
                                    None
                                }
                            })
                            .collect();

                        // Process based on stream
                        if stream_name == ACTIVITY_STREAM {
                            process_activity_event(&state, &fields).await;
                        } else if stream_name == APPROVALS_STREAM {
                            process_approval_event(&state, &fields).await;
                        }

                        // Acknowledge the message
                        let _: redis::RedisResult<()> = redis::cmd("XACK")
                            .arg(stream_name)
                            .arg(CONSUMER_GROUP)
                            .arg(entry_id)
                            .query_async(&mut conn)
                            .await;
                    }
                }
            }
            Err(e) => {
                // Timeout is expected (BLOCK returns nil), other errors should be logged
                if !e.to_string().contains("nil") {
                    tracing::warn!("XREADGROUP error: {}", e);
                }
            }
        }
    }
}

/// Process an activity stream event
async fn process_activity_event(
    state: &Arc<AppState>,
    fields: &std::collections::HashMap<String, String>,
) {
    let id = uuid::Uuid::new_v4().to_string();
    let source = fields.get("source").cloned().unwrap_or_default();
    let event_type = fields.get("type").cloned().unwrap_or_else(|| "unknown".to_string());
    let title = fields.get("title").cloned().unwrap_or_default();
    let content = fields.get("content").cloned().unwrap_or_default();
    let metadata_str = fields.get("metadata").cloned().unwrap_or_else(|| "{}".to_string());
    let severity = fields.get("severity").cloned().unwrap_or_else(|| "info".to_string());
    let timestamp = chrono::Utc::now().to_rfc3339();

    let metadata: serde_json::Value = serde_json::from_str(&metadata_str).unwrap_or_default();

    // Store in DuckDB
    {
        let db = state.db.lock().await;
        let event = db::activity::ActivityEvent {
            id: id.clone(),
            source: source.clone(),
            event_type: event_type.clone(),
            title: title.clone(),
            content: content.clone(),
            metadata: metadata.clone(),
            severity: severity.clone(),
            created_at: timestamp.clone(),
            read: false,
        };

        if let Err(e) = db::activity::insert(&db, &event) {
            tracing::error!("Failed to store activity event: {}", e);
        }
    }

    // Broadcast to WebSocket clients
    let ws_event = WsEvent::ActivityItem {
        id,
        source,
        event_type,
        title,
        content,
        metadata,
        timestamp,
    };

    let _ = state.ws_tx.send(ws_event);
}

/// Process an approval stream event
async fn process_approval_event(
    state: &Arc<AppState>,
    fields: &std::collections::HashMap<String, String>,
) {
    let id = uuid::Uuid::new_v4().to_string();
    let approval_type = fields.get("type").cloned().unwrap_or_default();
    let source = fields.get("source").cloned().unwrap_or_default();
    let title = fields.get("title").cloned().unwrap_or_default();
    let summary = fields.get("summary").cloned().unwrap_or_default();
    let spec = fields.get("spec").cloned().unwrap_or_default();
    let metadata_str = fields.get("metadata").cloned().unwrap_or_else(|| "{}".to_string());
    let timestamp = chrono::Utc::now().to_rfc3339();

    let metadata: serde_json::Value = serde_json::from_str(&metadata_str).unwrap_or_default();

    // Store in DuckDB
    {
        let db = state.db.lock().await;
        let approval = db::approvals::Approval {
            id: id.clone(),
            approval_type: approval_type.clone(),
            source: source.clone(),
            title: title.clone(),
            summary: summary.clone(),
            spec,
            metadata: metadata.clone(),
            status: "pending".to_string(),
            feedback: None,
            created_at: timestamp.clone(),
            updated_at: timestamp.clone(),
        };

        if let Err(e) = db::approvals::insert(&db, &approval) {
            tracing::error!("Failed to store approval: {}", e);
        }
    }

    // Broadcast to WebSocket clients
    let ws_event = WsEvent::NewApproval {
        id,
        approval_type,
        source,
        title,
        summary,
        timestamp,
    };

    let _ = state.ws_tx.send(ws_event);
}
```

---

## 6. Updated main.rs

### File: `backend/src/main.rs` (MODIFIED)

Changes to integrate the new state, WebSocket, and event consumer:

```rust
mod api;
mod cache;
mod db;       // NEW
mod events;   // NEW
mod mcp;
mod models;
mod parsers;
mod state;    // NEW

use anyhow::Result;
use axum::{
    routing::{get, post},
    Router,
};
use std::net::SocketAddr;
use std::sync::Arc;
use tower_http::cors::{Any, CorsLayer};
use tower_http::services::{ServeDir, ServeFile};
use tower_http::trace::TraceLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "kubani_ui_backend=info,tower_http=info".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    // Initialize cache
    cache::init_cache();

    // Initialize application state (SQLite, broadcast channel)
    let app_state = state::AppState::new().await?;

    tracing::info!("Starting Kubani UI Backend");

    // Start Redis Streams event consumer in background
    let consumer_state = app_state.clone();
    tokio::spawn(async move {
        events::start_event_consumer(consumer_state).await;
    });

    // Start heartbeat task (sends Ping every 30 seconds)
    let heartbeat_state = app_state.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(tokio::time::Duration::from_secs(30)).await;
            let _ = heartbeat_state.ws_tx.send(state::WsEvent::Ping {
                timestamp: chrono::Utc::now().to_rfc3339(),
            });
        }
    });

    // Static file serving for SPA
    let static_dir = std::env::var("STATIC_DIR").unwrap_or_else(|_| "/app/public".to_string());
    let index_file = format!("{}/index.html", static_dir);

    // Build application with routes
    let app = Router::new()
        // Health check endpoints
        .route("/health", get(health_check))
        .route("/api/health", get(api_health_check))

        // WebSocket endpoint (NEW)
        .route("/api/ws", get(api::ws::ws_handler))

        // Activity feed endpoints (NEW)
        .route("/api/activity", get(api::activity::list_events))
        .route("/api/activity/unread-count", get(api::activity::unread_count))
        .route("/api/activity/mark-read", post(api::activity::mark_read))

        // Approval endpoints (NEW)
        .route("/api/approvals", get(api::approvals::list_approvals))
        .route("/api/approvals/pending-count", get(api::approvals::pending_count))
        .route("/api/approvals/:id", get(api::approvals::get_approval))
        .route("/api/approvals/:id/approve", post(api::approvals::approve))
        .route("/api/approvals/:id/reject", post(api::approvals::reject))
        .route("/api/approvals/:id/modify", post(api::approvals::request_modify))

        // Session endpoints (NEW)
        .route("/api/sessions", get(api::sessions::list_sessions))
        .route("/api/sessions", post(api::sessions::create_session))
        .route("/api/sessions/:id", get(api::sessions::get_session))
        .route("/api/sessions/:id/message", post(api::sessions::send_message))

        // Existing monitoring endpoints
        .route("/api/monitoring/nodes", get(api::monitoring::get_nodes))
        .route("/api/monitoring/namespaces", get(api::monitoring::get_namespaces))
        .route("/api/monitoring/events", get(api::monitoring::get_events))
        .route("/api/monitoring/services", get(api::monitoring::get_services))

        // Existing registry endpoints
        .route("/api/agents", get(api::registry::get_agents))
        .route("/api/registry/agents", get(api::registry::get_agents))
        .route("/api/registry/mcp-servers", get(api::registry::get_mcp_servers))
        .route("/api/registry/models", get(api::registry::get_models))
        .route("/api/registry/skills", get(api::registry::get_skills))
        .route("/api/tools", get(api::registry::get_tools))

        // Existing workflows endpoint
        .route("/api/workflows", get(api::workflows::get_workflows))

        // Existing chat endpoint (kept for backward compatibility)
        .route("/api/chat", post(api::chat::chat_handler))

        // Serve static files with SPA fallback
        .fallback_service(
            ServeDir::new(&static_dir)
                .not_found_service(ServeFile::new(&index_file)),
        )
        // Add shared state
        .with_state(app_state)  // NEW
        // Add CORS middleware
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        )
        // Add tracing middleware
        .layer(TraceLayer::new_for_http());

    // Get port from environment
    let port: u16 = std::env::var("PORT")
        .unwrap_or_else(|_| "3000".to_string())
        .parse()
        .unwrap_or(3000);

    let addr = SocketAddr::from(([0, 0, 0, 0], port));
    tracing::info!("Listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}

async fn health_check() -> &'static str {
    "OK"
}

async fn api_health_check() -> axum::Json<serde_json::Value> {
    axum::Json(serde_json::json!({
        "status": "ok",
        "timestamp": chrono::Utc::now().to_rfc3339()
    }))
}
```

**Critical Note:** Adding `.with_state(app_state)` means all handlers that need state must use `State<Arc<AppState>>`. Existing handlers that don't need state continue to work -- Axum allows mixing stateful and stateless handlers.

---

## 7. New API Handler Stubs

### File: `backend/src/api/activity.rs` (NEW)

```rust
use axum::{extract::State, extract::Query, Json};
use std::sync::Arc;
use crate::state::AppState;
use serde::Deserialize;

#[derive(Deserialize)]
pub struct ListParams {
    source: Option<String>,
    event_type: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
}

pub async fn list_events(
    State(state): State<Arc<AppState>>,
    Query(params): Query<ListParams>,
) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    let events = crate::db::activity::list(
        &db,
        params.source.as_deref(),
        params.event_type.as_deref(),
        params.limit.unwrap_or(50),
        params.offset.unwrap_or(0),
    );

    match events {
        Ok(events) => {
            let items: Vec<serde_json::Value> = events.iter().map(|e| {
                serde_json::json!({
                    "id": e.id,
                    "source": e.source,
                    "event_type": e.event_type,
                    "title": e.title,
                    "content": e.content,
                    "metadata": e.metadata,
                    "severity": e.severity,
                    "created_at": e.created_at,
                    "read": e.read,
                })
            }).collect();
            Json(serde_json::json!(items))
        }
        Err(e) => {
            tracing::error!("Failed to list activity events: {}", e);
            Json(serde_json::json!([]))
        }
    }
}

pub async fn unread_count(
    State(state): State<Arc<AppState>>,
) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    let count = crate::db::activity::unread_count(&db).unwrap_or(0);
    Json(serde_json::json!({ "count": count }))
}

#[derive(Deserialize)]
pub struct MarkReadRequest {
    ids: Vec<String>,
}

pub async fn mark_read(
    State(state): State<Arc<AppState>>,
    Json(request): Json<MarkReadRequest>,
) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    match crate::db::activity::mark_read(&db, &request.ids) {
        Ok(()) => Json(serde_json::json!({ "status": "ok" })),
        Err(e) => Json(serde_json::json!({ "status": "error", "message": e.to_string() })),
    }
}
```

### File: `backend/src/api/approvals.rs` (NEW)

```rust
use axum::{extract::{State, Path}, Json};
use std::sync::Arc;
use crate::state::{AppState, WsEvent};
use serde::Deserialize;

pub async fn list_approvals(
    State(state): State<Arc<AppState>>,
    axum::extract::Query(params): axum::extract::Query<ListParams>,
) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    let status = params.status.as_deref().unwrap_or("pending");
    let limit = params.limit.unwrap_or(50);

    match crate::db::approvals::list_by_status(&db, status, limit) {
        Ok(approvals) => {
            let items: Vec<serde_json::Value> = approvals.iter().map(|a| {
                serde_json::json!({
                    "id": a.id,
                    "approval_type": a.approval_type,
                    "source": a.source,
                    "title": a.title,
                    "summary": a.summary,
                    "spec": a.spec,
                    "metadata": a.metadata,
                    "status": a.status,
                    "feedback": a.feedback,
                    "created_at": a.created_at,
                    "updated_at": a.updated_at,
                })
            }).collect();
            Json(serde_json::json!(items))
        }
        Err(e) => {
            tracing::error!("Failed to list approvals: {}", e);
            Json(serde_json::json!([]))
        }
    }
}

#[derive(Deserialize)]
pub struct ListParams {
    status: Option<String>,
    limit: Option<u32>,
}

pub async fn pending_count(
    State(state): State<Arc<AppState>>,
) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    let count = crate::db::approvals::pending_count(&db).unwrap_or(0);
    Json(serde_json::json!({ "count": count }))
}

pub async fn get_approval(
    State(state): State<Arc<AppState>>,
    Path(id): Path<String>,
) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    match crate::db::approvals::get_by_id(&db, &id) {
        Ok(Some(a)) => Json(serde_json::json!({
            "id": a.id,
            "approval_type": a.approval_type,
            "source": a.source,
            "title": a.title,
            "summary": a.summary,
            "spec": a.spec,
            "metadata": a.metadata,
            "status": a.status,
            "feedback": a.feedback,
            "created_at": a.created_at,
            "updated_at": a.updated_at,
        })),
        Ok(None) => Json(serde_json::json!({ "error": "not found" })),
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}

pub async fn approve(
    State(state): State<Arc<AppState>>,
    Path(id): Path<String>,
) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    match crate::db::approvals::update_status(&db, &id, "approved", None) {
        Ok(()) => {
            // Broadcast update
            let _ = state.ws_tx.send(WsEvent::ApprovalUpdated {
                id: id.clone(),
                status: "approved".to_string(),
                updated_by: "user".to_string(),
            });
            // TODO: Publish approval to Redis for learning system to pick up
            Json(serde_json::json!({ "status": "approved" }))
        }
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}

#[derive(Deserialize)]
pub struct RejectRequest {
    reason: Option<String>,
}

pub async fn reject(
    State(state): State<Arc<AppState>>,
    Path(id): Path<String>,
    Json(request): Json<RejectRequest>,
) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    match crate::db::approvals::update_status(&db, &id, "rejected", request.reason.as_deref()) {
        Ok(()) => {
            let _ = state.ws_tx.send(WsEvent::ApprovalUpdated {
                id: id.clone(),
                status: "rejected".to_string(),
                updated_by: "user".to_string(),
            });
            Json(serde_json::json!({ "status": "rejected" }))
        }
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}

#[derive(Deserialize)]
pub struct ModifyRequest {
    feedback: String,
}

pub async fn request_modify(
    State(state): State<Arc<AppState>>,
    Path(id): Path<String>,
    Json(request): Json<ModifyRequest>,
) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    match crate::db::approvals::update_status(&db, &id, "modified", Some(&request.feedback)) {
        Ok(()) => {
            let _ = state.ws_tx.send(WsEvent::ApprovalUpdated {
                id: id.clone(),
                status: "modified".to_string(),
                updated_by: "user".to_string(),
            });
            Json(serde_json::json!({ "status": "modified" }))
        }
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}
```

### File: `backend/src/api/sessions.rs` (NEW)

```rust
use axum::{extract::{State, Path}, Json};
use std::sync::Arc;
use crate::state::AppState;
use serde::Deserialize;

pub async fn list_sessions(
    State(state): State<Arc<AppState>>,
) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    match crate::db::sessions::list_recent(&db, 50) {
        Ok(sessions) => {
            let items: Vec<serde_json::Value> = sessions.iter().map(|s| {
                serde_json::json!({
                    "id": s.id,
                    "title": s.title,
                    "agent_id": s.agent_id,
                    "syndicate_id": s.syndicate_id,
                    "status": s.status,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                    // Don't include full messages in list — too large
                })
            }).collect();
            Json(serde_json::json!(items))
        }
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}

#[derive(Deserialize)]
pub struct CreateSessionRequest {
    agent_id: Option<String>,
    title: Option<String>,
}

pub async fn create_session(
    State(state): State<Arc<AppState>>,
    Json(request): Json<CreateSessionRequest>,
) -> Json<serde_json::Value> {
    let id = uuid::Uuid::new_v4().to_string();
    let session = crate::db::sessions::Session {
        id: id.clone(),
        title: request.title,
        agent_id: request.agent_id,
        syndicate_id: None,
        status: "active".to_string(),
        messages: serde_json::json!([]),
        metadata: serde_json::json!({}),
        created_at: chrono::Utc::now().to_rfc3339(),
        updated_at: chrono::Utc::now().to_rfc3339(),
    };

    let db = state.db.lock().await;
    match crate::db::sessions::create(&db, &session) {
        Ok(()) => Json(serde_json::json!({ "id": id, "status": "created" })),
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}

pub async fn get_session(
    State(state): State<Arc<AppState>>,
    Path(id): Path<String>,
) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    match crate::db::sessions::get_by_id(&db, &id) {
        Ok(Some(s)) => Json(serde_json::json!({
            "id": s.id,
            "title": s.title,
            "agent_id": s.agent_id,
            "syndicate_id": s.syndicate_id,
            "status": s.status,
            "messages": s.messages,
            "metadata": s.metadata,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        })),
        Ok(None) => Json(serde_json::json!({ "error": "not found" })),
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}

#[derive(Deserialize)]
pub struct SendMessageRequest {
    content: String,
}

pub async fn send_message(
    State(state): State<Arc<AppState>>,
    Path(id): Path<String>,
    Json(request): Json<SendMessageRequest>,
) -> Json<serde_json::Value> {
    // This is a simplified version. Phase 3 will add:
    // - Router agent for intent classification
    // - Multi-agent syndicate dispatch
    // - SSE streaming within the session
    // For now, it proxies to the existing chat endpoint logic

    let db = state.db.lock().await;
    let session = match crate::db::sessions::get_by_id(&db, &id) {
        Ok(Some(s)) => s,
        Ok(None) => return Json(serde_json::json!({ "error": "session not found" })),
        Err(e) => return Json(serde_json::json!({ "error": e.to_string() })),
    };
    drop(db); // Release lock before async work

    // TODO: Phase 3 will implement full routing + multi-agent here
    Json(serde_json::json!({
        "status": "ok",
        "message": "Message received. Full agent routing coming in Phase 3."
    }))
}
```

### Update `backend/src/api/mod.rs`

```rust
pub mod activity;    // NEW
pub mod approvals;   // NEW
pub mod chat;
pub mod chat_executor;
pub mod monitoring;
pub mod registry;
pub mod sessions;    // NEW
pub mod workflows;
pub mod ws;          // NEW
```

---

## 8. Environment Variables

New environment variables (add to deployment manifests):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_PATH` | `/data/kubani-ui.duckdb` | DuckDB database file path |
| `REDIS_URL` | `redis://redis.almckay.io:6379` | Redis connection URL |

Existing variables remain unchanged.

---

## 9. Data Volume

The DuckDB database needs a persistent volume in Kubernetes:

```yaml
# Add to deployment manifest
volumes:
  - name: data
    persistentVolumeClaim:
      claimName: kubani-ui-data
---
volumeMounts:
  - name: data
    mountPath: /data
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: kubani-ui-data
  namespace: ai-agents
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 1Gi  # More than enough for activity/sessions/approvals
```

---

## 10. Implementation Checklist

### Step 1: Add Dependencies
- [ ] Add `duckdb` and `redis` to `backend/Cargo.toml`
- [ ] Run `cargo check` to verify dependencies resolve

### Step 2: Create State Module
- [ ] Create `backend/src/state.rs`
- [ ] Define `WsEvent` enum with all event types
- [ ] Define `AppState` struct with broadcast channel, db, redis_url
- [ ] Implement `AppState::new()`

### Step 3: Create Database Module
- [ ] Create `backend/src/db.rs`
- [ ] Implement `run_migrations()` with all three tables (using DuckDB SQL)
- [ ] Implement `activity` module (insert, list, unread_count, mark_read)
- [ ] Implement `approvals` module (insert, update_status, list_by_status, pending_count, get_by_id)
- [ ] Implement `sessions` module (create, update_messages, update_status, list_recent, get_by_id)

### Step 4: Create WebSocket Handler
- [ ] Create `backend/src/api/ws.rs`
- [ ] Implement `ws_handler` for upgrade
- [ ] Implement `handle_socket` with broadcast forwarding
- [ ] Handle client disconnect gracefully

### Step 5: Create Event Consumer
- [ ] Create `backend/src/events.rs`
- [ ] Implement `start_event_consumer` with reconnect loop
- [ ] Implement consumer group creation
- [ ] Implement `process_activity_event`
- [ ] Implement `process_approval_event`
- [ ] Handle XACK for message acknowledgment

### Step 6: Create API Handlers
- [ ] Create `backend/src/api/activity.rs` (list, unread_count, mark_read)
- [ ] Create `backend/src/api/approvals.rs` (list, pending_count, get, approve, reject, modify)
- [ ] Create `backend/src/api/sessions.rs` (list, create, get, send_message stub)

### Step 7: Update main.rs
- [ ] Add new module declarations (db, events, state)
- [ ] Initialize AppState before building router
- [ ] Spawn event consumer background task
- [ ] Spawn heartbeat background task
- [ ] Add WebSocket route
- [ ] Add activity, approvals, sessions routes
- [ ] Add `.with_state(app_state)` to router

### Step 8: Update api/mod.rs
- [ ] Add module declarations for activity, approvals, sessions, ws

### Step 9: Verify
- [ ] `cargo build` succeeds
- [ ] `cargo test` (if tests exist) passes
- [ ] Backend starts without Redis (graceful degradation -- event consumer retries)
- [ ] Health endpoint still works
- [ ] Existing monitoring/registry/chat endpoints still work
- [ ] WebSocket endpoint accepts connections at /api/ws
- [ ] DuckDB database created at DB_PATH on startup

---

## 11. Testing Strategy

### Manual Testing

1. **WebSocket connection:**
   ```bash
   # Using websocat
   websocat ws://localhost:3000/api/ws
   # Should receive Connected event with counts
   ```

2. **Redis event propagation:**
   ```bash
   # Publish test activity event
   redis-cli XADD kubani:activity '*' \
     source "test" \
     type "test_event" \
     title "Test Activity" \
     content "This is a test event" \
     metadata '{"key": "value"}'

   # Should appear in WebSocket connection AND in:
   curl http://localhost:3000/api/activity
   ```

3. **Approval workflow:**
   ```bash
   # Publish test approval
   redis-cli XADD kubani:approvals '*' \
     type "skill_proposal" \
     source "test" \
     title "Test Skill" \
     summary "A test skill proposal" \
     spec "# Test Skill\n\nThis is a test." \
     metadata '{"confidence": 0.85}'

   # Should appear in WebSocket AND:
   curl http://localhost:3000/api/approvals
   curl http://localhost:3000/api/approvals/pending-count

   # Approve it (use ID from list response)
   curl -X POST http://localhost:3000/api/approvals/{id}/approve
   ```

4. **Session creation:**
   ```bash
   curl -X POST http://localhost:3000/api/sessions \
     -H 'Content-Type: application/json' \
     -d '{"title": "Test Session"}'

   curl http://localhost:3000/api/sessions
   ```

---

## Files Summary

| File | Status | Changes |
|------|--------|---------|
| `backend/Cargo.toml` | MODIFIED | Add duckdb, redis dependencies |
| `backend/src/main.rs` | MODIFIED | Add state, routes, background tasks |
| `backend/src/api/mod.rs` | MODIFIED | Add new module declarations |
| `backend/src/state.rs` | NEW | AppState, WsEvent |
| `backend/src/db.rs` | NEW | DuckDB schema, migrations, queries |
| `backend/src/events.rs` | NEW | Redis Streams consumer |
| `backend/src/api/ws.rs` | NEW | WebSocket handler |
| `backend/src/api/activity.rs` | NEW | Activity feed REST endpoints |
| `backend/src/api/approvals.rs` | NEW | Approvals REST endpoints |
| `backend/src/api/sessions.rs` | NEW | Sessions REST endpoints |

**Total: 7 new files, 3 modified files**
