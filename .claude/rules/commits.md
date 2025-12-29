---
paths:
  - "**/*"
---

# Commit Message Rules

Follow conventional commits format:

## Format

```
<type>(<scope>): <description>

[optional body]

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

## Types

- `feat`: New feature
- `fix`: Bug fix
- `chore`: Maintenance, dependencies, config
- `refactor`: Code restructuring
- `docs`: Documentation only
- `test`: Adding/updating tests

## Scopes

- `k8s-monitor`: K8s monitoring agent
- `news-monitor`: News monitoring agent
- `core`: Core agents library
- `gitops`: Kubernetes manifests
- `ansible`: Infrastructure provisioning
- `ci`: CI/CD pipeline

## Examples

```
feat(k8s-monitor): Add workflow health monitoring

fix(gitops): Update news-monitor image to fix ImagePullBackOff

chore(core): Bump version to 0.2.0
```

## Multi-file Changes

When changes span multiple areas, use the most significant scope or omit it:

```
feat: Add new AI agent scaffold command
```
