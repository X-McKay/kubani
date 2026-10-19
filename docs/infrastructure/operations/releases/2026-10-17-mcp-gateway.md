# 2026-10-17 MCP servers behind agentgateway

**Status:** in progress. M0 released 2026-10-17 23:34Z; M1 released
2026-10-18 00:35Z; M2 released 01:37Z, fixed forward 01:41Z (#210),
end-to-end sign-in passed 18:57Z; M2 gate complete 22:16Z (allow-list
and outsider checks with the test identities); M3 (Graphiti) in review
**Profile:** gateway
**Scope:** agentgateway (`ai-gateway`), new `mcp` namespace, Authentik
(`auth` network policy now; blueprint in M1), rig0 node label
**Window:** no downtime expected. Each step adds new objects; the existing
LLM routes on `ai.almckay.io` are only re-checked, never changed.

Plan: `docs/plans/ideas/2026-10-17-mcp-gateway-openshell-tetragon.md`,
section 2 (design and per-PR gates) and section 6 (testing and rollback).
One record covers M0 to M5; each step adds its own section below.

## Why
Give agents and Claude Code a single authenticated entry point
(`mcp.almckay.io`) to read-only Kubernetes, Graphiti, Postgres and GitHub
tools, with Authentik groups deciding who can call which tool.

## Rollout rules
Al shortened the soak on 2026-10-17: readings at T+15 min and T+1 h after
each step, then the next step, instead of 24 h. Stop and roll back on a
failed gate, an LLM-route regression, or a node over its memory ceiling.

**Shared-gateway regression check**, after every step: no new 4xx/5xx on
`agentgateway_requests_total`, and the gateway pods Ready with no restarts.
Baseline (24 h before M0): 12 requests, all 200; zero 400/404/502.

## M0: `mcp` namespace and network paths

| | Before | After |
|---|---|---|
| Namespaces | none | `mcp` (PSA `restricted`, default-deny ingress, DNS-only egress) |
| `ai-gateway` egress | LLM backends | + `mcp` pods on 8000/8080/8082, + Authentik server :9000 (JWKS) |
| `auth` ingress | existing | + from the `ai-gateway` data plane to the Authentik server :9000 |
| rig0 label | none | `topology.kubani.io/role=platform` (inventory, applied with `kubectl label`) |

**Rollback SHA:** `6a94426ad0aaa4dd6d85665a774bcf8191f3c311` (main before
M0). Rollback is `git revert -m 1 <M0 merge>`; nothing is left behind
(plan 6.2).
The rig0 label is harmless on its own and is removed with
`kubectl label node rig0 topology.kubani.io/role-` only if M2+ are reverted
too.

**Gate:**
- `just validate-local` before merge.
- After reconcile: `apps` Kustomization Ready, `kubectl get ns mcp` shows
  `pod-security.kubernetes.io/enforce=restricted`, the three network
  policies exist.
- Shared-gateway regression check above.

## M1: Authentik provider, groups and `mcp.almckay.io`

| | Before | After |
|---|---|---|
| Authentik | no MCP objects | blueprint `kubani-mcp.yaml`: groups `mcp-users`, `mcp-admin`, `mcp-agents`; public PKCE provider "Kubani agentgateway MCP" (`client_id: kubani-agentgateway-mcp`, grant types set explicitly, localhost callback regexes); application `agentgateway-mcp` bound to the three groups |
| Ingress | none | `mcp.almckay.io` to the `ai` data plane, certificate `mcp-tls` from `letsencrypt-prod`. The gateway answers 404 for it until M2 adds routes |

**Accepted risk (Al, 2026-10-17):** Authentik does not force PKCE on public
clients; a code without a challenge is accepted. Exploiting it needs a client
that skips PKCE (Claude Code and the MCP SDKs always send S256) and a second
local process that captures the loopback callback, which could already read
that client's tokens. Revisit before agents use any other OAuth client.

**Rollback SHA:** `1599e292d5c5d34421572b1d7ca51295bd97de7e` (main before
the M1 merge).
Rollback is **not** a plain revert: Authentik blueprints do not delete
objects that disappear from a blueprint. Revert in two steps:
1. A PR that sets `state: absent` on every entry of `kubani-mcp.yaml`, then
   confirm in Authentik that the provider, application and groups are gone.
2. A PR that removes the `kubani-mcp.yaml` key and the Ingress.

**Gate:**
- The blueprint instance `Kubani - MCP gateway` shows status `successful`
  in Authentik (Admin > Customization > Blueprints), and no other blueprint
  changes status.
- `https://auth.almckay.io/application/o/agentgateway-mcp/.well-known/openid-configuration`
  returns the discovery document, with `issuer` equal to
  `https://auth.almckay.io/application/o/agentgateway-mcp/` (the value M2's
  policy will check).
- `/application/o/agentgateway-mcp/jwks/` returns a key set.
- Certificate `mcp-tls` Ready; `https://mcp.almckay.io/` answers 404 from
  the gateway (not a TLS or Traefik error).
- Authentik regression: an existing login (Grafana) still works, and
  `authentik-server` and `authentik-worker` have no new restarts.
- Shared-gateway regression check above.

**Gate result (2026-10-18 00:37Z): PASS.** Blueprint `successful`; the
blueprints already in error before M1 are unchanged. Discovery `issuer` and
JWKS (RS256) as expected. `mcp-tls` Ready at 00:35Z; `mcp.almckay.io`
resolves and answers 404, counted by `agentgateway_requests_total`, so it is
the gateway answering. Grafana's OAuth redirect still reaches the Authentik
login flow; `authentik-server`, `authentik-worker` and the gateway pods have
0 restarts; gateway status counts show only 200s besides the two probe 404s.

## M2: Kubernetes MCP server

| | Before | After |
|---|---|---|
| `mcp` namespace | empty | `kubernetes-mcp` Deployment and Service on rig0 (`read_only`, ServiceAccount bound to cluster `view`) |
| `ai-gateway` | no MCP routes | AgentgatewayBackend, HTTPRoute (`/kubernetes/mcp` and its two `.well-known` paths on `mcp.almckay.io`) and AgentgatewayPolicy (Authentik JWT, read-tool allow-list for `mcp-users`/`mcp-agents`) |
| `auth` | none | ReferenceGrant letting the policy read the `authentik-server` JWKS |

**Capacity:** +50m / 64Mi requests on rig0 (ledger updated).

**Rollback SHA:** `c7da14d3ee1fce97ff6f73cd2764d40c6aea776b` (main before
the M2 merge). Rollback is
`git revert -m 1 <M2 merge>`; the backend, route, policy, grant and the
`view` binding all go with it (plan 6.2).

**Gate (plan 2.2):**
- `apps` Kustomization Ready; the AgentgatewayPolicy and HTTPRoute status
  conditions Accepted/ResolvedRefs (an unresolved JWKS ref 401s everything).
- `kubernetes-mcp` pod Ready on rig0, 0 restarts.
- Unauthenticated `POST /kubernetes/mcp` returns 401 with
  `WWW-Authenticate` pointing at the protected-resource metadata, and that
  metadata URL answers.
- Needs Al: `claude mcp add --transport http kubernetes
  https://mcp.almckay.io/kubernetes/mcp` completes the browser login, then
  `tools/list` shows only the allow-listed tools and listing pods works. A
  user outside `mcp-users` and `mcp-agents` gets no tools: 200 with an
  empty `tools/list` and every `tools/call` refused (the group check is a
  per-tool rule, so it filters rather than returning 403). The test
  identities below can run this without Al.
- Shared-gateway regression check above.

**Gate result (2026-10-18 01:38Z): one failure, fixed forward.**
- Pass: `apps` Ready at the M2 merge; HTTPRoute Accepted and ResolvedRefs;
  AgentgatewayPolicy Accepted and Attached. The first xDS push was NACKed
  ("MCP Authentication requires jwks_inline") because the controller had
  not fetched the JWKS yet; the next push 0.3 s later carried it.
- Pass: `kubernetes-mcp` Ready on rig0, 0 restarts.
- Pass: unauthenticated `POST /kubernetes/mcp` returns 401 ("no bearer
  token found"); the protected-resource metadata answers 200.
- **Fail:** `/.well-known/oauth-authorization-server/kubernetes/mcp`
  returned 500. The data plane builds it from Authentik's discovery
  document at `https://auth.almckay.io`, which in-cluster DNS sends to
  the Traefik ClusterIP, and the data plane had no egress there
  ("Connection refused"). Without it no client can start the OAuth flow.
- Decision: fix forward rather than revert. Nothing uses
  `mcp.almckay.io` yet, the LLM routes were unaffected, and the fix is one
  NetworkPolicy (`allow-data-plane-to-traefik-egress`, the same shape as
  Grafana's `allow-grafana-auth-egress`). Its PR re-runs this gate.

**Gate re-run after #210 (applied 01:41Z): PASS** for every check that does
not need a person. The authorization-server metadata answers 200 with
issuer `https://mcp.almckay.io/kubernetes/mcp` and Authentik's endpoints;
unauthenticated `POST` still 401; `apps` Ready; no restarts. Outstanding:
Al's `claude mcp add` sign-in (allow-listed `tools/list`, listing pods)
and the 403 check for a user outside `mcp-users`.

**End-to-end sign-in (2026-10-18 18:57Z): PASS.** The first attempt was
refused by Authentik ("Policy binding 'None' returned result 'False'")
because the three MCP groups were created empty and `al` was in none of
them. Al added `al` to `mcp-users` in the Authentik UI. Claude Code then
registered through the gateway (201), and `initialize`, `tools/list` and
`tools/call pods_list` all returned 200. The tool names in that
`tools/list` response were not recorded, so the allow-list check stays
outstanding until it is run with `mcp-test-user`. **Onboarding a person
means adding them to `mcp-users` in the Authentik UI**; the blueprint
manages the groups, not human members. Agents are different: each one is
defined in the blueprint with `mcp-agents` and its `agent-role-*` groups
(plan section 2.7), so its access is reviewed in git.

**Test identities (2026-10-18, Al's request):** two Authentik service
accounts in the MCP blueprint let the gate run without a person.
`mcp-test-user` (in `mcp-users`) should get 200 and the read tools;
`mcp-test-outsider` (in `mcp-admin` only) gets a token but must be
refused every tool. The group check sits in the per-tool MCP authorization
rule, not in a request-level policy, so agentgateway v1.5 is expected to
answer 200 with an empty `tools/list` and refuse each `tools/call`, rather
than return 403. The gate passes on either shape as long as no tool is
listed or callable; record which one was seen. Both use the `client_credentials` grant with their
Authentik-generated app password, which is never written to the repo.
Request `scope=profile` (with `openid`), or the token has no `groups` claim
and the gateway refuses even `mcp-test-user`:

```bash
curl -s https://auth.almckay.io/application/o/token/ \
  -d grant_type=client_credentials -d client_id=kubani-agentgateway-mcp \
  -d username=mcp-test-user -d "password=$APP_PASSWORD" \
  -d "scope=openid profile email"
```

Revoke with `state: absent` on their four blueprint entries.

**Test-identity gate (2026-10-18 22:16Z): PASS.** Tokens carried
`groups: [mcp-users]` and `groups: [mcp-admin]` respectively, issuer and
audience as configured. Requests went through Traefik to
`https://mcp.almckay.io/kubernetes/mcp`.

| Identity | `initialize` | `tools/list` | `tools/call` |
|---|---|---|---|
| `mcp-test-user` | 200, session issued | 200 with exactly the 10 allow-listed tools (`events_list`, `namespaces_list`, `nodes_top`, `pods_get`, `pods_list`, `pods_list_in_namespace`, `pods_log`, `pods_top`, `resources_get`, `resources_list`) | `pods_list_in_namespace` (`mcp`) 200 with the `kubernetes-mcp` pod; `pods_delete` 400 |
| `mcp-test-outsider` | 200, session issued | 200 with `"tools":[]` | `pods_list_in_namespace` 400 |

So the outsider is refused by filtering, not 403, as expected for a
per-tool rule. `auth` pods have no egress to Traefik, so mint the tokens
from the worker against the in-cluster Service
(`http://authentik-server.auth.svc.cluster.local/application/o/token/`
with `Host: auth.almckay.io` and `X-Forwarded-Proto: https`, which keeps
the issuer correct) and make the MCP calls from a host that reaches
Traefik.

## M3: embeddings on, Graphiti MCP server

| | Before | After |
|---|---|---|
| `vllm` | `vllm-embeddings` at 0 replicas | 1 replica on sparky (decision D1), served through the gateway's existing `/v1/embeddings` route |
| `mcp` | `kubernetes-mcp` only | `graphiti-mcp` Deployment and Service on rig0, Secret `graphiti-mcp` (the `graphiti_mcp` FalkorDB user's password), egress to FalkorDB and to Traefik for `ai.almckay.io` |
| `database` | FalkorDB reachable from `database` and Traefik; one account (`default`) | plus `allow-mcp-falkordb` from `graphiti-mcp` pods; an ACL user `graphiti_mcp` (Secret `falkordb-graphiti-mcp`) that may only run `GRAPH.QUERY`, `GRAPH.RO_QUERY` and `GRAPH.EXPLAIN` on the `graphiti_mcp` key. The FalkorDB pod restarts once to pick it up (RDB is saved on shutdown) |
| `ai-gateway` | Kubernetes MCP route | AgentgatewayBackend, HTTPRoute (`/graphiti/mcp` and its `.well-known` paths) and AgentgatewayPolicy: same Authentik auth; allow-list is the read tools plus `add_memory`; deletes, `clear_graph`, `add_triplet` and the batch jobs are denied |

Graphiti writes to its own `graphiti_mcp` graph (decision D2). Callers can
pass any `group_id`, which Graphiti uses as the graph name, and agentgateway
1.5 cannot read tool arguments at authorization time; so the isolation is in
FalkorDB itself: the server's account gets NOPERM on every other graph (Codex
review on #214). Tested locally against FalkorDB with the same ACL line: own
graph read and write work; other graphs, `GRAPH.DELETE`, `FLUSHALL` and
`KEYS` are refused. LLM calls go
to `default` (main with failover to fast); embeddings to
`Qwen/Qwen3-Embedding-0.6B` at 1024 dimensions.

**Capacity:** sparky +500m / 12Gi requests (the ledger line agreed in
advance; 45 GiB available before, floor 15 GiB, 2 of 4 GPU slices free);
rig0 +100m / 384Mi.

**Rollback SHA:** `f5487a01f43c81f0cae56885462eff8a9645dd25` (main before
the M3 merge). `git revert -m 1 <M3 merge>` removes the server, routes,
policies and secret, and scales embeddings back to 0. The revert also
removes the ACL user (FalkorDB restarts once more). Left behind: the
`graphiti_mcp` graph in FalkorDB (harmless; optional `GRAPH.DELETE
graphiti_mcp`).

**Gate (plan 2.8):**
- `vllm-embeddings` Ready; one `/v1/embeddings` call through
  `ai.almckay.io` returns a 1024-dimension vector; sparky available memory
  stays above 15 GiB.
- FalkorDB Ready after its restart; `ACL LIST` shows `graphiti_mcp`; the
  agent runtime's graphs still answer with the default account.
- `graphiti-mcp` Ready on rig0, 0 restarts, no FalkorDB connection errors.
- `search_nodes` with `group_ids: ["<another graph>"]` returns an error
  (NOPERM), not data.
- With `mcp-test-user`: `tools/list` shows exactly the seven allowed tools;
  `add_memory` then `search_nodes` returns the new entity; FalkorDB
  `GRAPH.LIST` includes `graphiti_mcp`.
- With `mcp-test-outsider`: empty `tools/list`.
- Shared-gateway regression check above.

**Gate result (2026-10-19 00:13Z, after #215): PASS.** One embeddings call
through `ai.almckay.io` returned a 1024-dimension vector. `ACL USERS` lists
`default` and `graphiti_mcp`; `GRAPH.LIST` includes `graphiti_mcp` beside
the agent runtime's graphs, which still answer with the default account.
`mcp-test-user` saw exactly the seven tools; `get_status` reported the
FalkorDB connection; `add_memory` queued an episode in `graphiti_mcp` and
`search_nodes` returned its entities; `search_nodes` on `redcell_fp`
returned "No permissions to access a key". `mcp-test-outsider` got an empty
`tools/list` and 400 on calls. Kubernetes MCP unchanged (10 tools,
`namespaces_list` works). `clear_graph` was not called as a negative test;
it is absent from `tools/list`.

Two fixes were needed after the M3 merge, both in #215: the backend path
`/mcp/` answered 307, so the target is `/mcp`; and `vllm` had no policy
admitting the gateway to the embeddings pods on 8000
(`allow-ai-gateway-embeddings-ingress`, plus the egress rule).

**Embeddings model cache:** the `vllm-embeddings` pod crash-looped at first
because its Hugging Face cache lacked `Qwen/Qwen3-Embedding-0.6B`. It was
downloaded by hand on sparky into the `vllm/model-storage` PVC's `hub`
directory (revision `97b0c614…`). Do not delete `hub/blobs`: the snapshot
links point into it, and the pod runs offline.

## M4: Postgres MCP server, read-only

| | Before | After |
|---|---|---|
| `database` | no MCP role | Job `postgres-mcp-role-v1` creates `mcp_readonly` (LOGIN only, `default_transaction_read_only`, 15 s statement timeout), CONNECT on `starbase2_prod` only, SELECT on its tables and views except any with a credential-like column (the Job logs the ones it skips); Secret `postgres-mcp-role`; `allow-mcp-postgresql` ingress and the Job's egress |
| `mcp` | Kubernetes and Graphiti servers | `postgres-mcp` Deployment (`crystaldba/postgres-mcp:0.3.0`, `--access-mode=restricted`, SSE) and Service on rig0; Secret `postgres-mcp` (DATABASE_URI for `mcp_readonly`); egress to PostgreSQL |
| `ai-gateway` | Kubernetes and Graphiti routes | AgentgatewayBackend (SSE target), HTTPRoute (`/postgres/mcp` and its `.well-known` paths) and AgentgatewayPolicy: same Authentik auth; all nine 0.3.0 tools allowed |

The password is new (generated for this step, never a copy of an existing
credential). Writes are refused twice: restricted mode runs every query in a
read-only transaction, and the role has no write grants anywhere.

**Capacity:** rig0 +50m / 128Mi requests.

**Rollback SHA:** `97401aa84be1cb1cc077320ceda7ee0bf20de1e2` (main
before the M4 merge). `git revert -m 1 <M4 merge>` removes the server, routes, policy, Job and
secrets. Left behind: the `mcp_readonly` role. Cleanup (plan 6.2), as
postgres: `DROP OWNED BY mcp_readonly` in `starbase2_prod`, then
`DROP ROLE mcp_readonly`.

**Gate (plan 2.8):**
- Job `postgres-mcp-role-v1` Complete; its log lists the skipped tables.
- `postgres-mcp` Ready on rig0, 0 restarts.
- With `mcp-test-user`: `tools/list` shows exactly the nine tools;
  `execute_sql` with `SELECT 1` succeeds; `CREATE TABLE` is refused.
- As `mcp_readonly` directly: `CREATE TABLE` fails (read-only transaction
  and no CREATE grant); reading any table in `authentik` or `temporal` is denied.
- With `mcp-test-outsider`: empty `tools/list`.
- Shared-gateway regression check above.

**Gate result (2026-10-19 00:15Z, after #215): PASS, with one correction.**
The Job completed (`granted SELECT on 19 of 19 relations`, none skipped)
and `postgres-mcp` is Ready on rig0. `mcp-test-user` saw exactly the nine
tools; `execute_sql` ran `SELECT 1` as `mcp_readonly` on `starbase2_prod`;
`CREATE TABLE` was refused by the server's query check. In the role's own
session: `default_transaction_read_only` on, 15 s statement timeout, no
CREATE on the database or on `public`. `mcp-test-outsider` got an empty
`tools/list` and 400 on calls.

Correction: the role can CONNECT to the other databases (`authentik`,
`temporal`) through PostgreSQL's default PUBLIC grant, which cannot be
revoked for one role alone. There it sees only the system catalogs, since
it holds no table grants. The MCP server cannot reach them: it connects
only to `starbase2_prod` and has no way to switch database. Closing it
fully needs a `pg_hba` reject rule for `mcp_readonly` outside
`starbase2_prod`, which restarts PostgreSQL.
Al chose to leave it (2026-10-19): catalog-only visibility does not justify
a PostgreSQL restart.

## M5: GitHub MCP server, read-only

| | Before | After |
|---|---|---|
| `mcp` | Kubernetes, Graphiti and Postgres servers | `github-mcp` Deployment (`ghcr.io/github/github-mcp-server:v2.0.2`, `http --read-only`, toolsets context, repos, issues, pull_requests, actions) and Service on rig0; egress to public addresses on 443 only |
| `ai-gateway` | three MCP routes | Secret `github-mcp-pat` (SOPS; Al's fine-grained read-only PAT, 90-day expiry) and AgentgatewayBackend whose auth policy sends it as `Authorization` in place of the client's JWT; HTTPRoute (`/github/mcp` and its `.well-known` paths) and AgentgatewayPolicy with the same Authentik auth; humans in `mcp-users`, agents in `mcp-agents` plus `agent-role-github-read` (Authentik blueprint) |

Read-only twice: the server never registers write tools with `--read-only`,
and the PAT has read-only permissions. The pod sees the PAT on every request
and is inside its trust boundary (plan section 7).

**Capacity:** rig0 +50m / 64Mi requests.

**Rollback SHA:** `fb947c3fe1e703edddf2ee6282f883f1680a009b` (main
before the M5 merge). `git revert -m 1 <M5 merge>` removes the server, route, policy and Secret; **also revoke
the PAT in GitHub** if a leak is the reason (plan 6.2).

**Gate (plan 2.8):**
- `github-mcp` Ready on rig0, 0 restarts.
- With `mcp-test-user`: `get_me` returns X-McKay (proves the gateway
  replaced the JWT with the PAT); `tools/list` has no write tool (`create_*`,
  `update_*`, `delete_*`, `merge_*`, `push_*`); one `list_*` or `search_*`
  call on an X-McKay repo succeeds.
- With `mcp-test-outsider`: empty `tools/list`.
- Shared-gateway regression check above.

**Gate result (2026-10-19 01:20Z, after #216): PASS.** `github-mcp` Ready on
rig0, 0 restarts. `mcp-test-user`: `get_me` returned X-McKay; `tools/list`
has 29 tools, all reads (`get_*`, `list_*`, `search_*`, `*_read`,
`actions_get`, `actions_list`, `ui_get`), none that create, update, delete,
merge or push; `list_branches` on `X-McKay/kubani` worked.
`mcp-test-outsider`: empty `tools/list`, 400 on calls. Unauthenticated POST:
401.

## O1: agent-sandbox controller

| | Before | After |
|---|---|---|
| cluster | no `sandboxes.agents.x-k8s.io` CRD | CRD and `agent-sandbox-controller` v0.5.6 (pinned, vendored unmodified, local changes as kustomize patches) in `agent-sandbox-system` on rig0, PSA restricted |
| network | | default-deny ingress; ingress from node addresses to the conversion webhook on 9443; egress to DNS and the API server only |

Nothing uses it until O2. The controller manages its own webhook certificate
and the CRD's `caBundle`; Flux does not set that field.

**Capacity:** rig0 +20m / 64Mi requests.

**Rollback SHA:** `e98d009fb3ff0aad6ea304e0e49fa1c78a10b512` (main
before the O1 merge). Revert only
after O2 and O3 are reverted: deleting the CRD deletes every `Sandbox` with
it, so check `kubectl get sandboxes -A` is empty first.

**Gate (plan 3.3):**
- CRD `sandboxes.agents.x-k8s.io` Established.
- `agent-sandbox-controller` Ready on rig0, 0 restarts, no webhook or
  permission errors in its log.
- A server-side dry run of a minimal `Sandbox` is accepted (exercises the
  CRD schema without creating anything).
- Shared-gateway regression check above.

**Gate result (2026-10-19 02:26Z, after #217): PASS, one check deferred.**
CRD `sandboxes.agents.x-k8s.io` Established, serving v1beta1 and v1alpha1;
the controller patched its conversion `caBundle` at startup. Controller
Ready on rig0, 0 restarts; its log shows the webhook serving on 9443 and no
errors. All pods in `mcp`, `ai-gateway` and `auth` Ready, no gateway 5xx.
The server-side dry run could not be run from the tooling available (its
dry run is client-side and accepts any field), so the schema and the
conversion webhook are first exercised by OpenShell in O2 (chart preflight)
and O3 (first Sandbox).

## O2: OpenShell gateway

| | Before | After |
|---|---|---|
| `openshell` (new, PSA baseline enforce, restricted warn/audit) | | HelmRelease `openshell` (chart 0.1.4 from `oci://ghcr.io/nvidia/openshell/helm-chart`, pinned): gateway StatefulSet on rig0 with SQLite on a 1Gi Longhorn PVC, telemetry off; cert-manager CA, internal server and client certificates (chart CA), external server certificate for `openshell.almckay.io` from `letsencrypt-prod`; retained key-encryption-key Secret generated in-cluster |
| `openshell-sandboxes` (new, PSA baseline enforce, restricted warn/audit) | | sandbox ServiceAccount, Role, the chart's SSH NetworkPolicy; ResourceQuota 4 CPU / 8Gi, LimitRange defaults. No sandboxes until O3 |
| Traefik | | `IngressRouteTCP` on websecure, SNI `openshell.almckay.io`, TLS passthrough; an `openshell-dns` Ingress on `web` that exists only so external-dns publishes the name (on websecure it shadowed the passthrough; fixed after the O2 gate) |
| Authentik | | blueprint `kubani-openshell.yaml`: application `openshell`, provider `Kubani OpenShell` (public, PKCE, client `kubani-openshell`), groups `openshell-admin`, `openshell-user`; gate identities `openshell-test-user` (openshell-user) `openshell-test-outsider` (group `openshell-test-norole`, admitted to the application with no OpenShell role) and, added after the gate, `openshell-test-admin` (openshell-admin) to grant workspace membership |
| network | | `openshell`: default-deny ingress; ingress to the gateway on 8080 from Traefik and from `openshell-sandboxes`; egress to DNS, the API server, Traefik (Authentik issuer and JWKS) and `openshell-sandboxes`. `openshell-sandboxes`: default-deny ingress; ingress from the gateway only |

The gateway validates every user call against Authentik: issuer
`https://auth.almckay.io/application/o/openshell/`, audience
`kubani-openshell`, roles from `groups`. mTLS stays on for supervisors; an
OIDC listener still admits bearer-only CLI clients. The data PVC's missing
storage class is patched with a post-renderer. The chart's certgen
pre-install hook has no runAsNonRoot or seccomp profile, and helm-controller
v1.4.x (Helm 3) does not post-render hooks, so `openshell` enforces baseline
rather than restricted; the gateway pod itself meets restricted, which
stays as warn and audit.

**Not checked in ring 0:** the supervisor pod spec comes from the gateway
binary, so its PSA needs and node placement show up only with the first
sandbox (O3). Landlock on rig0 is likewise exercised by O3: OpenShell fails
closed without it.

**Capacity:** rig0 +100m / 256Mi requests for the gateway; sandboxes
capped by quota at 4 CPU / 8Gi.

**Rollback SHA:** `e39caad371955a3518ae240267ef789b9ebeda7f` (main
before the O2 merge). `git revert -m 1 <O2 merge>`
removes the release, route and namespaces; set the blueprint entries to
`state: absent` first (authentik-app skill). The retained KEK Secret and
the PVC go with the namespace.

**Gate (plan 3.3):**
- HelmRelease Ready; gateway Ready on rig0, 0 restarts; both server
  certificates Ready, the external one with `openshell.almckay.io` only.
- `openshell.almckay.io` resolves and presents the Let's Encrypt
  certificate through Traefik.
- With an `openshell-test-user` token: an authenticated `ListSandboxes`
  call succeeds.
- Rejected: no token; an expired or altered token; a token from the MCP
  provider (wrong `aud`); an `openshell-test-outsider` token (no role).
- Shared-gateway regression check above.

**Gate result:** PASS at 04:34Z (the expired-token check, the last case run), after two fixes.
- Install (#218, 03:29Z): the HelmRelease was Ready and the gateway Ready on rig0 with 0 restarts. All four certificates were Ready, the external one from Let's Encrypt for `openshell.almckay.io`. external-dns published the A record.
- Through `openshell.almckay.io`, the result for each case:
  - no token: Unauthenticated, "missing authorization header";
  - altered signature: Unauthenticated, `InvalidSignature`;
  - expired token: Unauthenticated, `ExpiredSignature`;
  - MCP token: Unauthenticated, `InvalidIssuer`;
  - outsider: PermissionDenied, "role 'openshell-user' required";
  - test user: `ListSandboxes` OK (empty list) on the `default` workspace.
- Shared-gateway regression: the LLM, Authentik and Grafana routes stayed 200.
- Fix 1 (#220): Traefik answered `openshell.almckay.io` with its default certificate and a 502. Traefik runs websecure with `http.tls=true`, so the DNS-only Ingress there became a TLS router that shadowed the passthrough. A temporary probe route on a name with no HTTP router passed through, which confirmed it. The Ingress moved to `web`.
- Fix 2 (#221): OpenShell authorizes by workspace membership as well as role, and only a platform admin can grant membership. `openshell-test-admin` (openshell-admin) was added with Al's approval, and it added `openshell-test-user` to `default` as a user. The membership lives in the gateway's SQLite, not in Git. After O3 passed, the admin and its app password were set to `state: absent`; the two absent entries come out in a later change once the objects are confirmed gone.
- Expired token (04:34Z): an `openshell-test-user` token minted at 03:30Z with `exp` 04:23Z, otherwise valid and for a user who by then was a workspace member, was rejected: Unauthenticated, `ExpiredSignature`.

## O3: first sandbox

No new workload: O3 is the first sandbox on the O2 gateway, created and
deleted by the gate itself.

**Gate (plan 3.3):** a sandbox runs `uname`; egress the policy does not
allow fails; egress to `ai.almckay.io` that it allows returns a completion.
Also recorded: where the sandbox pods land, what PSA they need, and that
Landlock works on that node.

**Fix 1 (before the gate could run):** the first `o3-gate` sandbox never
became ready. Its supervisor pod sat in `ContainerCreating` with
`FailedMount: secret "openshell-client-tls" not found`. In shared workspace
mode the supervisor mounts that client certificate from
`openshell-sandboxes`, but the chart issues it only in `openshell`, from a
namespaced Issuer that cannot sign anywhere else. The fix makes the chart's
CA cluster-scoped with post-renderer patches (its CA Certificate moves to
`cert-manager`, both chart Issuers become ClusterIssuers) and adds
`sandbox-client-tls.yaml`, the same client Certificate issued into
`openshell-sandboxes`. The CA key is regenerated, so cert-manager reissues
the internal server and client certificates and Reloader restarts the
gateway. The external `openshell.almckay.io` certificate (Let's Encrypt) is
untouched, so CLI users see no change.

- Test: both client certificates and the internal server certificate Ready
  and signed by the new CA; gateway Ready after its restart; the O2 public
  checks (no token rejected, test user `ListSandboxes` OK) still pass; then
  the O3 gate.
- Rollback: revert the fix PR. The chart's namespaced Issuers and CA come
  back and cert-manager reissues from them; delete the leftover
  `openshell-ca-tls` Secret in `cert-manager` and the `openshell-client`
  Certificate and Secret in `openshell-sandboxes` if prune leaves them.
- Cleanup after the fix: the old CA Secret `openshell-ca-tls` in
  `openshell` is no longer referenced (cert-manager does not delete
  Secrets) and is deleted once the gateway runs on the new CA.
- Fix result (#223, reconciled 05:09Z): both ClusterIssuers Ready, the CA
  issued in `cert-manager`, the internal server and client certificates
  reissued, and the new `openshell-sandboxes` client certificate issued. All
  three carry the same `ca.crt`. Reloader restarted the gateway, which came
  back Ready with 0 restarts, and the CLI still authenticated through
  `openshell.almckay.io`. The old `openshell-ca-tls` Secret in `openshell`
  is still there, waiting on Al's go-ahead to delete it.

**Gate result:** PASS at 05:14Z (the last case run), on rig0.
- `uname -a` in the sandbox: `Linux 6.14.0-37-generic x86_64`, as uid 10001.
  The sandbox was Ready about 7 s after the create call.
- The default image (`nvcr.io/nvidia/base/ubuntu:24.04`) has no curl or
  wget, so the egress cases ran in `curlimages/curl:8.11.1` with this
  policy:
  ```yaml
  version: 1
  filesystem_policy:
    include_workdir: true
    read_only: [/usr, /lib, /etc, /bin]
    read_write: [/tmp]
  network_policies:
    ai_gateway:
      endpoints:
        - host: ai.almckay.io
          port: 443
          protocol: rest
          enforcement: enforce
          rules:
            - allow: {method: POST, path: "/v1/chat/completions"}
      binaries:
        - path: /usr/bin/curl
  ```
- Blocked egress: `curl https://example.com` failed to connect.
- Allowed egress: `POST https://ai.almckay.io/v1/chat/completions` with
  model `default` returned 200 and a `chat.completion`. `GET /v1/models` on
  the same host returned 403 from the policy's L7 rule. No credential was
  injected, because `ai.almckay.io` has no key auth until Phase 3.
- Landlock works on rig0. With the default filesystem policy the curl
  image's supervisor failed to start the workload, because `/bin/sh` was
  outside what it could read, so Landlock was enforcing. Adding `/bin`
  read-only fixed that.
- PSA: the supervisor and workload pods run as uid 10001 with no
  privilege escalation, every capability dropped and RuntimeDefault seccomp.
  A server-side dry run of `enforce=restricted` on `openshell-sandboxes`
  returned no warnings, so baseline is enough and restricted is possible
  later.
- Placement: the sandbox pods carry no node selector. Every one landed on
  rig0, but the scheduler chose that. Pinning needs
  `server.drivers.kubernetes.allowDriverConfig` and a per-sandbox driver
  config, and is left as a follow-up.
- Cleanup: both sandboxes and the gate client were deleted, leaving no
  pods, PVCs or Sandboxes in `openshell-sandboxes`. The driver's own
  NetworkPolicies stay, because the gateway manages them.

## Resource readings
| Step | T+15 min | T+1 h |
|---|---|---|
| M0 | PASS (23:48Z): no gateway requests in the window, no restarts in `ai-gateway` or `auth`, `mcp` policies present | PASS (00:33Z): 40 gateway requests since M0, all 200; no restarts; all pods Ready |
| M1 | PASS (00:52Z): no 4xx/5xx besides the gate probes' 404s, no 200s or errors from clients in the window; no restarts in `ai-gateway` or `auth`; all pods Ready; `mcp.almckay.io` still 404 from the gateway | PASS (01:36Z): 46 gateway requests, all 200 apart from 6 gate-probe 404s; no restarts in `ai-gateway` or `auth`; all pods Ready; `mcp.almckay.io` 404 from the gateway |
| M2 (from the #210 fix) | PASS (01:57Z): gateway 200s and only the gate probes' 401s, no 404/500/502; no restarts in `ai-gateway`, `auth` or `mcp`; all pods Ready; metadata 200, unauthenticated 401 | PASS (02:43Z): 42 gateway requests all 200 apart from 2 gate-probe 401s, no 500s; no restarts; all pods Ready; `kubernetes-mcp` at 15 MiB working set (request 64Mi) |
| M3 and M4 (live 00:12Z after #215) | PASS (00:29Z): gateway about 53 2xx, 4 gate-probe 400s, no 401/404/5xx; no restarts in `mcp`, `ai-gateway`, `auth`, `database` or `vllm`; all pods Ready; sparky 31.2 GiB available; `graphiti-mcp` 201 MiB, `postgres-mcp` 73 MiB working set | PASS (01:15Z): gateway about 113 2xx, 4 gate-probe 400s, no 401/404/5xx; no restarts; all pods Ready; sparky 31.2 GiB available; `graphiti-mcp` 203 MiB, `postgres-mcp` 73 MiB; PostgreSQL 0.91 ms per transaction |
| M5 (live 01:19Z after #216) | PASS (01:36Z): no gateway requests in the window, no errors; no restarts in `mcp`, `ai-gateway` or `auth`; all pods Ready; `github-mcp` 17.7 MiB working set (request 64Mi) | PASS (02:20Z): no gateway requests and no errors in the hour; no restarts; all pods Ready; `github-mcp` 18.0 MiB; sparky 31.2 GiB available |
| O1 (live 02:22Z after #217) | PASS (02:42Z): controller Ready, 0 restarts, no log errors, 14.7 MiB working set (request 64Mi); no gateway requests or errors; no restarts in `mcp`, `ai-gateway` or `auth`; all pods Ready; rig0 37.1 GiB available | PASS (03:24Z): controller Ready, 0 restarts, 17.7 MiB, info-level logs only; about 14 gateway 2xx and no errors; no restarts; all pods Ready; rig0 37.3 GiB available. A separate OpenShell install (`zetra-poc`, not in Git) started using the CRD at about 03:01Z; the controller reconciled its Sandboxes without errors |
| O2 (install 03:29Z after #218; route fix 03:40Z after #220) | PASS (03:47Z): HelmRelease Ready, gateway 0 restarts, 15.6 MiB working set (request 256Mi), 4/4 certificates Ready; rig0 37.2 GiB available; public path rejects no-token calls | PASS (04:31Z): gateway 0 restarts, 25.7 MiB (1 h max 25.7 MiB), negligible CPU; 4/4 certificates Ready; rig0 37.2 GiB available; gate client removed |
| O3 (gate PASS 05:14Z; CA fix live 05:09Z after #223) | PASS (05:30Z): gateway Ready, 0 restarts since the #223 restart, 46 MiB working set; every certificate and both OpenShell ClusterIssuers Ready; no pods or PVCs left in `openshell-sandboxes`; no restarts in `ai-gateway` or `auth`; rig0 at 43% memory; gateway logs show only the gate's own CreateSandbox warnings and one routine watch expiry, no errors | PASS (06:22Z): gateway Ready, 0 restarts, 46 MiB; every certificate and both OpenShell ClusterIssuers Ready; `openshell-sandboxes` still empty; no restarts in `ai-gateway` or `auth`; rig0 at 39% memory; gateway logs show one routine watch expiry and no errors in 55 minutes |

## Decision
<kept / reverted, and why>
