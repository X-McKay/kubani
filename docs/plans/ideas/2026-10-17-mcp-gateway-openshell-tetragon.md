# MCP servers behind agentgateway, OpenShell, and a Tetragon trial — 2026-10-17

**Status:** idea / spec, nothing implemented
**Requested by:** Al
**Scope:** four MCP servers (Graphiti, Kubernetes, GitHub, Postgres) routed
through the existing `ai` agentgateway with Authentik OAuth; NVIDIA OpenShell
on Kubani; an observe-only Tetragon (eBPF) trial on one node.
**Builds on:** roadmap Phase 3 and Phase 4
(`docs/plans/ideas/2026-09-29-inference-platform-roadmap.md`), the auth
decision table (`.claude/rules/auth.md`), `gateway-onboard` and
`authentik-app` skills.

> The request said "3 MCP servers" and named four. This plan covers all four.

---

## 0. TL;DR

| Workstream | Default chosen | Lands in | Node |
|---|---|---|---|
| Graphiti MCP | `zepai/knowledge-graph-mcp:1.1.1-standalone`, FalkorDB `falkordb.database:6379`, LLM + embeddings through the gateway's in-cluster route | new `mcp` namespace | rig0 |
| Kubernetes MCP | `containers/kubernetes-mcp-server` v0.0.67 (chart 0.1.0), `read_only = true`, bound to ClusterRole `view` | `mcp` | rig0 |
| GitHub MCP | self-hosted `ghcr.io/github/github-mcp-server:v2.0.2` in `http` mode, `--read-only`; gateway swaps the Authentik JWT for a SOPS-stored fine-grained PAT | `mcp` | rig0 |
| Postgres MCP | `crystaldba/postgres-mcp:0.3.0`, `--access-mode=restricted`, SSE, dedicated read-only Postgres role | `mcp` | rig0 |
| Gateway + auth | Per-server `HTTPRoute`s on `mcp.almckay.io`, one Authentik OAuth2 provider (`agentgateway-mcp`), JWT `Strict` + group CEL + per-tool CEL | `ai-gateway`, `auth` | rig0 |
| OpenShell | NVIDIA OpenShell 0.1.4 Helm chart + pinned `agent-sandbox` controller, Kubernetes compute driver, sandboxes on rig0 | `openshell`, `openshell-sandboxes`, `agent-sandbox-system` | rig0 |
| Tetragon | Tetragon 1.7.1 Helm chart, DaemonSet on **strix only**, audit/observe only (no enforcement) | `tetragon` | strix (agent), rig0 (operator) |

Order: Tetragon (independent, ring 0 now) → MCP auth plumbing + Kubernetes MCP
→ Graphiti → Postgres → GitHub → OpenShell. One PR per step, per the
roadmap's 9.1 rules.

---

## 1. What exists today (read from the repo and the live cluster, 2026-10-17)

- **agentgateway v1.5.0** is live in `ai-gateway`: control plane `agentgateway`
  and data plane `ai` on rig0, Gateway `ai` (HTTP :80, `allowedRoutes: Same`),
  TLS on Traefik via `ai.almckay.io` Ingress, CoreDNS wildcard rewrite of
  `*.almckay.io` to Traefik in-cluster. Phase 3 (Authentik on the gateway) and
  Phase 4 (MCP) are "not started"; the auth inventory already reserves an
  `mcp` subdomain row.
- **Authentik 2026.5.6** in namespace `auth` (`authentik-server`,
  `authentik-worker`), blueprints in
  `apps/authentik/blueprints-configmap.yaml`. Grafana is the precedent for a
  blueprint-created OAuth2 provider (note the `grant_types` gotcha recorded
  there).
- **FalkorDB v4.20.2** in `database`, Service `falkordb` on 6379 (RESP) and
  3000 (browser); `requirepass` from `falkordb-credentials`. Its
  `FALKORDB_ARGS` already carry timeouts tuned for Graphiti queries.
- **PostgreSQL** (Bitnami chart 16.2.1, PG 18.3, pgvector overlay) in
  `database` on the `topology.kubani.io/role: database` node (strix).
  Databases include `authentik`, `temporal`, `temporal_visibility`, and the
  starbase2 runtime's.
- **vLLM**: main and fast engines up; **`vllm-embeddings` is at replicas 0**
  (optional tier). The gateway already has an `embeddings` backend and an
  `ai.ai-gateway.svc.cluster.local` in-cluster route that serves `/v1/*`.
- **Nodes** (live `kubectl get nodes -o wide` / `top`):

  | Node | Role | Kernel | Mem used now | Ceiling |
  |---|---|---|---|---|
  | asio | control plane, etcd | 6.8.0 (Ubuntu 22.04) | 48% | 65% |
  | rig0 | platform node (excluded from Tetragon) | 6.14.0 | 33% | 75% |
  | sparky | GB10 inference (excluded) | 6.14.0-nvidia | 32% | 80% |
  | strix | small worker, database role | 6.17.0 (Ubuntu 24.04) | 26% | 80% |

- Every operational namespace is default-deny ingress + DNS-only egress;
  every cross-namespace path needs a NetworkPolicy pair. Every Secret is SOPS.
  New workloads get requests/limits, PSA-restricted securityContext, a
  capacity-ledger line, and (for new hostnames) an auth-inventory row.

