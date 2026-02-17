
># Nexus Implementation Plan: 02 - Conversational Gateway

**Author:** Manus AI
**Date:** February 6, 2026

## 1. Overview

This document provides the detailed implementation plan for the **Conversational Gateway**. This service acts as the central communication hub, bridging the gap between user-facing clients (Discord, Kubani UI) and the durable, asynchronous Nexus Temporal workflow.

Its primary responsibilities are:

1.  To provide a real-time, bidirectional communication channel for clients.
2.  To normalize messages from different sources into a canonical format.
3.  To reliably signal user messages to the correct Temporal workflow instance.
4.  To listen for agent responses and push them back to the appropriate clients.

## 2. Technology Stack

-   **Language:** Python
-   **Framework:** FastAPI
-   **Real-time Communication:** WebSockets
-   **Asynchronous Messaging:** Redis (Pub/Sub)
-   **Temporal Communication:** `temporalio` Python SDK

## 3. API Design

The gateway will expose a single primary endpoint for real-time communication and a standard health check endpoint.

### 3.1. WebSocket Endpoint: `/ws/{conversation_id}`

This is the main endpoint for clients like the Kubani UI to connect to.

-   **Path:** `/ws/{conversation_id}`
-   **Protocol:** WebSocket

**Lifecycle:**

1.  **Connection:** A client establishes a WebSocket connection to a specific `conversation_id`.
2.  **Authentication:** The gateway will verify the user's identity and authorization to join this conversation (details to be determined, likely via a JWT passed in the headers).
3.  **Receiving Messages:** The client sends JSON-encoded `UserMessage` objects over the WebSocket.
4.  **Sending Messages:** The gateway pushes JSON-encoded `AgentMessage` objects to the client when they are received from the agent.

**Data Models:**

```python
from pydantic import BaseModel

class UserMessage(BaseModel):
    """A message sent from the client to the agent."""
    text: str

class AgentMessage(BaseModel):
    """A message sent from the agent to the client."""
    text: str
    source: str # e.g., "NexusSyndicateWorkflow"
```

### 3.2. Health Check Endpoint: `/health`

-   **Path:** `/health`
-   **Method:** GET
-   **Response:**
    -   `200 OK`: If the service is running and can connect to Redis and Temporal.
    -   `503 Service Unavailable`: If any of its core dependencies are unreachable.

## 4. Core Logic

### 4.1. Inbound Message Flow (Client -> Agent)

1.  A message is received on the WebSocket for a given `conversation_id`.
2.  The gateway constructs a full `UserMessage` object, adding metadata like `source`, `user_id`, and `timestamp`.
3.  It uses the `temporalio` client to **signal** the `NexusSyndicateWorkflow` whose `conversation_id` matches. The signal sent is `receive_message`, and the payload is the `UserMessage` object.
4.  This process is asynchronous. The gateway does not wait for a response from the workflow.

### 4.2. Outbound Message Flow (Agent -> Client)

1.  The gateway maintains a long-lived subscription to a specific Redis Pub/Sub channel (e.g., `nexus-responses`).
2.  When the `send_agent_response_activity` in the Temporal workflow is executed, it publishes the `AgentMessage` to this Redis channel.
3.  The gateway receives the message from its Redis subscription.
4.  It looks up the active WebSocket connection(s) associated with the message's `conversation_id`.
5.  It sends the `AgentMessage` over the appropriate WebSocket to the connected client(s).

### 4.3. Discord Integration

The gateway will also be responsible for integrating with Discord. It will use the existing Discord MCP server for this.

1.  **Inbound:** The gateway will connect to the Discord MCP server and listen for incoming messages. When a message is received, it will be normalized into the standard `UserMessage` format and signaled to the Temporal workflow, just like a message from the WebSocket.
2.  **Outbound:** When an `AgentMessage` is received from the Redis Pub/Sub channel, if the original message source was Discord, the gateway will use the Discord MCP server to send the response to the correct Discord channel.

## 5. Deployment and Configuration

-   The gateway will be deployed as a standard Kubernetes `Deployment` and `Service` in the `kubani` cluster.
-   Configuration (Temporal host, Redis host, Discord MCP endpoint) will be managed via environment variables and a `ConfigMap`, following the existing `kubani` configuration patterns.
-   It will be a stateless service, allowing it to be scaled horizontally if needed, as all persistent state is managed by Temporal and Redis.
