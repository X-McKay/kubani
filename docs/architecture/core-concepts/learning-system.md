# Kubani Learning System Architecture

This document describes the Voyager-inspired continuous learning system implemented in Kubani.

## Overview

The learning system enables agents to continuously improve through:
1. **Execution Criticism**: Evaluating task execution quality
2. **Reflection**: Synthesizing learnings across agents
3. **Skill Synthesis**: Proposing new skills from successful patterns
4. **Shared Memory**: Cross-agent knowledge sharing via MCP

## Implementation

The learning system is implemented as a **syndicate** that orchestrates three specialized agents:

| Component | Location | Purpose |
|-----------|----------|---------|
| **LearningSystemSyndicate** | `kubani/syndicates/learning_system/` | Orchestrates learning agents on schedules |
| **CriticAgent** | `kubani/agents/critic/` | Evaluates execution quality |
| **ReflectionAgent** | `kubani/agents/reflection/` | Synthesizes cross-agent insights |
| **SkillSynthesizerAgent** | `kubani/agents/skill_synthesizer/` | Proposes new skills |

### Event Architecture

The learning system uses a hybrid event architecture:

- **Framework events** (`EventType` enum): Cross-cutting concerns like `AGENT_EXECUTION_COMPLETE`
- **Domain events** (local strings): Learning-specific events defined in `kubani/syndicates/learning_system/events.py`

```python
# Framework events (kubani/framework/events/types.py)
from kubani.framework.events import EventType
EventType.AGENT_EXECUTION_COMPLETE  # Triggers learning

# Domain events (kubani/syndicates/learning_system/events.py)
EVALUATION_COMPLETE = "learning:evaluation_complete"
REFLECTION_COMPLETE = "learning:reflection_complete"
SKILL_PROPOSED = "learning:skill_proposed"
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CONTINUOUS LEARNING SYSTEM                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        AGENT EXECUTION LAYER                           │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │ │
│  │  │ k8s-monitor  │  │ news-monitor │  │   other...   │                 │ │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                 │ │
│  │         │                 │                 │                          │ │
│  │         └─────────────────┼─────────────────┘                          │ │
│  │                           │                                            │ │
│  │                           ▼                                            │ │
│  │  ┌────────────────────────────────────────────────────────────────┐   │ │
│  │  │                   INTERACTION LOGGER                            │   │ │
│  │  │  • Task requests & responses                                    │   │ │
│  │  │  • Tool calls & results                                         │   │ │
│  │  │  • Errors & exceptions                                          │   │ │
│  │  │  • Performance metrics                                          │   │ │
│  │  └────────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                         │
│                                    ▼                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         LEARNING AGENTS                                │ │
│  │                                                                        │ │
│  │  ┌──────────────────┐                                                 │ │
│  │  │   CRITIC AGENT   │  Evaluates execution quality                    │ │
│  │  │                  │  • Success/failure analysis                     │ │
│  │  │  ┌────────────┐  │  • Improvement identification                   │ │
│  │  │  │ Evaluation │  │  • Structured feedback                          │ │
│  │  │  │  Criteria  │  │                                                 │ │
│  │  │  └────────────┘  │                                                 │ │
│  │  └────────┬─────────┘                                                 │ │
│  │           │                                                            │ │
│  │           ▼                                                            │ │
│  │  ┌──────────────────┐                                                 │ │
│  │  │ REFLECTION AGENT │  Synthesizes cross-agent learnings              │ │
│  │  │                  │  • Pattern recognition                          │ │
│  │  │  ┌────────────┐  │  • Knowledge extraction                         │ │
│  │  │  │  Pattern   │  │  • Insight generation                           │ │
│  │  │  │  Library   │  │                                                 │ │
│  │  │  └────────────┘  │                                                 │ │
│  │  └────────┬─────────┘                                                 │ │
│  │           │                                                            │ │
│  │           ▼                                                            │ │
│  │  ┌──────────────────┐                                                 │ │
│  │  │ SKILL SYNTHESIZER│  Proposes new skills                            │ │
│  │  │                  │  • Success pattern analysis                     │ │
│  │  │  ┌────────────┐  │  • Skill template generation                    │ │
│  │  │  │  Skill     │  │  • Validation & testing                         │ │
│  │  │  │ Templates  │  │                                                 │ │
│  │  │  └────────────┘  │                                                 │ │
│  │  └────────┬─────────┘                                                 │ │
│  │           │                                                            │ │
│  └───────────┼────────────────────────────────────────────────────────────┘ │
│              │                                                               │
│              ▼                                                               │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                      SHARED MEMORY SYSTEM                              │ │
│  │                                                                        │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐       │ │
│  │  │     QDRANT      │  │     NEO4J       │  │     REDIS       │       │ │
│  │  │  Vector Store   │  │  Knowledge Graph │  │  Session Cache  │       │ │
│  │  │                 │  │                 │  │                 │       │ │
│  │  │ • Learnings     │  │ • Relationships │  │ • Active state  │       │ │
│  │  │ • Knowledge     │  │ • Patterns      │  │ • Metrics       │       │ │
│  │  │ • Skills        │  │ • Dependencies  │  │ • Locks         │       │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘       │ │
│  │                                                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                         │
│                                    ▼                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    DISCORD APPROVAL WORKFLOW                           │ │
│  │                                                                        │ │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐               │ │
│  │  │  Proposal   │───▶│   Review    │───▶│   Deploy    │               │ │
│  │  │   Posted    │    │  (Emoji)    │    │  (if [OK])    │               │ │
│  │  └─────────────┘    └─────────────┘    └─────────────┘               │ │
│  │                                                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Critic Agent

Location: `kubani/agents/critic/`

The Critic Agent evaluates agent execution quality using multiple criteria:

```python
from kubani.agents.critic import CriticAgent
from kubani.agents.critic.models import CriticEvaluation