---

## 2. MCP architecture

```
MCP client (Claude Code, agents)
   │  https://mcp.almckay.io/<server>/mcp   (tailnet-only, Traefik TLS)
   ▼
Traefik ──Ingress──▶ Service ai-gateway/ai :80 (agentgateway data plane)
   │   AgentgatewayPolicy: jwtAuthentication (Authentik, Strict) + mcp OAuth metadata
   │   AgentgatewayPolicy: authorization  '"mcp-users" in jwt.groups'
   │   AgentgatewayPolicy (per backend): per-tool CEL allow-list
   ▼
AgentgatewayBackend (mcp.targets, static) ──▶ namespace mcp
   ├─ graphiti-mcp   :8000 /mcp/   (Streamable HTTP) ──▶ falkordb.database:6379, ai.ai-gateway/v1
   ├─ kubernetes-mcp :8080 /mcp    (Streamable HTTP) ──▶ kube-apiserver (ServiceAccount, view)
   ├─ github-mcp     :8082 /       (Streamable HTTP) ──▶ api.github.com:443 (PAT injected by gateway)
   └─ postgres-mcp   :8000 /sse    (SSE)             ──▶ postgresql.database:5432 (read-only role)
```

### 2.1 Decisions baked into the shape

- **One namespace `mcp`** for all four servers. Same default-deny/DNS-only
  baseline as `ai-gateway`; ingress only from the `ai` data plane pods.
  Servers are not reachable except through the gateway.
- **Per-server routes, not one federated endpoint.** Each server gets its
  own `AgentgatewayBackend` and `HTTPRoute` under
  `mcp.almckay.io/<server>/mcp`. Reasons: a client opts into only the servers
  it needs, a broken upstream does not break the others' sessions, and
  per-tool policies attach per backend. agentgateway can multiplex several
  targets behind one `/mcp` (tools prefixed by target name); that is a
  later option if a single URL matters more than isolation.
- **Static targets** (`spec.mcp.targets[].static`) for all four, because
  Postgres MCP 0.3.0 speaks SSE only and dynamic (selector) targets support
  Streamable HTTP only. Services still carry `appProtocol:
  agentgateway.dev/mcp` so a later switch to selectors is a one-line change.
- **One hostname `mcp.almckay.io`**: new Ingress to Service `ai` :80, same
  annotation pattern as `ai.almckay.io`; HTTPRoutes in `ai-gateway` with
  `hostnames: [mcp.almckay.io]` (the Gateway admits Same-namespace routes
  only, so routes live in `ai-gateway` and point at backends there). The
  CoreDNS wildcard rewrite already covers it for in-cluster clients.
- **No new Gateway, no chart bump.** The agentgateway MCP auth guide has a
  1.5.x page with the same fields as latest (1.6). v1.6.0 exists; the upgrade
  stays a separate Renovate PR.
- **Placement on rig0** for everything new, following the existing gateway
  precedent of pinning `kubernetes.io/hostname: rig0` (usage-class `general`
  covers three nodes). If we want to honour the topology-label rule strictly,
  add `topology.kubani.io/role: platform` to rig0 in the inventory and select
  on that; recommended as a small ansible PR before these land.

### 2.2 Authentik and agentgateway auth (roadmap 3.1 + Phase 4)

**Authentik side** (blueprint entry in `blueprints-configmap.yaml`, reviewed
via the `authentik-app` skill):

| Object | Value |
|---|---|
| OAuth2 provider | name `Kubani agentgateway MCP`, `client_type: public` (PKCE), `grant_types: [authorization_code, refresh_token, client_credentials]` (set explicitly; blueprint default is empty, see Grafana note), `sub_mode: user_username`, `include_claims_in_id_token: true`, scope mappings `openid`, `email`, `profile` (profile carries `groups`), signing key `authentik Self-signed Certificate` |
| Redirect URIs | strict list, not the guide's `.*`: Claude Code / MCP Inspector localhost callbacks (`http://localhost:*/callback` as a regex scoped to localhost) plus any named client. Exact list finalised in ring 0 by observing what each client sends |
| Application | slug `agentgateway-mcp` → issuer `https://auth.almckay.io/application/o/agentgateway-mcp/` |
| Groups | humans: `mcp-users` (all four servers, read tools), `mcp-admin` (later: write tools). Agents: `mcp-agents` plus per-role groups, see 2.7 |
| Client id | fixed value from blueprint `!Env`, public client so no secret; still stored with the other Authentik env in SOPS for consistency |

Open-source Authentik has no dynamic client registration (RFC 7591).
agentgateway's `mcp.provider: Authentik` covers this: it serves RFC 8414
metadata built from Authentik's discovery document and answers registration
with the pre-registered `clientId`. **`clientId` is mandatory in the policy.**

**Agents (non-interactive):** each agent gets its own Authentik identity and
least-privilege role groups, never `mcp-users`. Full model in 2.7.

**Gateway side** (`apps/ai-gateway/mcp/` new directory, one stage per file):

