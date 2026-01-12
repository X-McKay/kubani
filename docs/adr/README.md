# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the Kubani project.

## What is an ADR?

An Architecture Decision Record captures an important architectural decision made along with its context and consequences. ADRs help us:

- Document why decisions were made
- Provide context for future developers
- Enable informed decision-making when revisiting choices

## ADR Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| [001](001-unified-configuration.md) | Unified Configuration System | Accepted | 2026-01-11 |
| [002](002-mcp-first-integration.md) | MCP-First Tool Integration | Accepted | 2026-01-11 |
| [003](003-voyager-learning-system.md) | Voyager-Inspired Learning System | Accepted | 2026-01-11 |
| [004](004-federated-agent-pattern.md) | Federated Agent Pattern | Accepted | 2026-01-11 |
| [005](005-registry-centric-architecture.md) | Registry-Centric Architecture | Accepted | 2026-01-11 |

## ADR Template

```markdown
# ADR-XXX: Title

## Status
[Proposed | Accepted | Deprecated | Superseded]

## Context
What is the issue that we're seeing that is motivating this decision or change?

## Decision
What is the change that we're proposing and/or doing?

## Consequences
What becomes easier or more difficult to do because of this change?

## Alternatives Considered
What other options were considered and why were they not chosen?
```

## Creating a New ADR

1. Copy the template above
2. Create a new file: `XXX-short-title.md`
3. Fill in all sections
4. Add to the index table
5. Submit for review
