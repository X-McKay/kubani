//! Nexus agent chat proxy
//!
//! Proxies chat requests to the Nexus Gateway via REST + WebSocket,
//! bridging the gateway's WebSocket response into SSE events.

use crate::api::chat_executor::StreamEvent;
use crate::models::ChatMessage;
use futures::stream::{self, Stream};
use serde_json::json;
use std::convert::Infallible;
use std::env;
use tokio::sync::mpsc;

/// Create an SSE stream that proxies through the Nexus Gateway
pub fn create_nexus_stream(
    messages: Vec<ChatMessage>,
) -> impl Stream<Item = Result<axum::response::sse::Event, Infallible>> + Send {
    let (tx, rx) = mpsc::channel::<StreamEvent>(100);

    tokio::spawn(async move {
        if let Err(e) = run_nexus_chat(messages, &tx).await {
            let _ = tx
                .send(StreamEvent::Error {
                    message: e.to_string(),
                })
                .await;
        }
        let _ = tx.send(StreamEvent::Done).await;
    });

    let stream = tokio_stream::wrappers::ReceiverStream::new(rx);
    stream::unfold(stream, |mut stream| async move {
        use tokio_stream::StreamExt;
        match stream.next().await {
            Some(event) => {
                let json = serde_json::to_string(&event).unwrap_or_default();
                let sse_event = axum::response::sse::Event::default().data(json);
                Some((Ok(sse_event), stream))
            }
            None => None,
        }
    })
}

async fn run_nexus_chat(
    messages: Vec<ChatMessage>,
    tx: &mpsc::Sender<StreamEvent>,
) -> anyhow::Result<()> {
    let nexus_url =
        env::var("NEXUS_GATEWAY_URL").map_err(|_| anyhow::anyhow!("NEXUS_GATEWAY_URL not configured"))?;

    // Extract last user message
    let last_user_msg = messages
        .iter()
        .rev()
        .find(|m| m.role == "user")
        .ok_or_else(|| anyhow::anyhow!("No user message found"))?;

    // 1. POST to Nexus Gateway to queue the message
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{}/api/nexus/chat", nexus_url))
        .json(&json!({
            "text": last_user_msg.content,
            "user_id": "kubani-ui-user",
            "source": "kubani-ui",
        }))
        .send()
        .await?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        anyhow::bail!("Nexus gateway error: {} - {}", status, body);
    }

    let nexus_data: serde_json::Value = response.json().await?;
    let conversation_id = nexus_data["conversation_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("No conversation_id in gateway response"))?
        .to_string();

    tracing::info!("Nexus chat queued, conversation: {}", conversation_id);

    // 2. Connect WebSocket to Nexus Gateway for response streaming
    let ws_url = nexus_url.replacen("http", "ws", 1) + &format!("/ws/nexus/{}", conversation_id);

    let (ws_stream, _) = tokio_tungstenite::connect_async(&ws_url)
        .await
        .map_err(|e| anyhow::anyhow!("WebSocket connection failed: {}", e))?;

    tracing::debug!("Nexus WS connected for conversation {}", conversation_id);

    // 3. Read messages from WebSocket and bridge to SSE
    use futures::StreamExt;
    use tokio_tungstenite::tungstenite::Message;

    let (_, mut read) = ws_stream.split();

    let result = tokio::time::timeout(tokio::time::Duration::from_secs(120), async {
        while let Some(msg) = read.next().await {
            match msg {
                Ok(Message::Text(text)) => {
                    match serde_json::from_str::<serde_json::Value>(&text) {
                        Ok(agent_msg) => {
                            let content =
                                agent_msg["text"].as_str().unwrap_or("").to_string();
                            if !content.is_empty() {
                                let _ = tx.send(StreamEvent::Content { content }).await;
                            }
                        }
                        Err(e) => {
                            tracing::warn!("Failed to parse Nexus WS message: {}", e);
                        }
                    }
                    // Nexus sends one message per response
                    break;
                }
                Ok(Message::Close(_)) => break,
                Err(e) => {
                    anyhow::bail!("WebSocket error: {}", e);
                }
                _ => {} // Ignore ping/pong/binary
            }
        }
        Ok::<(), anyhow::Error>(())
    })
    .await;

    match result {
        Ok(Ok(())) => Ok(()),
        Ok(Err(e)) => Err(e),
        Err(_) => anyhow::bail!("Nexus agent timed out after 120s"),
    }
}