```yaml
# policy targeting each MCP HTTPRoute (or the set of them)
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata: {name: mcp-authn, namespace: ai-gateway}
spec:
  targetRefs:
    - {group: gateway.networking.k8s.io, kind: HTTPRoute, name: mcp-graphiti}
    # ... one per server route
  traffic:
    jwtAuthentication:
      mode: Strict
      providers:
        - issuer: https://auth.almckay.io/application/o/agentgateway-mcp/   # must equal token iss, trailing slash
          audiences: [<client_id>]
          jwks:
            remote:
              backendRef: {kind: Service, name: authentik-server, namespace: auth, port: 80}
              jwksPath: /application/o/agentgateway-mcp/jwks/
      mcp:
        provider: Authentik
        clientId: <client_id>
        resourceMetadata:
          resource: https://mcp.almckay.io/graphiti/mcp   # per route
          scopesSupported: [openid, profile, email]
          bearerMethodsSupported: [header]
    authorization:
      action: Allow
      policy:
        matchExpressions: ['"mcp-users" in jwt.groups']
```

The YAML above is reconstructed from the docs' field descriptions; ring 0
validates it against the v1.5.0 `AgentgatewayPolicy` CRD schema and
`kubectl apply --dry-run=server` before anything merges (same discipline as
the stage 2.1 files). Each route also matches
`/.well-known/oauth-protected-resource/<server>/mcp` and
`/.well-known/oauth-authorization-server/<server>/mcp`. Browser CORS goes in
an `AgentgatewayPolicy` (`traffic.cors`) rather than the HTTPRoute CORS
filter, which is experimental-channel Gateway API and the cluster has the
standard v1.4.0 CRDs from k3s.

**Issuer gotcha:** Authentik stamps the request host into `iss`. Clients get
tokens from `auth.almckay.io`, so the issuer is the public URL; JWKS is
fetched from the in-cluster Service. Needs NetworkPolicy pair
`ai-gateway (ai pods) → auth (authentik-server) :9000` (container port behind
Service :80).

**Per-tool authorization** (one policy per backend):

```yaml
spec:
  targetRefs: [{group: agentgateway.dev, kind: AgentgatewayBackend, name: mcp-github}]
  backend:
    mcp:
      authorization:
        action: Allow
        policy:
          matchExpressions:
            - '"mcp-users" in jwt.groups && mcp.tool.name in ["get_me","search_repositories","get_file_contents","list_pull_requests","pull_request_read","list_issues","issue_read"]'
```

Once an Allow policy exists, unmatched tools are denied and hidden from
`tools/list`. Start every backend with an explicit allow-list of read tools;
write tools come later behind `mcp-admin`.

**Verify (gate):** unauthenticated `POST /graphiti/mcp` → 401 with
`WWW-Authenticate` pointing at the protected-resource metadata; token without
`mcp-users` → 403; token with it → `initialize` + `tools/list` succeed and
show only allow-listed tools; Claude Code `claude mcp add --transport http
graphiti https://mcp.almckay.io/graphiti/mcp` completes the browser OAuth
flow end to end.

### 2.3 Graphiti MCP

| Item | Spec |
|---|---|
| Image | `zepai/knowledge-graph-mcp:1.1.1-standalone` (amd64+arm64; graphiti-core 0.31.1). The non-standalone tag bundles its own FalkorDB, which we do not want |
| Transport | Streamable HTTP, port 8000, path `/mcp/` (trailing slash; set `static.path: /mcp/`), health `GET /health` |
| Config | ConfigMap `graphiti-mcp-config` mounted at `/app/mcp/config/config.yaml`; secrets via env |
| Database | `provider: falkordb`, `uri: redis://falkordb.database.svc.cluster.local:6379`, `password: ${FALKORDB_PASSWORD}`, `database: graphiti_mcp` and `GRAPHITI_GROUP_ID=graphiti_mcp` (separate graph by default, see decision D2). With FalkorDB, Graphiti routes each non-default `group_id` to a graph of that name, so the group ID is what actually selects the graph: keep it equal to the database name, or set it to the existing workstream's group ID only if D2 picks shared memory |
| LLM | `provider: openai`, `api_url: http://ai.ai-gateway.svc.cluster.local/v1`, `model: default` (main with failover to fast), `structured_output_mode: json_schema` (fall back to `json_object` if vLLM does not enforce the schema), `api_key` = gateway virtual key once Phase 3.2 keys exist (placeholder until then; the in-cluster route has no key today) |
| Embedder | `provider: openai`, same `api_url`, `model: Qwen/Qwen3-Embedding-0.6B`, **`dimensions: 1024`** (default 1536 is wrong for this model). Needs `vllm-embeddings` at replicas 1, see decision D1 |
| Concurrency | `SEMAPHORE_LIMIT=4` to start (each episode is several LLM calls; the main engine was benchmarked at c=4) |
| Secret | `mcp/graphiti-mcp.enc.yaml`: `FALKORDB_PASSWORD` (same value as `database/falkordb-credentials`; a Secret cannot be read across namespaces), later `OPENAI_API_KEY` (gateway key) |
| Resources | 100m / 1 CPU, 384Mi / 1Gi |
| NetworkPolicy pairs | `mcp → database (falkordb) :6379`; `mcp → ai-gateway (ai) :80` (ingress allow on the `ai` pods from `mcp`, like the inference-bench rule); `ai-gateway → mcp :8000` |

