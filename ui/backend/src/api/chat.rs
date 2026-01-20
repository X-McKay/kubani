use crate::api::chat_executor::{create_agentic_stream, get_agent_config_dynamic};
use crate::models::ChatRequest;
use axum::{
    http::StatusCode,
    response::sse::{KeepAlive, Sse},
    Json,
};
use futures::stream::Stream;
use std::convert::Infallible;

pub async fn chat_handler(
    Json(request): Json<ChatRequest>,
) -> Result<Sse<impl Stream<Item = Result<axum::response::sse::Event, Infallible>>>, StatusCode> {
    tracing::info!(
        "Chat request with agent_id: {:?}, {} messages",
        request.agent_id,
        request.messages.len()
    );

    // Get agent-specific configuration with dynamic tool discovery
    let config = get_agent_config_dynamic(&request.agent_id).await;

    tracing::debug!("Using {} tools for agent", config.tools.len());

    // Create the agentic stream that handles tool execution
    let event_stream = create_agentic_stream(request.messages, config);

    Ok(Sse::new(event_stream).keep_alive(KeepAlive::default()))
}
