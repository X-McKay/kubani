# CLAUDE.md

Guidance for Claude Code when working on the Kubani infrastructure repository.

This repo owns provisioning, GitOps, and operations for the homelab cluster. Runtime code, MCP server implementations, and UI code live in separate workstreams — see [docs/infrastructure/repository-scope.md](../docs/infrastructure/repository-scope.md).

---

## Working Principles

### Think Before Coding
State assumptions explicitly. Surface tradeoffs. If uncertain, ask.

### Surgical Changes
Touch only what you must. Don't improve adjacent code. Match existing style. Remove only orphans your changes created.

### Goal-Driven Execution
Transform tasks into verifiable goals. State a brief plan with verification steps. Loop until verified.

### GitOps First
Cluster state is defined in `infrastructure/gitops/` and reconciled by Flux. Prefer committed manifests over imperative `kubectl apply`. Use `kubectl` for inspection, debugging, and time-sensitive recovery.

---

## Repository Layout

```
infrastructure/
├── ansible/          # Host bootstrap and K3s provisioning
├── gitops/           # Flux-managed Kubernetes manifests
├── scripts/          # Infrastructure helpers and validation
└── sops/             # Encrypted secret material policy
docs/
├── infrastructure/   # Cluster, configuration, gitops, operations runbooks
├── troubleshooting/  # Incident playbooks and known issues
└── plans/            # In-flight and archived planning docs
justfile              # Common task runner recipes
pyproject.toml        # Ansible / tooling dependencies (uv-managed)
```

---

## Common Commands

```bash
# Setup (one-time)
just setup

# Ansible
just inventory                    # Validate inventory
just ansible-ping                 # Reachability check
just provision                    # Provision/reconcile all hosts
just provision-host <host>        # One host
just preflight                    # Pre-provision checks
just lint                         # ansible-lint

# Validation
just validate-local               # Inventory + secrets + kustomize build
just validate-gitops-build        # kustomize build all roots
just validate-flux                # Flux Kustomization validation
just validate-cluster             # Runtime cluster checks
just secrets-check                # Verify .enc.yaml files are encrypted

# Cluster inspection
just nodes                        # kubectl get nodes -o wide
just pods                         # kubectl get pods -A
just pods-ns <ns>                 # Pods in a namespace
just flux-status                  # flux get all -A
just flux-reconcile <kustomization>

# Pre-commit
just check                        # Run all pre-commit hooks
```

Always set kubeconfig explicitly: `KUBECONFIG=/home/al/.kube/config kubectl ...`

---

## Cluster Architecture

The cluster runs on a single LAN site, with K3s bound to Tailscale. Key invariants:

- **Topology labels** drive workload placement — use `topology.kubani.io/` labels, not hostnames
- **Service tiers**: core (always on) → platform (always on) → optional (`replicas: 0` by default)
- **Storage**: Longhorn for stateful data, `local-path` for caches, NAS for model weights
- **Network**: default-deny ingress in every operational namespace; explicit allow rules for each cross-namespace path
- **Tailscale recovery**: K3s is bound to Tailscale via systemd drop-in — automatic route recovery on Tailscale restart

See [Cluster Stability Reference](../docs/infrastructure/cluster/cluster-stability.md) for the full reference.

---

## External Services

| Service | URL |
|---------|-----|
| vLLM (LLM) | https://llm.almckay.io/v1 |
| vLLM (Embeddings) | https://embeddings.almckay.io/v1 |
| Qdrant | https://qdrant.almckay.io |
| FalkorDB (graph) | redis://falkordb.almckay.io:6380 |
| Redis | redis://redis.almckay.io:6379 |
| Temporal | temporal.almckay.io:7233 |
| Container registry | registry.almckay.io |

---

## Workflow

1. **Edit manifests / playbooks**
2. **Validate locally** — `just validate-local` and any relevant `just lint` / `just check`
3. **Commit and push** — Flux reconciles GitOps changes automatically
4. **Verify** — `just flux-status`, watch the affected namespace, check `kubectl rollout status` if needed

For non-image manifest changes (env vars, resources, probes, network policies, etc.), edit the YAML directly. There is no longer a `kubani` CLI in this repo — image versioning and shipping happen in the workstreams that own each workload.

---

## Plans

Plans live in `docs/plans/` organized by stage:
```
ideas/ → active/ → archive/
```
Create new plans in `ideas/` with `YYYY-MM-DD-<name>.md` format.

---

## Getting Help

1. Check `.claude/rules/` for workflow rules (gitops, kubernetes, secrets, commits)
2. Check `.claude/commands/` for runnable diagnostic commands
3. Read [docs/infrastructure/README.md](../docs/infrastructure/README.md) for the runbook hub
4. Read [docs/troubleshooting/](../docs/troubleshooting/) for known issues