Note the two-graph question (D2): FalkorDB's comment says Graphiti queries
already run against it, so some workstream already writes a Graphiti graph.
Pointing the MCP server at that graph lets agents read shared memory;
a separate `graphiti_mcp` graph avoids a schema/version clash between
graphiti-core versions.

### 2.4 Kubernetes MCP

| Item | Spec |
|---|---|
| Server | `containers/kubernetes-mcp-server` (native client-go, not a kubectl wrapper; in-cluster ServiceAccount; read-only mode; Helm chart) |
| Chart / image | `oci://ghcr.io/containers/charts/kubernetes-mcp-server` 0.1.0 (Flux `OCIRepository` + `chartRef`, like agentgateway); image `quay.io/containers/kubernetes_mcp_server:v0.0.67` pinned (chart default is `latest`) |
| Config (TOML via `config:` value, works on v0.0.67 and on main where CLI flags are gone) | `port = "8080"`, `read_only = true`, `stateless = true`, `toolsets = ["core"]` (add `helm` read later), `metrics_port = "9090"`, `denied_resources` = Secrets, ServiceAccount tokens, `sops`-decrypted objects |
| RBAC | chart creates none by default; add `rbac.extraClusterRoleBindings` to ClusterRole `view` (excludes Secrets). Answers audit-followup question 6 for this path: blast radius = cluster-wide read of non-secret objects |
| Chart values to flip | `ingress.enabled: false` (default true), `httpRoute.enabled: false` |
| Resources | 50m / 500m, 64Mi / 256Mi |
| NetworkPolicy | egress to apiserver `10.43.0.1/32:443` and `100.64.0.0/10:6443` (same pair as the agentgateway control plane); ingress from `ai` :8080; Prometheus :9090 |
| Ring 0 check | quay manifest is arm64+amd64 (could not be read from here); irrelevant while pinned to rig0 |

Flux has its own MCP server (Flux Operator MCP) that would add GitOps-aware
tools (reconcile status, diffs); worth a later look, not in this plan.

### 2.5 GitHub MCP

| Item | Spec |
|---|---|
| Option chosen | self-hosted `ghcr.io/github/github-mcp-server:v2.0.2` (amd64+arm64), `github-mcp-server http --port 8082 --read-only --toolsets context,repos,issues,pull_requests,actions` |
| Auth to GitHub | in `http` mode the server uses the caller's `Authorization` header per request. The client's header carries the Authentik JWT, so the **gateway replaces it**: `AgentgatewayBackend.spec.policies.auth.secretRef: github-mcp-pat` (Secret key `Authorization` = `Bearer <PAT>`), SOPS file `apps/ai-gateway/mcp/github-mcp-pat.enc.yaml` |
| PAT | fine-grained, resource owner `X-McKay`, repositories: all or a named list (decision D4), permissions read-only on contents, issues, pull requests, actions, metadata. 90-day expiry, rotation row in the auth inventory |
| Alternative | no pod: backend straight to GitHub's hosted `https://api.githubcopilot.com/mcp/readonly` (TLS SNI, same PAT injection). Fewer moving parts and more tools, but GitHub controls the version and the gateway needs general internet egress |
| Resources | 50m / 500m, 64Mi / 256Mi |
| NetworkPolicy | `mcp` egress to `0.0.0.0/0:443 except 10.0.0.0/8,100.64.0.0/10,172.16.0.0/12,192.168.0.0/16` for `github-mcp` pods only |
| Ring 0 check | confirm the backend `auth` policy overwrites (not appends) the client Authorization header, by logging the header at a debug echo target before pointing it at GitHub |

### 2.6 Postgres MCP

| Item | Spec |
|---|---|
| Server | `crystaldba/postgres-mcp:0.3.0` (amd64+arm64), `--access-mode=restricted --transport=sse` (entrypoint adds `--sse-host=0.0.0.0`), port 8000, path `/sse`, target `protocol: SSE` |
| Caveat | 0.3.0 is from 2025-05 and the last release; Streamable HTTP exists only on main. Acceptable for a read-only tool; if it bites, alternatives are Google's MCP Toolbox for Databases or a build from main pushed to `registry.almckay.io` |
| Database access | new role `mcp_readonly` (LOGIN, `statement_timeout = 15s`, `default_transaction_read_only = on`) with **explicit grants only**: `CONNECT` on the target database, `USAGE` on its schemas, `SELECT` on their tables plus `ALTER DEFAULT PRIVILEGES ... GRANT SELECT` for new tables. No `pg_read_all_data`: Postgres grants `CONNECT` to `PUBLIC` by default, so that role would read every other database too (`temporal`, `temporal_visibility`, ...). The init Job also runs `REVOKE CONNECT ON DATABASE <each other db> FROM PUBLIC` where that is safe, and the gate checks `mcp_readonly` cannot connect to `authentik` or `temporal`. Defence in depth: the server's restricted mode **and** a role that cannot write |
| Which database | **Decision D3.** One `DATABASE_URI` = one database. Default: the starbase2 runtime database; never `authentik` (sessions, tokens, password hashes) |
| Role creation | a Flux-applied idempotent Job in `database`, same pattern as `apps/temporal/db-init-job.yaml`; password from SOPS |
| Secrets | `mcp/postgres-mcp.enc.yaml` (`DATABASE_URI` with the role password), `database/postgres-mcp-role.enc.yaml` (for the init Job) |
| Resources | 50m / 500m, 128Mi / 512Mi |
| NetworkPolicy pair | `mcp → database (app.kubernetes.io/name: postgresql) :5432` and the matching `allow-mcp-postgresql` ingress in `netpol-database.yaml` |
| Future | roadmap 5.2 (CloudNativePG) changes the host and role management; the role then moves to a CNPG `Database`/managed role |

