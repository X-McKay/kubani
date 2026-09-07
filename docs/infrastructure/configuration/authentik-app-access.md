# Authentik App Access Pattern

This note captures the preferred Authentik pattern for apps exposed by the Kubani homelab cluster.

## Preferred Split

- Use native OIDC when the application supports it well.
- Use Traefik `forwardAuth` with Authentik for HTTP admin UIs that do not need native SSO.
- Manage Authentik proxy providers, applications, and outpost assignments with
  mounted Authentik blueprints.
- Keep non-HTTP protocols and service-to-service APIs on their own auth model and restrict them to internal or tailnet access.

## Current Examples

- Grafana already uses native Authentik OIDC.
- Temporal Web uses native OIDC with Authentik.
- FalkorDB Browser uses Traefik `forwardAuth` with Authentik.
- Qdrant's HTTP ingress uses Traefik `forwardAuth` with Authentik.
- Prometheus is not part of the current Authentik app-access surface while the
  monitoring stack remains scaled down.

Native OIDC and Traefik `forwardAuth` should be the default patterns for future apps.

Starbase, the previous native OIDC example, was decommissioned on 2026-09-06.
Its blueprint entries remain in the ConfigMap as `state: absent` until the
discovery endpoint is confirmed to return 404.

## Authentik Blueprints

- Proxy-backed apps must be added to
  `infrastructure/gitops/apps/authentik/blueprints-configmap.yaml`.
- The Authentik HelmRelease mounts `authentik-blueprints` through
  `values.blueprints.configMaps`, and Authentik instantiates blueprints labeled
  `blueprints.goauthentik.io/instantiate: "true"`.
- Do not attach `authentik-auth@kubernetescrd` to an Ingress until the matching
  proxy provider and outpost assignment are present in the blueprint.
- Keep the Traefik middleware as a transport integration only. The application,
  provider, external host, internal host, and outpost membership belong in
  Authentik.
- A mounted blueprint is not automatically undone by removing its ConfigMap
  key. First reconcile a reviewed `state: absent` blueprint in dependency
  order, verify the objects and discovery endpoint are gone, then remove the
  file in a follow-up cleanup revision.

## Temporal

- Use Temporal Web's native OIDC integration with Authentik.
- Do not add Traefik `forwardAuth` in front of Temporal Web unless the Authentik
  proxy provider and outpost assignment are managed and validated first.
- Keep the OIDC provider URL on `https://auth.almckay.io` so issuer, browser
  redirects, and TLS names match.

## FalkorDB

- Protect the Browser UI on `falkordb.almckay.io` with Traefik `forwardAuth`.
- The Authentik proxy provider is `Kubani FalkorDB Browser`, with external host
  `https://falkordb.almckay.io` and internal host
  `http://falkordb.database.svc.cluster.local:3000`.
- Do not treat RESP on port `6380` as something Authentik can protect through Traefik HTTP middleware.
- Keep RESP private to the cluster or tailnet unless there is a strong reason to expose it.

FalkorDB is a Redis module, so its wire protocol authenticates with
`requirepass` only — there is no native SSO to fall back on. Ingress-level
protection of the Browser UI plus a strong generated password on the RESP port
is the practical posture.

## Qdrant

- Keep Qdrant's native API-key authentication for API and SDK traffic.
- The external HTTP ingress is protected with Authentik `forwardAuth` for browser access.
- The Authentik proxy provider is `Kubani Qdrant`, with external host
  `https://qdrant.almckay.io` and internal host
  `http://qdrant.database.svc.cluster.local:6333`.
- Do not use Authentik as a replacement for the Qdrant API key.

Qdrant's documented self-hosted security model is API key plus TLS, not full native OIDC.

## Practical Rule

For homelab services, the clean standard is:

- Browser/admin UI: Authentik in front
- Service API: native app auth
- TCP/database protocols: private network access

This keeps the setup understandable, consistent, and avoids pretending every protocol can be solved with one SSO layer.

## Validation

After changing Authentik proxy blueprints:

```bash
flux reconcile helmrelease authentik -n auth
kubectl rollout status deployment/authentik-worker -n auth
```

Unauthenticated browser routes should redirect to Authentik login, not return an
outpost 404:

```bash
curl -skL -o /dev/null -w '%{http_code} %{url_effective}\n' https://falkordb.almckay.io/
curl -skL -o /dev/null -w '%{http_code} %{url_effective}\n' https://qdrant.almckay.io/
```

After changing a native OIDC blueprint, confirm the provider's discovery
endpoint under `https://auth.almckay.io/application/o/<slug>/` reflects the
change, then verify launch access in the Authentik UI with both an authorized
member and a denied non-member.
