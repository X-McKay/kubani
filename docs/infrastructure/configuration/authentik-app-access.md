# Authentik App Access Pattern

This note captures the preferred Authentik pattern for apps exposed by the Kubani homelab cluster.

## Preferred Split

- Use native OIDC when the application supports it well.
- Use Traefik `forwardAuth` with Authentik for HTTP admin UIs that do not need native SSO.
- Keep non-HTTP protocols and service-to-service APIs on their own auth model and restrict them to internal or tailnet access.

## Current Examples

- Grafana already uses native Authentik OIDC.
- Prometheus already uses Traefik `forwardAuth` with Authentik.

These two patterns should be the default for future apps.

## Neo4j

- Protect the Browser UI on `neo4j.almckay.io` with Traefik `forwardAuth`.
- Do not treat Bolt on port `7687` as something Authentik can protect through Traefik HTTP middleware.
- Keep Bolt private to the cluster or tailnet unless there is a strong reason to expose it.

Neo4j Community should be treated as an app where ingress-level protection is the practical option. Native Neo4j OIDC/SSO exists, but the official docs describe it as an Enterprise capability.

## Qdrant

- Keep Qdrant's native API-key authentication for API and SDK traffic.
- If the HTTP endpoint remains externally reachable for human access, protect that ingress with Authentik `forwardAuth`.
- Do not use Authentik as a replacement for the Qdrant API key.

Qdrant's documented self-hosted security model is API key plus TLS, not full native OIDC.

## Practical Rule

For homelab services, the clean standard is:

- Browser/admin UI: Authentik in front
- Service API: native app auth
- TCP/database protocols: private network access

This keeps the setup understandable, consistent, and avoids pretending every protocol can be solved with one SSO layer.
