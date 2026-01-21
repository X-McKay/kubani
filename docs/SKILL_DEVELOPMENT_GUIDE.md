# Kubani Skill Development Guide

This guide provides a comprehensive walkthrough of the skill development workflow in Kubani. It covers everything from creating your first skill to promoting it to production.

## 1. Overview

The skill development workflow is designed to be **fast, systematic, and agent-driven**. It enables both human developers and AI agents to create high-quality, reliable skills through iterative evaluation.

**Key Principles:**
- **File-Based First:** Simple, works offline, easy to version control.
- **Iterative Evaluation:** Test-driven development for skills.
- **Automatic Versioning:** Semantic versioning handled automatically.
- **Unified Workspace:** Seamless experience for both local and Claude Code development.

## 2. Getting Started

### Prerequisites
- Python 3.11+
- `kubani-dev` CLI installed (`pip3 install -e tools/kubani-dev/`)

### Your First Skill

1. **Draft the skill:**
   ```bash
   kubani-dev skill draft my-first-skill --description "My first skill"
   ```
   This creates a new skill in `skills/development/my-first-skill/` with:
   - `SKILL.md`: Documentation and metadata
   - `skill.py`: Skill implementation skeleton
   - `test_cases.yaml`: Test cases for evaluation

2. **Implement the logic:**
   Open `skills/development/my-first-skill/skill.py` and add your logic to the `execute()` function.

3. **Add test cases:**
   Open `skills/development/my-first-skill/test_cases.yaml` and add test cases to cover different scenarios.

4. **Evaluate locally:**
   ```bash
   kubani-dev skill eval my-first-skill --local
   ```
   This runs your skill against the test cases and provides a detailed report.

5. **Iterate:**
   Fix any issues and re-run the evaluation until all tests pass.

6. **Promote to production:**
   ```bash
   kubani-dev skill promote my-first-skill --category core
   ```
   This automatically bumps the version and moves the skill to `skills/core/my-first-skill/v1.0.0/`.

## 3. CLI Commands

### `kubani-dev skill draft`
Create a new skill from a template.

```bash
kubani-dev skill draft <name> --description "..."
```

### `kubani-dev skill list`
List all skills in development and production.

```bash
kubani-dev skill list
```

### `kubani-dev skill info`
Show detailed information about a skill.

```bash
kubani-dev skill info <name>
```

### `kubani-dev skill eval`
Evaluate a skill locally.

```bash
kubani-dev skill eval <name> --local
```

### `kubani-dev skill eval-history`
View the evaluation history of a skill.

```bash
kubani-dev skill eval-history <name> --limit 5
```

### `kubani-dev skill promote`
Promote a skill to production with automatic versioning.

```bash
# Auto-increment patch version
kubani-dev skill promote <name> --category core

# Auto-increment minor version
kubani-dev skill promote <name> --category core --bump minor

# Specify exact version
kubani-dev skill promote <name> --category core --version 2.0.0
```

## 4. Best Practices

- **Write comprehensive test cases:** Cover both success and failure scenarios.
- **Keep skills focused:** Each skill should do one thing well.
- **Document your skill:** `SKILL.md` is crucial for discovery and usage.
- **Use descriptive names:** Make it easy to understand what the skill does.
- **Iterate frequently:** Run evaluations often to catch issues early.

## 5. Architecture Decisions

For details on the architecture, see the Architecture Decision Records (ADRs) in `docs/adr/`:
- [ADR 001: Symlinked Development Workspace](adr/001-symlinked-development-workspace.md)
- [ADR 002: File-Based First Approach](adr/002-file-based-first-approach.md)

## 6. Migration

Existing skills from `.claude/skills/` have been migrated to the new system. See the migration summary in `tools/kubani-dev/migration_summary.md` for details.

## 7. Future Work

This implementation is the foundation for a complete skill development ecosystem. Future work includes:
- **Database Integration:** Centralized skill registry and evaluation history.
- **Cluster Evaluation:** Running evaluations in a secure cluster environment.
- **Agent-Driven Workflows:** AI agents that create and improve skills.
- **Automated PR Creation:** Automatic PRs for cluster-generated improvements.
