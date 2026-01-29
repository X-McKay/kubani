# Kubani UI - Remaining Integration Work

This document outlines the remaining work needed to fully integrate the Kubani UI with the backend services.

---

## Table of Contents

1. [API Integration](#1-api-integration)
2. [Real-Time Updates](#2-real-time-updates)
3. [Chat Interface Backend](#3-chat-interface-backend)
4. [Authentication & Authorization](#4-authentication--authorization)
5. [Deployment & Infrastructure](#5-deployment--infrastructure)
6. [Enhanced Features](#6-enhanced-features)
7. [Testing](#7-testing)

---

## 1. API Integration

### 1.1 Kubani Registry API

**Location:** `registry/src/kubani_registry/`

Connect the Registry page to the actual kubani-registry service.

- [ ] **Agents endpoint** (`/api/agents`)
  - Fetch registered agents with status, capabilities, and heartbeat info
  - File: `client/src/pages/Registry.tsx` - Replace `mockAgents` with API call
  - Registry model: `registry/src/kubani_registry/db/models.py` - `Agent` class

- [ ] **MCP Servers endpoint** (`/api/mcp-servers`)
  - Fetch registered MCP servers with transport type and tool counts
  - File: `client/src/pages/Registry.tsx` - Replace `mockMCPServers` with API call
  - Registry model: `registry/src/kubani_registry/db/models.py` - `MCPServer` class

- [ ] **Skills endpoint** (`/api/skills`)
  - Fetch validated skills with confidence scores and success rates
  - File: `client/src/pages/Registry.tsx` - Replace `mockSkills` with API call
  - Registry model: `registry/src/kubani_registry/db/models.py` - `Skill` class

- [ ] **Models endpoint** (`/api/models`)
  - Fetch available LLM models with status and configuration
  - File: `client/src/pages/Registry.tsx` - Replace `mockModels` with API call
  - Registry model: `registry/src/kubani_registry/db/models.py` - `Model` class

- [ ] **Deployments endpoint** (`/api/deployments`)
  - Fetch deployment configurations and status
  - Consider adding a Deployments tab to the Registry page

**Implementation Notes:**
```typescript
// Example API service pattern
// Create: client/src/lib/api.ts

const API_BASE = import.meta.env.VITE_REGISTRY_API_URL || 'http://kubani-registry.ai-agents.svc:8080';

export async function fetchAgents() {
  const response = await fetch(`${API_BASE}/api/agents`);
  return response.json();
}
```

### 1.2 Kubernetes Cluster API

Connect the Monitoring page to Kubernetes cluster data.

- [ ] **Nodes endpoint** (`/api/cluster/nodes`)
  - Fetch node status, roles, and resource metrics
  - File: `client/src/pages/Monitoring.tsx` - Replace `mockNodes` with API call
  - Consider using: `kubani cluster/` Python code or direct K8s API

- [ ] **Pods endpoint** (`/api/cluster/pods`)
  - Fetch pod status across namespaces
  - Aggregate counts for the overview cards

- [ ] **Services endpoint** (`/api/cluster/services`)
  - Fetch service health and endpoints
  - File: `client/src/pages/Monitoring.tsx` - Replace `mockServices` with API call

- [ ] **Namespaces endpoint** (`/api/cluster/namespaces`)
  - Fetch namespace list with pod counts
  - File: `client/src/pages/Monitoring.tsx` - Replace `mockNamespaces` with API call

- [ ] **Events endpoint** (`/api/cluster/events`)
  - Fetch recent Kubernetes events
  - File: `client/src/pages/Monitoring.tsx` - Replace `mockEvents` with API call

- [ ] **Metrics endpoint** (`/api/cluster/metrics`)
  - Fetch historical CPU/memory metrics for charts
  - Consider integrating with Prometheus if available

**Backend Options:**
1. Create a new API service in `kubani cluster/` that wraps the Kubernetes Python client
2. Use the existing TUI code as reference: `kubani cluster/tui/app.py`
3. Deploy a lightweight API gateway (e.g., FastAPI) that proxies K8s API calls

---

## 2. Real-Time Updates

### 2.1 WebSocket Infrastructure

- [ ] **Set up WebSocket server**
  - Add WebSocket support to the backend (FastAPI with `websockets` or dedicated service)
  - Consider using the existing Temporal infrastructure for event streaming

- [ ] **Client WebSocket hook**
  - Create: `client/src/hooks/useWebSocket.ts`
  - Handle connection, reconnection, and message parsing

### 2.2 Monitoring Real-Time Updates

- [ ] **Node status updates**
  - Subscribe to node status changes
  - Update UI without full page refresh

- [ ] **Pod status updates**
  - Subscribe to pod creation/deletion/status changes
  - Update namespace counts in real-time

- [ ] **Event stream**
  - Stream Kubernetes events as they occur
  - Auto-scroll the events feed

- [ ] **Metrics streaming**
  - Stream CPU/memory metrics for live charts
  - Consider 5-10 second polling as alternative

### 2.3 Registry Real-Time Updates

- [ ] **Agent heartbeat status**
  - Update agent status badges in real-time
  - Show "last seen" timestamps updating live

- [ ] **Registration events**
  - Notify when new agents/MCP servers register
  - Toast notifications for important events

---

## 3. Chat Interface Backend

### 3.1 Agent Communication

- [ ] **Agent selection API**
  - Fetch available agents for the dropdown
  - Include agent status (ready/offline)
  - File: `client/src/pages/Chat.tsx` - Replace `mockAgents` with API call

- [ ] **Chat session management**
  - Create: `POST /api/chat/sessions`
  - List: `GET /api/chat/sessions`
  - Get: `GET /api/chat/sessions/:id`
  - File: `client/src/pages/Chat.tsx` - Replace `mockConversations` with API calls

- [ ] **Message sending**
  - Send: `POST /api/chat/sessions/:id/messages`
  - Integrate with agent endpoints (likely via Temporal workflows)
  - Handle streaming responses

### 3.2 Tool Call Visualization

- [ ] **Tool execution tracking**
  - Capture tool calls from agent execution
  - Stream tool arguments and results to the UI
  - File: `client/src/pages/Chat.tsx` - Wire up `ToolCallBlock` component

- [ ] **MCP tool integration**
  - Show which MCP server is handling each tool call
  - Display tool execution time/latency

### 3.3 Activity Panel

- [ ] **Thought streaming**
  - Stream agent "thinking" steps in real-time
  - Integrate with agent's internal reasoning (if exposed)

- [ ] **Action logging**
  - Log all tool invocations with timestamps
  - Show success/failure status

- [ ] **Context display**
  - Show actual active skills from the agent
  - Display real token usage from the LLM

**Integration with Temporal:**
```python
# The chat backend likely needs to:
# 1. Start a Temporal workflow for the agent
# 2. Stream workflow events to the UI via WebSocket
# 3. Capture tool calls and results from workflow activities
```

---

## 4. Authentication & Authorization

### 4.1 Authentication

- [ ] **Auth provider integration**
  - Options: OAuth2, OIDC, or simple JWT
  - Consider using existing cluster auth if available

- [ ] **Login page**
  - Create: `client/src/pages/Login.tsx`
  - Add route in `client/src/App.tsx`

- [ ] **Auth context**
  - Create: `client/src/contexts/AuthContext.tsx`
  - Store user session and tokens

- [ ] **Protected routes**
  - Wrap routes with auth check
  - Redirect to login if unauthenticated

### 4.2 Authorization

- [ ] **Role-based access control**
  - Define roles: admin, operator, viewer
  - Restrict actions based on role (e.g., only admins can delete agents)

- [ ] **Namespace-level permissions**
  - Consider limiting visibility to specific namespaces
  - Filter data based on user permissions

---

## 5. Deployment & Infrastructure

### 5.1 Container Image

- [ ] **Create Dockerfile**
  ```dockerfile
  # ui/Dockerfile
  FROM node:22-alpine AS builder
  WORKDIR /app
  COPY package.json pnpm-lock.yaml ./
  RUN corepack enable && pnpm install --frozen-lockfile
  COPY . .
  RUN pnpm build

  FROM nginx:alpine
  COPY --from=builder /app/dist /usr/share/nginx/html
  COPY nginx.conf /etc/nginx/conf.d/default.conf
  EXPOSE 80
  ```

- [ ] **Create nginx.conf**
  - Handle SPA routing (fallback to index.html)
  - Configure API proxy if needed

- [ ] **Add to CI/CD pipeline**
  - Build and push image on merge to main
  - Tag with version/commit SHA

### 5.2 Kubernetes Deployment

- [ ] **Create Kubernetes manifests**
  - Location: `gitops/apps/kubani-ui/`
  - Deployment, Service, Ingress/IngressRoute

- [ ] **Environment configuration**
  - ConfigMap for API URLs
  - Consider using Kustomize overlays for different environments

- [ ] **Traefik IngressRoute**
  ```yaml
  apiVersion: traefik.io/v1alpha1
  kind: IngressRoute
  metadata:
    name: kubani-ui
    namespace: ai-agents
  spec:
    entryPoints:
      - websecure
    routes:
      - match: Host(`kubani.yourdomain.com`)
        kind: Rule
        services:
          - name: kubani-ui
            port: 80
  ```

### 5.3 Environment Variables

- [ ] **Define required env vars**
  ```
  VITE_REGISTRY_API_URL=http://kubani-registry.ai-agents.svc:8080
  VITE_CLUSTER_API_URL=http://cluster-api.ai-agents.svc:8080
  VITE_WS_URL=ws://kubani-ws.ai-agents.svc:8080
  ```

---

## 6. Enhanced Features

### 6.1 Command Palette (⌘K)

- [ ] **Implement command palette**
  - Use `cmdk` package (already installed)
  - Quick navigation between pages
  - Search agents, services, pods

### 6.2 ReactFlow Visualization

- [ ] **Install ReactFlow**
  ```bash
  pnpm add @xyflow/react
  ```

- [ ] **Agent execution graph**
  - Visualize agent plan as a node graph
  - Show execution progress through nodes
  - Display tool calls as edges

- [ ] **Workflow visualization**
  - Integrate with Temporal workflow visualization
  - Show workflow state and history

### 6.3 Additional Pages

- [ ] **Pod detail page**
  - View pod logs
  - Show container status
  - Exec into containers (if permitted)

- [ ] **Agent detail page**
  - Full agent configuration
  - Execution history
  - Performance metrics

- [ ] **Settings page**
  - User preferences
  - Theme toggle (dark/light)
  - Notification settings

### 6.4 Notifications

- [ ] **Toast notifications for events**
  - Agent registration/deregistration
  - Pod failures
  - Workflow completions

- [ ] **Browser notifications**
  - Optional push notifications for critical events

---

## 7. Testing

### 7.1 Unit Tests

- [ ] **Component tests**
  - Test individual UI components
  - Use Vitest + React Testing Library

- [ ] **Hook tests**
  - Test custom hooks (useWebSocket, etc.)

### 7.2 Integration Tests

- [ ] **API integration tests**
  - Mock API responses
  - Test data flow through components

- [ ] **E2E tests**
  - Use Playwright or Cypress
  - Test critical user flows

### 7.3 Visual Regression Tests

- [ ] **Screenshot tests**
  - Capture component screenshots
  - Detect unintended visual changes

---

## Priority Order

For initial integration, focus on these in order:

1. **Registry API Integration** - Easiest win, data already exists
2. **Kubernetes Cluster API** - Core monitoring functionality
3. **WebSocket for real-time updates** - Makes the UI feel alive
4. **Chat backend integration** - Most complex, save for last
5. **Authentication** - Add when ready for production
6. **Deployment** - Once features are stable

---

## Files to Create/Modify

| File | Purpose |
|------|---------|
| `client/src/lib/api.ts` | API client with fetch wrappers |
| `client/src/lib/websocket.ts` | WebSocket client |
| `client/src/hooks/useWebSocket.ts` | WebSocket React hook |
| `client/src/hooks/useQuery.ts` | Data fetching hook (or use TanStack Query) |
| `client/src/contexts/AuthContext.tsx` | Authentication state |
| `client/src/pages/Login.tsx` | Login page |
| `ui/Dockerfile` | Container build |
| `ui/nginx.conf` | Nginx configuration |
| `gitops/apps/kubani-ui/` | Kubernetes manifests |

---

## Questions to Resolve

1. **API Gateway** - Should we create a unified API gateway or call services directly?
2. **Auth Provider** - What auth system should we integrate with?
3. **Metrics Backend** - Is Prometheus available for historical metrics?
4. **Chat Protocol** - How should the UI communicate with agents? (REST, WebSocket, gRPC?)
5. **Multi-tenancy** - Do we need to support multiple users/teams with isolated views?

---

*Last updated: January 2025*
