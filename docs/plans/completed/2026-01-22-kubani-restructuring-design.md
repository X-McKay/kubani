# Kubani Codebase Restructuring Design

> **Status**: Draft
> **Author**: Claude + Al
> **Date**: 2026-01-22
> **Supersedes**: Current `agents/` directory structure

---

## Executive Summary

This document proposes a comprehensive restructuring of the Kubani codebase to better align with the conceptual model of **Skills**, **Agents**, and **Syndicates** as distinct but related concerns:

- **Skills**: Isolated, executable units with clear objectives (aligned with AgentSkills.io standard)
- **Agents**: Roles/personas that use skills to perform specific work
- **Syndicates**: Missions that orchestrate multiple agents to accomplish objectives

The restructuring renames `agents/` to `kubani/` and introduces clear separation between these three concepts, enabling independent development, testing, and evaluation at each layer.

---

## Design Principles

### 1. Clear Separation of Concerns

| Concept | Responsibility | Can Be Tested/Evaluated Independently |
|---------|----------------|--------------------------------------|
| **Skill** | Execute a specific action | Yes - via Skills MCP Server |
| **Agent** | Embody a role, decide which skills to use | Yes - with mocked skills |
| **Syndicate** | Orchestrate agents to achieve a mission | Yes - with mocked agents |

### 2. Skills as MCP Tools

Skills are exposed via a **Skills MCP Server**, providing:
- Sandboxed execution
- Observable invocations (for performance measurement)
- Agent-scoped access control (allowed/denied patterns)
- Alignment with MCP standard

### 3. Python-First, Content-External

Agent definitions follow a minimal Python pattern:
- `agent.py`: Minimal class with behavior/hooks
- `prompt.md`: System prompt (easy to iterate)
- `config.yaml`: Skills manifest and configuration

### 4. Standards Alignment

- **AgentSkills.io**: Skill format (SKILL.md + scripts/ + references/)
- **MCP**: Tool access protocol
- **A2A**: Agent-to-agent discovery and communication
- **Strands SDK**: Agent implementation

---

## Directory Structure

### Top-Level

```
kubani/                          # Renamed from agents/
├── skills/                      # Executable units (AgentSkills.io format)
├── agents/                      # Role/persona definitions
├── syndicates/                  # Multi-agent orchestrations
├── framework/                   # Shared libraries
└── evaluations/                 # Cross-cutting evaluation suites

infrastructure/                  # Unchanged
├── gitops/
├── ansible/
└── sops/

tools/                           # MCP servers and CLI
├── skills-mcp/                  # NEW: Skills MCP Server
├── kubernetes-mcp/
├── temporal-mcp/
├── qdrant-mcp/
├── memory-mcp/
├── discord-mcp/
└── kubani/

platform/                        # Platform services
├── registry/
└── ui/

config/                          # Configuration files
```

### Skills Directory

Following AgentSkills.io standard:

```
kubani/skills/
├── k8s/                              # Domain
│   ├── diagnostic/                   # Category
│   │   └── check-pod-health/         # Individual skill
│   │       ├── SKILL.md              # Skill definition
│   │       ├── scripts/              # Executable scripts
│   │       │   └── check_health.py
│   │       ├── references/           # Additional docs
│   │       ├── assets/               # Static resources
│   │       ├── test.yaml             # Test scenarios
│   │       └── eval/
│   │           └── latest.json
│   ├── remediation/
│   │   ├── restart-crashloop/
│   │   ├── scale-deployment/
│   │   └── drain-node/
│   └── collection/
├── news/
│   ├── collection/
│   ├── analysis/
│   └── publishing/
├── general/
│   ├── notifications/
│   └── memory/
└── _development/                     # Skills in development
```

### Agents Directory

```
kubani/agents/
├── sentinel/
│   ├── agent.py                      # Minimal Python class
│   ├── prompt.md                     # System prompt
│   ├── config.yaml                   # Skills manifest + config
│   ├── tests/
│   └── eval/
├── healer/
├── explorer/
├── analyst/
├── composer/
└── _base/
    └── agent.py                      # KubaniAgent base class
```

### Syndicates Directory

