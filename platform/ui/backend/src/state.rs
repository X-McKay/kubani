use duckdb::Connection;
use std::sync::Arc;
use tokio::sync::{broadcast, Mutex};

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
    Ping { timestamp: String },
}

/// Shared application state
pub struct AppState {
    /// Broadcast channel for WebSocket events
    pub ws_tx: broadcast::Sender<WsEvent>,

    /// DuckDB database connection (wrapped in Mutex for thread safety)
    pub db: Mutex<Connection>,

    /// Redis connection URL for streams
    pub redis_url: String,
}

impl AppState {
    pub async fn new() -> anyhow::Result<Arc<Self>> {
        // Initialize broadcast channel (buffer 1000 events)
        let (ws_tx, _) = broadcast::channel(1000);

        // Initialize DuckDB
        let db_path =
            std::env::var("DB_PATH").unwrap_or_else(|_| "/data/kubani-ui.duckdb".to_string());

        // Create parent directory if it doesn't exist
        if let Some(parent) = std::path::Path::new(&db_path).parent() {
            if !parent.exists() {
                std::fs::create_dir_all(parent)?;
            }
        }

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
