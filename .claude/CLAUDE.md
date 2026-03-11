# CLAUDE.md

Guidance for Claude Code when working on the Kubani repository.

---

## Design Principles

### 1. Agentic-First Design
Lean on AI as much as possible. Agents should be autonomous, self-improving, and capable of handling complex tasks with minimal human intervention.

### 2. Simplicity Over Complexity
Single source of truth for configuration. Consistent patterns. Remove duplication aggressively.

### 3. Easy Iteration and Evaluation
Local-first development with cluster services. Hot-reload. Comprehensive evaluation framework.

### 4. Registry-Centric Architecture
Everything is registered, discoverable, and synchronized (agents, skills, models).

### 5. MCP-First Tool Integration
All external tool access goes through MCP servers — standardized interfaces, consistent error handling.

---

## Coding Guidelines

### Think Before Coding
State assumptions explicitly. Surface tradeoffs. If uncertain, ask.

### Simplicity First
Minimum code that solves the problem. No speculative features, abstractions, or error handling for impossible scenarios.

### Surgical Changes
Touch only what you must. Don't improve adjacent code. Match existing style. Remove only orphans YOUR changes created.

### Goal-Driven Execution
Transform tasks into verifiable goals. State a brief plan with verification steps. Loop until verified.

---

## Project Structure

```
kubani/
├── framework/          # Core: config, events, MCP client, registry, LLM
├── agents/             # Reusable agents (Critic, Reflection, SkillSynthesizer, etc.)
├── syndicates/         # Multi-agent orchestration (k8s_monitor, news_digest, learning_system)
├── nexus/              # Conversational PI agent (Strands SDK, Temporal entity workflow)
│   ├── orchestrator/   # Temporal worker, activities, workflow
│   └── gateway/        # FastAPI, WebSocket, Discord bridge
├── mcp/servers/        # MCP server implementations (temporal, qdrant, memory, discord, skills)
├── cli/                # kubani CLI
├── skills/             # Agent runtime skill definitions
└── evaluations/        # Evaluation suites
infrastructure/
├── gitops/             # Kubernetes manifests (Flux)
├── ansible/            # Node provisioning
└── sops/               # Standard operating procedures
platform/
├── registry/           # Metadata registry
└── ui/                 # Web interface
config/                 # YAML config (default, production, local)
docs/                   # Documentation hub
```

---

## Development Workflow

Follow the **3-stage workflow** (see `local-development` skill for details):

1. **Local Test** — Edit, run locally with cluster services, `just test-unit`, `just lint`
2. **Integration Test** — `just test-integration`, verify MCP/Temporal connections
3. **Ship** — `kubani ship <component>` (builds, pushes, patches manifest, commits, pushes, verifies)

### Quick Reference

```bash
# Syndicate agents
kubani local-run --agent k8s-monitor --temporal cluster --hot-reload

# Nexus agent
cd kubani/nexus/orchestrator && source .env && python -m kubani.nexus.orchestrator.worker

# Testing & linting
just test          # All tests
just lint          # Ruff linting
just ci            # Pre-commit checks

# Ship (test -> build -> push -> deploy -> verify)
kubani ship <component>           # Full pipeline
kubani ship <component> --dry-run # Tests only
kubani ship --list                # List components

# Registry & config
kubani sync        # Sync skills/agents/MCP to registry
kubani config show # Show effective config
```

---

## Configuration

Loads in order (later overrides earlier):
1. `config/default.yaml` — Base defaults
2. `config/{env}.yaml` — Environment-specific
3. `config/local.yaml` — Local overrides (gitignored)
4. Environment variables — `KUBANI_` prefix with `__` nesting

```python
from kubani.framework.config import get_config
config = get_config()
```

Nexus uses direct env vars (not the config system). See `kubani/nexus/.env.example`.

---

## Architecture Summary

| Component | Purpose |
|-----------|---------|
| **Framework** | Config, events, MCP client, registry (`kubani/framework/`) |
| **Syndicates** | Multi-agent orchestration: k8s-monitor, news-digest, learning-system |
| **Nexus** | Conversational PI agent (Strands SDK + Temporal entity workflow) |
| **MCP Servers** | Temporal (8081), Qdrant (8082), Memory (8083), Discord (8084), K8s (8080) |
| **Memory** | Qdrant (vectors), Neo4j (graph), Redis (cache/pubsub) |
| **Registry** | Agent/skill/model metadata (`platform/registry/`) |
| **UI** | Agent dashboard (`platform/ui/`) |

---

## Skills

Skills in `.claude/skills/` provide development guidance:

| Skill | Purpose |
|-------|---------|
| `architecture` | Design principles, patterns, component overview |
| `code-standards` | Code patterns, conventions, testing practices |
| `continuous-learning` | Learning system operations |
| `frontend` | UI design guidelines |
| `local-development` | Standard 4-stage development workflow |
| `mcp-integration` | MCP server development and usage |
| `nexus` | Nexus agent architecture and development |
| `skill-developer` | Creating agent runtime skills |
| `workflow-monitor` | Temporal workflow monitoring |

---

## External Services

| Service | URL |
|---------|-----|
| vLLM (LLM) | https://llm.almckay.io/v1 |
| vLLM (Embeddings) | https://embeddings.almckay.io/v1 |
| Qdrant | https://qdrant.almckay.io |
| Neo4j | bolt://neo4j.almckay.io:7687 |
| Redis | redis://redis.almckay.io:6379 |
| Temporal | temporal.almckay.io:7233 |

---

## Plans Lifecycle

Plans live in `docs/plans/` organized by stage:
```
ideas/ → active/ → archive/
```

Check `active/` for current implementation plans. Create new plans in `ideas/` with `YYYY-MM-DD-<name>.md` format.

---

## Getting Help

1. Check the skill for your task: `.claude/skills/`
2. Read the component README
3. Check the docs: `docs/README.md`
4. Review test files for examples
