# Repository Restructuring Design

**Date:** 2026-01-21
**Status:** Approved
**Branch:** `feature/restructure`

---

## Executive Summary

This document outlines an iterative approach to restructuring the Kubani repository to improve cognitive load, deployment isolation, and developer experience. The restructuring prioritizes local-first development, enabling rapid skill and agent iteration outside the cluster.

### Core Objectives

1. **Reduce cognitive load** - Clear top-level directory structure with distinct boundaries
2. **Deployment isolation** - Each component has independent deployment lifecycle
3. **Local-first development** - Develop, test, and evaluate skills/agents locally with confidence they'll work in cluster
4. **Unified architecture** - Single Agent Framework with composable mixins

---

## Target Directory Structure

```
kubani/
├── agents/                    # All AI agents and their ecosystem
│   ├── core/                  # Shared agent framework
│   ├── k8s-monitor/          # Unified K8s monitoring (absorbs cluster-monitor)
│   ├── news-monitor/         # News aggregation
│   ├── learning-agent/       # Continuous learning
│   ├── backup-agent/         # TBD - re-evaluate
│   ├── cluster-swarm/        # Keep - architecture testing
│   ├── evaluations/          # Evaluation suites (moved from root)
│   └── skills/               # Agent runtime skills (moved from root)
│
├── platform/                  # Shared services & libraries
│   ├── registry/             # Metadata registry
│   ├── mcp-common/           # MCP base classes
│   ├── agent-framework/      # NEW - base classes and mixins
│   └── ui/                   # Web interface
│
├── infrastructure/            # Deployment and operations
│   ├── gitops/               # Kubernetes manifests
│   ├── ansible/              # Node provisioning
│   └── scripts/              # Operational scripts
│
├── tools/                     # CLIs and MCP servers
│   ├── kubani-dev/           # Unified CLI (absorbs cluster-mgr)
│   ├── temporal-mcp/         # MCP servers
│   ├── qdrant-mcp/
│   ├── memory-mcp/
│   └── discord-mcp/
│
├── docs/                      # All documentation
│   ├── architecture/
│   ├── development/
│   ├── plans/                # Design documents (like this one)
│   └── archive/              # Historical root markdown files
│
├── config/                    # All configuration files
│   ├── default.yaml
│   ├── production.yaml
│   └── local.yaml.example
│
├── .claude/                   # Claude Code configuration
│   └── skills/               # Development workflow skills (NOT runtime)
│
└── README.md
```

### Key Distinctions

- **`agents/skills/`** = Agent runtime skills (what agents execute)
- **`.claude/skills/`** = Development workflow skills (how Claude Code assists development)

---

## Agent Framework Architecture

### Design Principle

**"Local-first, cluster-ready."** An agent should be runnable with a single command locally, with cluster deployment being purely a packaging/orchestration concern.

### Dual Execution Model

```
┌─────────────────────────────────────────────────────────────┐
│                     kubani-dev CLI                          │
└─────────────────────────────────────────────────────────────┘
          │                                    │
          ▼                                    ▼
┌─────────────────────┐            ┌─────────────────────────┐
│    SkillExecutor    │            │      AgentRunner        │
│                     │            │                         │
│ - Run single skill  │            │ - Run full agent        │
│ - Record traces     │            │ - Orchestrate skills    │
│ - Capture metrics   │            │ - Handle workflows      │
│ - Run evaluations   │            │ - Manage state          │
└─────────────────────┘            └─────────────────────────┘
          │                                    │
          └──────────────┬─────────────────────┘
                         ▼
              ┌─────────────────────┐
              │   Shared Services   │
              │  (LLM, MCP, Memory) │
              └─────────────────────┘
```

### Core Abstractions

```python
class AgentBase:
    """Base class for all agents."""

    def initialize(self) -> None: ...
    def run(self) -> None: ...
    def shutdown(self) -> None: ...

class SkillExecutor:
    """Execute and evaluate skills in isolation."""

    def execute(self, skill_name: str, context: dict) -> SkillResult: ...
    def evaluate(self, skill_name: str, suite: EvalSuite) -> EvalReport: ...
    def record(self, execution: SkillResult) -> None: ...

class AgentRunner:
    """Run full agents in local or cluster mode."""

    def run_local(self, agent: AgentBase) -> None: ...
    def run_cluster(self, agent: AgentBase) -> None: ...
```

