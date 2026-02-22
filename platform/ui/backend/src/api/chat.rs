use crate::api::chat_executor::{create_agentic_stream, get_agent_config_dynamic};
use crate::api::nexus;
use crate::models::ChatRequest;
use axum::{
    http::StatusCode,
    response::sse::{KeepAlive, Sse},
    Json,
};
use futures::stream::Stream;
use std::convert::Infallible;
use std::pin::Pin;

type SseStream = Pin<Box<dyn Stream<Item = Result<axum::response::sse::Event, Infallible>> + Send>>;

pub async fn chat_handler(
    Json(request): Json<ChatRequest>,
) -> Result<Sse<SseStream>, StatusCode> {
    tracing::info!(
        "Chat request with agent_id: {:?}, {} messages",
        request.agent_id,
        request.messages.len()
    );

    let stream: SseStream = if request.agent_id.as_deref() == Some("nexus") {
        tracing::info!("Routing to Nexus Gateway");
        Box::pin(nexus::create_nexus_stream(request.messages))
    } else {
        // Get agent-specific configuration with dynamic tool discovery
        let config = get_agent_config_dynamic(&request.agent_id).await;
        tracing::debug!("Using {} tools for agent", config.tools.len());
        Box::pin(create_agentic_stream(request.messages, config))
    };

    Ok(Sse::new(stream).keep_alive(KeepAlive::default()))
}
