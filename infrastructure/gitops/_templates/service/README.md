# Service skeleton

`just new-service <name> <namespace>` copies this directory into
`infrastructure/gitops/apps/<namespace>/<name>/` (or an existing service
directory) and replaces the literal placeholders `SERVICE_NAME` and
`SERVICE_NAMESPACE` with the arguments you gave it. This directory is a
template, not a deployable component: it is never listed in any
`infrastructure/gitops/apps` or `infrastructure/gitops/infrastructure`
kustomization (its `Namespace` placeholder is not a real namespace, and a
directory starting with `_` under `infrastructure/gitops/` is skipped by
every build root — `infrastructure/gitops/infrastructure`,
`infrastructure/gitops/apps/databases`, `infrastructure/gitops/apps`, and
`flux-system` — unless something explicitly lists it, which nothing does).

## What is in the skeleton, and why

| File | Carries | Why it exists |
|---|---|---|
| `deployment.yaml` | requests/limits, restricted `securityContext` (pod and container), a `topology.kubani.io/usage-class` `nodeSelector`, startup/liveness/readiness probes, `reloader.stakater.com/auto`, a digest/sha-pinned image, Prometheus scrape annotations | These are exactly the fields `docs/infrastructure/gitops/guides/deploying-services.md`'s original hand-written example omitted, which is why new services kept arriving without them (roadmap 10.3) |
| `service.yaml` | ClusterIP in front of the pod | Stable in-cluster name for the Ingress and for other services |
| `netpol.yaml` | allow-traefik-ingress, allow-monitoring-scrape, allow-dns-egress, allow-same-namespace, a commented cross-namespace placeholder | Every operational namespace is default-deny ingress; a service with no explicit allow rule is simply unreachable. The namespace-level default-deny itself is not here — see the file's own header |
| `ingress.yaml` | `ingressClassName: traefik`, the cert-manager annotation, TLS, and a commented forwardAuth middleware line | Traefik is the single TLS terminator; external-dns and cert-manager do the rest once the Ingress exists |
| `pdb.yaml` | `minAvailable: 1` | Protects anything that survives a node drain; most singletons here use `Recreate` and do not need it — see the file's own header before adding it |
| `auth.md` | which row of the auth decision table this service uses | Auth model has to be a decision made at scaffold time, not an afterthought once the Ingress is live |

## Checklist before the PR merges

1. Replace `SERVICE_NAME` and `SERVICE_NAMESPACE` everywhere (`just
   new-service` does this for you).
2. Add the service directory to the owning namespace's
   `kustomization.yaml` under `infrastructure/gitops/apps/` (or
   `infrastructure/gitops/infrastructure/` for an infra add-on).
3. Add the namespace's default-deny policy (if this is the first service in
   a new namespace) or the cross-namespace allow rule this service needs
   under `infrastructure/gitops/infrastructure/networking/`.
4. Add a line for the service to
   `docs/infrastructure/cluster/capacity.md` — requests/limits and node,
   per roadmap 9.1 rule 5 ("everything new gets requests and limits... and
   is added to the capacity ledger before the PR merges").
5. Fill in `auth.md` and copy its row into the auth inventory in
   `docs/infrastructure/configuration/authentik-app-access.md`.
6. Run `just validate-local`.
