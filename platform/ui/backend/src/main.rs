mod api;
mod cache;
mod db;
mod events;
mod mcp;
mod models;
mod parsers;
mod state;

use anyhow::Result;
use axum::{
    routing::{get, post},
    Router,
};
use std::net::SocketAddr;
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

    // Initialize application state (DuckDB, broadcast channel)
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

    // Static file serving for SPA (fallback to index.html for client-side routing)
    let static_dir = std::env::var("STATIC_DIR").unwrap_or_else(|_| "/app/public".to_string());
    let index_file = format!("{}/index.html", static_dir);

    // Build our application with routes
    let app = Router::new()
        // Health check endpoints
        .route("/health", get(health_check))
        .route("/api/health", get(api_health_check))
        // WebSocket endpoint
        .route("/api/ws", get(api::ws::ws_handler))
        // Activity feed endpoints
        .route("/api/activity", get(api::activity::list_events))
        .route(
            "/api/activity/unread-count",
            get(api::activity::unread_count),
        )
        .route("/api/activity/mark-read", post(api::activity::mark_read))
        // Approval endpoints
        .route("/api/approvals", get(api::approvals::list_approvals))
        .route(
            "/api/approvals/pending-count",
            get(api::approvals::pending_count),
        )
        .route("/api/approvals/:id", get(api::approvals::get_approval))
        .route("/api/approvals/:id/approve", post(api::approvals::approve))
        .route("/api/approvals/:id/reject", post(api::approvals::reject))
        .route(
            "/api/approvals/:id/modify",
            post(api::approvals::request_modify),
        )
        // Session endpoints
        .route("/api/sessions", get(api::sessions::list_sessions))
        .route("/api/sessions", post(api::sessions::create_session))
        .route("/api/sessions/:id", get(api::sessions::get_session))
        .route(
            "/api/sessions/:id/message",
            post(api::sessions::send_message),
        )
        // Monitoring endpoints
        .route("/api/monitoring/nodes", get(api::monitoring::get_nodes))
        .route(
            "/api/monitoring/namespaces",
            get(api::monitoring::get_namespaces),
        )
        .route("/api/monitoring/events", get(api::monitoring::get_events))
        .route(
            "/api/monitoring/services",
            get(api::monitoring::get_services),
        )
        // Registry endpoints (with aliases for frontend compatibility)
        .route("/api/agents", get(api::registry::get_agents))
        .route("/api/registry/agents", get(api::registry::get_agents))
        .route(
            "/api/registry/mcp-servers",
            get(api::registry::get_mcp_servers),
        )
        .route("/api/registry/models", get(api::registry::get_models))
        .route("/api/registry/skills", get(api::registry::get_skills))
        // Tools endpoint
        .route("/api/tools", get(api::registry::get_tools))
        // Workflows endpoint
        .route("/api/workflows", get(api::workflows::get_workflows))
        .route(
            "/api/workflows/:id",
            get(api::workflows::get_workflow_detail),
        )
        // Chat endpoint (kept for backward compatibility)
        .route("/api/chat", post(api::chat::chat_handler))
        // Serve static files with SPA fallback
        .fallback_service(
            ServeDir::new(&static_dir).not_found_service(ServeFile::new(&index_file)),
        )
        // Add shared state
        .with_state(app_state)
        // Add CORS middleware
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        )
        // Add tracing middleware
        .layer(TraceLayer::new_for_http());

    // Get port from environment (default 3000 for production)
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
