use crate::db;
use crate::state::{AppState, WsEvent};
use redis::FromRedisValue;
use std::sync::Arc;

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
            .arg("$") // Start from new messages
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

    tracing::info!(
        "Event consumer started, listening on {} and {}",
        ACTIVITY_STREAM,
        APPROVALS_STREAM
    );

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
            .arg(5000) // 5 second block timeout
            .arg("STREAMS")
            .arg(ACTIVITY_STREAM)
            .arg(APPROVALS_STREAM)
            .arg(">") // Only new messages
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
                        let fields: std::collections::HashMap<String, String> = entry
                            .map
                            .iter()
                            .filter_map(|(k, v)| {
                                // Use FromRedisValue trait to convert
                                String::from_redis_value(v)
                                    .ok()
                                    .map(|s| (k.clone(), s))
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
async fn process_activity_event(state: &Arc<AppState>, fields: &std::collections::HashMap<String, String>) {
    let id = uuid::Uuid::new_v4().to_string();
    let source = fields.get("source").cloned().unwrap_or_default();
    let event_type = fields
        .get("type")
        .cloned()
        .unwrap_or_else(|| "unknown".to_string());
    let title = fields.get("title").cloned().unwrap_or_default();
    let content = fields.get("content").cloned().unwrap_or_default();
    let metadata_str = fields
        .get("metadata")
        .cloned()
        .unwrap_or_else(|| "{}".to_string());
    let severity = fields
        .get("severity")
        .cloned()
        .unwrap_or_else(|| "info".to_string());
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
async fn process_approval_event(state: &Arc<AppState>, fields: &std::collections::HashMap<String, String>) {
    let id = uuid::Uuid::new_v4().to_string();
    let approval_type = fields.get("type").cloned().unwrap_or_default();
    let source = fields.get("source").cloned().unwrap_or_default();
    let title = fields.get("title").cloned().unwrap_or_default();
    let summary = fields.get("summary").cloned().unwrap_or_default();
    let spec = fields.get("spec").cloned().unwrap_or_default();
    let metadata_str = fields
        .get("metadata")
        .cloned()
        .unwrap_or_else(|| "{}".to_string());
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
