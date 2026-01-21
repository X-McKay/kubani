# ADR 001: Symlinked Development Workspace

**Date:** 2026-01-20

**Status:** Accepted

## Context

We need a way for both Claude Code and cluster-based tools to access the same skill development workspace. Claude Code operates on files in `.claude/skills/`, while cluster tools and local developers work in the main `skills/` directory.

## Decision

We will use a symbolic link (`symlink`) to create a unified development workspace:

```
.claude/skills/development -> ../../skills/development
```

## Rationale

### Considered Options

1. **Symbolic Link (Chosen)**
   - **Pros:** Single source of truth, no sync issues, simple to implement, works seamlessly with both environments.
   - **Cons:** Requires filesystem support for symlinks (standard on Linux/macOS).

2. **Dual Storage with Sync Script**
   - **Pros:** No symlink dependency.
   - **Cons:** Complex to implement and maintain, risk of sync conflicts, potential for divergence, slower workflow.

3. **Separate Workspaces**
   - **Pros:** Simple to set up.
   - **Cons:** Confusing for developers, requires manual copying, high risk of working on outdated files.

### Justification

The symlink approach is the most elegant and robust solution. It provides a single source of truth, eliminating any possibility of synchronization errors or divergence between the Claude Code and local development environments. This simplicity is crucial for a fast and reliable development workflow.

## Consequences

- Developers must have a filesystem that supports symlinks.
- The `skills/development/` directory becomes the canonical source for all new skill development.
- Any changes made in `.claude/skills/development/` are instantly reflected in `skills/development/` and vice-versa.