```
kubani/syndicates/
├── k8s-monitor/
│   ├── syndicate.py                  # Orchestration logic
│   ├── config.yaml                   # Agent bindings, schedules
│   ├── workflows/                    # Temporal workflows
│   ├── tests/
│   └── eval/
├── news-digest/
├── incident-response/
└── _base/
    └── syndicate.py                  # Syndicate base class
```

### Framework Directory

```
kubani/framework/
├── __init__.py                       # Public API exports
├── config.py                         # Unified configuration
├── factory.py                        # Agent/Syndicate factory
├── mcp/                              # MCP client integration
│   ├── client.py
│   ├── skills.py                     # Skills MCP client
│   └── registry.py
├── events/                           # Event bus
│   ├── bus.py
│   └── types.py
├── a2a/                              # Agent-to-Agent protocol
│   ├── protocol.py
│   ├── discovery.py
│   └── card.py
├── memory/                           # Memory systems
├── learning/                         # Continuous learning
├── observability/                    # Metrics, tracing
├── temporal/                         # Temporal integration
└── testing/                          # Test utilities
```

---

## Component Designs

### Skills

Skills follow the AgentSkills.io standard with additions for evaluation:

**SKILL.md Format:**
```yaml
---
name: restart-crashloop
description: Restart a pod stuck in CrashLoopBackOff state. Use when pod has restarted multiple times without OOM events.
metadata:
  domain: k8s
  category: remediation
  requires-approval: false
---

# Restart CrashLoopBackOff Pod

## Preconditions
- Pod status is CrashLoopBackOff
- Pod has restarted >3 times
- No OOMKilled events in last 10 minutes

## Actions
1. Delete the pod to trigger recreation
2. Wait for new pod to be scheduled
3. Verify new pod reaches Running state

## Success Criteria
- New pod created within 30s
- New pod reaches Running within 2 minutes
```

**Execution via Skills MCP Server:**
- Skills are loaded from filesystem
- Scripts executed in sandboxed environment
- Outcomes recorded for learning
- Access filtered by agent's skill manifest

### Agents

Agents are minimal Python classes with externalized content:

**agent.py:**
```python
from kubani.agents._base import KubaniAgent

class SentinelAgent(KubaniAgent):
    """Detects and classifies Kubernetes cluster events."""

    async def on_skill_complete(self, skill_name: str, result: dict):
        await self.record_outcome(skill_name, result)

agent = SentinelAgent()
```

**prompt.md:**
```markdown
# Sentinel

You are Sentinel, a vigilant observer of the Kubernetes cluster.

## Responsibilities
- Monitor cluster events and detect anomalies
- Classify events by type and severity
- Alert the Healer agent when remediation is needed
- Never attempt to fix issues yourself

## Workflow
1. Gather context using diagnostic skills
2. Classify the issue (type, severity, affected resources)
3. Post a notification with your findings
4. If remediation is needed, signal the Healer agent
```

**config.yaml:**
```yaml
name: sentinel
description: "Detects and classifies Kubernetes cluster events"
version: "1.0.0"

skills:
  allowed:
    - k8s/diagnostic/*
    - k8s/collection/*
    - general/notifications/post-to-discord
  denied:
    - k8s/remediation/*

capabilities:
  - name: classify-event
    description: "Classify a Kubernetes event by severity and type"
  - name: detect-anomaly
    description: "Analyze cluster state for anomalies"

limits:
  max_tokens: 4096
  timeout_seconds: 300
```

**Base Class:**
```python
class KubaniAgent:
    """Base class that loads config.yaml and prompt.md from agent directory."""

    def __init__(self):
        self._agent_dir = Path(__file__).parent
        self._config = self._load_config()
        self._prompt = self._load_prompt()
        self._agent: Agent | None = None

    @property
    def agent(self) -> Agent:
        if self._agent is None:
            self._agent = Agent(
                system_prompt=self._prompt,
                tools=self._get_tools(),
            )
        return self._agent

    def _get_tools(self) -> list:
        skills_config = self._config.get("skills", {})
        return get_filtered_skills(
            allowed=skills_config.get("allowed", ["*"]),
            denied=skills_config.get("denied", []),
        )

    async def on_skill_complete(self, skill_name: str, result: dict):
        """Override in subclass for custom behavior."""
        pass
```

### Syndicates

Syndicates orchestrate multiple agents:

**syndicate.py:**
```python
from kubani.syndicates._base import Syndicate
from kubani.agents.sentinel import SentinelAgent
from kubani.agents.healer import HealerAgent
from kubani.agents.explorer import ExplorerAgent

class K8sMonitorSyndicate(Syndicate):
    """Keep the Kubernetes cluster healthy."""

    agents = [SentinelAgent, HealerAgent, ExplorerAgent]

    async def run(self):
        sentinel = self.get_agent(SentinelAgent)
        healer = self.get_agent(HealerAgent)

        async for event in sentinel.watch():
            classification = await sentinel.run(f"Classify: {event}")

            if classification.needs_remediation:
                await healer.run(f"Remediate: {classification.summary}")

syndicate = K8sMonitorSyndicate()
```

**Orchestration Patterns:**

| Pattern | Description | Example |
|---------|-------------|---------|
| event-driven | Agents react to events | k8s-monitor |
| pipeline | Sequential transformation | news-digest |
| swarm | Collaborative problem-solving | incident-response |
| dag | Directed acyclic graph | complex workflows |

### Skills MCP Server

New MCP server that exposes skills as tools:

**Responsibilities:**
- Load skills from `kubani/skills/` directory
- Filter skills based on agent identity
- Execute skill scripts in sandboxed environment
- Record outcomes for learning system
- Provide skill metadata for discovery

**API:**
- `tools/list(agent_id)` → Returns filtered skill list
- `tools/call(skill_path, params)` → Executes skill

**Skill Filtering:**
```python
class SkillsMCPClient:
    def get_tools(self, allowed: list[str], denied: list[str]) -> list:
        skills = await self.list_skills()

        filtered = []
        for skill in skills:
            skill_path = skill["name"]

            if denied and any(fnmatch(skill_path, p) for p in denied):
                continue

            if allowed and not any(fnmatch(skill_path, p) for p in allowed):
                continue

            filtered.append(skill)

        return filtered
```

---

## Data Flows

### K8s-Monitor Syndicate

```
Temporal (schedule) → K8sMonitorSyndicate
                            │
                            ▼
                      Sentinel.watch()
                            │
                            ▼
                      Sentinel.classify(event)
                            │
                            │ Uses: k8s/diagnostic/*, k8s/collection/*
                            │       via Skills MCP Server
                            ▼
                      if needs_remediation:
                            │
                            ▼
                      Healer.remediate(classification)
                            │
                            │ Uses: k8s/remediation/*
                            │       via Skills MCP Server
                            ▼
                      EventBus.publish("remediation_complete")
                            │
                            ▼
                      Explorer (hourly) analyzes outcomes
                            │
                            ▼
                      Proposes new skills → Discord approval
```

### News-Digest Syndicate

```
Temporal (8 AM daily) → NewsDigestSyndicate
                            │
                            ▼
                      skill("news/collection/fetch-rss")
                            │
                            ▼
                      skill("news/collection/filter-seen")
                            │
                            ▼
                      AnalystAgent.run("Analyze articles")
                            │
                            │ Uses: general/analysis/*
                            ▼
                      ComposerAgent.run("Write digest")
                            │
                            │ Uses: general/writing/*
                            ▼
                      skill("news/publishing/post-discord")
```

---

## Migration from Current Structure

### Current → New Mapping

| Current | New | Notes |
|---------|-----|-------|
| `agents/core/` | `kubani/framework/` | Reorganized |
| `agents/k8s-monitor/` | `kubani/syndicates/k8s-monitor/` | Becomes syndicate |
| `agents/k8s-monitor/federated/sentinel.py` | `kubani/agents/sentinel/` | Extracted agent |
| `agents/k8s-monitor/federated/healer.py` | `kubani/agents/healer/` | Extracted agent |
| `agents/k8s-monitor/federated/explorer.py` | `kubani/agents/explorer/` | Extracted agent |
| `agents/news-monitor/` | `kubani/syndicates/news-digest/` | Becomes syndicate |
| `agents/skills/` | `kubani/skills/` | Moved |
| `infrastructure/sops/` | `infrastructure/sops/` | Unchanged |

### Migration Strategy

**Phase 1: Foundation**
- Create new directory structure alongside existing
- Implement framework base classes
- Build Skills MCP Server

**Phase 2: Extract Agents**
- Extract Sentinel from k8s-monitor
- Extract Healer from k8s-monitor
- Extract Explorer from k8s-monitor
- Create agent tests/evals

