# ADR-003: Voyager-Inspired Learning System

## Status
Accepted

## Context

AI agents in Kubani need to improve over time based on their execution experiences. Without a structured learning system, agents repeat the same mistakes, fail to generalize from successful patterns, and require manual intervention to add new capabilities.

The Voyager project from MineDojo demonstrated an effective approach to continuous learning in AI agents through a curriculum-based skill acquisition system with automatic verification. We sought to adapt these principles for our Kubernetes operations domain while adding human oversight through Discord-based approval workflows.

## Decision

We implemented a Voyager-inspired continuous learning system with three main components working together in a learning loop.

The **Critic Agent** evaluates every agent execution and provides structured feedback. It runs hourly to analyze recent executions, scoring them on success, efficiency, and adherence to best practices. The critic identifies both successful patterns worth replicating and failure patterns to avoid.

The **Reflection Agent** synthesizes learnings across all agents to identify cross-cutting patterns and knowledge gaps. Running daily, it builds the knowledge graph by connecting related concepts and identifying areas where agents consistently struggle or succeed.

The **Skill Synthesizer** proposes new skills based on successful execution patterns. When the system identifies a pattern that has been successful multiple times across different contexts, the synthesizer generates a complete skill definition including triggers, steps, and expected outcomes.

All proposed skills go through a Discord-based approval workflow before deployment. Team members can approve, reject, or request modifications using emoji reactions. Skills with very high confidence scores (above 0.95) can be auto-approved based on configuration.

## Consequences

### Positive

Agents improve automatically over time without requiring manual skill authoring for every new capability. The system captures institutional knowledge that would otherwise be lost when team members leave or forget past solutions.

The Discord approval workflow provides human oversight while keeping the process lightweight. Team members can review proposals asynchronously and provide feedback without blocking the learning system.

Cross-agent learning through the Reflection Agent means insights from one agent benefit all agents. A pattern discovered by the k8s-monitor can inform the news-monitor's approach to similar problems.

### Negative

The learning system adds complexity to the overall architecture. Three additional agents (Critic, Reflection, Synthesizer) must be maintained and monitored. The Discord integration requires careful handling of rate limits and message formatting.

There is a risk of learning incorrect patterns if the Critic Agent's evaluation criteria are not well-calibrated. Regular review of approved skills is necessary to catch any degradation in quality.

The approval workflow can become a bottleneck if the team does not regularly review proposals. Stale proposals may accumulate, and valuable skills may not be deployed in a timely manner.

### Neutral

The learning system requires significant compute resources for continuous evaluation and synthesis. The hourly critic runs and daily reflection cycles consume LLM tokens and processing time. This cost is offset by the value of automated improvement but should be monitored.

## Alternatives Considered

### Manual Skill Authoring Only

Relying entirely on manual skill creation would ensure quality but would not scale. The team cannot anticipate every scenario agents will encounter, and manual authoring is time-consuming.

### Fully Automated Learning Without Approval

Removing the approval workflow would accelerate skill deployment but risks deploying incorrect or harmful skills. The Discord approval provides a safety net while keeping overhead low.

### Traditional Machine Learning Approach

Using traditional ML for pattern recognition would require labeled training data and periodic retraining. The LLM-based approach can learn from natural language descriptions and generalizes better to novel situations.

### Centralized Learning Service

A separate learning service could handle all learning logic, but this would add another service to maintain and create tight coupling. Embedding learning in the agent framework keeps the system cohesive and allows agents to access learning capabilities directly.
