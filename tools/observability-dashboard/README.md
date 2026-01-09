# Kubani Observability Dashboard

A real-time dashboard for monitoring the Kubani AI agent system, providing visibility into agent execution, memory state, and system health.

## Features

- **Real-time Metrics**: Live view of event bus activity, agent status, and memory system
- **Execution Traces**: Track agent actions and their outcomes
- **System Architecture**: Visual representation of the agent system
- **Auto-refresh**: Dashboard updates automatically every 30 seconds

## Installation

```bash
pip install aiohttp redis
```

## Usage

```bash
# Start with defaults
python dashboard.py

# Custom host and port
python dashboard.py --host 0.0.0.0 --port 8080

# With custom Redis URL
python dashboard.py --redis-url redis://my-redis:6379
```

## Metrics Displayed

### Sentinel Agent
- Current status (active/idle)
- Number of deduplication entries
- Event classification statistics

### Event Bus
- Stream lengths for each event type
- Recent event activity

### Memory System
- Working memory items
- Episodic memory count
- Semantic memory count

### Execution Traces
- Recent agent actions
- Execution status and duration
- Error tracking

## API Endpoints

- `GET /` - Dashboard HTML page
- `GET /api/stats` - JSON metrics data
- `GET /api/traces` - JSON trace data

## Integration

The dashboard can be integrated with:
- **Prometheus**: Export metrics for long-term storage
- **Grafana**: Create custom visualizations
- **Alertmanager**: Set up alerts based on metrics

## Development

```bash
# Run in development mode
python dashboard.py --host localhost --port 3000
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Dashboard Server                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Metrics   │  │   Traces    │  │    HTML     │        │
│  │  Collector  │  │  Collector  │  │  Generator  │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │
│         ▼                ▼                ▼                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                   aiohttp Server                     │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │                │
         ▼                ▼
    ┌─────────┐     ┌─────────┐
    │  Redis  │     │ Browser │
    └─────────┘     └─────────┘
```
