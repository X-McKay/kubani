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
  warnings for `falkordb`, `qdrant`, `postgres-backup`, `vllm`, and
  `temporal-db-init` are tracked as follow-up work.
- **Browser admin auth uses the best native fit.** Temporal Web uses native
  OIDC with Authentik. FalkorDB Browser and Qdrant HTTP ingress use Traefik
  `forwardAuth` backed by Authentik proxy providers and embedded-outpost
  assignment managed through mounted Authentik blueprints.
- **Forward-auth must not be attached speculatively.** An Ingress should only
  reference Authentik middleware after the matching proxy provider and outpost
  assignment are declared and validated.
- **vLLM API key is deferred.** It remains acceptable without an API key for now;
  add one later if its exposure boundary changes.

## Authentik Upgrade

- **Authentik upgrade is no longer an unbounded hold.** Kubani proved the exact
  sequential path from `2025.10.3` to supported `2026.5.6` against an isolated
  restored copy and completed the same bounded live alignment and upgrade
  ladder at revision `a96a321914b964a65a86d8e549a27035f855aa9f`. The provider
  and trust architecture are unchanged, so no new Starbase ADR is required.
  Recovery, drain, migration, activation, and post-activation verification use
  separate review boundaries in the
  [upgrade and recovery plan](operations/authentik-upgrade.md). A direct Helm
  jump and downgrade-based rollback remain prohibited.
- **The failed first rehearsal required exact-fingerprint repair evidence.**
  Rehearsal v1 proved that the current backup carries RBAC migration-history and
  physical-schema state inconsistent with one another after the earlier
  unsupported `2026.2.2` attempt and recovery; the exact recovery action that
  produced the mismatch remains unproven. Rehearsal v2 aligned only an isolated
  restored copy and proved the complete ladder. The later live alignment was
  separately reviewed, fixed-backup-bound, and completed before the ladder;
  its migration merge was the irreversible boundary. Activation does not rerun
  that repair, remove its evidence, or authorize database downgrade.

## Deferred Decisions

- **GitHub/Tailscale workload federation for external Starbase observation.**
  Phase 5 uses the separate Osprey desktop's existing Tailscale identity for
  credential-free pull checks and sends an empty success ping to an independent
  dead-man receiver. This is the simplest sufficient pre-production boundary:
  Osprey is not a Kubani node and receives no Kubernetes, provider, GitHub, or
  Starbase credential. Revisit GitHub OIDC-to-Tailscale federation before
  production or unattended operation, or if Osprey ceases to be a separate,
  reliable observer. Any future federation must separately review repository
  and workflow claims, ephemeral tag ownership, destination/port ACLs, Actions
  cost, revocation, and evidence retention; no trust credential is authorized
  or partially configured by the current decision. Follow-up is owned by Al
  McKay in [issue #90](https://github.com/X-McKay/kubani/issues/90).
- **ServiceLB exposure boundary.** Decide whether to restrict Traefik
  LoadBalancer exposure to Tailscale source ranges or replace ServiceLB with
  MetalLB.
- **Monitoring stack.** Decide whether to delete, replace, or revive the current
  monitoring stack.
- **Bitnami/PostgreSQL migration.** Decide when to move PostgreSQL to
  CloudNativePG and how to replace Bitnami Redis.
- **Storage migration.** Decide whether registry and vLLM model storage should
  move off `local-path`.
