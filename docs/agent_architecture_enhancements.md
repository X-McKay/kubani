# Agent Architecture Analysis: Scaling the Multi-Agent Ecosystem

## Overview

This document analyzes architectural approaches for scaling the Kubani agent ecosystem as we enhance both k8s-monitor and news-monitor with more sophisticated capabilities. The key questions are:

1. **Skill Library Placement**: Should skill creation be centralized in `core`?
2. **Agent Isolation**: Should each agent remain strictly isolated in its own directory?
3. **Unified Swarm**: Would a single giant swarm spanning all domains be beneficial?

We'll analyze these through the lens of current state, proposed enhancements, and practical trade-offs.

---

## Table of Contents

1. [Current State Summary](#current-state-summary)
2. [Architectural Options](#architectural-options)
3. [Option A: Centralized Skill Library in Core](#option-a-centralized-skill-library-in-core)
4. [Option B: Strict Domain Isolation](#option-b-strict-domain-isolation)
5. [Option C: One Giant Swarm](#option-c-one-giant-swarm)
6. [Option D: Federated Architecture (Recommended)](#option-d-federated-architecture-recommended)
7. [Detailed Trade-off Analysis](#detailed-trade-off-analysis)
8. [News-Monitor Enhancement Considerations](#news-monitor-enhancement-considerations)
9. [Shared vs Domain-Specific Components](#shared-vs-domain-specific-components)
10. [Recommended Architecture](#recommended-architecture)
11. [Migration Path](#migration-path)

---

## Current State Summary

### What We Have Today

```
agents/
├── core/                          # Shared library (v0.2.7)
│   └── src/core_agents/
│       ├── base.py               # create_agent(), create_model()
│       ├── agents/               # DiscordAgent, MemoryAgent
│       ├── memory/               # mem0 config, hierarchical memory
│       ├── intelligence/         # Anomaly, capacity, recurrence
│       ├── communication/        # A2A, saga patterns
│       ├── integrations/         # Discord, Temporal, MCP
│       └── observability/        # Hooks, metrics
│
├── k8s-monitor/                   # Kubernetes monitoring (v0.2.14)
│   └── src/k8s_monitor/
│       ├── worker.py             # Temporal worker
│       ├── workflows.py          # 5 workflows
│       ├── activities.py         # 12 activities
│       ├── agents/               # 6 swarm agents
│       ├── tools.py              # K8s-specific tools
│       ├── memory.py             # Issue/remediation memory
│       └── swarm.py              # Swarm configuration
│
└── news-monitor/                  # AI news monitoring (v0.3.5)
    └── src/news_monitor/
        ├── worker.py             # Temporal worker
        ├── workflows.py          # 9 workflows (4 legacy + 5 new)
        ├── activities.py         # 14 activities
        ├── agents/               # 5 specialized agents
        ├── feeds.py              # RSS feed sources
        ├── memory.py             # Article deduplication
        └── memory_config.py      # News-specific graph prompts
```

### Current Dependency Pattern

```
k8s-monitor ──depends-on──▶ core-agents
news-monitor ─depends-on──▶ core-agents

(core-agents has no dependencies on domain agents)
```

### Core Library Current Contents

| Category | Components | Purpose |
|----------|------------|---------|
| **Base** | `create_agent()`, `create_model()` | Agent factory functions |
| **Agents** | `DiscordAgent`, `MemoryAgent` | Reusable agent implementations |
| **Memory** | mem0 config, hierarchical, facts | Memory system configuration |
| **Intelligence** | Anomaly, capacity, recurrence | Pattern detection algorithms |
| **Communication** | A2A, saga patterns | Cross-agent coordination |
| **Integrations** | Discord, Temporal, MCP | External service connectors |
| **Observability** | Hooks, metrics | Monitoring infrastructure |

---

## Architectural Options

### The Four Approaches

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ARCHITECTURAL OPTIONS                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Option A: Centralized          Option B: Strict Isolation                  │
│  ┌────────────────────┐         ┌────────────────────┐                      │
│  │       CORE         │         │   k8s-monitor      │                      │
│  │  ┌──────────────┐  │         │   (self-contained) │                      │
│  │  │ Skill Library│  │         └────────────────────┘                      │
│  │  │ + Registry   │  │         ┌────────────────────┐                      │
│  │  └──────────────┘  │         │   news-monitor     │                      │
│  └─────────┬──────────┘         │   (self-contained) │                      │
│      ┌─────┴─────┐              └────────────────────┘                      │
│      │           │              (No shared components                       │
│      ▼           ▼               beyond basic library)                      │
│  k8s-mon    news-mon                                                        │
│                                                                              │
│  Option C: Giant Swarm          Option D: Federated                         │
│  ┌────────────────────┐         ┌────────────────────┐                      │
│  │    MEGA SWARM      │         │       CORE         │                      │
│  │  ┌────┐ ┌────┐     │         │  ┌──────────────┐  │                      │
│  │  │K8s │ │News│     │         │  │Skill Library │  │                      │
│  │  │Agt │ │Agt │     │         │  │  Framework   │  │                      │
│  │  └────┘ └────┘     │         │  └──────────────┘  │                      │
│  │  ┌────┐ ┌────┐     │         └─────────┬──────────┘                      │
│  │  │Home│ │Sec │     │               ┌───┴───┐                             │
│  │  │Agt │ │Agt │     │               │       │                             │
│  │  └────┘ └────┘     │          ┌────▼───┐ ┌─▼────┐                        │
│  └────────────────────┘          │k8s-lib │ │news- │                        │
│  (All agents in one              │(skills)│ │lib   │                        │
│   deployment)                    └────┬───┘ └──┬───┘                        │
│                                       │        │                            │
│                                  ┌────▼───┐ ┌──▼────┐                       │
│                                  │k8s-mon │ │news-  │                       │
│                                  │(agent) │ │monitor│                       │
│                                  └────────┘ └───────┘                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Option A: Centralized Skill Library in Core

### Description

Move ALL skill-related functionality into `core-agents`:
- Skill schema and storage
- Skill retrieval and execution
- Skill generation and verification
- Skill library API

Domain agents become thin wrappers that only define domain-specific tools.

### Architecture

```
core/
├── skills/
│   ├── schema.py          # Skill model, categories
│   ├── library.py         # SkillLibrary class
│   ├── retrieval.py       # Semantic search, ranking
│   ├── execution.py       # Safe execution framework
│   ├── generation.py      # LLM skill generation
│   └── verification.py    # Critic/self-verification
├── agents/
│   └── skill_agent.py     # Generic skill-using agent
└── ...existing modules...

k8s-monitor/
├── skills/                # Domain skills only
│   ├── diagnostic/
│   └── remediation/
└── worker.py              # Thin orchestrator
```

### Pros

| Benefit | Impact |
|---------|--------|
| **Single source of truth** | All skill logic in one place |
| **Consistent behavior** | Same verification, execution, storage across domains |
| **Reduced duplication** | One implementation of skill patterns |
| **Easier testing** | Test skill framework in isolation |
| **Cross-domain learning** | Skills could theoretically transfer |

### Cons

| Drawback | Impact |
|----------|--------|
| **Tight coupling** | All agents depend on skill framework changes |
| **Complexity in core** | Core becomes much larger and more complex |
| **Domain leakage** | Risk of domain concepts bleeding into core |
| **Release coordination** | Core changes require all agent updates |
| **Skill semantics differ** | K8s skills vs news skills have different shapes |

### When This Makes Sense

- If we plan many agents (5+) all using skills
- If skills are truly generic and transferable
- If we want a "skill marketplace" across domains

---

## Option B: Strict Domain Isolation

### Description

Each agent is completely self-contained. No shared skill library. Minimal core.

### Architecture

```
core/
├── base.py               # Only create_agent(), create_model()
├── integrations/         # Discord, Temporal (thin wrappers)
└── observability/        # Hooks only

k8s-monitor/
├── skills/               # Full skill implementation
├── memory/               # Full memory implementation
├── agents/               # All K8s-specific agents
└── ...everything else...

news-monitor/
├── skills/               # Independent skill implementation
├── memory/               # Independent memory implementation
├── agents/               # All news-specific agents
└── ...everything else...
```

### Pros

| Benefit | Impact |
|---------|--------|
| **Complete independence** | Change one agent without affecting others |
| **Domain optimization** | Each agent perfectly tuned for its domain |
| **Simple deployment** | No cross-agent dependencies |
| **Clear ownership** | One team owns everything for an agent |
| **Parallel development** | Teams work independently |

### Cons

| Drawback | Impact |
|----------|--------|
| **Massive duplication** | Same patterns reimplemented everywhere |
| **Inconsistent evolution** | Each agent drifts in different directions |
| **No knowledge sharing** | K8s learnings don't help news (and vice versa) |
| **Higher maintenance** | N implementations of similar patterns |
| **Harder onboarding** | Each agent has different patterns to learn |

### When This Makes Sense

- Only 2-3 agents with very different domains
- Different teams with no coordination
- Rapid experimentation where consistency doesn't matter

---

## Option C: One Giant Swarm

### Description

All agents (K8s, news, future home automation, security, etc.) run as one mega-swarm with shared context.

### Architecture

```
kubani-swarm/
├── agents/
│   ├── k8s/              # K8s specialist agents
│   ├── news/             # News specialist agents
│   ├── home/             # Future: home automation
│   └── security/         # Future: security monitoring
├── skills/               # Universal skill library
├── memory/               # Single shared memory
└── orchestrator/         # One swarm to rule them all
```

### Pros

| Benefit | Impact |
|---------|--------|
| **Rich context** | Agents can correlate across domains |
| **Emergent behaviors** | K8s agent might use news insights |
| **Simple architecture** | One deployment, one swarm |
| **Natural A2A** | Handoffs between any agents |
| **Unified memory** | All knowledge in one place |

### Cons

| Drawback | Impact |
|----------|--------|
| **Massive complexity** | Swarm routing becomes very complex |
| **Blast radius** | Bug in one agent affects all |
| **Resource contention** | All agents compete for LLM/memory |
| **Confusing handoffs** | When should K8s agent hand to news agent? |
| **Scaling nightmare** | Can't scale domains independently |
| **Context explosion** | Swarm context grows unbounded |
| **Deployment risk** | Can't deploy one agent without all |

### When This Makes Sense

- Domains genuinely overlap (e.g., "DevOps + Security")
- Small scale with only a few agents
- Strong cross-domain correlations needed

### Why This is Generally Wrong

The Strands Swarm pattern works well when agents have **clear handoff paths** and **shared problem space**. K8s monitoring and AI news have almost no natural handoffs:

```
User: "Why is the vLLM pod crashing?"
K8s Agent: Investigating... Found OOMKilled error.
           Should I hand off to... News Agent?
           (No, that makes no sense)
```

Cross-domain correlations are rare and forced:
- "News about Kubernetes vulnerability" → K8s agent should check for exposure
- This is better handled via **events** than swarm handoffs

---

## Option D: Federated Architecture (Recommended)

### Description

A layered approach that balances shared infrastructure with domain independence:

1. **Core**: Generic frameworks and interfaces
2. **Domain Libraries**: Domain-specific skills, tools, patterns
3. **Domain Agents**: Thin orchestrators using domain libraries

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      FEDERATED ARCHITECTURE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                            CORE (agents/core)                          │ │
│  │                                                                         │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │ │
│  │  │  Skill          │  │  Memory         │  │  Communication  │        │ │
│  │  │  FRAMEWORK      │  │  FRAMEWORK      │  │  FRAMEWORK      │        │ │
│  │  │                 │  │                 │  │                 │        │ │
│  │  │ • Schema        │  │ • Hierarchical  │  │ • A2A Protocol  │        │ │
│  │  │ • Retrieval API │  │ • Consolidation │  │ • Event Bus     │        │ │
│  │  │ • Execution API │  │ • Query API     │  │ • Registry      │        │ │
│  │  │ • Verification  │  │                 │  │                 │        │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘        │ │
│  │                                                                         │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │ │
│  │  │  Intelligence   │  │  Integrations   │  │  Observability  │        │ │
│  │  │                 │  │                 │  │                 │        │ │
│  │  │ • Anomaly       │  │ • Discord       │  │ • Hooks         │        │ │
│  │  │ • Patterns      │  │ • Temporal      │  │ • Metrics       │        │ │
│  │  │ • Forecasting   │  │ • MCP           │  │ • Tracing       │        │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘        │ │
│  │                                                                         │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                     │                                        │
│                      ┌──────────────┴──────────────┐                        │
│                      │                             │                        │
│                      ▼                             ▼                        │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────┐  │
│  │     k8s-skills (NEW LAYER)      │  │    news-skills (NEW LAYER)      │  │
│  │         (agents/k8s-skills)     │  │        (agents/news-skills)     │  │
│  │                                 │  │                                 │  │
│  │  ┌───────────────────────────┐  │  │  ┌───────────────────────────┐  │  │
│  │  │ Diagnostic Skills         │  │  │  │ Collection Skills         │  │  │
│  │  │ • analyze_oom_kill        │  │  │  │ • parse_rss_feed          │  │  │
│  │  │ • trace_network_path      │  │  │  │ • extract_article_content │  │  │
│  │  │ • decode_crash_logs       │  │  │  │ • classify_article        │  │  │
│  │  └───────────────────────────┘  │  │  └───────────────────────────┘  │  │
│  │  ┌───────────────────────────┐  │  │  ┌───────────────────────────┐  │  │
│  │  │ Remediation Skills        │  │  │  │ Analysis Skills           │  │  │
│  │  │ • restart_pod             │  │  │  │ • detect_trending_topics  │  │  │
│  │  │ • scale_deployment        │  │  │  │ • cluster_related_articles│  │  │
│  │  │ • drain_node_safely       │  │  │  │ • assess_importance       │  │  │
│  │  └───────────────────────────┘  │  │  └───────────────────────────┘  │  │
│  │  ┌───────────────────────────┐  │  │  ┌───────────────────────────┐  │  │
│  │  │ K8s Tools                 │  │  │  │ News Tools                │  │  │
│  │  │ • kubectl wrappers        │  │  │  │ • feed parser             │  │  │
│  │  │ • MCP integration         │  │  │  │ • content extractor       │  │  │
│  │  │ • Prometheus queries      │  │  │  │ • similarity checker      │  │  │
│  │  └───────────────────────────┘  │  │  └───────────────────────────┘  │  │
│  │                                 │  │                                 │  │
│  └───────────────┬─────────────────┘  └───────────────┬─────────────────┘  │
│                  │                                    │                    │
│                  ▼                                    ▼                    │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────┐  │
│  │        k8s-monitor              │  │        news-monitor             │  │
│  │      (agents/k8s-monitor)       │  │      (agents/news-monitor)      │  │
│  │                                 │  │                                 │  │
│  │  • Temporal workflows           │  │  • Temporal workflows           │  │
│  │  • Swarm orchestration          │  │  • Agent orchestration          │  │
│  │  • Domain-specific prompts      │  │  • Domain-specific prompts      │  │
│  │  • Configuration                │  │  • Configuration                │  │
│  │                                 │  │                                 │  │
│  └─────────────────────────────────┘  └─────────────────────────────────┘  │
│                                                                              │
│                      ┌──────────────────────────────────┐                   │
│                      │         EVENT BUS (Redis)         │                   │
│                      │                                   │                   │
│                      │  Cross-domain correlation only:   │                   │
│                      │  • news:k8s_vulnerability_found   │                   │
│                      │  • k8s:critical_incident          │                   │
│                      │                                   │                   │
│                      └──────────────────────────────────┘                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Core contains frameworks, not implementations**
   - Skill schema and interfaces, not K8s skills
   - Memory framework, not issue-specific memory
   - Communication protocols, not domain events

2. **Domain libraries contain domain knowledge**
   - K8s skills know about pods, deployments, etc.
   - News skills know about articles, trends, etc.
   - These are pip-installable packages

3. **Domain agents are thin orchestrators**
   - Wire together skills, memory, workflows
   - Define domain-specific prompts and policies
   - Handle Temporal worker registration

4. **Cross-domain via events, not swarms**
   - Agents publish significant events to bus
   - Other agents can subscribe and react
   - No complex swarm routing needed

---

## Detailed Trade-off Analysis

### Comparison Matrix

| Factor | Centralized (A) | Isolated (B) | Giant Swarm (C) | Federated (D) |
|--------|----------------|--------------|-----------------|---------------|
| **Code Reuse** | High | None | High | High |
| **Domain Optimization** | Medium | High | Low | High |
| **Deployment Independence** | Low | High | None | High |
| **Development Velocity** | Medium | High | Low | High |
| **Cross-Domain Learning** | High | None | Implicit | Explicit |
| **Testing Complexity** | Medium | Low | Very High | Medium |
| **Onboarding Ease** | Medium | Low | Low | High |
| **Scaling Flexibility** | Medium | High | Low | High |
| **Consistency** | High | Low | High | High |
| **Blast Radius** | High | None | Very High | Low |

### Decision Factors

**Choose Federated (D) when:**
- Multiple agents with distinct domains (our case)
- Want consistent patterns but domain flexibility
- Need independent scaling and deployment
- Cross-domain correlation is occasional, not constant

**Choose Centralized (A) when:**
- All agents genuinely share the same problem space
- Skills are truly transferable across domains
- Single team owns everything

**Choose Isolated (B) when:**
- Completely different teams with no coordination
- Domains are wildly different with no shared patterns
- Rapid experimentation phase

**Choose Giant Swarm (C) when:**
- Domains are tightly coupled (e.g., "security + compliance")
- Small scale (2-3 agents maximum)
- Strong need for real-time cross-domain handoffs

---

## News-Monitor Enhancement Considerations

### Current News-Monitor Capabilities

| Component | Current State | Enhancement Opportunity |
|-----------|--------------|------------------------|
| **Collection** | RSS parsing, keyword filtering | Skill-based with learning |
| **Analysis** | LLM-based classification | Pattern learning, trend prediction |
| **Memory** | Redis + Qdrant + Neo4j | Hierarchical with consolidation |
| **Trends** | Entity clustering, momentum | Prophet-style forecasting |
| **Publishing** | Discord webhook | Multi-channel, personalized |

### Voyager-Inspired News Enhancements

Applying the same Voyager concepts to news-monitor:

```
┌─────────────────────────────────────────────────────────────────┐
│                 NEWS-MONITOR ENHANCED ARCHITECTURE               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  CONTINUOUS AGENTS                        │   │
│  │                                                           │   │
│  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐  │   │
│  │  │   Ingester   │   │   Analyst    │   │   Prophet    │  │   │
│  │  │   Agent      │   │   Agent      │   │   Agent      │  │   │
│  │  │              │   │              │   │              │  │   │
│  │  │ • RSS watch  │   │ • Classify   │   │ • Trend      │  │   │
│  │  │ • Dedup      │   │ • Extract    │   │   forecast   │  │   │
│  │  │ • Queue      │   │ • Score      │   │ • Breaking   │  │   │
│  │  │              │   │              │   │   predict    │  │   │
│  │  └──────────────┘   └──────────────┘   └──────────────┘  │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  REACTIVE AGENTS                          │   │
│  │                                                           │   │
│  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐  │   │
│  │  │  Composer    │   │  Publisher   │   │   Curator    │  │   │
│  │  │  Swarm       │   │  Agent       │   │   Agent      │  │   │
│  │  │              │   │              │   │              │  │   │
│  │  │ • Narrative  │   │ • Discord    │   │ • Learn      │  │   │
│  │  │ • Summarize  │   │ • Email      │   │ • Document   │  │   │
│  │  │ • Format     │   │ • API        │   │ • Teach      │  │   │
│  │  └──────────────┘   └──────────────┘   └──────────────┘  │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   EXPLORER AGENT                          │   │
│  │                                                           │   │
│  │  • Discover new RSS feeds based on coverage gaps          │   │
│  │  • Generate new classification skills for emerging topics │   │
│  │  • Learn source reliability patterns                      │   │
│  │  • Build entity relationship models                       │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   NEWS SKILL LIBRARY                      │   │
│  │                                                           │   │
│  │  Collection:           Analysis:          Publishing:     │   │
│  │  • parse_rss           • classify_topic   • format_discord│   │
│  │  • extract_content     • extract_entities • summarize     │   │
│  │  • detect_paywall      • score_importance • personalize   │   │
│  │  • find_primary_source • detect_breaking  • schedule      │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Shared Patterns Between K8s and News

| Pattern | K8s Implementation | News Implementation | Abstraction |
|---------|-------------------|---------------------|-------------|
| **Skill Library** | K8s diagnostic/remediation skills | Collection/analysis skills | Skill framework in core |
| **Continuous Watcher** | Sentinel (events, logs) | Ingester (RSS feeds) | Stream processing pattern |
| **Trend Analysis** | Resource usage trends | Topic momentum | Forecasting framework |
| **Memory Consolidation** | Incident → Pattern | Article → Topic | Hierarchical memory |
| **Self-Verification** | Remediation critic | Classification validator | Verification framework |
| **Explorer/Curriculum** | Learn new diagnostics | Discover new sources | Curriculum framework |

---

## Shared vs Domain-Specific Components

### What Should Live in Core

| Component | Rationale | Status |
|-----------|-----------|--------|
| **Skill Schema** | Universal skill representation | NEW - add to core |
| **Skill Retrieval** | Semantic search is generic | NEW - add to core |
| **Skill Verification** | Critic pattern is universal | NEW - add to core |
| **Memory Framework** | Hierarchical pattern is generic | EXISTS - enhance |
| **Event Bus** | Cross-domain communication | NEW - add to core |
| **Agent Registry** | A2A discovery | EXISTS - enhance |
| **Observability** | Metrics, tracing | EXISTS |
| **Base Agents** | Discord, Memory | EXISTS |

### What Should Stay Domain-Specific

| Component | Domain | Rationale |
|-----------|--------|-----------|
| **K8s Skills** | k8s-skills | Domain knowledge (pods, deployments) |
| **K8s Tools** | k8s-skills | kubectl, MCP integration |
| **K8s Prompts** | k8s-monitor | Domain-specific instructions |
| **News Skills** | news-skills | Domain knowledge (articles, feeds) |
| **News Tools** | news-skills | RSS parsing, content extraction |
| **News Prompts** | news-monitor | Domain-specific instructions |
| **Workflows** | each agent | Temporal orchestration |

### Proposed Core Skill Framework

```python
# core/skills/schema.py
from pydantic import BaseModel
from enum import Enum

class SkillCategory(str, Enum):
    DIAGNOSTIC = "diagnostic"
    REMEDIATION = "remediation"
    COLLECTION = "collection"
    ANALYSIS = "analysis"
    OPTIMIZATION = "optimization"
    MONITORING = "monitoring"

class Skill(BaseModel):
    id: str
    name: str
    description: str
    category: SkillCategory
    domain: str  # "k8s", "news", etc.

    # Semantic search fields
    preconditions: list[str]
    success_criteria: list[str]

    # Execution
    code: str
    tools_required: list[str]

    # Composition
    builds_on: list[str]
    composed_of: list[str]

    # Learning
    success_count: int = 0
    failure_count: int = 0
    confidence: float = 0.5

# core/skills/library.py
class SkillLibrary(Protocol):
    """Interface for domain skill libraries."""

    async def search(self, query: str, limit: int = 5) -> list[Skill]: ...
    async def add(self, skill: Skill) -> str: ...
    async def update(self, skill_id: str, updates: dict) -> None: ...
    async def record_outcome(self, skill_id: str, success: bool) -> None: ...

# core/skills/verification.py
class SkillVerifier:
    """Voyager-style skill verification."""

    async def verify(
        self,
        skill: Skill,
        goal: str,
        result: Any,
        before_state: Any,
        after_state: Any,
    ) -> Verification: ...
```

---

## Recommended Architecture

### Final Recommendation: Federated (Option D)

Based on the analysis, the Federated Architecture provides the best balance:

```
agents/
├── core/                          # Frameworks + Interfaces
│   ├── skills/                    # NEW: Skill framework
│   │   ├── schema.py              # Skill model
│   │   ├── library.py             # SkillLibrary interface
│   │   ├── retrieval.py           # Semantic search
│   │   └── verification.py        # Critic/verifier
│   ├── events/                    # NEW: Event bus
│   │   ├── bus.py                 # Redis Streams wrapper
│   │   └── schemas.py             # Event types
│   ├── memory/                    # Enhanced
│   ├── intelligence/              # Enhanced
│   ├── agents/                    # Existing
│   ├── communication/             # Existing
│   ├── integrations/              # Existing
│   └── observability/             # Existing
│
├── k8s-skills/                    # NEW: K8s domain library
│   ├── skills/
│   │   ├── diagnostic/
│   │   └── remediation/
│   ├── tools/
│   └── library.py                 # K8sSkillLibrary(SkillLibrary)
│
├── news-skills/                   # NEW: News domain library
│   ├── skills/
│   │   ├── collection/
│   │   └── analysis/
│   ├── tools/
│   └── library.py                 # NewsSkillLibrary(SkillLibrary)
│
├── k8s-monitor/                   # Orchestrator
│   ├── agents/
│   ├── workflows/
│   └── worker.py
│
└── news-monitor/                  # Orchestrator
    ├── agents/
    ├── workflows/
    └── worker.py
```

### Dependency Graph

```
k8s-monitor ──▶ k8s-skills ──▶ core
news-monitor ──▶ news-skills ──▶ core

# Cross-domain (via events, not direct dependency)
k8s-monitor ◀──events──▶ news-monitor
```

### Cross-Domain Communication

Instead of a giant swarm, use event-driven coordination:

```python
# k8s-monitor publishes
await event_bus.publish("k8s:critical_incident", {
    "type": "OOMKilled",
    "namespace": "vllm",
    "pod": "vllm-xxx",
    "timestamp": now(),
})

# news-monitor subscribes (if relevant)
@event_bus.subscribe("k8s:*")
async def on_k8s_event(event):
    if event.type == "critical_incident":
        # Maybe correlate with recent news about the affected component
        pass

# news-monitor publishes
await event_bus.publish("news:vulnerability_detected", {
    "cve": "CVE-2024-xxx",
    "affects": ["kubernetes", "containerd"],
    "severity": "critical",
})

# k8s-monitor subscribes
@event_bus.subscribe("news:vulnerability_detected")
async def on_vulnerability(event):
    if "kubernetes" in event.affects:
        # Trigger security scan workflow
        await workflow.start(SecurityScanWorkflow, event)
```

---

## Migration Path

### Phase 1: Core Skill Framework (1-2 weeks)

1. Add `skills/` module to core with interfaces
2. Add `events/` module for event bus
3. Keep existing agents unchanged
4. Write tests for new framework

### Phase 2: K8s Skills Extraction (2 weeks)

1. Create `agents/k8s-skills/` package
2. Move existing remediation actions to skills
3. Implement `K8sSkillLibrary`
4. Update k8s-monitor to use new library
5. Maintain backward compatibility

### Phase 3: News Skills Extraction (2 weeks)

1. Create `agents/news-skills/` package
2. Extract collection/analysis patterns as skills
3. Implement `NewsSkillLibrary`
4. Update news-monitor to use new library

### Phase 4: Cross-Domain Events (1 week)

1. Deploy Redis Streams event bus
2. Add event publishers to both agents
3. Add selective event subscriptions
4. Test cross-domain scenarios

### Phase 5: Voyager Enhancements (ongoing)

1. Add Explorer agents to each domain
2. Implement curriculum generation
3. Add skill verification
4. Enable continuous learning

---

## Summary

| Question | Recommendation | Rationale |
|----------|---------------|-----------|
| **Skill creation in core?** | Framework only, not domain skills | Core provides interfaces; domains implement |
| **Strict isolation?** | No, share frameworks | Too much duplication otherwise |
| **One giant swarm?** | No, use events | Domains don't have natural handoffs |
| **Architecture?** | Federated (Option D) | Best balance of reuse and independence |

The Federated Architecture allows us to:
- Share the Voyager-inspired patterns (skill library, verification, curriculum) via core
- Keep domain knowledge where it belongs (k8s-skills, news-skills)
- Maintain deployment independence
- Enable cross-domain correlation via events without complex swarm routing
- Scale each domain independently
- Onboard new domains (home automation, security) cleanly

This approach scales well from 2 agents to 10+ while maintaining consistency and enabling continuous learning across all domains.