### 2.7 Agent identities (least privilege)

Goal: every agent is a first-class Authentik identity, separate from humans,
holding only the tools its job needs. Agents are expected to run inside
OpenShell sandboxes and as Temporal workers, so the identity has to work in
both places.

**Identity.** One Authentik service account per agent, named `agent-<name>`
(for example `agent-triage`), authenticating with `client_credentials`
against the `agentgateway-mcp` provider. Token lifetime 10 minutes, so
disabling the account cuts access within one token's life. `sub` is the
service account username, so audit logs and gateway traces name the agent.

**Groups.** Three layers, all defined in the Authentik blueprint so they are
reviewed in git:

| Group | Members | Grants |
|---|---|---|
| `mcp-agents` | every agent service account | admission to the MCP routes for agents (the route-level CEL becomes `"mcp-users" in jwt.groups \|\| "mcp-agents" in jwt.groups`), nothing else |
| `agent-role-<role>` (e.g. `agent-role-k8s-read`, `agent-role-graph-write`, `agent-role-github-read`, `agent-role-pg-read`) | agents that need that capability | tool allow-lists in the per-backend policies key on these groups |
| `mcp-users` / `mcp-admin` | humans only | unchanged; an agent is never in a human group |

Per-tool CEL keys on role groups rather than on individual `jwt.sub` values,
so adding an agent is a blueprint change (new service account, group
membership) and never a gateway policy edit. A per-`sub` rule is reserved for
a one-off deny. Example:

```yaml
matchExpressions:
  - '"agent-role-k8s-read" in jwt.groups && mcp.tool.name in ["pods_list","pods_get","pods_log","events_list","resources_get","resources_list"]'
  - '"mcp-users" in jwt.groups && mcp.tool.name in [...]'   # humans
```

Requirement to verify in ring 0: that Authentik puts `groups` into
`client_credentials` tokens for service accounts (the `profile` scope
mapping does it for users; if not, a custom scope mapping adds it).

**Credentials inside OpenShell.** The agent's client secret is a SOPS Secret
exposed to OpenShell through `server.credentialDrivers.kubernetesSecrets`.
The supervisor injects it only on requests to the approved endpoints
(`auth.almckay.io` token endpoint, `mcp.almckay.io`, the `ai` gateway), so the
untrusted workload never holds a long-lived secret and cannot use it anywhere
else. Ring 0 checks whether injection can cover the token request itself or
only a static header; if only a header, the fallback is a short-lived token
minted by a sidecar outside the sandbox.

**Temporal.** Agents run as Temporal workers, with their workflows in a
Temporal namespace per agent or team. Temporal's server can authorize with
the same Authentik JWT (its JWT claim mapper reads a `permissions` claim), so
the identity that calls MCP tools is also the identity allowed to poll its own
task queue and nothing else. That is a follow-up to this plan (Temporal auth
is not enabled today); until then Temporal stays on the
network-policy-plus-tailnet row.

**LLM access.** Today the rule is one gateway virtual key per agent (Phase
3.2). With agent identities in Authentik, the gateway could accept the same
JWT on the LLM routes and attach budgets per `sub`, so an agent carries one
credential. Decision D8; the virtual-key path stays the default until then.

**Lifecycle.** Adding an agent is one blueprint PR: service account, role
group memberships, SOPS client secret, and an auth-inventory row. Removing
one is a `state: absent` blueprint pass, per the authentik-app skill.

### 2.8 Files and order of PRs (MCP)

| PR | Content | Gate |
|---|---|---|
| M0 | rig0 topology label (optional), `mcp` namespace in `namespace-policy`, `infrastructure/networking/netpol-mcp.yaml` baseline, `ai-gateway → auth :9000` pair | `just validate-local` |
| M1 | Authentik blueprint: provider, application, groups; `mcp.almckay.io` Ingress; auth-inventory row | discovery doc at `https://auth.almckay.io/application/o/agentgateway-mcp/.well-known/openid-configuration` |
| M2 | Kubernetes MCP + backend + route + authn/authz policies + tool allow-list | the 401/403/200 gate in 2.2; Claude Code lists pods through it |
| M3 | Graphiti MCP (after D1) | `add_memory` then `search_nodes` round trip; FalkorDB `GRAPH.LIST` shows the graph; no FalkorDB timeout errors |
| M4 | Postgres role Job + Postgres MCP | `SELECT 1` works; `CREATE TABLE` fails at both the server and the role |
| M5 | GitHub PAT (operator mints SOPS file) + GitHub MCP | `get_me` returns X-McKay; a write tool is absent from `tools/list` |

Each PR adds its capacity-ledger line and, where relevant, auth-inventory row.
SOPS files that need `age.key` (FalkorDB password copy, Postgres role,
GitHub PAT, Authentik MCP client id) are listed in
`docs/infrastructure/operations/pending-secrets.md` like the Phase 0/3 ones.

---

## 3. OpenShell

