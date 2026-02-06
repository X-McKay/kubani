
># Nexus Implementation Plan: 06 - Enhanced Web UI

**Author:** Manus AI
**Date:** February 6, 2026

## 1. Overview

This document details the plan for enhancing the existing `kubani` web UI to support the new conversational and monitoring capabilities of Kubani Nexus. As per the architectural decision, we will enhance the existing React-based web application, making it fully responsive and installable as a Progressive Web App (PWA).

This provides a cost-effective way to deliver a native-like mobile experience without the overhead of a separate native app codebase.

## 2. Core UI Components

We will develop a new, primary view within the Kubani UI dedicated to interacting with the Nexus agent. This view will be composed of several key components.

### 2.1. Conversational Panel

-   **Purpose:** The main interface for back-and-forth conversation with the agent.
-   **Features:**
    -   A scrolling message history, clearly distinguishing between user and agent messages.
    -   A text input area for sending new messages.
    -   Support for rendering Markdown and code blocks in the agent's responses.
-   **Technology:** This component will establish a WebSocket connection to the **Conversational Gateway** (as detailed in Plan 02) to send and receive messages in real-time.

### 2.2. Status & Activity Panel

-   **Purpose:** To provide a real-time view into the agent's current state and actions.
-   **Features:**
    -   **Current Status:** A simple display showing the agent's status (e.g., "Idle," "Planning," "Executing Skill"). This will be powered by the `get_status` query on the Temporal workflow.
    -   **Current Plan:** A checklist-style view of the agent's current plan, with steps being checked off as they are completed.
    -   **Recent Actions:** A log of the most recent high-level actions taken by the agent.
-   **Technology:** This panel will periodically poll the `get_state` query on the `NexusSyndicateWorkflow` via a simple API endpoint on the UI backend.

### 2.3. Human-in-the-Loop (HITL) Approval Panel

-   **Purpose:** To display pending approval requests, such as for medium-risk skills.
-   **Features:**
    -   A list of pending requests, each with a clear description of the action requiring approval.
    -   "Approve" and "Deny" buttons for each request.
-   **Technology:** This will be powered by a new set of Temporal workflows and activities for managing human approvals. When an action requires approval, the workflow will pause and wait for a signal that is sent when a user clicks a button in this UI panel.

## 3. Progressive Web App (PWA) Enablement

To make the UI installable and feel like a native app on mobile devices, we will implement the core requirements for a PWA:

1.  **Web App Manifest:** We will add a `manifest.json` file that defines the app's name, icons, and display properties.
2.  **Service Worker:** A service worker will be implemented to handle offline caching of the application shell, allowing the UI to load instantly even without a network connection.
3.  **HTTPS:** The UI is already served over HTTPS, which is a prerequisite.

This will enable users to "Add to Home Screen" on both iOS and Android, creating an icon that launches the UI in a full-screen, native-like window.

## 4. Backend (Rust/Axum)

The existing Rust/Axum backend for the UI will be extended slightly to support the new features.

-   **New Endpoint:** A new API endpoint will be created to proxy the `get_state` and `get_status` queries to the Temporal workflow. This avoids exposing the Temporal client directly to the frontend.
-   **WebSocket Proxy (Optional):** While the frontend can connect directly to the Conversational Gateway, we may choose to proxy the WebSocket connection through the UI backend for simplified authentication and routing. This is a minor implementation detail to be decided.

By building upon the existing, robust foundation of the Kubani UI, we can deliver a powerful and modern interface for Kubani Nexus efficiently.
