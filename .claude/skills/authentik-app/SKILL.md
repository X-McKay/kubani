---
name: authentik-app
description: Use when putting Authentik in front of a new or existing HTTP service (native OIDC or Traefik forwardAuth), editing an Authentik blueprint, or changing what app/provider/outpost assignment an Ingress uses.
---

# Authentik App

Wraps the procedure in
`docs/infrastructure/configuration/authentik-app-access.md` — read that doc
for the worked examples (Grafana, Temporal, FalkorDB, Qdrant) before
changing a blueprint for the first time.

## Procedure

1. **Pick the row** from the auth decision table
   (`.claude/rules/auth.md` / roadmap 10.5): native OIDC if the app supports
   it well, else Traefik `forwardAuth` for an HTTP admin UI, else (non-HTTP
   protocols) private network plus native credentials. Don't default to
   `forwardAuth` out of habit when native OIDC is on the table — Grafana and
   Temporal Web both use native OIDC today.
2. **Write the blueprint** in
   `infrastructure/gitops/apps/authentik/blueprints-configmap.yaml`: the
   application, the provider (OIDC or proxy), and the outpost assignment for
   a proxy provider. Keep the Traefik middleware as a transport integration
   only — the application/provider/host/outpost all belong in the
   blueprint, not in Traefik config.
3. **Reconcile** the HelmRelease so Authentik picks up the mounted blueprint:
   ```bash
   KUBECONFIG=/home/al/.kube/config flux reconcile helmrelease authentik -n auth
   KUBECONFIG=/home/al/.kube/config kubectl rollout status deployment/authentik-worker -n auth
   ```
4. **Validate** with the curls from the doc — unauthenticated browser routes
   should redirect to Authentik login, not return an outpost 404:
   ```bash
   curl -skL -o /dev/null -w '%{http_code} %{url_effective}\n' https://<host>/
   ```
5. **Auth inventory row**: add the hostname, decision-table row, Authentik
   application name, and rotation date (for a proxy provider with a shared
   secret) to the inventory in
   `docs/infrastructure/configuration/authentik-app-access.md`.

## Red flags: stop (from the pattern doc)

- **Attaching the `authentik-auth@kubernetescrd` forwardAuth middleware to
  an Ingress before the matching proxy provider and outpost assignment
  exist in the blueprint.** The middleware will forward to an outpost that
  doesn't know about the app yet, which fails closed in a confusing way —
  land the blueprint first, confirm the provider and outpost exist, then
  attach the middleware.
- **Removing a blueprint key without a `state: absent` pass first.** A
  mounted blueprint's objects are not automatically undone by deleting its
  ConfigMap key. Reconcile a reviewed `state: absent` blueprint in
  dependency order, verify the objects and the discovery endpoint are
  actually gone, and only then remove the file in a follow-up revision.
- Treating Authentik as a substitute for a service's own auth (Qdrant's API
  key, FalkorDB's `requirepass`) rather than a layer in front of the
  browser-facing UI — see the "Practical Rule" section of the pattern doc.