critic = CriticAgent()
evaluations = await critic.evaluate_recent_executions(hours=24, agent_id="k8s-monitor")

# CriticEvaluation dataclass
@dataclass
class CriticEvaluation:
    execution_id: str
    agent_id: str
    task_description: str

    # Scores (0.0-1.0)
    overall_score: float
    task_completion_score: float
    efficiency_score: float
    safety_score: float
    quality_score: float

    # Analysis
    success: bool
    failure_reason: str | None
    improvement_suggestions: list[str]
    identified_patterns: list[str]

    # Metadata
    confidence: float
    timestamp: datetime
```

**Evaluation Criteria:**

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Task Completion | 0.35 | Did the agent complete the requested task? |
| Efficiency | 0.20 | Was the execution efficient (time, resources)? |
| Safety | 0.25 | Were safety guidelines followed? |
| Quality | 0.20 | Was the output high quality? |

### 2. Reflection Agent

Location: `kubani/agents/reflection/`

The Reflection Agent synthesizes learnings across all agents:

```python
from kubani.agents.reflection import ReflectionAgent
from kubani.agents.reflection.models import ReflectionResult, ReflectionInsight, InsightType

reflection = ReflectionAgent()
result: ReflectionResult = await reflection.reflect(
    time_window_hours=168,  # 1 week
    min_evaluations=10,
)

# ReflectionInsight dataclass
@dataclass
class ReflectionInsight:
    insight_id: str
    insight_type: InsightType  # PATTERN, ANTI_PATTERN, BEST_PRACTICE, KNOWLEDGE, SKILL_OPPORTUNITY
    title: str
    description: str
    evidence: list[str]  # Execution IDs that support this
    applicable_agents: list[str]
    applicable_domains: list[str]
    confidence: float
    timestamp: datetime

# ReflectionResult aggregates insights by type
@dataclass
class ReflectionResult:
    patterns: list[ReflectionInsight]
    anti_patterns: list[ReflectionInsight]
    best_practices: list[ReflectionInsight]
    knowledge: list[ReflectionInsight]
    skill_opportunities: list[ReflectionInsight]
    evaluations_analyzed: int
    agents_analyzed: list[str]
    time_window_hours: int
