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

When updating deployment images:
1. Update ALL image references in the deployment
2. Use consistent tag format: `{version}-{sha}`
3. Commit with message: `chore(gitops): deploy <agent>:<version>`

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