### Mixins (Composable Capabilities)

| Mixin | Responsibility |
|-------|---------------|
| `MCPClientMixin` | Connect to MCP servers (auto-discovers local vs cluster endpoints) |
| `SkillLoaderMixin` | Load and execute skills from `agents/skills/` |
| `MemoryMixin` | Unified memory interface (Qdrant, Neo4j, Redis) |
| `ObservabilityMixin` | Structured logging, metrics, tracing |
| `LLMClientMixin` | LLM access with provider abstraction |
| `TemporalMixin` | Workflow/activity registration (cluster mode only) |

### AgentRunner Modes

```bash
# Local development - single process, direct execution
kubani-dev local-run --agent k8s-monitor

# Local with cluster services - connects to remote LLM/MCP
kubani-dev local-run --agent k8s-monitor --services cluster

# Cluster mode - Temporal worker, full orchestration
python -m k8s_monitor.worker
```

---

## Developer Workflow

### Skill Development Lifecycle

```
  1. CREATE                2. EVALUATE              3. ITERATE
  ┌──────────┐            ┌──────────────┐         ┌──────────┐
  │ skill-   │  ───────►  │ Auto-gen     │ ──────► │ Compare  │
  │ developer│            │ eval suite + │         │ versions │
  │          │            │ test data    │         │ & models │
  └──────────┘            └──────────────┘         └──────────┘
```

### CLI Commands

```bash
# Create new skill with auto-generated eval
kubani-dev skill create investigate-oom-kill \
  --category k8s/diagnostic \
  --description "Diagnose OOM killed pods"

# Run skill once to test
kubani-dev skill run investigate-pod-failure \
  --context '{"pod": "nginx-abc", "namespace": "default"}' \
  --trace

# Run evaluation suite
kubani-dev skill eval investigate-pod-failure

# Run with model comparison matrix
kubani-dev skill eval investigate-pod-failure \
  --matrix "model:opus,haiku thinking:on,off" \
  --report comparison

# Run full agent
kubani-dev agent run k8s-monitor \
  --trigger '{"event": "pod_crash", "pod": "nginx-abc"}'

# Evaluate agent end-to-end
kubani-dev agent eval k8s-monitor \
  --suite agents/evaluations/k8s/full_remediation.yaml
```

### Simple Developer Experience

```bash
# 1. Create a skill
kubani-dev skill create my-new-skill --category k8s/diagnostic

# 2. Edit the skill definition
$EDITOR agents/skills/k8s/my-new-skill/skill.md

# 3. Run it once to test
kubani-dev skill run my-new-skill --context '{"pod": "test"}'

# 4. Run full eval suite
kubani-dev skill eval my-new-skill

# 5. Compare models
kubani-dev skill eval my-new-skill --matrix "model:opus,haiku"

# 6. Commit and deploy
git add agents/skills/k8s/my-new-skill/
git commit -m "feat(skills): add my-new-skill"
kubani-dev deploy --agent k8s-monitor
```

---

## Trace Persistence

### Backend Abstraction

Pluggable backends with OpenTelemetry compatibility for future adoption of Langfuse, Tempo, etc.

```python
class TraceBackend(Protocol):
    async def record(self, trace: ExecutionTrace) -> str: ...
    async def query(self, filters: TraceQuery) -> list[ExecutionTrace]: ...
    async def get_metrics(self, skill: str, window: timedelta) -> SkillMetrics: ...
```

### Backend Options

| Backend | Use Case |
|---------|----------|
| **JSONL files** (default) | Quick local iteration |
| **SQLite** | Local dev with query capability |
| **OpenTelemetry** | Production, Grafana/Langfuse integration |

### Configuration

```yaml
# config/default.yaml
traces:
  backend: jsonl
  path: ${skill_dir}/traces/

# config/production.yaml
traces:
  backend: opentelemetry
  endpoint: https://tempo.almckay.io
```

### Trace Format (OTEL Compatible)