**What it is:** NVIDIA OpenShell (Apache-2.0, `github.com/NVIDIA/OpenShell`),
a sandboxed runtime for autonomous agents: a gateway (control plane), a
trusted supervisor per sandbox, and an untrusted, capability-less workload
confined with Landlock and seccomp user-notification. All sandbox egress goes
through the supervisor, which enforces policy and injects credentials only for
approved endpoints. Latest release **0.1.4**; only the latest and previous
minor are supported, so this is early software and gets pinned.

It fits the project's stated direction (sandboxed agent evaluation, safety
gates); it is third-party platform software, so it belongs in this repo under
the scope rule.

### 3.1 Deployment shape

| Item | Spec |
|---|---|
| Prerequisite | `kubernetes-sigs/agent-sandbox` controller + `sandboxes.agents.x-k8s.io` CRD, **pinned release** (not `latest/download`), vendored into `infrastructure/gitops/infrastructure/agent-sandbox/` (namespace `agent-sandbox-system`). Lives in the infrastructure Kustomization so the CRD exists before apps |
| Chart | `oci://ghcr.io/nvidia/openshell/helm-chart`, version `0.1.4` (tags have no `v` prefix), Flux `OCIRepository` + `HelmRelease` in namespace `openshell` |
| Gateway | StatefulSet with SQLite on a 5Gi Longhorn PVC (single replica; external Postgres only needed for replicas > 1), Service :8080 (gRPC + HTTP, mTLS), `server.telemetryEnabled: false` |
| Sandboxes | `server.sandboxNamespace: openshell-sandboxes`; each sandbox = supervisor Pod + workload Pod + boundary Service + PVC (`/sandbox`, local-path) + NetworkPolicy. Placement on rig0 |
| PKI | chart's pre-install hook generates the internal mTLS PKI (gateway ↔ supervisors). Its server certificate does not cover `openshell.almckay.io` and is privately signed, so for external access the gateway's serving certificate comes from cert-manager instead: a `Certificate` for `openshell.almckay.io` from the existing `letsencrypt-prod` issuer (DNS-01), wired into the chart's external-certificate setting per NVIDIA's [Kubernetes ingress guide](https://docs.nvidia.com/openshell/latest/kubernetes/ingress). Alternative: add the hostname as an extra SAN on the chart PKI and distribute the chart CA to CLI users. Ring 0 checks which values keys the 0.1.4 chart exposes for this |
| User auth | OIDC with Authentik as issuer: new OAuth2 provider `Kubani OpenShell` (public, PKCE), CLI `openshell gateway add https://openshell.almckay.io --oidc-issuer https://auth.almckay.io/application/o/openshell/ --oidc-client-id <id>`. Authentik compatibility is unverified; fallback is mTLS + tailnet-only. Never `allowUnauthenticatedUsers` or `disableTls` |
| Exposure | `openshell.almckay.io` via Traefik `IngressRouteTCP` with TLS passthrough (the gateway does its own mTLS, so Traefik must not terminate) — same pattern as the existing Postgres/FalkorDB TCP routes. Because Traefik passes TLS through, the CLI validates OpenShell's own certificate, which is why the PKI row above needs a publicly trusted cert for this hostname. Decision D6 |
| Inference | sandboxes reach `ai.almckay.io` (or the in-cluster `ai` route) through an OpenShell network policy allow-rule; credentials (gateway key) injected by the supervisor from a Kubernetes Secret via `server.credentialDrivers.kubernetesSecrets` |
| Resources | gateway 100m / 1 CPU, 256Mi / 1Gi; sandboxes need a namespace `ResourceQuota` (start: 4 CPU / 8Gi total on rig0) and `LimitRange` defaults |

### 3.2 Requirements to check in ring 0

1. **Kernel:** Landlock ABI ≥ 3 and `landlock` in `/sys/kernel/security/lsm`
   on rig0 (kernel 6.14, Ubuntu 24.04 ships Landlock enabled; confirm),
   seccomp user-notify `ADDFD`/`SEND`. OpenShell fails closed if missing.
2. **NetworkPolicy egress enforcement:** OpenShell's isolation assumes the
   CNI enforces egress. k3s's kube-router controller does (the repo's
   DNS-only egress policies rely on it), but test explicitly: a sandbox with
   no allow rule must fail `curl https://example.com`.
3. **PSA:** render the chart with `helm template` and check which
   securityContext the supervisor needs; set the sandbox namespace's PSA
   level to the least that works and record why (the cluster has a
   `namespace-psa-patch` precedent for privileged namespaces).
4. **RBAC:** the chart creates ClusterRole `openshell-node-reader`
   (`tokenreviews` create, `nodes` read) and a namespaced Role on sandboxes,
   events and pods. Accept as-is.

### 3.3 PRs and gates

| PR | Content | Gate |
|---|---|---|
| O1 | agent-sandbox controller (pinned) + namespace baseline netpols | CRD established; controller Ready |
| O2 | OpenShell HelmRelease, Authentik provider, TCP route, auth-inventory row, ledger | `openshell gateway add` + login from rig0 works |
| O3 | First policy + sandbox | sandbox runs `uname`, blocked egress fails, allowed egress to `ai` gateway returns a completion |

Upgrade note: if agent-sandbox is upgraded in place, restart the OpenShell
gateway (by deleting its pod, never `rollout restart`).

