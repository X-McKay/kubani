---
name: continuous-learning
description: Voyager-inspired continuous learning system with Critic Agent, Reflection Agent, and Discord-based approval workflow for skill proposals.
---

# Continuous Learning System

The continuous learning system enables agents to improve over time through automated analysis, pattern recognition, and skill synthesis.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Learning System                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   Critic    │───▶│ Reflection  │───▶│ Synthesizer │         │
│  │   Agent     │    │   Agent     │    │             │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│        │                  │                   │                 │
│        ▼                  ▼                   ▼                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Shared Memory System                        │   │
│  │  (Qdrant + Neo4j + Redis via Memory MCP)                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Discord Approval Workflow                   │   │
│  │  (Skill proposals → Team review → Auto-deploy)          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### Critic Agent

Evaluates every agent execution and provides structured feedback:

```python
from kubani.framework.learning.voyager import CriticAgent

critic = CriticAgent()
evaluation = await critic.evaluate_execution(
    agent_id="k8s-monitor",
    task_description="Diagnose OOM kill in production",
    execution_result=result,
    context={"namespace": "production"},
)

# Returns:
# - success: bool
# - score: 0.0-1.0
# - feedback: Detailed analysis
# - improvement_suggestions: List of suggestions
# - patterns_identified: Reusable patterns
```

### Reflection Agent

Synthesizes learnings across agents and identifies cross-cutting patterns:

```python
from kubani.framework.learning.voyager import ReflectionAgent

reflection = ReflectionAgent()
insights = await reflection.reflect(
    time_window_hours=24,
    min_interactions=10,
)

# Returns:
# - cross_agent_patterns: Patterns seen across multiple agents
# - knowledge_gaps: Areas needing improvement
# - skill_opportunities: Potential new skills
# - agent_recommendations: Per-agent suggestions
```

### Skill Synthesizer

Proposes new skills based on successful patterns:

```python
from kubani.framework.learning.voyager import SkillSynthesizer

synthesizer = SkillSynthesizer()
proposal = await synthesizer.propose_skill(
    pattern_id="pattern-123",
    examples=successful_executions,
)

# Returns:
# - skill_name: Proposed name
# - skill_content: Full SKILL.md content
# - confidence: 0.0-1.0
# - supporting_evidence: Examples that support this skill
```

## Discord Approval Workflow

### Skill Proposals

When a skill is proposed, it's posted to Discord for review:

```
🆕 New Skill Proposal: k8s/oom-remediation

📋 Description:
Automated remediation for OOM killed pods including
memory analysis and scaling recommendations.

📊 Confidence: 0.87
📈 Based on: 12 successful executions

React to approve:
✅ Approve and deploy
❌ Reject
🔄 Request modifications
```

### Approval Flow

1. **Proposal Posted**: Skill proposal appears in `#learning-proposals`
2. **Team Review**: Team members review and react
3. **Threshold Met**: If ✅ reactions >= threshold, skill is approved
4. **Auto-Deploy**: Approved skills are automatically:
   - Added to the skills library
   - Synced to the registry
   - Available to all agents

### Configuration

```yaml
# config.yaml
learning:
  enabled: true
  critic_enabled: true
  reflection_enabled: true
  auto_approve_threshold: 0.95  # Auto-approve if confidence >= 0.95
  require_discord_approval: true
  min_examples_for_skill: 3
  approval_timeout_hours: 72

discord:
  learning_channel: "learning-proposals"
  approval_reactions:
    approve: "✅"
    reject: "❌"
    modify: "🔄"
  approval_threshold: 2  # Number of approvals needed
```

## Memory Integration

### Storing Learnings

```python
from kubani.framework.memory.shared import SharedMemorySystem

memory = SharedMemorySystem()

# Store a learning
await memory.store_learning(
    agent_id="k8s-monitor",
    learning_type="pattern",  # pattern, anti_pattern, insight, fact
    content="OOM kills in production often indicate need for VPA",
    context={"namespace": "production", "pod": "api-server"},
    confidence=0.85,
    tags=["kubernetes", "memory", "scaling"],
)
```

### Querying Learnings

```python
# Semantic search
learnings = await memory.query_learnings(
    query="kubernetes memory issues",
    agent_id="k8s-monitor",  # Optional filter
    min_confidence=0.7,
    limit=10,
)

# Get agent-specific learnings
agent_learnings = await memory.get_agent_learnings(
    agent_id="k8s-monitor",
    learning_type="pattern",
)
```

### Knowledge Graph

```python
# Store knowledge with relationships
await memory.store_knowledge(
    topic="kubernetes/memory-management",
    content="Best practices for memory management...",
    related_topics=["kubernetes/resources", "kubernetes/vpa"],
)

# Explore knowledge graph
graph = await memory.get_knowledge_graph(
    topic="kubernetes/memory-management",
    depth=2,
)
```

## Commands

### View Learning Status

```bash
# View learning system status
kubani-dev learning status

# View recent learnings
kubani-dev learning list --agent k8s-monitor --last 24h

# View pending proposals
kubani-dev learning proposals
```

### Trigger Learning Cycle

```bash
# Run critic evaluation manually
kubani-dev learning evaluate --agent k8s-monitor

# Run reflection cycle
kubani-dev learning reflect

# Propose skill from pattern
kubani-dev learning propose --pattern pattern-123
```

### Manage Approvals

```bash
# List pending approvals
kubani-dev learning approvals

# Approve a proposal (CLI fallback)
kubani-dev learning approve --proposal proposal-456

# Reject a proposal
kubani-dev learning reject --proposal proposal-456 --reason "Needs more examples"
```

## Best Practices

1. **Start with critic enabled** to collect execution data
2. **Review proposals carefully** before approving
3. **Set appropriate thresholds** for auto-approval
4. **Monitor the learning channel** for new proposals
5. **Provide feedback** on rejected proposals
6. **Track skill effectiveness** after deployment
7. **Periodically review** the knowledge graph

## Monitoring

View learning metrics in the dashboard:

```bash
kubani-dev dashboard
# Navigate to: http://localhost:8080/learning
```

Dashboard shows:
- Learning rate over time
- Skill proposal success rate
- Pattern identification trends
- Knowledge graph visualization
- Agent improvement metrics
