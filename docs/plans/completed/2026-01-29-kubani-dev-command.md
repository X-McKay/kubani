# Design: `kubani dev` Command

**Date:** 2026-01-29
**Status:** Draft
**Author:** Claude + Al

## Summary

A CLI command for local agent development that spawns MCP servers as subprocesses, connects them to cluster backends via Tailscale, and runs agents directly with rich console output.

## Problem

Testing news syndicate agents locally requires:
- MCP servers (Memory, Discord) running and configured
- Environment variables pointing to cluster services (Qdrant, Redis, LLM)
- Manual coordination of multiple processes

This friction slows iteration and makes it hard to test agent logic in isolation.

## Solution

A single command that handles all setup automatically:

```bash
# Direct agent testing (default) - fast iteration
kubani dev feed-collector
kubani dev content-analyst

# Syndicate testing - runs agents in sequence
kubani dev news-digest

# With full Temporal workflow
kubani dev news-digest --workflow

# Actually publish to Discord (default is dry run)
kubani dev news-digest --publish
```

## Design

### Command Interface

```bash
kubani dev <target> [options]

Arguments:
  target              Agent or syndicate name

Options:
  --workflow          Run full Temporal workflow instead of direct execution
  --publish           Actually publish to Discord (default: dry run)
  --mcp <servers>     Specify MCP servers to run (default: auto-detect)
  --no-mcp            Skip MCP server startup
  --json              Output results as JSON
  --memory-port PORT  Override Memory MCP port (default: 8083)
  --discord-port PORT Override Discord MCP port (default: 8084)
```

### Console Output

Rich formatted output showing:
1. Session configuration panel
2. MCP server startup status
3. Phase-by-phase execution results
4. Final summary with actionable options

Example for syndicate:

```
╭──────────────────────────────────────────────────────────────╮
│                    Kubani Dev Session                        │
├──────────────────────────────────────────────────────────────┤
│  Syndicate: news-digest                                      │
│  Mode:      direct (no Temporal)                             │
│  Agents:    feed-collector → content-analyst → digest-publisher │
│  MCP:       memory, discord                                  │
╰──────────────────────────────────────────────────────────────╯

[1/2] Starting Memory MCP server...  ✓ (localhost:8083)
[2/2] Starting Discord MCP server... ✓ (localhost:8084)

═══════════════════ Phase 1: Collection ════════════════════════
Running feed-collector.collect()...
  Articles: 23 collected, 7 duplicates filtered

═══════════════════ Phase 2: Analysis ══════════════════════════
Running content-analyst.full_analysis()...
  Analyzed: 23 articles
  Breaking: 2 detected

═══════════════════ Phase 3: Publishing ════════════════════════
Running digest-publisher.compose_digest()...
  [Digest preview shown inline]
  Discord: [DRY RUN - would send to #ai-news]

MCP servers stopped. Session complete.
```

### Environment Configuration

Reads from `config.local.yaml`:

```yaml
environment: development

services:
  qdrant_url: https://qdrant.almckay.io
  redis_url: redis://redis.almckay.io:6379
  neo4j_uri: bolt://neo4j.almckay.io:7687
  llm_url: https://llm.almckay.io/v1
  embeddings_url: https://embeddings.almckay.io/v1

llm:
  model: nvidia/Qwen3-14B-FP4

mcp:
  memory_port: 8083
  discord_port: 8084
```

Automatically sets environment variables:

```bash
QDRANT_URL=https://qdrant.almckay.io
REDIS_URL=redis://redis.almckay.io:6379
VLLM_API_URL=https://llm.almckay.io/v1
VLLM_MODEL=nvidia/Qwen3-14B-FP4
MEMORY_MCP_URL=http://localhost:8083
DISCORD_MCP_URL=http://localhost:8084
```

### MCP Server Lifecycle

```python
class MCPServerManager:
    def start_server(self, server_name: str, port: int) -> subprocess.Popen:
        server_path = f"kubani/mcp/servers/{server_name}"

        proc = subprocess.Popen(
            ["uv", "run", f"{server_name}-mcp"],
            cwd=server_path,
            env={**os.environ, "PORT": str(port)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._wait_healthy(f"http://localhost:{port}/health", timeout=10)
        return proc

    def stop_all(self):
        for proc in self.processes:
            proc.terminate()
            proc.wait(timeout=5)
```

### Target Detection

```python
def detect_target(name: str) -> Target:
    # Check if it's a syndicate
    syndicate_path = Path(f"kubani/syndicates/{name}")
    if syndicate_path.exists():
        return load_syndicate(name)

    # Check if it's an agent
    agent_path = Path(f"kubani/agents/{name.replace('-', '_')}")
    if agent_path.exists():
        return load_agent(name)

    raise TargetNotFoundError(f"No agent or syndicate named '{name}'")
```

### Agent Method Detection

```python
AGENT_METHODS = {
    "feed-collector": "collect",
    "content-analyst": "full_analysis",
    "digest-publisher": "compose_digest",
    "research-collector": "collect_research",
}

# Or defined in agent's config.yaml:
# dev:
#   method: collect
#   args:
#     max_articles: 10
```

### Error Handling

| Failure | Impact | Behavior |
|---------|--------|----------|
| MCP port in use | Server can't start | Warn, suggest alternatives, continue |
| Memory MCP down | No trend history | Warn and continue - agent still runs |
| Discord MCP down | Can't preview Discord | Show digest in console only |
| LLM unreachable | Analysis fails | Fail fast with clear error |
| Redis unreachable | Dedup unavailable | Warn and continue |

Graceful degradation with clear messaging:

```
[1/2] Starting Memory MCP server...  ✗ Failed (port 8083 in use)

      Options:
        • Kill existing process: lsof -ti:8083 | xargs kill
        • Use different port: kubani dev news-digest --memory-port 8093
        • Skip this server: kubani dev news-digest --no-mcp memory

⚠️  Running with degraded MCP: memory unavailable
```

## Implementation Plan

### Files to Create/Modify

1. **`kubani/cli/dev.py`** (new) - Main command implementation
2. **`kubani/cli/mcp_manager.py`** (new) - MCP subprocess management
3. **`kubani/cli/cli.py`** - Register new command
4. **`kubani/agents/_base/agent.py`** - Add `format_result()` method

### Estimated Scope

- ~300 lines for `dev.py`
- ~100 lines for `mcp_manager.py`
- ~50 lines for result formatters
- Leverages existing `kubani.cli.ui` for output

## Open Questions

1. Should `--workflow` mode reuse existing `local-run` infrastructure or be independent?
2. Should we support running a single phase of a syndicate? (e.g., `kubani dev news-digest --phase collection`)

## Success Criteria

- [ ] `kubani dev feed-collector` runs collection and shows results
- [ ] `kubani dev news-digest` runs full pipeline with preview
- [ ] MCP servers start/stop cleanly
- [ ] Ctrl+C terminates everything gracefully
- [ ] Clear error messages when things fail
