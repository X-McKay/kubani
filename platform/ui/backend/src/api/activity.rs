use axum::{extract::Query, extract::State, Json};
use serde::Deserialize;
use std::sync::Arc;

use crate::state::AppState;

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
            let items: Vec<serde_json::Value> = events
                .iter()
                .map(|e| {
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
                })
                .collect();
            Json(serde_json::json!(items))
        }
        Err(e) => {
            tracing::error!("Failed to list activity events: {}", e);
            Json(serde_json::json!([]))
        }
    }
}

pub async fn unread_count(State(state): State<Arc<AppState>>) -> Json<serde_json::Value> {
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
