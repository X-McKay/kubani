# Kubani Learning System Architecture

This document describes the Voyager-inspired continuous learning system implemented in Kubani.

## Overview

The learning system enables agents to continuously improve through:
1. **Execution Criticism**: Evaluating task execution quality
2. **Reflection**: Synthesizing learnings across agents
3. **Skill Synthesis**: Proposing new skills from successful patterns
4. **Shared Memory**: Cross-agent knowledge sharing

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
│  │  │   Posted    │    │  (Emoji)    │    │  (if ✅)    │               │ │
│  │  └─────────────┘    └─────────────┘    └─────────────┘               │ │
│  │                                                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Critic Agent

The Critic Agent evaluates agent execution quality using multiple criteria:

```python
@dataclass
class CriticEvaluation:
    execution_id: str
    agent_id: str
    task_description: str
    
    # Scores (0-10)
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

The Reflection Agent synthesizes learnings across all agents:

```python
@dataclass
class ReflectionInsight:
    insight_id: str
    insight_type: str  # pattern, anti_pattern, best_practice, knowledge
    
    title: str
    description: str
    evidence: list[str]  # Execution IDs that support this
    
    applicable_agents: list[str]
    applicable_domains: list[str]
    
    confidence: float
    impact_score: float
```

**Insight Types:**

- **Patterns**: Successful approaches that should be replicated
- **Anti-patterns**: Approaches that lead to failures
- **Best Practices**: General guidelines derived from experience
- **Knowledge**: Domain-specific facts and information

### 3. Skill Synthesizer

The Skill Synthesizer proposes new skills based on successful patterns:

```python
@dataclass
class ProposedSkill:
    skill_id: str
    name: str
    domain: str
    category: str
    
    description: str
    implementation_notes: str
    
    # Evidence
    source_patterns: list[str]
    source_executions: list[str]
    
    # Validation
    test_cases: list[dict]
    estimated_success_rate: float
    
    # Approval
    status: str  # pending, approved, rejected, deployed
    approval_message_id: str | None
```

### 4. Shared Memory System

The shared memory system enables cross-agent knowledge sharing:

```python
class SharedMemorySystem:
    """
    Unified memory interface for all agents.
    
    Storage backends:
    - Qdrant: Vector similarity search for learnings/knowledge
    - Neo4j: Graph relationships between concepts
    - Redis: Fast cache for active state
    """
    
    async def store_learning(
        self,
        agent_id: str,
        learning_type: str,
        content: str,
        context: dict,
        confidence: float,
    ) -> str:
        """Store a learning from an agent."""
        
    async def query_learnings(
        self,
        query: str,
        agent_id: str | None = None,
        learning_type: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 10,
    ) -> list[Learning]:
        """Query learnings using semantic search."""
        
    async def store_knowledge(
        self,
        topic: str,
        content: str,
        source: str,
        related_topics: list[str],
    ) -> str:
        """Store domain knowledge."""
        
    async def get_knowledge_graph(
        self,
        topic: str,
        depth: int = 2,
    ) -> dict:
        """Get knowledge graph around a topic."""
```

## Learning Flow

### 1. Execution Logging

Every agent execution is logged:

```python
# Automatic logging via AgentWorker
class AgentWorker:
    async def execute_task(self, task: Task) -> Result:
        execution_id = generate_id()
        
        # Log start
        await self.logger.log_execution_start(execution_id, task)
        
        try:
            result = await self._execute(task)
            await self.logger.log_execution_success(execution_id, result)
            return result
        except Exception as e:
            await self.logger.log_execution_failure(execution_id, e)
            raise
```

### 2. Critic Evaluation

The Critic Agent periodically evaluates recent executions:

```python
class CriticAgent:
    async def evaluate_recent_executions(self):
        """Evaluate executions from the last hour."""
        executions = await self.get_recent_executions(hours=1)
        
        for execution in executions:
            evaluation = await self.evaluate(execution)
            
            # Store evaluation
            await self.memory.store_evaluation(evaluation)
            
            # Trigger learning if significant
            if evaluation.has_improvement_opportunity:
                await self.trigger_learning(evaluation)
```

### 3. Reflection Synthesis

The Reflection Agent synthesizes insights:

```python
class ReflectionAgent:
    async def synthesize_insights(self):
        """Generate insights from recent evaluations."""
        evaluations = await self.get_recent_evaluations(days=7)
        
        # Identify patterns
        patterns = await self.identify_patterns(evaluations)
        
        for pattern in patterns:
            insight = await self.generate_insight(pattern)
            
            # Store in shared memory
            await self.memory.store_insight(insight)
            
            # Update knowledge graph
            await self.update_knowledge_graph(insight)
```

### 4. Skill Synthesis

The Skill Synthesizer proposes new skills:

```python
class SkillSynthesizer:
    async def propose_skills(self):
        """Propose skills from successful patterns."""
        patterns = await self.get_successful_patterns()
        
        for pattern in patterns:
            if await self.should_create_skill(pattern):
                skill = await self.synthesize_skill(pattern)
                
                # Validate skill
                if await self.validate_skill(skill):
                    # Post for approval
                    await self.post_for_approval(skill)
```

### 5. Discord Approval

Skills are posted to Discord for human approval:

```
📝 **New Skill Proposal**

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
✅ Ingress policy blocking traffic
✅ Egress policy preventing DNS
✅ Missing namespace selector

React to approve:
✅ Approve and deploy
❌ Reject
🔄 Request revisions
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
