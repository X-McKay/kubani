# Kubani Cluster Architecture

This page is the current-state reference for the Kubani homelab cluster. Older
reviews and planning notes are historical records and may describe prior
versions, paths, or incidents.

## Design Choices

- **K3s is the Kubernetes distribution.** It keeps the cluster lightweight while
  preserving the Kubernetes APIs used by Flux, Helm, cert-manager, CSI drivers,
  NetworkPolicy, and the NVIDIA GPU Operator.
- **Tailscale runs on the hosts.** K3s binds node and Flannel traffic to
  `tailscale0`; the Tailscale Kubernetes Operator is intentionally not used.
- **Ansible owns host state.** It bootstraps nodes, installs K3s, manages the
  Tailscale recovery drop-ins, writes K3s config, and applies node metadata.
- **Flux owns cluster resources.** After bootstrap, Kubernetes manifests under
  `infrastructure/gitops/` are reconciled by Flux.
- **SOPS with age is the secret workflow.** Encrypted `*.enc.yaml` files are safe
  to commit; plaintext Kubernetes Secrets should not be committed.
- **Authentik is pinned at chart `2025.10.3`.** Later versions are held until the
  upstream migration regression is fixed.
- **The registry uses BasicAuth.** This is intentional because Docker clients use
  registry auth challenges rather than browser SSO redirects.
- **Temporal Web uses native Authentik OIDC.** It should not also be wrapped in
  Traefik forward-auth unless the Authentik proxy-provider/outpost state is
  explicitly managed.
- **Authentik proxy apps are declarative.** FalkorDB Browser and Qdrant HTTP access
  use Traefik forward-auth only after the Authentik proxy providers,
  applications, and embedded-outpost assignment are declared in mounted
  Authentik blueprints.

## Ownership Boundary

Ansible should stay focused on host-level concerns:

- OS prerequisites and firewall rules
- Tailscale validation and recovery integration
- K3s server/agent install, config, and validation
- node labels, taints, topology metadata, and hardware facts
- Flux CLI host tooling
- explicit initial Flux bootstrap

Flux should own in-cluster concerns:

- Helm repositories and HelmReleases
- namespaces, workloads, services, ingress, and middleware
- NetworkPolicies
- storage classes, PVs, PVCs, and CSI-driver configuration
- SOPS-encrypted Kubernetes Secrets

## GitOps Order

Flux reconciles these layers in order:

1. `infrastructure`
2. `databases`
3. `apps`

The manifests live under `infrastructure/gitops/`. Local validation should use:

```bash
just validate-gitops-build
just validate-flux
```

## Pod Security

Pod Security Admission is rolled out in tiers:

- `registry` enforces `restricted`.
- host-integrated infrastructure namespaces such as `kube-system`,
  `longhorn-system`, `gpu-operator`, CSI driver namespaces, and `flux-system`
  explicitly enforce `privileged`.
- application and platform namespaces start with `audit=restricted` and
  `warn=restricted`; enforcement is deferred until violations are reviewed.

## Do Not Undo Without Review

These constraints came from prior incidents or difficult recovery work:

- Do not remove the K3s/Tailscale recovery drop-ins unless another mechanism
  restores Flannel routes after Tailscale restarts.
- Do not remove the systemd-resolved `kubani-dns.conf` drop-in as redundant; it
  protects host DNS while K3s `resolv-conf` protects pod DNS.
- Do not upgrade Authentik past `2025.10.3` until the upstream migration issue is
  fixed and a restore plan is ready.
- Do not skip Longhorn minor versions during upgrades.
- Do not run the K3s install script on workers without `INSTALL_K3S_EXEC=agent`.
- Do not let normal provisioning silently upgrade K3s. Version changes require
  an explicit upgrade run.
- Do not let normal provisioning silently bootstrap or repair Flux. Controller
  installs, controller upgrades, and root GitOps repair require explicit runs.
- Do not broadly enforce restricted Pod Security without reviewing audit/warn
  violations first. Some infrastructure namespaces intentionally require
  privileged policy.

See also:

- [Infrastructure Decision Record](decisions.md)
- [Cluster Stability Reference](cluster/cluster-stability.md)
- [Cluster audit follow-up](../plans/ideas/2026-05-09-audit-followup.md)
- [Flannel route troubleshooting](../troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md)