```

**Insight Types (InsightType enum):**

- **PATTERN**: Successful approaches that should be replicated
- **ANTI_PATTERN**: Approaches that lead to failures
- **BEST_PRACTICE**: General guidelines derived from experience
- **KNOWLEDGE**: Domain-specific facts and information
- **SKILL_OPPORTUNITY**: Potential new skills to create

### 3. Skill Synthesizer Agent

Location: `kubani/agents/skill_synthesizer/`

The Skill Synthesizer proposes new skills based on successful patterns:

```python
from kubani.agents.skill_synthesizer import SkillSynthesizerAgent
from kubani.agents.skill_synthesizer.models import SynthesisResult, SkillProposal

synthesizer = SkillSynthesizerAgent()
result: SynthesisResult = await synthesizer.synthesize_skills()

# SynthesisResult dataclass
@dataclass
class SynthesisResult:
    proposals_created: int
    proposals_posted: int
    proposals: list[SkillProposal]

# SkillProposal dataclass
@dataclass
class SkillProposal:
    skill_id: str
    name: str
    domain: str
    category: str
    description: str
    skill_content: str  # Full SKILL.md content

    # Evidence
    source_patterns: list[str]
    source_executions: list[str]

    # Validation
    confidence: float
    estimated_success_rate: float

    # Approval
    status: str  # pending, approved, rejected, deployed
    approval_message_id: str | None
```

### 4. Shared Memory System

The shared memory system enables cross-agent knowledge sharing via the Memory MCP server:

```python
from kubani.framework.mcp import get_mcp_client

client = get_mcp_client()

# Store a learning
await client.memory.store_learning(
    agent_id="k8s-monitor",
    learning_type="pattern",  # pattern, anti_pattern, insight, fact
    content="OOM kills in production often indicate need for VPA",
    confidence=0.85,
    context={"namespace": "production", "pod": "api-server"},
)

# Query learnings using semantic search
results = await client.memory.search_learnings(
    query="kubernetes memory issues",
    agent_id="k8s-monitor",  # Optional filter
    limit=10,
)
```

**Storage backends (accessed via Memory MCP):**
- **Qdrant**: Vector similarity search for learnings/knowledge
- **Neo4j**: Graph relationships between concepts
- **Redis**: Fast cache for active state and event streaming

## Learning Flow

The Learning System Syndicate orchestrates the learning flow with configurable schedules.

### Syndicate Orchestration

```python
from kubani.syndicates.learning_system import LearningSystemSyndicate

# Run the full learning system
syndicate = LearningSystemSyndicate()
await syndicate.start()

# The syndicate runs three concurrent loops:
# - Critic evaluation (default: hourly)
# - Reflection synthesis (default: daily)
# - Skill synthesis (default: weekly)
# - Event listener (continuous)
```

### 1. Execution Logging

Executions are logged via the event bus. The syndicate listens for `AGENT_EXECUTION_COMPLETE` events:

```python
# In syndicate._listen_for_events()
async for event in self._event_bus.subscribe(
    EventType.AGENT_EXECUTION_COMPLETE,
    consumer_group=self.name,
):
    await self._log_execution(event)
```

### 2. Critic Evaluation

The Critic Agent periodically evaluates recent executions:

```python
# In syndicate._run_critic_loop()
evaluations = await critic.evaluate_recent_executions(hours=1)

if evaluations:
    # Publish domain event
    await self._event_bus.publish(
        EVALUATION_COMPLETE,
        {"evaluations": len(evaluations), "avg_score": avg_score},
        source=self.name,
    )
```

### 3. Reflection Synthesis

The Reflection Agent synthesizes insights:

```python
# In syndicate._run_reflection_loop()
result = await reflection.reflect(
    time_window_hours=interval_hours * 7,  # Look back 1 week
    min_evaluations=10,
)

if result.total_insights > 0:
    await self._event_bus.publish(
        REFLECTION_COMPLETE,
        {"insights": result.total_insights, "patterns": len(result.patterns)},
        source=self.name,
    )
```

### 4. Skill Synthesis

The Skill Synthesizer proposes new skills:

```python
# In syndicate._run_synthesis_loop()
result = await synthesizer.synthesize_skills()

if result.proposals_created > 0:
    await self._event_bus.publish(
        SKILL_PROPOSED,
        {"proposals_created": result.proposals_created},
        source=self.name,
    )
```

### 5. Discord Approval

Skills are posted to Discord for human approval:

```
 **New Skill Proposal**

