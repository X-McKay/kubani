use axum::{
    extract::{Path, State},
    Json,
};
use serde::Deserialize;
use std::sync::Arc;

use crate::state::AppState;

pub async fn list_sessions(State(state): State<Arc<AppState>>) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    match crate::db::sessions::list_recent(&db, 50) {
        Ok(sessions) => {
            let items: Vec<serde_json::Value> = sessions
                .iter()
                .map(|s| {
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
                })
                .collect();
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
    Json(_request): Json<SendMessageRequest>,
) -> Json<serde_json::Value> {
    // This is a simplified version. Phase 3 will add:
    // - Router agent for intent classification
    // - Multi-agent syndicate dispatch
    // - SSE streaming within the session
    // For now, it validates the session exists

    let db = state.db.lock().await;
    match crate::db::sessions::get_by_id(&db, &id) {
        Ok(Some(_s)) => {
            // Session exists, message received
            // TODO: Phase 3 will implement full routing + multi-agent here
            Json(serde_json::json!({
                "status": "ok",
                "message": "Message received. Full agent routing coming in Phase 3."
            }))
        }
        Ok(None) => Json(serde_json::json!({ "error": "session not found" })),
        Err(e) => Json(serde_json::json!({ "error": e.to_string() })),
    }
}
