use crate::state::{AppState, WsEvent};
use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    response::IntoResponse,
};
use futures::{SinkExt, StreamExt};
use std::sync::Arc;
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
    let (pending_approvals, active_sessions) = {
        let db = state.db.lock().await;
        let pending = crate::db::approvals::pending_count(&db).unwrap_or(0);
        let active = crate::db::sessions::active_count(&db).unwrap_or(0);
        (pending, active)
    };

    let connected = WsEvent::Connected {
        pending_approvals,
        active_sessions,
    };

    if let Ok(json) = serde_json::to_string(&connected) {
        let _ = sender.send(Message::Text(json.into())).await;
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
                                if sender.send(Message::Text(json.into())).await.is_err() {
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
                Message::Ping(_data) => {
                    // Pong is handled automatically by axum
                    tracing::trace!("WS ping received");
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
