# Skills MCP Server

MCP server that discovers and executes Kubani skills with sandboxed isolation.

## Features

- **Skill Discovery**: Automatically discovers skills from `kubani/skills/` by parsing SKILL.md files
- **Agent Filtering**: Filter skills by domain, category, or glob patterns (allowed/denied)
- **Sandboxed Execution**: Execute skill scripts in isolated Microsandbox environments
- **Outcome Recording**: Record execution outcomes for the learning system

## Installation

```bash
# Install with uv
uv pip install -e .

# Or with pip
uv pip install -e .
```

## Usage

### Running the Server

```bash
# Stdio mode (for Claude Code / local development)
skills-mcp-server --mode stdio

# SSE mode (for cluster deployment)
skills-mcp-server --mode sse --port 8080

# HTTP mode
skills-mcp-server --mode http --port 8080
```

### Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SKILLS_PATH` | Path to skills directory | `kubani/skills` |
| `MICROSANDBOX_URL` | Microsandbox server URL | `http://localhost:8090` |
| `MICROSANDBOX_ENABLED` | Enable Microsandbox isolation | `true` |
| `MCP_ALLOWED_HOSTS` | Additional allowed hosts for MCP | - |

### MCP Tools

#### `list_skills`

List available skills with optional filtering.

```json
{
  "domain": "k8s",
  "category": "diagnostic"
}
```

#### `get_skill`

Get detailed information about a specific skill.

```json
{
  "skill_path": "k8s/diagnostic/check-pod-health"
}
```

#### `execute_skill`

Execute a skill with the provided context.

```json
{
  "skill_path": "k8s/remediation/restart-crashloop",
  "context": {
    "pod_name": "nginx-abc123",
    "namespace": "default"
  },
  "timeout": 60.0
}
```

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check src/
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Skills MCP Server                         │
├─────────────────────────────────────────────────────────────┤
│  SkillDiscovery         │  SkillExecutor                    │
│  - Scan filesystem      │  - MicrosandboxExecutor (primary) │
│  - Parse SKILL.md       │  - SubprocessExecutor (fallback)  │
│  - Filter by patterns   │  - Record outcomes                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Microsandbox   │
                    │  (microVM)      │
                    └─────────────────┘
```

## Framework Integration

This server uses `TransportConfig` from `kubani.framework.mcp.server` for unified command-line argument parsing and transport configuration. See [kubani/framework/mcp/server/README.md](../../../framework/mcp/server/README.md) for details on the shared utilities.

## License

MIT
