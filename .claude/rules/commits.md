---
paths:
  - "**/*"
---

# Commit Message Rules

Follow conventional commits format.

## Format

```
<type>(<scope>): <description>

[optional body]
```

Multi-line bodies are encouraged when the *why* is non-obvious. Keep the subject under ~72 chars.

## Types

- `feat`: new feature or capability
- `fix`: bug fix
- `chore`: maintenance, dependencies, config
- `refactor`: structural change, no behavior change
- `docs`: documentation only
- `test`: tests only

## Scopes

- `gitops`: Kubernetes manifests under `infrastructure/gitops/`
- `ansible`: host provisioning under `infrastructure/ansible/`
- `scripts`: infra helper scripts
- `docs`: documentation
- `repo`: repo-wide tooling, justfile, pyproject, pre-commit

Use the scope that best matches the bulk of the change. Omit the scope for repo-wide cross-cutting work.

## Examples

```
fix(gitops): add egress NetworkPolicy so backup CronJob can reach postgres

feat(ansible): provisioning role for new GPU worker

chore(repo): tighten pre-commit hooks for SOPS encrypted files

docs(infrastructure): document Tailscale recovery sequence
```
