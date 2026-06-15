# Infrastructure Decision Record

This page records current decisions for the Kubani cluster. Historical reviews
and planning notes may describe older states.

## K3s And Host Automation

- **K3s remains the Kubernetes distribution.** It fits the homelab footprint
  while preserving the Kubernetes APIs needed by Flux, Helm, cert-manager,
  storage drivers, NetworkPolicy, and the NVIDIA GPU Operator.
- **Ansible owns host state.** It manages prerequisites, Tailscale recovery,
  K3s installation/configuration, kubeconfig handling, node metadata, and host
  tooling.
- **K3s version changes are explicit.** Normal provisioning must not silently
  upgrade K3s. Planned upgrades use `just upgrade-k3s`.
- **The Python interpreter discovery warning is tracked separately.** It should
  be fixed consistently across inventory rather than patched per host.

## GitOps Ownership

- **Flux owns ongoing Kubernetes resources.** Ansible may bootstrap Flux, but it
  should not continuously manage Flux-owned manifests.
- **Flux bootstrap is explicit.** Normal provisioning validates or installs the
  Flux CLI only. Controller/root bootstrap uses `just bootstrap-flux`.
- **Flux drift fails closed.** Flux CLI, controller version, and root
  `GitRepository`/`Kustomization` drift require explicit upgrade or repair
  commands.
- **Root Flux objects are rendered as Kubernetes manifests.** Ansible applies the
  root `GitRepository` and `Kustomization` through `kubectl`, while Flux CLI is
  used for controller install/checks.
- **The repository URL is the SSH form.** Bootstrap uses
  `ssh://git@github.com/X-McKay/kubani` to match the live Flux source and avoid
  avoidable drift.

## Security Posture

- **Registry external access uses BasicAuth, not Authentik.** Docker clients use
  registry auth challenges rather than browser SSO redirects.
- **Registry runtime is minimally hardened.** The registry uses a dedicated
  ServiceAccount with token automount disabled, runs as non-root UID/GID
  `65532`, drops capabilities, disables privilege escalation, uses RuntimeDefault
  seccomp, and has a read-only root filesystem.
- **Only registry storage is writable.** `/var/lib/registry` remains the only
  writable mount unless testing proves another path is required.
- **Pod Security Admission is tiered.** `registry` enforces `restricted`;
  host-integrated infrastructure namespaces enforce `privileged`; application
  namespaces start with `audit=restricted` and `warn=restricted`.
- **Restricted enforcement expands only after review.** Current restricted
  warnings for `neo4j`, `qdrant`, `postgres-backup`, `vllm`, and
  `temporal-db-init` are tracked as follow-up work.
- **Browser admin ingresses use Authentik forward-auth.** Temporal Web, Neo4j
  Browser, and Qdrant HTTP ingress are protected with Traefik `forwardAuth`.
- **vLLM API key is deferred.** It remains acceptable without an API key for now;
  add one later if its exposure boundary changes.

## Deferred Decisions

- **ServiceLB exposure boundary.** Decide whether to restrict Traefik
  LoadBalancer exposure to Tailscale source ranges or replace ServiceLB with
  MetalLB.
- **Monitoring stack.** Decide whether to delete, replace, or revive the current
  monitoring stack.
- **Bitnami/PostgreSQL migration.** Decide when to move PostgreSQL to
  CloudNativePG and how to replace Bitnami Redis.
- **Storage migration.** Decide whether registry and vLLM model storage should
  move off `local-path`.
- **Authentik upgrade.** Do not upgrade beyond chart `2025.10.3` until the
  upstream migration issue is fixed and a restore plan is ready.
