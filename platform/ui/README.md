# Kubani UI

A modern, clean web interface for managing and monitoring the Kubani AI agent cluster.

## Overview

The Kubani UI provides a comprehensive dashboard for:

1. **Cluster Monitoring** - Real-time overview of cluster health, node status, resource utilization, and Kubernetes events
2. **Registry Browser** - Browse and manage registered agents, MCP servers, skills, and models
3. **Agent Chat Interface** - Interact with agents using a Manus-style dual-pane interface with live activity transparency

## Design Philosophy

The UI follows a **Glass Terminal** design aesthetic:
- Dark glassmorphism with translucent, frosted-glass panels
- Vibrant violet and cyan accents against deep space black backgrounds
- Native split-pane architecture for the dual interface
- Inter + JetBrains Mono font pairing
- Animated gradient orbs for visual depth

## Tech Stack

- **React 19** with TypeScript
- **Tailwind CSS 4** for styling
- **shadcn/ui** components (Radix UI primitives)
- **Recharts** for data visualization
- **Wouter** for client-side routing
- **Vite** for development and building

## Getting Started

### Prerequisites

- Node.js 22+
- pnpm 10+

### Installation

```bash
cd ui
pnpm install
```

### Development

```bash
pnpm dev
```

The development server will start at `http://localhost:3000`.

### Building

```bash
pnpm build
```

## Project Structure

```
ui/
├── client/
│   ├── public/          # Static assets
│   └── src/
│       ├── components/  # Reusable UI components
│       │   └── ui/      # shadcn/ui components
│       ├── contexts/    # React contexts
│       ├── hooks/       # Custom React hooks
│       ├── lib/         # Utility helpers
│       └── pages/       # Page components
│           ├── Monitoring.tsx  # Cluster dashboard
│           ├── Registry.tsx    # Registry browser
│           └── Chat.tsx        # Agent chat interface
├── server/              # Express server (for production)
└── shared/              # Shared types and constants
```

## Pages

### Monitoring (`/monitoring`)

Real-time cluster monitoring dashboard featuring:
- Cluster health overview cards
- Resource utilization charts (CPU/Memory)
- Node status table with metrics
- Services health status
- Namespace pod counts
- Live Kubernetes event feed

### Registry (`/registry`)

Browse and manage registered entities:
- **Agents** - View registered AI agents with capabilities and status
- **MCP Servers** - Model Context Protocol servers and their tools
- **Skills** - Validated skills with confidence and success rates
- **Models** - Available LLM models with context lengths and status

### Chat (`/chat`)

Manus-style agent interaction interface:
- Agent selector dropdown
- Chat history sidebar
- Conversational interface with markdown rendering
- Tool call visualization (expandable arguments/results)
- Activity panel showing agent thoughts, actions, and results
- Context panel showing active skills, tools, and memory usage

## Integration

The UI is designed to integrate with the Kubani backend services:

- **kubani-registry** - For agent, MCP server, skill, and model data
- **Kubernetes API** - For cluster monitoring data
- **Agent endpoints** - For chat interactions

Currently using mock data for demonstration. To connect to real services, update the API calls in each page component.

## Future Enhancements

- [ ] WebSocket connections for real-time updates
- [ ] ReactFlow visualization for agent execution plans
- [ ] Command palette (⌘K) for quick navigation
- [ ] Dark/light theme toggle
- [ ] Agent registration wizard
- [ ] Log streaming from pods
- [ ] Metrics history and alerting configuration
