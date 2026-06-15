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
- Neo4j Browser uses Traefik `forwardAuth` with Authentik.
- Qdrant's HTTP ingress uses Traefik `forwardAuth` with Authentik.
- Prometheus is not part of the current Authentik app-access surface while the
  monitoring stack remains scaled down.

Native OIDC and Traefik `forwardAuth` should be the default patterns for future apps.

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

## Temporal

- Use Temporal Web's native OIDC integration with Authentik.
- Do not add Traefik `forwardAuth` in front of Temporal Web unless the Authentik
  proxy provider and outpost assignment are managed and validated first.
- Keep the OIDC provider URL on `https://auth.almckay.io` so issuer, browser
  redirects, and TLS names match.

## Neo4j

- Protect the Browser UI on `neo4j.almckay.io` with Traefik `forwardAuth`.
- The Authentik proxy provider is `Kubani Neo4j Browser`, with external host
  `https://neo4j.almckay.io` and internal host
  `http://neo4j.database.svc.cluster.local:7474`.
- Do not treat Bolt on port `7687` as something Authentik can protect through Traefik HTTP middleware.
- Keep Bolt private to the cluster or tailnet unless there is a strong reason to expose it.

Neo4j Community should be treated as an app where ingress-level protection is the practical option. Native Neo4j OIDC/SSO exists, but the official docs describe it as an Enterprise capability.

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
curl -skL -o /dev/null -w '%{http_code} %{url_effective}\n' https://neo4j.almckay.io/
curl -skL -o /dev/null -w '%{http_code} %{url_effective}\n' https://qdrant.almckay.io/
```
