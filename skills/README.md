# Kubani Skills Directory

This directory contains all skills for the Kubani agent system. Skills are self-contained, executable units of work that agents can perform.

## Directory Structure

```
skills/
├── development/          # Active development workspace (symlinked from .claude/skills/development)
│   └── <skill-name>/
├── core/                 # General-purpose, cross-agent skills
│   └── <skill-name>/
│       └── v<version>/
└── agents/               # Agent-specific skills
    └── <agent-name>/
        └── <skill-name>/
            └── v<version>/
```

## Skill Lifecycle

1. **Development** (`skills/development/`): Skills under active development
2. **Production** (`skills/core/` or `skills/agents/`): Approved, versioned skills

## Skill Structure

Each skill directory contains:

- `SKILL.md`: Skill definition and documentation
- `skill.py`: Python implementation
- `test_cases.yaml`: Test cases for evaluation
- `latest_eval.json`: Most recent evaluation results

## Usage

### Create a new skill
```bash
kubani-dev skill draft <skill-name> --description "..."
```

### Evaluate a skill
```bash
kubani-dev skill eval <skill-name> --local
```

### Promote to production
```bash
kubani-dev skill promote <skill-name> --category core
```

### List all skills
```bash
kubani-dev skill list
```

## Symlink Note

The `.claude/skills/development` directory is a symlink to `skills/development/`, allowing both Claude Code and cluster tools to access the same development workspace simultaneously.