---

## 4. Tetragon (eBPF) trial

### 4.1 Node choice

Excluding rig0, sparky and the control plane (asio) leaves **strix** as the
only eligible node. strix runs Postgres and FalkorDB (role `database`), so the
trial is observe-only and the gate watches database latency.

strix: Ubuntu 24.04, kernel 6.17 (BTF at `/sys/kernel/btf/vmlinux` expected;
Tetragon needs ≥ 4.19 and BTF), 7 CPU / 13 GiB, 26% memory used, ceiling 80%.

### 4.2 Deployment shape

| Item | Spec |
|---|---|
| Source | `HelmRepository` `cilium` → `https://helm.cilium.io` in `infrastructure/sources/` |
| Chart | `tetragon` 1.7.1 (images `quay.io/cilium/tetragon:v1.7.1`, operator `quay.io/cilium/tetragon-operator:v1.7.1`) |
| Namespace | `tetragon` (own namespace rather than `kube-system`, so the PSA exception — the agent is privileged with hostPID — is scoped and visible in `namespace-policy`) |
| Node pinning | agent `nodeSelector: {topology.kubani.io/ebpf-trial: "true"}`, a label added to strix through `topology_labels` in the inventory (honours the topology-label rule; moving the trial is a one-line inventory change). **Override the chart's default `tolerations: [{operator: Exists}]` to `[]`**, otherwise the DaemonSet also lands on tainted sparky |
| Operator | `tetragonOperator.nodeSelector`: rig0 |
| Resources | agent 100m / 1 CPU, 256Mi / 768Mi (chart default is none); export-stdout sidecar 20m / 100m, 32Mi / 64Mi |
| Events | `export.mode: stdout` sidecar → Alloy already tails pod logs → Loki. Keep the file export rotation at 10 MB × 5. **Replace the default `exportDenyList`** so host (`""`) and `kube-system` events are visible for the trial, still dropping health checks |
| Metrics | port 2112; add a scrape job in `prometheus-helmrelease.yaml` and the monitoring → tetragon :2112 netpol pair. `metricsLabelFilter` = namespace, workload, binary (drop pod to cap cardinality) |
| Enforcement | none during the trial: no `Sigkill`/`Override` actions in any policy |

### 4.3 TracingPolicies for the trial

All in `infrastructure/gitops/infrastructure/tetragon/policies/`:

1. **Process exec/exit**: built-in, no policy. Answers "what runs on the DB
   node" (exec into the Postgres pod, unexpected binaries).
2. **Sensitive file access** (`security_file_permission` kprobe, narrow
   prefixes): reads of `/etc/shadow`, `/etc/sudoers`, `/root/.ssh`,
   `/var/lib/rancher/k3s/server/token`, `/etc/rancher/k3s/k3s.yaml`; writes
   under `/etc`, `/usr/bin`, `/usr/lib`. Kept narrow because a broad
   `security_file_permission` hook is the expensive one.
3. **Network egress outside the cluster** (`tcp_connect` kprobe,
   `NotDAddr: 127.0.0.1, 10.42.0.0/16, 10.43.0.0/16, 100.64.0.0/10`). Rendered
   literally (no `envsubst` in GitOps). Shows whether anything on strix talks
   to the internet unexpectedly; also the evidence base for tightening the
   database namespace's egress.
4. **Privilege changes** (`commit_creds` / `setuid` family): optional, add in
   week 2 if event volume allows.

### 4.4 Trial gates (2 weeks)

| Metric | Threshold | Where |
|---|---|---|
| strix CPU from the tetragon agent | < 5% of a core p95 | Prometheus `container_cpu_usage_seconds_total` |
| strix memory | stays under the 80% ceiling | `just capacity` |
| Postgres query latency | no regression vs the week before (`pg_stat_statements` mean, exporter) | Grafana |
| FalkorDB | no new TIMEOUT errors in its logs | Loki |
| Event volume into Loki | < 1 GB/day | Loki ingestion metrics |
| Usefulness | at least one finding worth acting on, or a clear "nothing here" | trial notes |

Exit: write up findings in `docs/plans/`; decide between (a) remove, (b)
extend to rig0 with audit policies, (c) add enforcement on selected
policies. Rollback = revert the PR; Tetragon detaches its BPF programs when
the pod stops.

`tetra` usage during the trial:
`kubectl exec -n tetragon ds/tetragon -c tetragon -- tetra getevents -o compact --namespace database`.

---

## 5. Capacity

| Service | Namespace | CPU req/lim | Mem req/lim | Node |
|---|---|---|---|---|
| graphiti-mcp | mcp | 100m / 1 | 384Mi / 1Gi | rig0 |
| kubernetes-mcp | mcp | 50m / 500m | 64Mi / 256Mi | rig0 |
| github-mcp | mcp | 50m / 500m | 64Mi / 256Mi | rig0 |
| postgres-mcp | mcp | 50m / 500m | 128Mi / 512Mi | rig0 |
| OpenShell gateway | openshell | 100m / 1 | 256Mi / 1Gi | rig0 |
| OpenShell sandboxes (quota) | openshell-sandboxes | 4 / — total | 8Gi total | rig0 |
| agent-sandbox controller | agent-sandbox-system | 50m / 500m | 64Mi / 256Mi | rig0 |
| Tetragon agent (+ export sidecar) | tetragon | 120m / 1.1 | 288Mi / 832Mi | strix |
| Tetragon operator | tetragon | 20m / 200m | 64Mi / 128Mi | rig0 |
| vLLM embeddings (if D1 = yes) | vllm | 500m / — | 12Gi / 14Gi | sparky |