**Name:** diagnose-network-policy-issues
**Domain:** k8s/diagnostic
**Category:** network

**Description:**
Diagnose pod connectivity issues caused by NetworkPolicy misconfigurations.

**Evidence:**
- 12 successful manual diagnoses in past week
- 89% pattern match with existing network skills
- Estimated 15 min time savings per incident

**Test Cases:**
[OK] Ingress policy blocking traffic
[OK] Egress policy preventing DNS
[OK] Missing namespace selector

React to approve:
[OK] Approve and deploy
[FAIL] Reject
 Request revisions
```

## Memory Schema

### Qdrant Collections

```python
# Learnings collection
{
    "collection": "learnings",
    "vector_size": 1536,
    "distance": "Cosine",
    "payload_schema": {
        "agent_id": "keyword",
        "learning_type": "keyword",
        "content": "text",
        "confidence": "float",
        "timestamp": "datetime",
    }
}

# Knowledge collection
{
    "collection": "knowledge",
    "vector_size": 1536,
    "distance": "Cosine",
    "payload_schema": {
        "topic": "keyword",
        "content": "text",
        "source": "keyword",
        "timestamp": "datetime",
    }
}
```

### Neo4j Schema

```cypher
// Node types
(:Agent {id, name, type})
(:Learning {id, type, content, confidence})
(:Knowledge {id, topic, content})
(:Skill {id, name, domain, category})
(:Pattern {id, type, description})

// Relationships
(Agent)-[:LEARNED]->(Learning)
(Learning)-[:SUPPORTS]->(Pattern)
(Pattern)-[:SUGGESTS]->(Skill)
(Knowledge)-[:RELATED_TO]->(Knowledge)
(Skill)-[:USES]->(Knowledge)
```

## Configuration

```yaml
# config.default.yaml
learning:
  enabled: true
  
  critic:
    evaluation_interval_minutes: 60
    min_executions_for_evaluation: 5
    
  reflection:
    synthesis_interval_hours: 24
    min_evaluations_for_synthesis: 10
    
  synthesizer:
    proposal_interval_hours: 168  # Weekly
    min_pattern_occurrences: 5
    min_success_rate: 0.8
    
  discord:
    approval_channel: "skill-proposals"
    approval_timeout_hours: 72
    
  memory:
    learning_retention_days: 90
    knowledge_retention_days: 365
```

## Integration with News Monitor

The news-monitor integrates with the learning system through emoji feedback:

```python
class NewsFeedbackLearner:
    """Learn from emoji reactions on news posts."""
    
    async def process_feedback(self, reaction: Reaction):
        feedback_type = EMOJI_MAPPING.get(reaction.emoji)
        
        if feedback_type == FeedbackType.POSITIVE:
            # Boost similar topics
            await self.memory.store_learning(
                agent_id="news-monitor",
                learning_type="topic_preference",
                content=f"Users value content about: {reaction.topic}",
                context={"source": reaction.source, "topic": reaction.topic},
                confidence=0.7,
            )
            
        elif feedback_type == FeedbackType.NEGATIVE:
            # Filter similar content
            await self.memory.store_learning(
                agent_id="news-monitor",
                learning_type="topic_filter",
                content=f"Users not interested in: {reaction.topic}",
                context={"source": reaction.source, "topic": reaction.topic},
                confidence=0.6,
            )
```

## Metrics

The learning system tracks:

| Metric | Description |
|--------|-------------|
| `learning.executions_evaluated` | Number of executions evaluated |
| `learning.insights_generated` | Number of insights generated |
| `learning.skills_proposed` | Number of skills proposed |
| `learning.skills_approved` | Number of skills approved |
| `learning.skills_deployed` | Number of skills deployed |
| `learning.memory_queries` | Number of memory queries |
| `learning.memory_stores` | Number of memory stores |

## Future Enhancements

1. **Automated A/B Testing**: Test skill variations automatically
2. **Confidence Decay**: Reduce confidence of old learnings
3. **Cross-Domain Transfer**: Apply learnings across domains
4. **Human-in-the-Loop Training**: Incorporate human feedback
5. **Skill Versioning**: Track skill evolution over time
