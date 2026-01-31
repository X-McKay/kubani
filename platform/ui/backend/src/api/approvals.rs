use axum::{
    extract::{Path, State},
    Json,
};
use serde::Deserialize;
use std::sync::Arc;

use crate::state::{AppState, WsEvent};

#[derive(Deserialize)]
pub struct ListParams {
    status: Option<String>,
    limit: Option<u32>,
}

pub async fn list_approvals(
    State(state): State<Arc<AppState>>,
    axum::extract::Query(params): axum::extract::Query<ListParams>,
) -> Json<serde_json::Value> {
    let db = state.db.lock().await;
    let status = params.status.as_deref().unwrap_or("pending");
    let limit = params.limit.unwrap_or(50);

    match crate::db::approvals::list_by_status(&db, status, limit) {
        Ok(approvals) => {
            let items: Vec<serde_json::Value> = approvals
                .iter()
                .map(|a| {
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
                })
                .collect();
            Json(serde_json::json!(items))
        }
        Err(e) => {
            tracing::error!("Failed to list approvals: {}", e);
            Json(serde_json::json!([]))
        }
    }
}

pub async fn pending_count(State(state): State<Arc<AppState>>) -> Json<serde_json::Value> {
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