rig0 requests grow by about 1 GiB plus whatever sandboxes use (bounded by the
8 GiB quota): 33% today, worst case ~52% with sandboxes full, under the 75%
ceiling. strix gains < 0.3 GiB request. Embeddings on sparky is the existing
pre-agreed ledger line.

---

## 6. Risks

- **agentgateway MCP auth fields reconstructed from docs.** Mitigation: CRD
  schema check and server-side dry run in ring 0, as for stage 2.1.
- **Authentik issuer mismatch** (`iss` host vs configured issuer) silently
  401s everything. Mitigation: issuer is the public URL, verified by decoding
  a real token before the policy merges.
- **GitHub PAT exposure**: PAT lives only in a SOPS Secret in `ai-gateway`,
  injected by the gateway; the MCP pod never holds it. Read-only scopes.
- **Postgres MCP staleness** (0.3.0, SSE only). Mitigation: read-only role
  makes the server's own guarantees a second layer, not the only one.
- **Graphiti + small/fast model**: if main fails over to the 0.8B fast model,
  entity extraction quality drops and JSON can be malformed. Option: point
  Graphiti at `llm-main` directly (no failover) so it errors instead of
  degrading.
- **OpenShell 0.x churn** and N-1 support window. Pin, Renovate PR-only,
  treat upgrades as a release.
- **Tetragon on the database node**: kprobe overhead on a 7-core box. Narrow
  selectors, no enforcement, latency gate, revert on regression.

---

## 7. Decisions for Al

| # | Question | Default if no answer |
|---|---|---|
| D1 | Graphiti needs embeddings: scale `vllm-embeddings` to 1 (12 GiB on sparky, existing ledger line)? | Yes, scale to 1 |
| D2 | Graphiti MCP graph: separate `graphiti_mcp` graph, or the one the agent runtime already writes? | Separate graph |
| D3 | Postgres MCP: which database(s) may it read? | starbase2's database only, read-only role, never `authentik` |
| D4 | GitHub: self-host the server (pinned, PAT injected) or use GitHub's hosted endpoint? Which repos does the PAT cover? | Self-host, read-only, all X-McKay repos |
| D5 | Tetragon on strix (the only eligible node, it hosts Postgres/FalkorDB), observe-only for 2 weeks | Yes |
| D6 | OpenShell: expose `openshell.almckay.io` on the tailnet with Authentik OIDC, or in-cluster only for now? | Tailnet with OIDC, fallback mTLS-only |
| D7 | Read-only tools only for the first release of every MCP server, write tools later behind `mcp-admin`? | Yes |
| D8 | Agents: one Authentik JWT for MCP and LLM calls (budgets per `sub`), or JWT for MCP plus a separate gateway virtual key for LLM calls? | JWT for MCP plus a virtual key for LLM until the JWT path is proven |

---

## 8. Sources

- agentgateway MCP auth with Authentik: https://agentgateway.dev/docs/kubernetes/latest/documentation/mcp/auth/authentik/ (1.5.x page: https://agentgateway.dev/docs/kubernetes/1.5.x/documentation/mcp/auth/authentik/)
- agentgateway static/dynamic MCP and tool access: https://agentgateway.dev/docs/kubernetes/latest/documentation/mcp/static-mcp/, .../dynamic-mcp/, .../tool-access
- agentgateway GitHub MCP example: https://agentgateway.dev/blog/2026-02-19-connect-any-ide-githhub-mcp-agentgateway/
- Graphiti MCP: https://github.com/getzep/graphiti/tree/main/mcp_server, https://hub.docker.com/r/zepai/knowledge-graph-mcp
- kubernetes-mcp-server: https://github.com/containers/kubernetes-mcp-server (docs/configuration.md, charts/)
- github-mcp-server: https://github.com/github/github-mcp-server (docs/streamable-http.md, docs/remote-server.md)
- postgres-mcp: https://github.com/crystaldba/postgres-mcp
- OpenShell: https://github.com/NVIDIA/OpenShell, https://docs.nvidia.com/openshell/latest/ (kubernetes/setup, about/support-matrix, upgrade/0-1-0)
- agent-sandbox: https://github.com/kubernetes-sigs/agent-sandbox
- Tetragon: https://tetragon.io/docs/installation/kubernetes/, https://tetragon.io/docs/installation/faq/, values at https://github.com/cilium/tetragon/blob/v1.7.1/install/kubernetes/tetragon/values.yaml

Versions checked 2026-10-17 from upstream tags and registries: agentgateway
v1.6.0 latest (cluster on v1.5.0), graphiti MCP 1.1.1, kubernetes-mcp-server
v0.0.67, github-mcp-server v2.0.2, postgres-mcp 0.3.0, OpenShell 0.1.4,
Tetragon 1.7.1. Not verified from here (registries blocked): quay.io image
architectures for kubernetes-mcp-server and Tetragon (irrelevant while both
run on amd64 nodes).
