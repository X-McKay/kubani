# GitOps Service Deployment Guide

How to add a new service to the cluster with Flux, starting from the
service skeleton under `infrastructure/gitops/_templates/service/` rather
than hand-writing manifests.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Step 1: Scaffold the service](#step-1-scaffold-the-service)
- [Step 2: Validate locally](#step-2-validate-locally)
- [Step 3: Commit and let Flux deploy it](#step-3-commit-and-let-flux-deploy-it)
- [Step 4: Verify](#step-4-verify)
- [Step 5: Troubleshoot](#step-5-troubleshoot)
- [Worked example](#worked-example)
- [Related documentation](#related-documentation)

## Overview

```
just new-service <name> <namespace>  →  fill in the skeleton  →  just validate-local  →  commit + push  →  Flux applies it  →  verify
```

Flux polls the Git repository and applies changes within about 1 minute,
then each `Kustomization` (`infrastructure`, `databases`, `apps`)
reconciles on its own 10-minute interval on top of that — a push is not
instantaneous, but it is never more than about 10 minutes away without
doing anything by hand. There is no `kubani` CLI in this repo; image
versioning and shipping happen in the workstream that owns each workload
(see `.claude/CLAUDE.md`).

## Prerequisites

- Cluster is provisioned and Flux is healthy (`just flux-status`).
- `KUBECONFIG=/home/al/.kube/config` set, or pass it inline on every
  `kubectl` command — this repo does not use a `.kube/homelab.yaml` path.
- Git repository access.

## Step 1: Scaffold the service

```bash
just new-service my-service platform
```

This copies `infrastructure/gitops/_templates/service/` into
`infrastructure/gitops/apps/platform/my-service/` and replaces the literal
placeholders `SERVICE_NAME` and `SERVICE_NAMESPACE` with the arguments you
gave it (see `infrastructure/gitops/_templates/service/README.md` for the
exact recipe). Each file in the result exists for a reason:

| File | Carries | Why |
|---|---|---|
| `deployment.yaml` | requests/limits, restricted `securityContext` at pod and container level, a `topology.kubani.io/usage-class` `nodeSelector`, startup/liveness/readiness probes, `reloader.stakater.com/auto`, an image pinned by digest or CI sha tag, Prometheus scrape annotations | These are exactly the fields that used to be missing from hand-written manifests in this repo, and the reason `just drift` keeps finding services without them |
| `service.yaml` | a `ClusterIP` in front of the pod | stable in-cluster name for the Ingress and for other services |
| `netpol.yaml` | allow-traefik-ingress, allow-monitoring-scrape, allow-dns-egress, allow-same-namespace, a commented cross-namespace placeholder | every operational namespace is default-deny ingress (see `.claude/rules/gitops.md`); a service with no explicit allow rule is simply unreachable. The namespace's default-deny policy itself lives separately under `infrastructure/gitops/infrastructure/networking/` |
| `ingress.yaml` | `ingressClassName: traefik`, the cert-manager annotation, TLS, a commented forwardAuth middleware line | Traefik is the single TLS terminator; external-dns and cert-manager do the rest once the `Ingress` exists |
| `pdb.yaml` | `minAvailable: 1` | for anything that must survive a node drain; most singletons in this repo use `Recreate` and do not need one — see the file's own comment |
| `auth.md` | which row of the auth decision table this service uses | forces the auth model to be a decision made at scaffold time, not an afterthought once the `Ingress` is already live |

Now fill in the placeholders that are genuinely per-service: the image,
the port, the probe path, resource sizing, and `auth.md`.

## Step 2: Validate locally

```bash
just validate-local
```

This runs inventory validation, the secrets check, and a `kustomize build`
of every root. Testing a deploy with `kubectl apply -k` against the live
cluster before merging is discouraged — it bypasses the PR review the rest
of the GitOps workflow relies on, and a Job or transient object you forget
to clean up is now live outside Git's view of the world. `just
validate-local` plus a PR is the supported pre-merge check; if you need to
see the rendered manifests, `kustomize build
infrastructure/gitops/apps/<namespace>/<name>` is read-only and safe.

## Step 3: Commit and let Flux deploy it

Add the service directory to its namespace's `kustomization.yaml` (or
create one under `infrastructure/gitops/infrastructure/` for an infra
add-on), add the namespace's default-deny policy if this is the first
service in a new namespace, add a line to
`docs/infrastructure/cluster/capacity.md`, then commit and push:

```bash
git add infrastructure/gitops/apps/platform/my-service/
git commit -m "feat(gitops): add my-service"
git push
```

Flux's targets are the three `Kustomization`s `infrastructure`,
`databases`, and `apps` (in that dependency order) — not a `flux-system`
kustomization as such. To force reconciliation instead of waiting:

```bash
KUBECONFIG=/home/al/.kube/config just flux-reconcile
```

or reconcile just one:

```bash
KUBECONFIG=/home/al/.kube/config flux reconcile kustomization apps --with-source
```

## Step 4: Verify

```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -n platform -l app.kubernetes.io/name=my-service
KUBECONFIG=/home/al/.kube/config kubectl rollout status deployment/my-service -n platform
KUBECONFIG=/home/al/.kube/config kubectl get ingress my-service -n platform
```

The hostname is always `<name>.almckay.io` — never `.local`; every
`*.almckay.io` name resolves through Cloudflare to Traefik on the
Tailscale IPs, so it is reachable only from the tailnet (see invariant 1 in
`docs/plans/ideas/2026-09-29-inference-platform-roadmap.md` section 3).

```bash
curl -sk https://my-service.almckay.io/healthz
```

## Step 5: Troubleshoot

```bash
# Pod not starting
KUBECONFIG=/home/al/.kube/config kubectl describe pod -n platform -l app.kubernetes.io/name=my-service

# Logs
KUBECONFIG=/home/al/.kube/config kubectl logs -n platform -l app.kubernetes.io/name=my-service --tail=100
KUBECONFIG=/home/al/.kube/config kubectl logs -n platform -l app.kubernetes.io/name=my-service --previous

# Flux not applying changes — first check for a reconciliation window
# (any commit to main re-reconciles every Kustomization; see
# docs/infrastructure/operations/scheduled-audit.md's "rule out a Flux
# reconciliation window")
KUBECONFIG=/home/al/.kube/config flux get kustomizations
KUBECONFIG=/home/al/.kube/config kubectl logs -n flux-system deployment/kustomize-controller --tail=100

# Not reachable — check the NetworkPolicy before assuming DNS or Traefik
KUBECONFIG=/home/al/.kube/config kubectl get networkpolicy -n platform
KUBECONFIG=/home/al/.kube/config kubectl get endpoints my-service -n platform

# Resource pressure
KUBECONFIG=/home/al/.kube/config kubectl top pods -n platform -l app.kubernetes.io/name=my-service
KUBECONFIG=/home/al/.kube/config kubectl describe pod -n platform -l app.kubernetes.io/name=my-service | grep -A5 'Limits\|Requests'
```

Never `kubectl rollout restart` a Flux-managed Deployment to recover a
stuck pod — Flux reverts the `restartedAt` annotation on its next
reconcile (within 10 minutes), which can kill a replacement pod mid-start
and double an outage. Delete the pod instead; see
`docs/troubleshooting/vllm-main-engine-hang-gb10.md` for the incident this
rule comes from and `.claude/rules/kubernetes.md` for the general rule.

## Worked example

```bash
just new-service web-api platform
# edit infrastructure/gitops/apps/platform/web-api/deployment.yaml:
#   image, containerPort, probe paths, resources
# edit ingress.yaml: confirm the host is web-api.almckay.io
# fill in auth.md
just validate-local
git add infrastructure/gitops/apps/platform/web-api/ docs/infrastructure/cluster/capacity.md
git commit -m "feat(gitops): add web-api service"
git push
KUBECONFIG=/home/al/.kube/config just flux-reconcile
KUBECONFIG=/home/al/.kube/config kubectl rollout status deployment/web-api -n platform
```

## Related documentation

- [Service skeleton](../../../../infrastructure/gitops/_templates/service/README.md) — the template itself and its checklist
- [GitOps Validation Guide](validation.md) — verify Flux is healthy
- [Service Validation Guide](service-validation.md) — validate a deployed service
- [Platform release process](../../operations/release-process.md) — for any hot-path or data-bearing change to an existing service
- [Authentik App Access](../../configuration/authentik-app-access.md) — the auth decision table `auth.md` references
- [Capacity ledger](../../cluster/capacity.md) — add a line here for every new workload
