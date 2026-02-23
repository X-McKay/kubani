# Claude Code Skills

Skills in `.claude/skills/` provide development guidance for Claude Code when working on Kubani.

## Available Skills

| Skill | Purpose |
|-------|---------|
| `architecture/` | Design principles, patterns, component overview |
| `code-standards/` | Code patterns, conventions, testing practices |
| `continuous-learning/` | Learning system operations (Critic, Reflection, Synthesizer) |
| `frontend/` | UI design guidelines for Kubani web interfaces |
| `local-development/` | Standard 4-stage development workflow |
| `mcp-integration/` | MCP server development and usage |
| `nexus/` | Nexus agent architecture and development |
| `skill-developer/` | Creating agent runtime skills |
| `workflow-monitor/` | Temporal workflow monitoring |

## Two Kinds of Skills

- **`.claude/skills/`** (this directory) — Claude Code development guidance. These are documentation skills that help Claude Code understand Kubani's architecture and conventions.
- **`kubani/skills/`** — Agent runtime skills. These are executable skills that agents use at runtime (k8s diagnostics, news analysis, etc.).

## Development Workspace

- `development/` — Symlink to `../../agents/skills/development/`. Active workspace for developing new agent runtime skills.
