---
paths:
  - gitops/**/*
---

# GitOps Deployment Rules

When working with Kubernetes manifests in `gitops/`:

## Deployment Changes

- Prefer GitOps over direct kubectl commands
- Changes to `gitops/` are auto-synced by Flux
- After updating manifests, commit and push to trigger deployment

## Image Updates

Use `kubani ship <component>` to update deployment images — it handles manifest patching, version bumping, commit, and push automatically. Do NOT manually edit image tags in deployment manifests.

Manual manifest edits are only appropriate for non-image changes (env vars, resources, probes, etc.).

## Manifest Standards

- Use `app.kubernetes.io/name` label for pod selection
- Include resource requests and limits
- Use ConfigMapRef for model configuration
- Use SecretRef for sensitive data

## Namespace Organization

- `ai-agents`: All AI monitoring and automation agents
- `vllm`: LLM inference service
- `temporal`: Workflow orchestration
- `flux-system`: GitOps controllers

## Verification

After deploying, verify with:
```bash
KUBECONFIG=/home/al/.kube/config kubectl rollout status deployment/<name> -n <namespace>
```
