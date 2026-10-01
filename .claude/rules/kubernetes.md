---
paths:
  - "**/*"
---

# Kubernetes Operations Rules

When interacting with the Kubernetes cluster:

## Environment

Always use explicit kubeconfig:
```bash
KUBECONFIG=/home/al/.kube/config kubectl <command>
```

## Safe Operations

These are safe and can be run freely:
- `kubectl get` — read resources
- `kubectl describe` — resource details
- `kubectl logs` — container logs
- `kubectl top` — resource usage
- `kubectl top nodes` compared against the capacity ledger
  (`docs/infrastructure/cluster/capacity.md`, or `just capacity` which does
  the comparison and exits non-zero if any node is over its ceiling)
- `flux get all -A` — Flux state

## Modifying Operations

Use caution with:
- `kubectl apply` — prefer GitOps; use only for emergency fixes
- `kubectl delete` — confirm scope first
- `kubectl scale` — record prior replica count

## Never on Flux-managed workloads

- `kubectl rollout restart` — it works by stamping a `restartedAt` annotation
  on the pod template, and Flux reverts that within its reconcile interval
  (≤10 min). On 2026-09-25 that killed a replacement `vllm` pod 3 minutes into
  weight loading and started a second one, doubling a 5-minute outage into a
  10-minute one. See `docs/troubleshooting/vllm-main-engine-hang-gb10.md`.
- Hand-editing a live Deployment/ConfigMap/etc. with `kubectl edit` or
  `kubectl patch` — same problem, Flux reverts it on the next reconcile.

**Recovery instead:** delete the pod. The Deployment's `Recreate` strategy
makes this a clean restart without touching the spec Flux owns:

```bash
KUBECONFIG=/home/al/.kube/config kubectl delete pod -n vllm -l app=vllm
KUBECONFIG=/home/al/.kube/config kubectl rollout status deployment/vllm -n vllm --timeout=15m
```

(`just inference-restart main` / `just inference-restart fast` wraps this plus
a real-completion check — see `justfile` under "Operations".)

**Stall signature** (from the GB10 runbook — recognize before reaching for
`rollout restart`): `/v1/models` answers normally, chat completions hang
until client timeout, `/health` stays 200 the whole time, and
`vllm:num_requests_running` in `/metrics` is stuck non-zero with generation
throughput at 0 — the EngineCore is wedged in a CUDA kernel while the API
server process (and therefore the liveness probe) is still alive. The fast
model answering on the same GPU confirms only the main engine's CUDA context
is wedged, not the whole GPU. Capture forensics before restarting: `just
incident-capture main` (or `fast`).

## Dangerous Operations

Avoid unless explicitly requested:
- `kubectl delete namespace` — deletes all resources
- `kubectl delete --all` — bulk deletion
- Force deletion with `--force --grace-period=0`

## Debugging

For pod issues:
```bash
# Events for the namespace, newest last
kubectl get events -n <namespace> --sort-by='.lastTimestamp'

# Logs
kubectl logs <pod> -n <namespace> --tail=50
kubectl logs <pod> -n <namespace> --previous   # crashed container

# Exec into pod
kubectl exec -it <pod> -n <namespace> -- /bin/bash
```

## Common Namespaces

- `flux-system` — GitOps
- `cert-manager` — TLS certificates
- `database` — postgres, falkordb, qdrant
- `cache` — redis
- `monitoring` — prometheus, grafana, alertmanager, Alloy, Loki, ntfy (Phase 0)
- `auth` — authentik
- `ai-gateway` — agentgateway (Phase 2: model routing, API-key policy, MCP
  backends in Phase 4) — see `.claude/skills/gateway-onboard/SKILL.md`
- `temporal` — workflows
- `vllm` — LLM inference
- `registry` — cluster image registry
- `longhorn-system` — distributed storage

See `.claude/rules/gitops.md` for the full namespace inventory.