```python
@dataclass
class ExecutionTrace:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str           # "skill.investigate-pod-failure"
    kind: str           # "skill" | "agent" | "llm_call" | "tool_call"
    start_time: datetime
    end_time: datetime
    attributes: dict    # skill_version, model, thinking_enabled
    events: list[TraceEvent]
    metrics: dict       # tokens, latency, accuracy
```

---

## Implementation Phases

### Phase 1: Structure & Move (Low Risk)

**Objective:** Establish clean directory boundaries.

**Changes:**
- `gitops/` + `ansible/` → `infrastructure/`
- `registry/` → `platform/registry/`
- `tools/mcp-common/` → `platform/mcp-common/`
- `evaluations/` + `skills/` → `agents/`
- Root `.md` files (except README) → `docs/archive/`
- `config.*.yaml` → `config/`

**Validation:** All tests pass, CI/CD pipelines work, deployments unchanged.

**Rollback:** `git revert`

---

### Phase 2: Agent Framework Foundation (Low Risk)

**Objective:** Establish target architecture before migration.

**Changes:**
- Create `platform/agent-framework/` with base classes and mixins
- Comprehensive test suite for framework
- Example agent demonstrating patterns

**Validation:** Framework tests pass, example agent runs locally.

**Rollback:** Not needed—additive only.

---

### Phase 3: Unified Skills System (Medium Risk)

**Objective:** Single skill loading mechanism.

**Changes:**
- Skills loaded from `agents/skills/`
- New SkillExecutor implementation
- Feature flag for gradual rollout

**Validation:**
```bash
kubani-dev skill run <skill> --loader v2
KUBANI_SKILLS_V2=true kubani-dev local-run --agent k8s-monitor
```

**Rollback:** Set `skills_v2: false` in config.

---

### Phase 4: Local Development Experience (Low Risk)

**Objective:** Complete local development workflow.

**Changes:**
- Enhanced `kubani-dev skill` commands
- Model comparison matrix evaluation
- Trace persistence with backend abstraction

**Validation:** Full skill development cycle works locally.

**Rollback:** Previous CLI version.

---

### Phase 5: Agent Consolidation (High Risk)

**Objective:** Merge cluster-monitor into k8s-monitor.

**Changes:**
- Migrate cluster-monitor patterns to use new framework
- Blue-green deployment with shadow mode
- Decommission cluster-monitor after validation

**Deployment Strategy:**
```
Week 1: Deploy new k8s-monitor in shadow mode (receives events, doesn't act)
Week 2: Enable as leader, cluster-monitor to shadow
Week 3: Decommission cluster-monitor
```

**Validation:**
```bash
kubani-dev compare-decisions --agent1 cluster-monitor --agent2 k8s-monitor
```

**Rollback:** Re-enable cluster-monitor as leader.

---

### Phase 6: CLI & Config Consolidation (Medium Risk)

**Objective:** Single CLI, unified configuration.

**Changes:**
- Migrate cluster-mgr commands to kubani-dev
- All config in `config/` directory
- Clear precedence: default → env → local → env vars

**Validation:** All operational commands work via kubani-dev.

**Rollback:** Alias old commands.

---

## Risk Mitigation Summary

| Phase | Risk | Blast Radius | Rollback |
|-------|------|--------------|----------|
| 1. Structure & Move | Low | None | `git revert` |
| 2. Agent Framework | Low | None | Don't use new classes |
| 3. Unified Skills | Medium | Skill loading | Feature flag |
| 4. Local Dev Experience | Low | CLI only | Previous version |
| 5. Agent Consolidation | High | K8s monitoring | Blue-green |
| 6. CLI & Config | Medium | Developer workflow | Alias old commands |

### Continuous Validation

Every phase includes:
1. **Pre-merge:** All tests pass, dry-run deployments work
2. **Post-merge:** Smoke tests in staging
3. **Production:** Gradual rollout with feature flags
4. **Monitoring:** Alert on error rate/latency changes

---

## Open Questions

1. **backup-agent disposition** - Re-evaluate during Phase 1
2. **Trace backend selection** - Start with JSONL/SQLite, adopt Langfuse/Tempo later
3. **cluster-swarm** - Keep for architecture testing, don't migrate

---

## Next Steps

1. Begin Phase 1: Structure & Move
2. Create detailed task breakdown for each phase
3. Set up feature flags infrastructure for Phase 3+
