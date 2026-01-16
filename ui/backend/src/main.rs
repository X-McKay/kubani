mod api;
mod cache;
mod mcp;
mod models;
mod parsers;

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

    tracing::info!("Starting Kubani UI Backend");

    // Static file serving for SPA (fallback to index.html for client-side routing)
    let static_dir = std::env::var("STATIC_DIR").unwrap_or_else(|_| "/app/public".to_string());
    let index_file = format!("{}/index.html", static_dir);

    // Build our application with routes
    let app = Router::new()
        // Health check
        .route("/health", get(health_check))
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
        // Registry endpoints
        .route("/api/registry/agents", get(api::registry::get_agents))
        .route(
            "/api/registry/mcp-servers",
            get(api::registry::get_mcp_servers),
        )
        .route("/api/registry/models", get(api::registry::get_models))
        .route("/api/registry/skills", get(api::registry::get_skills))
        // Chat endpoint
        .route("/api/chat", post(api::chat::chat_handler))
        // Serve static files with SPA fallback
        .fallback_service(
            ServeDir::new(&static_dir)
                .not_found_service(ServeFile::new(&index_file)),
        )
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