**Phase 3: Create Syndicates**
- Create k8s-monitor syndicate using new agents
- Create news-digest syndicate
- Verify behavior matches current implementation

**Phase 4: Migrate Skills**
- Move skills to new location
- Update to AgentSkills.io format
- Add scripts/ directories where needed

**Phase 5: Cutover**
- Update GitOps to deploy new structure
- Deprecate old structure
- Remove old code

---

## Deployment Model

### Kubernetes Deployments

Each **syndicate** becomes a deployment:

```yaml
# infrastructure/gitops/apps/ai-agents/k8s-monitor/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k8s-monitor
  namespace: ai-agents
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: k8s-monitor
          image: registry.almckay.io/kubani/k8s-monitor:latest
          # Runs the syndicate, which instantiates its agents
```

### MCP Server Deployments

Skills MCP Server is deployed separately:

```yaml
# infrastructure/gitops/apps/ai-agents/skills-mcp/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: skills-mcp
  namespace: ai-agents
spec:
  template:
    spec:
      containers:
        - name: skills-mcp
          image: registry.almckay.io/kubani/skills-mcp:latest
          volumeMounts:
            - name: skills
              mountPath: /skills
              readOnly: true
      volumes:
        - name: skills
          configMap:
            name: kubani-skills  # Or persistent volume
```

---

## Testing and Evaluation

### Skill Testing

```yaml
# kubani/skills/k8s/remediation/restart-crashloop/test.yaml
scenarios:
  - name: successful-restart
    context:
      pod_name: nginx-abc123
      namespace: default
      restart_count: 5
    mocks:
      kubernetes-mcp.pods_delete: { success: true }
    expected:
      success: true

  - name: skip-if-oom
    context:
      recent_oomkill: true
    expected:
      skipped: true
      reason: "OOMKilled in last 10 minutes"
```

### Agent Evaluation

```yaml
# kubani/agents/sentinel/eval/suite.yaml
layers:
  - name: automated
    scenarios:
      - scenarios/skill_selection.yaml

  - name: llm_judge
    scenarios:
      - scenarios/classification_quality.yaml
    judge:
      model: claude-sonnet
      criteria: [accuracy, completeness]

  - name: simulation
    scenarios:
      - scenarios/oom_detection.yaml
    environment:
      mock_kubernetes: true

thresholds:
  automated: { min_pass_rate: 1.0 }
  llm_judge: { min_score: 0.8 }
  simulation: { min_pass_rate: 0.9 }
```

### Syndicate Evaluation

End-to-end evaluation of complete missions:

```yaml
# kubani/syndicates/k8s-monitor/eval/suite.yaml
scenarios:
  - name: detect-and-remediate-crashloop
    setup:
      inject_event:
        type: Warning
        reason: CrashLoopBackOff
    expected:
      sentinel_detected: true
      healer_remediated: true
      outcome: success
```

---

## Resolved Questions

1. **SOPs Location**: **Yes** - SOPs move to `kubani/syndicates/` since they orchestrate skills.

2. **Skill Versioning**: **Yes** - Skills should be versioned. Mechanism TBD during Phase 0 (options: Git tags, semantic version in SKILL.md, registry metadata).

3. **Agent Standalone Deployment**: **No** - Only syndicates are deployed. Agents are instantiated by syndicates.

4. **Hot Reload**: **Research needed** - Investigate during Phase 0/1, implement if feasible.

---

## Success Criteria

1. **Skills can be tested in isolation** via Skills MCP Server
2. **Agents can be tested with mocked skills** without cluster access
3. **Syndicates can be tested with mocked agents** for orchestration logic
4. **Performance impact of skill changes is measurable** via evaluation framework
5. **Current k8s-monitor and news-monitor functionality is preserved** after migration
6. **A2A protocol compliance** for agent discovery and communication

---

## Appendix: Research References

- [AgentSkills.io Specification](https://agentskills.io/specification)
- [Strands Agent Skills Implementation](https://github.com/aws-samples/sample-strands-agents-agentskills)
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25)
- [A2A Protocol](https://google.github.io/A2A/)
- [Skills vs Tools Production Guide](https://blog.arcade.dev/what-are-agent-skills-and-tools)
