# Live Service Probes

Live service probes are opt-in operational smoke tests for a running Kubani
cluster. They are intentionally separate from the pytest suite because they
require a reachable Kubernetes cluster, live Secrets, and externally reachable
routes.

Run the full probe set:

```bash
just live-service-probes
```

Run only in-cluster service checks:

```bash
just live-service-probes-internal
```

## Post-Reconcile Standard

After Flux reconciliation, run:

```bash
just post-reconcile-validate
```

The normal reconcile helper does this automatically:

```bash
just flux-reconcile
```

`just flux-reconcile` reconciles `infrastructure`, `databases`, and `apps` in
dependency order before validation. Use `just flux-reconcile-only <target>` only
for narrow debugging when downstream reconciliation or live service probes would
be intentionally noisy.

## Coverage

The probe script validates the post-reconcile operational contract with
read-only checks:

- Kubernetes API reachability
- Flux `infrastructure`, `databases`, `apps`, and `flux-system`
  Kustomizations are ready at the same Git revision
- pod health, including readiness and container waiting/terminated states
- service Endpoints for non-exempt Services
- cert-manager Certificate readiness
- Longhorn volume robustness
- PostgreSQL connectivity with `SELECT 1`
- Redis authentication with `PING`
- Neo4j Bolt authentication and a `RETURN 1` Cypher query
- Qdrant REST authentication and the collections endpoint
- internal registry `/v2/` availability
- external registry BasicAuth challenge
- external registry rejection of known-bad credentials
- optional authenticated registry catalog access
- Authentik readiness
- Authentik embedded outpost assignment for the Neo4j and Qdrant proxy
  providers
- Neo4j and Qdrant Authentik forward-auth redirects
- Temporal Web HTTPS access
- Temporal ingress middleware posture
- vLLM OpenAI-compatible model-list endpoints

The authenticated registry probe is skipped unless credentials are supplied:

```bash
KUBANI_REGISTRY_USER=automation \
KUBANI_REGISTRY_PASSWORD='<password>' \
just live-service-probes
```

Do not commit registry passwords or put them in shell history. Prefer loading
them from a local password manager or ephemeral shell environment.

## Design Notes

- Probes are read-only by default.
- Qdrant is tested through a short-lived local `kubectl port-forward`, so its
  API key does not need to be injected into a temporary pod.
- Neo4j is tested inside the existing Neo4j pod using its configured
  `NEO4J_AUTH` environment variable.
- Registry external auth is tested as a challenge by default; authenticated
  catalog access is optional because only htpasswd hashes are stored in the
  cluster.
- Authentik outpost assignment is checked through the in-cluster Authentik API
  using the bootstrap token already stored in the cluster Secret. The token is
  passed through stdin and is never printed by the probe.
- The endpoint check has an explicit exemption list for Services that are
  expected to have no ready endpoints, such as intentionally inactive replica
  Services or chart-created placeholder Services.
