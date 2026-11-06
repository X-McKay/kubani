# Agent Runtime Platform — Implementation Specification

Oct 30, 2026 · @Al McKay

This specification defines a platform that runs AI agents in per-session Kata Containers virtual machines, forces every outbound call (model inference and MCP tool calls) through agentgateway, authenticates agents with OAuth 2.0 access tokens, injects every upstream credential at the gateway, and lets each agent act either under its own identity or on behalf of a user. It is self-contained: an engineer who has never seen any earlier system can implement it from this document alone. Revision 2 incorporates an external design review; section 18 records each finding, its verdict and where the specification changed.

## 1. Scope, requirements and definitions

The platform guarantees that an agent can reach only the gateway, holds no credential usable anywhere else, and is identified, authorized, budgeted and audited on every call by policy bound to its registered release.

### 1.1 Requirements

Each requirement is normative. The test column names the conformance test in section 15 that proves it.

| ID | Requirement | Test |
| --- | --- | --- |
| R1 | Every byte leaving a sandbox is delivered to the agentgateway data plane. No other destination is reachable, including DNS, the Kubernetes API server, the identity provider, model servers and MCP servers. | T1, T2 |
| R2 | The only secret material inside a sandbox is a Kubernetes projected ServiceAccount token bound to that pod, with a 10-minute lifetime and the identity provider as its sole audience. | T3 |
| R3 | Agents authenticate to the gateway over TLS with an OAuth 2.0 access token issued by the identity provider, obtained with the projected token as an RFC 7523 client assertion through the gateway's token route. No static client secret or API key exists for any agent. | T4, T5 |
| R4 | Every model endpoint and every MCP endpoint requires authentication. The gateway authenticates the agent inbound and presents a gateway-held or freshly exchanged credential outbound. The inbound token is never forwarded upstream. | T6, T7, T12 |
| R5 | The gateway derives the agent and the session from the access token and the source pod, not from any header the sandbox sets. Headers prefixed `x-agent-` arriving from a sandbox are discarded. | T8 |
| R6 | Each agent release is an immutable snapshot of image digest, manifest digest and policy-bundle digest, bound by a signature. Approval applies to that snapshot only; a change to any of the three is a new release. A sandbox may be created only for an approved, signature-verified, drift-free release. | T9 |
| R7 | Each agent declares a delegation mode, `agent` or `on-behalf-of`, with a per-upstream override. In `on-behalf-of` mode the upstream receives a token whose `sub` is the user and whose `act.sub` is the agent, audience-restricted to that upstream. | T10, T11 |
| R8 | Per-agent and per-session token budgets are enforced by trusted components (never by code in the sandbox) and survive gateway restarts. | T13 |
| R9 | Every request carries, in traces and access logs, the agent ID, SPIFFE ID, release, policy digest, session ID, principal (when delegated), decision reason and request ID. | T14 |
| R10 | Cancelling a session, disabling an agent, revoking a user's consent or rotating a gateway-held credential takes effect without touching a running sandbox, within the bounds in section 3. | T15, T16 |
| R11 | The Agent Policy Service fails closed. If it is unreachable, every request that depends on it is denied. | T17 |

### 1.2 Out of scope

- Multi-agent orchestration and agent-to-agent protocols. The registry can publish an A2A Agent Card, but no agent-to-agent call is admitted.
- The content of agent code. The platform treats the sandbox as hostile; it does not review prompts, tools or models.
- Human consent user interfaces. Consent is recorded by the identity provider; this specification only requires that the identity provider can express it.
- Protection against a compromised gateway, policy service, identity provider or Kubernetes control plane. Those are trusted components.

### 1.3 Definitions

| Term | Meaning |
| --- | --- |
| Agent | A registered identity that runs code in sandboxes. Stable across releases. One Kubernetes ServiceAccount per agent per tenant. |
| Agent release | An immutable, signed combination of container image digest, agent manifest, compiled policy bundle and policy digest. The unit of approval. |
| Tenant | A Kubernetes namespace that owns agents, their releases and their sandboxes. Policy never crosses tenants. |
| Session | One execution of one agent release, identified by a session ID chosen by the Session Runner. Exactly one sandbox generation is live per session at a time. |
| Generation | A counter within a session; incremented when a sandbox is replaced after failure. |
| Sandbox | A Kata Containers pod created from the release's pod template, named deterministically from session and generation. |
| Session Runner | The Temporal worker that creates sandboxes, drives execution through the kubelet exec API, records progress in Temporal history and confirms deletion. |
| Gateway | agentgateway, version 1.7.0 or later, the single egress point for sandboxes. |
| Agent Policy Service (APS) | The external authorization service the gateway calls on every sandbox request. It resolves the agent and session, applies registry policy, performs token exchange and returns the upstream credential. |
| Registry | The `Agent` and `AgentRelease` custom resources, reconciled by the Registry Controller into ServiceAccounts, identity provider clients, gateway policies and sandbox templates. |
| Identity provider (IdP) | An OAuth 2.0 and OpenID Connect server that can accept a Kubernetes projected token as an RFC 7523 client assertion and perform RFC 8693 token exchange with delegation. Keycloak 26.8 is the reference; section 7 maps Authentik and Entra ID. |
| Projected token | The Kubernetes ServiceAccount token the kubelet writes into the sandbox, bound to the pod, with audience set to the identity provider. |
| Agent access token | The OAuth 2.0 access token the identity provider issues to the agent, audience `agent-gateway`, used as the bearer token on every gateway request. |
| Subject token | A user's access token, captured when a delegated session is submitted and stored in the APS token vault. Never enters a sandbox or Temporal history. |
| Upstream token | A token minted by RFC 8693 exchange for exactly one upstream resource, with `act` set in delegated mode. |
| Grant handle | An opaque identifier for a vault entry. The only reference to a subject token that leaves the APS. |
| Delegation mode | `agent` (the agent acts as itself) or `on-behalf-of` (the agent acts for a user). Declared per agent, overridable per upstream. |
| Policy bundle | The compiled allow-lists and limits for one release: routes, models, MCP backends and tools, effect classes, budgets, delegation per upstream. Its SHA-256 is the policy digest. |
| Effect class | `workspace_read`, `workspace_write`, `remote_read` or `remote_write`, declared per tool. Only the first three are admitted by this specification. |
| SPIFFE ID | `spiffe://<trust-domain>/ns/<tenant>/sa/agent-<name>`, the agent's identity string, carried as a token claim and a trace attribute. |
| Trust domain | The DNS-style name under which SPIFFE IDs are minted. One per organisation. |

## 2. Architecture

Seven components, one of which (the sandbox) is untrusted; the gateway is the only component the sandbox can reach.

&#91;embedded content: architecture · 7 components, 9 calls\]

The sandbox obtains its OAuth token through the gateway's token route, then calls models and tools through the gateway; the gateway asks the policy service, which reads the registry and exchanges tokens at the identity provider; the Session Runner provisions sandboxes and reports session events.

### 2.1 Responsibilities

| Component | Runs in | Must do | Must never do |
| --- | --- | --- | --- |
| Sandbox (Kata VM) | namespace `agent-sandboxes-<tenant>` | Run one session of one release; obtain its access token with the projected token; call models and tools through the gateway; write results to its workspace volume. | Hold any other secret; reach any address except the gateway; set `x-agent-*` headers (they are discarded). |
| agentgateway (1.7.0 or later) | namespace `ai-gateway` | Terminate every sandbox connection; validate the access token against the identity provider; call the policy service on every request; apply CEL tool and model rules; enforce budgets; inject upstream credentials; strip the inbound token; emit traces and access logs. | Forward the inbound token upstream; serve any route to a sandbox without a policy service decision; accept human-issued tokens on the agents listener. |
| Agent Policy Service | namespace `agent-platform`, 2 or more replicas | Map token and source pod to agent, tenant, session and release; evaluate the release's policy bundle; perform delegated token exchange; hold subject tokens in the vault; return headers and a decision reason; deny when uncertain. | Return a subject token to anyone; cache a decision beyond its TTL; allow when the registry or pod lookup fails. |
| Registry Controller | namespace `agent-platform`, 1 replica, leader elected | Reconcile `Agent` and `AgentRelease` into ServiceAccounts, identity provider clients, compiled policy bundles, sandbox pod templates and the policy digest. | Approve a release (approval is a human status change); write any credential value into a resource. |
| Session Runner | namespace `agent-platform` (one Deployment per tenant queue) | Create sandboxes idempotently with deterministic names; wait for readiness; drive execution over the kubelet exec API; record every accepted step in Temporal history; confirm deletion; deposit the subject token in the vault at submission and keep only the grant handle. | Pass a token into a sandbox spec or a workflow input; create a second generation before deletion of the previous one is confirmed. |
| Identity provider (Keycloak 26.8 reference) | namespace `auth` or external | Accept projected tokens as client assertions for agent clients; issue agent access tokens with `aud: agent-gateway`; perform RFC 8693 exchange with `act` for delegation; enforce `may_act` and consent; expose JWKS. | Issue an agent token to a client that presents a client secret; issue a delegated token for a resource the user did not consent to. |
| Upstreams (model servers, MCP servers, external APIs) | namespaces `llm`, `mcp`, or external | Require a credential on every request; validate the audience of OAuth tokens; apply their own authorization using `sub` and `act`. | Accept traffic from any source other than the gateway (in-cluster NetworkPolicy enforces this). |

## 3. Naming and constants

Every name below is used verbatim by every component; a mismatch in any one of them is the most likely implementation error, so treat this section as the shared configuration file. Values written as `<...>` are deployment inputs; everything else is fixed.

### 3.1 Namespaces and workloads

| Constant | Value | Notes |
| --- | --- | --- |
| Platform namespace | `agent-platform` | Registry Controller, Agent Policy Service, Session Runner, rate-limit service, Redis, cleanup reconciler |
| Tenant | a namespace whose name matches `^tenant-[a-z0-9-]{1,50}$`, e.g. `tenant-a` | The tenant's name **is** its namespace name; the `tenant` claim, the `agent_id` prefix and the SPIFFE path all use it verbatim. Holds that tenant's `Agent`, `AgentRelease`, ServiceAccounts and sandbox pods. Label `agentplatform.io/tenant: <tenant>` |
| Gateway namespace | `ai-gateway` | agentgateway control plane and the `agents` data plane |
| Identity provider namespace | `auth` | Keycloak, or an external IdP reachable from `ai-gateway` and `agent-platform` only |
| Model namespace | `llm` | Model servers (vLLM). Existing deployments may keep their namespace; the NetworkPolicy selectors in section 5 change accordingly |
| MCP namespace | `mcp` | MCP servers |
| Gateway resource | `Gateway/agents` in `ai-gateway`, class `agentgateway` | Data plane Deployment and Service are both named `agents` by the controller |
| Data plane pod label | `app.kubernetes.io/name: agents` | Used in every NetworkPolicy that names the gateway |
| Kata RuntimeClass | `kata-qemu-runtime-rs` | Installed by the kata-deploy chart with `k8sDistribution: k3s` |
| Egress guard image | `registry.example.com/platform/egress-guard@sha256:<digest>` | Platform-owned init container that proves host-side denial before the agent container starts (5.5); pinned by digest in every pod template and by admission |
| Pinned versions | agentgateway 1.7.0 (control plane, data plane and CRDs), Keycloak 26.8.x, Kata Containers at or above the CVE-2026-44210 fix, K3s 1.34.x, `mcp` Python SDK 1.x, `temporalio` 1.x, `openai` 1.x | One tested compatibility set; upgrades move the whole set and rerun section 15 |

### 3.2 Network identifiers

| Constant | Value | Notes |
| --- | --- | --- |
| `GATEWAY_CLUSTER_IP` | a fixed address in the service CIDR, e.g. `10.43.250.10` | Set as `spec.clusterIP` on Service `agents`; sandboxes have no DNS |
| `GATEWAY_PORT` | `443`, TLS from the internal CA | The reference profile is HTTPS (RFC 6750 requires TLS for bearer tokens). A plain-HTTP listener on 80 may exist only in a development profile that never runs a tenant workload |
| Internal CA | ConfigMap `agent-gateway-ca` (key `ca.crt`) copied by the Registry Controller into every tenant namespace | Mounted read-only at `/etc/agent-platform/ca.crt`; the SDK sets `AGENT_GATEWAY_CA` |
| Token route host | `token.agents.internal` | Proxies only the IdP token endpoint |
| Inference route host | `inference.agents.internal` | One path prefix per model backend: `/models/<backend>/v1/...`; the backend pins the model, so the request body is never used for authorization |
| MCP route host | `mcp.agents.internal` | One path prefix per MCP backend: `/<backend>/mcp` |
| Public MCP resource URL | `https://mcp.<domain>/<backend>/mcp` | The RFC 8707 `resource` value and token `aud` for that backend, identical inside and outside the cluster |
| Trust domain | `<trust-domain>`, default `cluster.local` | Part of every SPIFFE ID |

### 3.3 Identity provider

| Constant | Value | Notes |
| --- | --- | --- |
| `ISSUER_URL` | `https://idp.<domain>/realms/agents` | Exact string compared against `iss`; trailing slash exactly as the IdP emits it |
| Token endpoint | `${ISSUER_URL}/protocol/openid-connect/token` | Reached only by the APS; sandboxes never see it |
| Sandbox token route | `POST /v1/token` on the APS, through the gateway's `token.agents.internal` route | Accepts `client_credentials` with a projected-token assertion only; pins the issued token to the calling pod |
| JWKS | `${ISSUER_URL}/protocol/openid-connect/certs` | Cached by the gateway for at least 5 minutes |
| Cluster issuer | `https://kubernetes.default.svc.cluster.local` | The `iss` of projected tokens on K3s; other distributions differ, read it from `/.well-known/openid-configuration` |
| Cluster JWKS | `https://kubernetes.default.svc.cluster.local/openid/v1/jwks` | Readable by the IdP after the RBAC binding in section 7 |
| Agent client ID | `agent-<tenant>-<name>`, e.g. `agent-tenant-a-investigator` | One per agent, no secret, federated JWT authentication only; the actor client in delegation |
| Agent access token audience | `agent-gateway` | The only audience the agents listener accepts |
| Projected token audience | `${ISSUER_URL}` | The client assertion audience; rejected by the gateway and every other verifier |
| Client scope requested by the SDK | `agent-gateway` | A Keycloak client scope of that exact name carries the audience mappers (7.4) |
| Realm roles | `agent-role-<backend>-read`, e.g. `agent-role-kubernetes-read` | `<backend>` is the MCP backend name from the `Agent`; referenced by MCP tool rules; assigned by the Registry Controller |
| Custom claims on agent tokens | `agent_id` (`<tenant>/<name>`), `spiffe_id`, `tenant`, `client_type` (value `agent`) | Added by protocol mappers; section 7 |
| Delegation consent scope | `delegation:client:agent-<tenant>-<name>` | Keycloak's parameterized scope; the only scope that lets a user token be exchanged with that agent as actor |
| Delegation flow | the documented Keycloak client-delegation flow: requester = actor = the agent client, `actor_token` = the agent's access token (7.5) | Preview feature; proven by T10a before Phase C |

### 3.4 Tokens and lifetimes

| Token | Issuer | Lifetime | Refresh rule |
| --- | --- | --- | --- |
| Projected token | kubelet | 600 s | kubelet rewrites the file at 80 percent of lifetime; the SDK re-reads the file on every use |
| Agent access token | IdP | 300 s | SDK persists it under `/sandbox/state/token.json` (mode 0600) so each boundary process reuses it, and requests a new one when fewer than 120 s remain; a `401` from the gateway triggers one refresh and one retry |
| Upstream token (agent mode) | IdP via APS exchange | 300 s | APS cache until 30 s before expiry |
| Upstream token (delegated) | IdP via APS exchange | 300 s | APS cache until 30 s before expiry |
| Subject token in vault | IdP, deposited by the submitting client | until session end, at most 8 h | APS refreshes with the stored refresh token when fewer than 120 s remain |
| Gateway-held static credentials | operators | rotation per section 14 | Secret watch, no restart |

Revocation bounds that follow from these lifetimes and from the absence of any decision cache (3.7):

| Action | Takes effect for new requests within |
| --- | --- |
| Session cancelled, agent disabled, release unapproved, pod deleted | the APS informer latency, under 5 s, plus any request already in flight |
| User consent revoked at the IdP | the remaining life of the cached upstream token, at most 300 s |
| APS scaled to zero | immediately (the gateway fails closed) |
| Gateway-held credential rotated | the Secret watch latency, under 10 s |

### 3.5 Headers

| Header | Set by | Value |
| --- | --- | --- |
| `Authorization` (inbound) | sandbox | `Bearer <agent access token>`; preserved through the APS check, then removed or replaced by the APS response |
| `Authorization` (outbound) | APS (MCP) or gateway backend policy (models) | the upstream credential; never the inbound token |
| `x-agent-id` | APS | `<tenant>/<name>` |
| `x-agent-spiffe-id` | APS | `spiffe://<trust-domain>/ns/<tenant>/sa/agent-<name>` |
| `x-agent-tenant` | APS | `<tenant>` |
| `x-agent-session-id` | APS | session UUID |
| `x-agent-generation` | APS | integer |
| `x-agent-release` | APS | `AgentRelease` name |
| `x-agent-policy` | APS | `sha256:<64 hex>` |
| `x-agent-principal` | APS | user `sub` in delegated mode; removed otherwise |
| `x-agent-decision-id` | APS | UUID, logged by APS and gateway |
| `x-request-id`, `traceparent` | gateway | standard |

The APS response to the gateway sets every `x-agent-*` header it emits with overwrite semantics and lists every other `x-agent-*` name in `headers_to_remove`, so a client-supplied value never survives regardless of the order in which the gateway applies its policies. No transformation policy is involved.

A sandbox can send any header it likes; none of the `x-agent-*` values it sends survives the APS response (9.6), and the APS never reads them.

### 3.6 Labels, names and identifiers

| Item | Format |
| --- | --- |
| CRD group and version | `agentplatform.io/v1alpha1` |
| Label prefix | `agentplatform.io/` |
| Sandbox pod labels | `sandbox: "true"`, `agent: <name>`, `tenant: <tenant>`, `session: <uuid>`, `generation: <n>`, `release: <AgentRelease name>` (all with the prefix) |
| Sandbox pod annotation | `agentplatform.io/policy-digest: sha256:<hex>` |
| ServiceAccount | `agent-<name>` in namespace `<tenant>` |
| Session ID | UUID v4, lower-case |
| Sandbox name | `s-<first 16 hex chars of sha256(session ID)>-g<generation>` |
| Temporal workflow ID | `session:<tenant>:<agent>:<session ID>` |
| Temporal task queue | `sessions-<tenant>` |
| Policy digest | `sha256:` + hex SHA-256 of the canonical JSON policy bundle (keys sorted, no whitespace, UTF-8, computed by `agentctl policy-digest` at build time and recomputed by the controller) |
| Decision ID | UUID v4 per APS check |

### 3.7 Timeouts and limits

| Item | Value |
| --- | --- |
| APS check timeout at the gateway | 2 s, fail closed |
| APS decision cache at the gateway | **none**. Every request is evaluated. The APS caches only its inputs (JWKS, immutable policy bundles by digest, exchanged tokens, pod index) |
| IdP call timeout from APS | 5 s |
| Sandbox creation acknowledgement | 600 s schedule-to-close |
| Sandbox readiness | 180 s per attempt, 3 attempts |
| Execution step (one model or tool boundary) | 300 s, exactly one attempt |
| Boundaries per session | 64 |
| Cleanup | 600 s, retry on transient errors only; unfinished cleanup is picked up by the reconciler within 5 minutes |
| Session maximum | 8 h business deadline as a workflow timer, with 15 minutes reserved for cleanup inside the 8 h 15 min execution timeout |
| Default sandbox TTL | 1800 s after last activity |
| Per-agent budget | 2,000,000 tokens per UTC day, hard ceiling by APS reservation (9.3 step 10); the gateway's global token limit is a soft second layer |
| Per-session budget | 200,000 tokens, hard ceiling by APS reservation; the SDK's own counter is advisory |
| `reserve_tokens` per inference request | the model backend's `maxModelLen` from the platform's backend catalogue (server-enforced prompt plus output bound), or `max_context_tokens + max_tokens` when the gateway pins `max_tokens` (17.3) |
| Overshoot contract | none beyond the reservation: a request is admitted only if `spent + inflight + reserve_tokens <= budget` for both budgets; an unsettled reservation is charged in full after 130 s |
| Concurrency bound per session | `floor((budget - spent - inflight) / reserve_tokens)`; the 30-requests-per-minute local limit is abuse control, not a concurrency bound |
| Settlement latency | the access-log pipeline delay, target under 5 s |
| Token route limit | 60 requests per minute per source address |
| Kata pod overhead | `memory: 160Mi`, `cpu: 600m` in the RuntimeClass until measured |

### 3.8 Decision reasons

The APS returns exactly one of these strings in the `x-agent-decision-reason` response header to the gateway (never forwarded upstream) and in its log line.

| Reason | Meaning |
| --- | --- |
| `allow` | all checks passed |
| `deny.token_invalid` | no valid token (defence in depth; the gateway should have refused it) |
| `deny.token_not_agent` | `client_type` is not `agent` or `aud` lacks `agent-gateway` |
| `deny.pod_unknown` | no sandbox pod has the request's source address |
| `deny.pod_agent_mismatch` | the pod's `agent` label differs from the token's `agent_id`, or its namespace differs from the token's `tenant` |
| `deny.token_bound_elsewhere` | this token (`jti`) is pinned to a different pod |
| `deny.session_inactive` | the pod is terminating, the session was marked stopped, or the pod's host-side network attestation is missing or stale |
| `deny.generation_stale` | the pod's generation is not the session's active generation |
| `deny.release_unapproved` | the pod's release is not ready (unapproved, unsigned, drifted) or its digest differs from the pod's annotation, or the agent is disabled |
| `deny.route_not_permitted` | the route, model backend, MCP backend, JSON-RPC method or tool is not in the policy bundle |
| `deny.budget_exhausted` | the reservation does not fit the session or agent-day budget (returned as HTTP 429) |
| `deny.delegation_required` | the upstream requires on-behalf-of and the session has no grant |
| `deny.exchange_failed` | the IdP refused or timed out on token exchange |
| `deny.internal` | any other error; always deny |

## 4. Identities and tokens

Five token types exist; each has exactly one issuer, one audience and one place it may be used, and the matrix in 4.6 says where each may never appear.

### 4.1 Projected token (sandbox to identity provider)

The kubelet writes it into the sandbox from this volume in the sandbox pod template:

```yaml
volumes:
  - name: agent-identity
    projected:
      defaultMode: 0440
      sources:
        - serviceAccountToken:
            audience: https://idp.example.com/realms/agents   # ISSUER_URL
            expirationSeconds: 600
            path: token
containers:
  - name: agent
    volumeMounts:
      - name: agent-identity
        mountPath: /var/run/secrets/agent-identity
        readOnly: true
```

Decoded payload (K3s, Kubernetes 1.33 or later):

```json
{
  "iss": "https://kubernetes.default.svc.cluster.local",
  "sub": "system:serviceaccount:tenant-a:agent-investigator",
  "aud": ["https://idp.example.com/realms/agents"],
  "exp": 1761800600, "iat": 1761800000, "nbf": 1761800000,
  "jti": "c6f1...",
  "kubernetes.io": {
    "namespace": "tenant-a",
    "serviceaccount": {"name": "agent-investigator", "uid": "..."},
    "pod": {"name": "s-3f9a1c0b7e2d4a61-g1", "uid": "..."},
    "node": {"name": "rig0", "uid": "..."}
  }
}
```

Rules:

- The pod sets `automountServiceAccountToken: false`. This volume is the only token in the pod.
- The only verifier is the identity provider, which accepts it as an RFC 7523 client assertion for the client `agent-<tenant>-<name>` whose expected subject is `system:serviceaccount:<tenant>:agent-<name>`. The gateway rejects it (`aud` is not `agent-gateway`); the API server rejects it (`aud` is not the API audience).
- The SDK re-reads the file every time it builds a client assertion. Caching the file contents in memory for longer than 60 s is an error, because the kubelet rotates it.

### 4.2 Agent access token (sandbox to gateway)

Obtained with one request to the gateway's token route (section 11 has the code):

```http
POST /v1/token HTTP/1.1
Host: token.agents.internal
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=agent-tenant-a-investigator
&client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer
&client_assertion=<projected token>
&scope=agent-gateway
```

Decoded payload as the reference identity provider issues it:

```json
{
  "iss": "https://idp.example.com/realms/agents",
  "sub": "9b2c...",
  "azp": "agent-tenant-a-investigator",
  "aud": ["agent-gateway"],
  "typ": "Bearer",
  "exp": 1761800300, "iat": 1761800000, "jti": "7a0e...",
  "scope": "agent-gateway",
  "client_type": "agent",
  "agent_id": "tenant-a/investigator",
  "tenant": "tenant-a",
  "spiffe_id": "spiffe://cluster.local/ns/tenant-a/sa/agent-investigator",
  "realm_access": {"roles": ["agent-role-kubernetes-read"]}
}
```

The token route terminates at the APS, not at the identity provider (8.3). The APS validates the assertion with a TokenReview (which also returns the bound pod's name and UID), checks that the pod is a running sandbox of that agent, forwards the identical `client_credentials` request to the identity provider's token endpoint, pins the issued token's `jti` to the pod UID, and returns the token. Any other grant type, any other client, or an assertion that is not a projected token bound to a sandbox pod is refused before the identity provider sees it. `sub` is the identity provider's identifier for the agent's service-account user; it is stable for the life of the client and is the value upstreams see as `act.sub` in delegated tokens. The gateway validates signature, `iss` (exact string), `aud` contains `agent-gateway`, `exp` and `nbf`. The APS additionally requires `client_type == "agent"`, uses `agent_id`, `tenant` and `azp`, and enforces the `jti` pin on every request, so the token proves the agent and the pod proves the session.

### 4.3 Subject token (user to Agent Policy Service)

A delegated session begins with the submitting client (a CLI or a service acting for a human) obtaining a user token from the identity provider by authorization code with PKCE, requesting:

- `scope=openid offline_access agent-policy-service delegation:client:agent-tenant-a-investigator`
- `audience=agent-policy-service` (Keycloak: a client scope with an audience mapper)

The client deposits it once:

```http
POST /v1/grants HTTP/1.1
Host: aps.agent-platform.svc.cluster.local
Authorization: Bearer <subject access token>
Content-Type: application/json

{
  "session_id": "6f1d2c3e-...",
  "tenant": "tenant-a",
  "agent": "investigator",
  "refresh_token": "<refresh token or null>",
  "expires_at": "2026-10-30T18:00:00Z"
}
```

Response: `201 {"grant_handle": "gh_7c1f..."}`. The APS validates the bearer (`iss`, `aud` contains `agent-policy-service`, `exp`), stores access token, refresh token and expiry encrypted at rest keyed by `session_id`, and returns the handle. Only the handle enters the session's workflow input. The deposit is rejected with `409` if a grant for that session already exists and with `403` if the token's `scope` lacks `delegation:client:agent-<tenant>-<agent>`.

### 4.4 Upstream tokens (gateway to MCP servers)

Two mint paths produce the same shape of token; which one runs depends on the upstream's delegation setting in the policy bundle.

| Mode | Who exchanges | `subject_token` | `actor_token` | `resource` |
| --- | --- | --- | --- | --- |
| `agent` | APS (section 9.5); optionally the gateway natively (`oauthTokenExchange`, section 8.11) | agent access token | none | `https://mcp.<domain>/<backend>/mcp` |
| `on-behalf-of` | APS (section 9.5) | vaulted subject token | agent access token | same |

Delegated token payload:

```json
{
  "iss": "https://idp.example.com/realms/agents",
  "sub": "alice",
  "aud": ["https://mcp.example.com/kubernetes/mcp"],
  "act": {"sub": "9b2c..."},
  "azp": "agent-tenant-a-investigator",
  "scope": "mcp:kubernetes",
  "exp": 1761800300, "iat": 1761800000, "jti": "d41a..."
}
```

Every MCP server validates: signature against the identity provider JWKS, `iss` exact, `aud` equals its own resource URL (one value), `exp`. A server that requires delegation (`delegation: required` in its registry entry) also requires `act` to be present and resolves `act.sub` to an agent through the `agent-subjects` ConfigMap the Registry Controller publishes in `mcp` (`data[<sub>] = <tenant>/<agent>`). The Kubernetes MCP server then impersonates `sub` with the `Impersonate-User` header, so cluster RBAC for the user decides.

A tool allow-list bounds operation names only. Which namespaces, resource kinds or records a tool may touch is enforced below the gateway: in delegated mode by cluster RBAC for the impersonated user (the MCP server's own ServiceAccount holds the `impersonate` verb on users and groups plus read verbs, never more); in agent mode by RBAC bound to the MCP server's ServiceAccount, scoped per backend; and in both modes by the MCP server's own configuration (read-only mode, namespace allow-list), which is part of the backend's registry entry and reviewed with it. The gateway's CEL rules may additionally match `mcp.tool.arguments` for backends whose tools take a namespace argument; that is an optimisation, not the boundary.

### 4.5 Gateway-held static credentials (gateway to model servers and SaaS)

| Secret | Namespace | Key | Used by |
| --- | --- | --- | --- |
| `backend-cred-llm-<name>` | `ai-gateway` | `Authorization: Bearer <random 32 bytes, base64url>` | `AgentgatewayBackend` for that model server (`policies.auth.secretRef`) |
| `llm-api-key` | `llm` | `VLLM_API_KEY` = the same value | vLLM `--api-key`, so the model server rejects anything but the gateway |
| `backend-cred-<saas>` | `ai-gateway` | `Authorization` | SaaS MCP or model providers that use static keys |

Values are generated by the operator recipe in section 14, stored SOPS-encrypted in git (homelab) or synchronised from a secrets manager by External Secrets Operator (enterprise). The gateway watches Secrets, so rotation needs no restart; vLLM does, so rotation follows the two-key overlap in section 14.

### 4.6 Where each token may appear

| Token | Sandbox filesystem | Sandbox memory | Request to gateway | APS memory or store | Temporal history | Upstream request | Logs and traces |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Projected token | yes (projected volume) | transient | only in the token route body | no | no | no | never (log `jti` only) |
| Agent access token | no (memory only) | yes | `Authorization` | transient, during a check | no | no | never (log `jti`, `agent_id`) |
| Subject token | no | no | no | yes, encrypted | no (handle only) | no | never |
| Upstream token | no | no | no | cache until expiry | no | `Authorization` | never (log `jti`) |
| Static credential | no | no | no | no | no | `Authorization` | never |

"Never" rows are enforced by the log redaction rule in section 13 and tested by T3 and T14.

## 5. Sandbox isolation and network

A sandbox is a Kata Containers pod whose only permitted destination is the gateway data plane; the VM boundary keeps the workload away from the kernel that enforces that rule.

### 5.1 Kata installation

Install with the kata-deploy Helm chart. The values below are the ones that matter; keep every other default.

```yaml
# helm install kata-deploy oci://ghcr.io/kata-containers/kata-deploy-charts/kata-deploy \
#   --version <pinned, at or above the CVE-2026-44210 fix> -n kube-system -f values.yaml
k8sDistribution: k3s
shims:
  qemu-runtime-rs:
    enabled: true
runtimeClass:
  nodeSelector:
    katacontainers.io/kata-runtime: "true"   # set by the DaemonSet on nodes that pass its checks
```

The chart creates `RuntimeClass/kata-qemu-runtime-rs`. Patch it with the overhead so the scheduler reserves VM memory:

```yaml
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: kata-qemu-runtime-rs
handler: kata-qemu-runtime-rs
overhead:
  podFixed:
    memory: 160Mi
    cpu: 600m
scheduling:
  nodeSelector:
    katacontainers.io/kata-runtime: "true"
```

On mixed-architecture clusters (x86\_64 and arm64) the shim images are per architecture; the chart handles that, but each node must expose `/dev/kvm`. Verify on every node before anything else:

```bash
test -c /dev/kvm && echo kvm-ok
```

In the Kata configuration (`configuration-qemu-runtime-rs.toml`), set `disable_guest_seccomp = false` so the pod's seccomp profile applies inside the guest. The guest kernel shipped by Kata has Landlock enabled; the SDK uses it (section 11.6).

### 5.2 Sandbox pod template

The Registry Controller renders this template into `AgentRelease.status.compiled.podTemplate`; the Session Runner submits it unchanged except for the fields marked `# per session`.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: s-3f9a1c0b7e2d4a61-g1                 # per session: s-<sha256(session)[:16]>-g<generation>
  namespace: tenant-a
  labels:
    agentplatform.io/sandbox: "true"
    agentplatform.io/agent: investigator
    agentplatform.io/tenant: tenant-a
    agentplatform.io/release: investigator-2026-10-29-a93557ad
    agentplatform.io/session: 6f1d2c3e-4b5a-4c6d-8e7f-9a0b1c2d3e4f   # per session
    agentplatform.io/generation: "1"                                   # per session
  annotations:
    agentplatform.io/policy-digest: sha256:9c1e...
    # agentplatform.io/netpol-attested is added by the node attestor (5.5), never by the template
spec:
  runtimeClassName: kata-qemu-runtime-rs
  serviceAccountName: agent-investigator
  automountServiceAccountToken: false
  enableServiceLinks: false
  hostNetwork: false
  hostPID: false
  hostIPC: false
  dnsPolicy: None                     # no resolver at all
  dnsConfig:
    nameservers: ["127.0.0.1"]        # a non-answering address; the SDK never resolves names
  restartPolicy: Never
  terminationGracePeriodSeconds: 30
  securityContext:
    runAsNonRoot: true
    runAsUser: 1500
    runAsGroup: 1500
    fsGroup: 1500
    seccompProfile: {type: RuntimeDefault}
  initContainers:
    # Platform-owned, pinned by digest, verified by admission. It exits 0 only
    # after the node attestor has recorded host-side policy for this pod and
    # the gateway is reachable; the agent container cannot start before that.
    - name: egress-guard
      image: registry.example.com/platform/egress-guard@sha256:5b2c...
      args: ["--gateway", "10.43.250.10:443",
             "--forbidden", "10.43.0.1:443,10.43.0.10:53",
             "--attestation", "/etc/podinfo/annotations",
             "--attestation-key", "agentplatform.io/netpol-attested",
             "--timeout", "90"]
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities: {drop: ["ALL"]}
      resources:
        requests: {cpu: "50m", memory: "32Mi"}
        limits:   {cpu: "100m", memory: "64Mi"}
      volumeMounts:
        - {name: podinfo, mountPath: /etc/podinfo, readOnly: true}
  containers:
    - name: agent
      image: registry.example.com/agents/investigator@sha256:a93557ad...   # digest from the release
      command: ["/app/.venv/bin/python", "-m", "agent_runtime.wait"]      # blocks until exec'd into
      env:
        - {name: AGENT_GATEWAY_URL, value: "https://10.43.250.10:443"}
        - {name: AGENT_GATEWAY_CA, value: "/etc/agent-platform/ca.crt"}
        - {name: AGENT_TOKEN_HOST, value: "token.agents.internal"}
        - {name: AGENT_INFERENCE_HOST, value: "inference.agents.internal"}
        - {name: AGENT_MCP_HOST, value: "mcp.agents.internal"}
        - {name: AGENT_CLIENT_ID, value: "agent-tenant-a-investigator"}
        - {name: AGENT_TOKEN_PATH, value: "/var/run/secrets/agent-identity/token"}
        - {name: AGENT_TOKEN_ENDPOINT_PATH, value: "/v1/token"}
        - {name: AGENT_MODEL_ROUTE, value: "/models/llm-main"}            # from the policy bundle
        - {name: AGENT_TOKENS_PER_SESSION, value: "200000"}                # advisory; the APS ledger enforces
        - {name: AGENT_SESSION_ID, value: "6f1d2c3e-4b5a-4c6d-8e7f-9a0b1c2d3e4f"}   # per session, informational
      resources:
        requests: {cpu: "500m", memory: "1Gi"}
        limits:   {cpu: "1",    memory: "2Gi"}
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities: {drop: ["ALL"]}
      volumeMounts:
        - {name: agent-identity, mountPath: /var/run/secrets/agent-identity, readOnly: true}
        - {name: gateway-ca, mountPath: /etc/agent-platform, readOnly: true}
        - {name: workspace, mountPath: /sandbox}
        - {name: tmp, mountPath: /tmp}
  volumes:
    - name: agent-identity
      projected:
        defaultMode: 0440
        sources:
          - serviceAccountToken:
              audience: https://idp.example.com/realms/agents
              expirationSeconds: 600
              path: token
    - name: gateway-ca
      configMap: {name: agent-gateway-ca}
    - name: podinfo
      downwardAPI:
        items:
          - {path: annotations, fieldRef: {fieldPath: metadata.annotations}}
    - name: workspace
      emptyDir: {sizeLimit: 2Gi}
    - name: tmp
      emptyDir: {sizeLimit: 256Mi}
```

If the `agent-sandbox` controller (`sandboxes.agents.x-k8s.io/v1beta1`) is used for warm pools, this pod spec is the `podTemplate` of its `Sandbox`, and its managed NetworkPolicy, which allows the public internet by default, is switched off through the controller's own managed/unmanaged policy setting rather than deleted (a deleted policy is re-created on the next reconcile). Never use `volumeMounts.subPath` on a Kata pod; it is unsupported.

### 5.3 NetworkPolicies in every tenant namespace

The Registry Controller applies these four policies to each tenant namespace before any sandbox exists and reverts manual edits. Because Kubernetes NetworkPolicies are additive, an extra policy could widen access, so `preflight` (10.3) checks the **effective** set: the namespace must contain exactly these four policies with exactly this content (compared by a canonical hash the controller publishes in the namespace annotation `agentplatform.io/netpol-digest`), and nothing else.

```yaml
# 1. Deny everything by default, both directions, for every pod in the namespace.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: tenant-a
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
# 2. Sandboxes may reach the gateway data plane and nothing else.
#    Pod and namespace selectors, never ipBlock: NAT runs before policy, so an
#    ipBlock on the Service ClusterIP would not match.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sandbox-egress-gateway-only
  namespace: tenant-a
spec:
  podSelector:
    matchLabels:
      agentplatform.io/sandbox: "true"
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ai-gateway
          podSelector:
            matchLabels:
              app.kubernetes.io/name: agents
      ports:
        - {protocol: TCP, port: 80}
        - {protocol: TCP, port: 443}
---
# 3. Nothing may connect to a sandbox. The kubelet exec path is not pod
#    network traffic and is unaffected.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sandbox-ingress-none
  namespace: tenant-a
spec:
  podSelector:
    matchLabels:
      agentplatform.io/sandbox: "true"
  policyTypes: [Ingress]
---
# 4. Non-sandbox pods in the tenant namespace (none are expected) get no
#    exception either; this policy exists so a future pod cannot be added
#    without an explicit allow rule.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: tenant-no-other-egress
  namespace: tenant-a
spec:
  podSelector:
    matchExpressions:
      - {key: agentplatform.io/sandbox, operator: DoesNotExist}
  policyTypes: [Egress]
```

And the matching ingress rule on the gateway side, plus the upstream rules that complete the chain:

```yaml
# ai-gateway: accept sandboxes from every tenant namespace on the agents listener.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: agents-ingress-from-sandboxes
  namespace: ai-gateway
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: agents
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchExpressions:
              - {key: agentplatform.io/tenant, operator: Exists}
          podSelector:
            matchLabels:
              agentplatform.io/sandbox: "true"
      ports:
        - {protocol: TCP, port: 443}
---
# llm: model servers accept only the gateway.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: llm-ingress-from-gateway-only
  namespace: llm
spec:
  podSelector: {}
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ai-gateway
          podSelector:
            matchLabels:
              app.kubernetes.io/name: agents
---
# mcp: MCP servers accept only the gateway.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mcp-ingress-from-gateway-only
  namespace: mcp
spec:
  podSelector: {}
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ai-gateway
          podSelector:
            matchLabels:
              app.kubernetes.io/name: agents
---
# agent-platform: the policy service accepts the gateway on the ext_authz port
# and the Session Runner on the sessions and grants port; nothing else.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: aps-ingress
  namespace: agent-platform
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: agent-policy-service
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ai-gateway
          podSelector:
            matchLabels:
              app.kubernetes.io/name: agents
      ports:
        - {protocol: TCP, port: 9001}   # ext_authz gRPC
        - {protocol: TCP, port: 9002}   # grants API reached by submitting clients through the humans' gateway
    - from:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: session-runner
      ports:
        - {protocol: TCP, port: 9002}   # sessions and grants API; the APS authorizes the runner identity per request (9.7)
```

The identity provider's namespace needs an ingress rule from `ai-gateway` (token route, JWKS, native exchange) and from `agent-platform` (APS exchange); nothing else may reach it from inside the cluster except humans' traffic through the existing ingress.

### 5.4 Why the boundary holds with Kata

The CNI creates the pod's veth on the host exactly as for a normal container; Kata bridges it into the VM through a tap device with traffic-control redirects. kube-router, the policy engine K3s embeds, programs its rules in the host kernel's filter table, so the guest cannot see or alter them. Two documented caveats shape the rules above, and the first one is why the boundary is proven by a trusted component rather than assumed:

1. kube-router programs a new pod's chains shortly after the CNI wires it and fails open during that window; connections opened in the window stay usable afterwards. K3s hard-codes kube-router's stricter default-deny start-up option off, so the engine cannot be made to start closed without patching K3s. The platform therefore makes the **untrusted** code start closed instead: a node-level attestor (5.5) verifies from the host that the pod's policy chain exists and records that on the pod; the platform-owned egress-guard init container waits for that record through the Downward API and only then exits 0; the kubelet starts the agent container only after the init container succeeds; and the Session Runner re-reads the attestation before every exec. A failed probe connection is treated as nothing more than a diagnostic, because an unreachable destination looks the same as a blocked one; the attestation, not the probe, is the authority. The engine's own window therefore exists only while nothing untrusted is running, and T2 measures it rather than assuming it. The enterprise profile replaces kube-router with Cilium, whose `reserved:init` identity denies traffic until an endpoint's policy is computed (start-closed semantics), and keeps the attestor as independent verification.
2. A ClusterIP is matched by namespace and pod selectors, never `ipBlock`, because NAT runs before policy.

### 5.5 Startup egress probe

Two platform components implement the gate.

**Node attestor.** A DaemonSet `netpol-attestor` in `agent-platform` on every sandbox node (`hostNetwork: true`, capabilities `NET_ADMIN` and `NET_RAW` to read the netfilter tables, image pinned by digest). It watches sandbox pods scheduled to its node; when a pod has an IP it reads `iptables-save -t filter`, finds the kube-router per-pod firewall chain that references that IP (chain names start with `KUBE-POD-FW-`; the exact naming and comment format is a to-confirm item in 17.3), verifies the chain ends in the engine's reject rule and references the ipset of the sandbox egress policy, and patches the pod annotation `agentplatform.io/netpol-attested: "<RFC3339>;<chain>"`. It re-verifies every 30 s while the pod runs and removes the annotation if the chain disappears; the APS treats an annotation older than 90 s as absent (9.3 step 5), so the attestation is continuous, not only at start. Its RBAC is `pods` list and watch cluster-wide and `pods` patch in tenant namespaces (RoleBindings created by the Registry Controller). Sandbox nodes run the kubelet with `--sync-frequency=5s` so the Downward API file reflects the annotation within seconds.

**Egress guard.** The init container of 5.2, built from the platform repository, pinned by digest in the pod template and in the admission policy (6.5). It has no volumes except the Downward API file. Its verdict is its exit code: 0 only when the attestation is present **and** the gateway is reachable **and** no forbidden connection succeeded; 3 immediately on the first forbidden connection that succeeds (no retry: a leak is a finding about the attestor or the engine, not a transient); 4 when the attestation or the gateway did not appear within the timeout. A non-zero exit fails the pod, the kubelet never starts the agent container, and the Session Runner records the generation as lost.

```python
# platform/egress_guard/main.py  (packaged as the egress-guard image; the agent image never contains it)
import argparse, pathlib, socket, sys, time

def can_connect(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

def attested(path: pathlib.Path, key: str) -> bool:
    # Downward API annotations file: one key="value" per line, rewritten by the kubelet on change.
    try:
        return any(line.startswith(key + "=") for line in path.read_text().splitlines())
    except OSError:
        return False

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gateway", required=True)          # host:port
    p.add_argument("--forbidden", required=True)        # comma-separated host:port list
    p.add_argument("--attestation", required=True)      # Downward API annotations file
    p.add_argument("--attestation-key", required=True)
    p.add_argument("--timeout", type=int, default=90)
    a = p.parse_args()
    gw_host, gw_port = a.gateway.rsplit(":", 1)
    forbidden = [f.rsplit(":", 1) for f in a.forbidden.split(",")]
    deadline = time.monotonic() + a.timeout
    while time.monotonic() < deadline:
        for host, port in forbidden:
            if can_connect(host, int(port)):
                print(f"LEAK {host}:{port}", file=sys.stderr)
                return 3                                  # immediate failure; never retried
        if attested(pathlib.Path(a.attestation), a.attestation_key) and can_connect(gw_host, int(gw_port)):
            print("egress-guard ok: attested, gateway reachable")
            return 0
        time.sleep(1)
    print("no attestation or gateway unreachable within timeout", file=sys.stderr)
    return 4

if __name__ == "__main__":
    sys.exit(main())
```

The agent container's own entrypoint (`agent_runtime.wait`) does nothing but sleep until the Session Runner execs into it; it has no security role, and it is the first untrusted instruction the pod runs, which by construction happens only after the guard has exited 0.

## 6. Agent registry

Two custom resources are the source of truth; a controller compiles them into every identity, policy and template object, and an admission policy refuses any sandbox that is not backed by an approved, signed release.

### 6.1 `Agent`

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: agents.agentplatform.io
spec:
  group: agentplatform.io
  scope: Namespaced
  names: {kind: Agent, plural: agents, singular: agent, shortNames: [ag]}
  versions:
    - name: v1alpha1
      served: true
      storage: true
      subresources: {status: {}}
      schema:
        openAPIV3Schema:
          type: object
          required: [spec]
          properties:
            spec:
              type: object
              required: [owner, identity, capabilities]
              properties:
                owner: {type: string, format: email}
                description: {type: string, maxLength: 512}
                enabled: {type: boolean, default: true}
                identity:
                  type: object
                  required: [mode]
                  properties:
                    mode: {type: string, enum: [agent, on-behalf-of]}
                    onBehalfOf:
                      type: object
                      properties:
                        required: {type: boolean, default: true}
                        fallback: {type: string, enum: [deny, agent], default: deny}
                capabilities:
                  type: object
                  properties:
                    models:
                      type: array
                      items:
                        type: object
                        required: [backend, models]
                        properties:
                          backend: {type: string, pattern: '^[a-z0-9-]{1,63}$'}
                          models: {type: array, minItems: 1, items: {type: string}}
                          budget:
                            type: object
                            properties:
                              tokensPerDay: {type: integer, minimum: 1, default: 2000000}
                              tokensPerSession: {type: integer, minimum: 1, default: 200000}
                    mcp:
                      type: array
                      items:
                        type: object
                        required: [backend, effect, tools]
                        properties:
                          backend: {type: string, pattern: '^[a-z0-9-]{1,63}$'}
                          effect: {type: string, enum: [remote_read]}
                          tools: {type: array, minItems: 1, items: {type: string, pattern: '^[A-Za-z0-9_.-]{1,128}$'}}
                          delegation: {type: string, enum: [inherit, agent, on-behalf-of], default: inherit}
                runtime:
                  type: object
                  properties:
                    runtimeClass: {type: string, default: kata-qemu-runtime-rs}
                    cpu: {type: string, default: "1"}
                    memory: {type: string, default: 2Gi}
                    ttlSeconds: {type: integer, minimum: 60, maximum: 28800, default: 1800}
                    maxBoundaries: {type: integer, minimum: 1, maximum: 64, default: 64}
            status:
              type: object
              properties:
                serviceAccount: {type: string}
                clientId: {type: string}
                spiffeId: {type: string}
                idpSubject: {type: string}
                conditions:
                  type: array
                  items:
                    type: object
                    required: [type, status]
                    properties:
                      type: {type: string}
                      status: {type: string, enum: ["True", "False", Unknown]}
                      reason: {type: string}
                      message: {type: string}
                      lastTransitionTime: {type: string, format: date-time}
```

Example:

```yaml
apiVersion: agentplatform.io/v1alpha1
kind: Agent
metadata:
  name: investigator
  namespace: tenant-a
spec:
  owner: platform-team@example.com
  description: Read-only Kubernetes incident investigator
  identity:
    mode: on-behalf-of
    onBehalfOf: {required: true, fallback: deny}
  capabilities:
    models:
      - backend: llm-main
        models: [Qwen3.6-35B-A3B-NVFP4]
        budget: {tokensPerDay: 5000000, tokensPerSession: 200000}
    mcp:
      - backend: kubernetes
        effect: remote_read
        tools: [pods_list_in_namespace, pods_get, events_list]
        delegation: inherit
  runtime: {cpu: "1", memory: 2Gi, ttlSeconds: 1800}
```

### 6.2 `AgentRelease`

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: agentreleases.agentplatform.io
spec:
  group: agentplatform.io
  scope: Namespaced
  names: {kind: AgentRelease, plural: agentreleases, singular: agentrelease, shortNames: [agr]}
  versions:
    - name: v1alpha1
      served: true
      storage: true
      subresources: {status: {}}
      schema:
        openAPIV3Schema:
          type: object
          required: [spec]
          properties:
            spec:
              type: object
              required: [agent, image, manifestSha256, policySha256, approval]
              # Everything except approval is immutable: a release is a snapshot.
              x-kubernetes-validations:
                - rule: "self.agent == oldSelf.agent"
                  message: agent is immutable
                - rule: "self.image == oldSelf.image"
                  message: image is immutable
                - rule: "self.manifestSha256 == oldSelf.manifestSha256"
                  message: manifestSha256 is immutable
                - rule: "self.policySha256 == oldSelf.policySha256"
                  message: policySha256 is immutable
                - rule: "!has(self.lockSha256) || !has(oldSelf.lockSha256) || self.lockSha256 == oldSelf.lockSha256"
                  message: lockSha256 is immutable
              properties:
                agent: {type: string}
                image:
                  type: string
                  pattern: '^[a-z0-9.:/-]+@sha256:[a-f0-9]{64}$'
                manifestSha256: {type: string, pattern: '^[a-f0-9]{64}$'}
                policySha256:
                  type: string
                  pattern: '^[a-f0-9]{64}$'
                  description: digest of the policy bundle compiled at build time from the Agent as it was then; the controller recompiles from the current Agent and refuses the release if they differ
                sourceSha256: {type: string, pattern: '^[a-f0-9]{64}$'}
                lockSha256: {type: string, pattern: '^[a-f0-9]{64}$'}
                buildRevision: {type: string}
                approval:
                  type: object
                  required: [approved]
                  properties:
                    approved: {type: boolean}
                    approvedBy: {type: string, format: email}
                    approvedAt: {type: string, format: date-time}
                    ticket: {type: string}
            status:
              type: object
              properties:
                policyDigest: {type: string, pattern: '^sha256:[a-f0-9]{64}$'}
                policyBundleConfigMap: {type: string}
                podTemplateConfigMap: {type: string}
                identityMode: {type: string, enum: [agent, on-behalf-of]}
                delegationRequired: {type: boolean}
                signatureVerified: {type: boolean}
                policyDrift: {type: boolean}
                ready: {type: boolean}
                conditions:
                  type: array
                  items:
                    type: object
                    required: [type, status]
                    properties:
                      type: {type: string}
                      status: {type: string, enum: ["True", "False", Unknown]}
                      reason: {type: string}
                      message: {type: string}
                      lastTransitionTime: {type: string, format: date-time}
```

Example:

```yaml
apiVersion: agentplatform.io/v1alpha1
kind: AgentRelease
metadata:
  name: investigator-2026-10-29-a93557ad
  namespace: tenant-a
spec:
  agent: investigator
  image: registry.example.com/agents/investigator@sha256:a93557ad1581152d031dd22f0d2dc70ade957eb6140666894709ccbeeaf58193
  manifestSha256: 4e0c...
  policySha256: 9c1e...          # agentctl policy-digest --agent tenant-a/investigator, at build time
  lockSha256: 91bd...
  buildRevision: 12647b3
  approval:
    approved: true
    approvedBy: security-review@example.com
    approvedAt: 2026-10-29T16:00:00Z
    ticket: SEC-412
```

Approval lives in `spec` so that it is a reviewed change in git; the controller never sets it. The three digests are what approval covers. The build pipeline also publishes a cosign attestation on the image whose predicate carries `manifestSha256` and `policySha256`; the controller verifies that attestation (enterprise profile) or recomputes the digests itself (homelab profile), and in both profiles a release whose recomputed policy digest differs from `spec.policySha256` is never ready.

### 6.3 Policy bundle

`agentctl policy-digest` compiles one JSON document from the `Agent` at build time; its SHA-256 over the canonical form (keys sorted, no whitespace, UTF-8) is `spec.policySha256`. The controller compiles the same document from the `Agent` as it stands at reconcile time, stores it in ConfigMap `policy-<release name>` (key `bundle.json`) in the tenant namespace, and compares digests: equal means the release is drift-free; different means the `Agent` changed after the build and the release is not ready until a new release is built and approved.

```json
{
  "version": 1,
  "tenant": "tenant-a",
  "agent": "investigator",
  "release": "investigator-2026-10-29-a93557ad",
  "image": "registry.example.com/agents/investigator@sha256:a93557ad...",
  "client_id": "agent-tenant-a-investigator",
  "spiffe_id": "spiffe://cluster.local/ns/tenant-a/sa/agent-investigator",
  "identity": {"mode": "on-behalf-of", "required": true, "fallback": "deny"},
  "routes": {
    "inference.agents.internal": ["/v1/chat/completions", "/v1/embeddings"],
    "mcp.agents.internal": ["/kubernetes/mcp"],
    "token.agents.internal": ["/realms/agents/protocol/openid-connect/token"]
  },
  "models": {"llm-main": ["Qwen3.6-35B-A3B-NVFP4"]},
  "mcp": {
    "kubernetes": {
      "effect": "remote_read",
      "tools": ["events_list", "pods_get", "pods_list_in_namespace"],
      "delegation": "on-behalf-of",
      "resource": "https://mcp.example.com/kubernetes/mcp"
    }
  },
  "budgets": {"tokens_per_day": 5000000, "tokens_per_session": 200000},
  "runtime": {"ttl_seconds": 1800, "max_boundaries": 64}
}
```

`delegation: inherit` resolves to the agent's `identity.mode`. Routes are derived: the token route is always present; an inference route is present when `models` is non-empty; one MCP path per `mcp` entry. Tool lists are sorted so the digest is stable.

### 6.4 Controller reconciliation

The Registry Controller is a Kubernetes operator (kubebuilder or kopf; the choice does not matter) with these rules. Every rule is idempotent and re-run on every change to the `Agent`, its `AgentRelease`s, or the tenant namespace.

For each `Agent`:

1. Ensure ServiceAccount `agent-<name>` exists in the tenant namespace with `automountServiceAccountToken: false` and the label `agentplatform.io/agent: <name>`.
2. Ensure the tenant namespace carries label `agentplatform.io/tenant: <tenant>` and the four NetworkPolicies of section 5.3. The controller owns those policies; manual edits are reverted.
3. Ensure the identity provider client `agent-<tenant>-<name>` exists (section 7.3) with federated JWT authentication bound to the cluster issuer, expected subject `system:serviceaccount:tenant-<tenant>:agent-<name>`, no secret, grant type `client_credentials` only, and the protocol mappers of section 7.4. Record the service-account user's `sub` in `status.idpSubject`.
4. Ensure realm roles `agent-role-<backend>-read` exist for each `capabilities.mcp[].backend` and are assigned to the client's service-account user; remove roles no longer declared.
5. Ensure the ConfigMap `agent-subjects` in namespace `mcp` has `data[<idpSubject>] = <tenant>/<name>`; remove the entry when the agent is deleted.
6. If `spec.enabled` is false, set condition `Enabled=False`; the APS denies with `deny.release_unapproved` for every release of a disabled agent.
7. Set `status.serviceAccount`, `status.clientId`, `status.spiffeId` and condition `Ready`.

For each `AgentRelease`:

1. Verify the image signature with cosign against the organisation's public key (or the keyless identity policy in section 14), and in the enterprise profile verify the attestation whose predicate names `manifestSha256` and `policySha256` equal to the spec. Set `status.signatureVerified` and condition `SignatureVerified`. Fail closed: a verification error is `False`.
2. Compile the policy bundle from the referenced `Agent` and this release; compute its digest. If it differs from `spec.policySha256`, set `status.policyDrift: true`, condition `PolicyDrift`, and stop: `status.ready` becomes false and `status.policyDigest` is **not** changed. The approved bundle is never silently widened or narrowed.
3. Otherwise write ConfigMap `policy-<release>`; set `status.policyDigest = sha256:<spec.policySha256>`, `status.policyBundleConfigMap`, `status.identityMode` and `status.delegationRequired` (copied from the bundle so the Session Runner's preflight reads them from one place).
4. Render the pod template of section 5.2 with the image digest, runtime values, environment and the per-release labels; write ConfigMap `podtemplate-<release>` (key `pod.yaml`); set `status.podTemplateConfigMap`. The template embeds the egress-guard image digest and the CA ConfigMap name from the controller's own configuration.
5. `status.ready = spec.approval.approved && status.signatureVerified && !status.policyDrift && Agent.spec.enabled && Agent condition Ready`. Only a ready release may be run.
6. A later change to the `Agent` that alters the bundle therefore makes every existing release of that agent drift (`ready: false`): new sessions cannot start on it, and running sandboxes are denied by the APS (`deny.release_unapproved`) because their release is no longer ready. Restoring service requires a new `AgentRelease` with the new digest and a new approval. Narrowing a capability is the same procedure; revocation without a new release is `Agent.spec.enabled: false` or `approval.approved: false`, both of which are mutable.

### 6.5 Admission

Kyverno enforces that every pod in a tenant namespace is a sandbox of a ready, signed, drift-free release and is shaped exactly like the template. The rules match on the namespace, not on the sandbox label, so omitting the label is itself a violation. Install Kyverno in `Enforce` mode. RBAC completes the picture: only the Session Runner's ServiceAccount may create pods in tenant namespaces (10.6), and `pods/ephemeralcontainers` is granted to nobody.

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: agent-sandbox-admission
spec:
  validationFailureAction: Enforce
  background: false
  rules:
    # Rule 0: every pod in a tenant namespace must declare itself a sandbox.
    - name: tenant-pods-are-sandboxes
      match:
        any:
          - resources:
              kinds: [Pod]
              namespaceSelector:
                matchExpressions:
                  - {key: agentplatform.io/tenant, operator: Exists}
      validate:
        message: "only sandbox pods may exist in a tenant namespace"
        pattern:
          metadata:
            labels:
              agentplatform.io/sandbox: "true"
              agentplatform.io/agent: "?*"
              agentplatform.io/release: "?*"
              agentplatform.io/session: "?*"
              agentplatform.io/generation: "?*"
            annotations:
              agentplatform.io/policy-digest: "sha256:?*"
    # Rule 1: the image is signed by the organisation key.
    - name: verify-image-signature
      match:
        any:
          - resources:
              kinds: [Pod]
              namespaceSelector:
                matchExpressions:
                  - {key: agentplatform.io/tenant, operator: Exists}
      verifyImages:
        - imageReferences: ["registry.example.com/agents/*"]
          mutateDigest: false
          verifyDigest: true
          required: true
          attestors:
            - entries:
                - keys:
                    publicKeys: |-
                      -----BEGIN PUBLIC KEY-----
                      <organisation cosign public key>
                      -----END PUBLIC KEY-----
    # Rule 2: the pod's shape is the template's shape. Fields with a required
    # literal are pinned; fields that must be absent are denied below.
    - name: sandbox-shape
      match:
        any:
          - resources:
              kinds: [Pod]
              namespaceSelector:
                matchExpressions:
                  - {key: agentplatform.io/tenant, operator: Exists}
      validate:
        message: "sandbox pod does not match the required shape"
        pattern:
          spec:
            runtimeClassName: kata-qemu-runtime-rs
            automountServiceAccountToken: false          # must be present and false; absence fails
            serviceAccountName: "agent-{{request.object.metadata.labels.\"agentplatform.io/agent\"}}"
            hostNetwork: false
            hostPID: false
            hostIPC: false
            dnsPolicy: None
            restartPolicy: Never
            securityContext:
              runAsNonRoot: true
              runAsUser: 1500
              seccompProfile: {type: RuntimeDefault}
            initContainers:
              - name: egress-guard
                image: "registry.example.com/platform/egress-guard@sha256:5b2c*"
                securityContext:
                  allowPrivilegeEscalation: false
                  readOnlyRootFilesystem: true
                  capabilities: {drop: ["ALL"]}
            containers:
              - name: agent
                command: ["/app/.venv/bin/python", "-m", "agent_runtime.wait"]
                securityContext:
                  allowPrivilegeEscalation: false
                  readOnlyRootFilesystem: true
                  privileged: "!true"
                  capabilities: {drop: ["ALL"]}
            volumes:
              - name: agent-identity
                projected:
                  sources:
                    - serviceAccountToken:
                        audience: https://idp.example.com/realms/agents
                        expirationSeconds: 600
              - name: gateway-ca
                configMap: {name: agent-gateway-ca}
              - name: podinfo
                downwardAPI: {}
              - name: workspace
                emptyDir: {}
              - name: tmp
                emptyDir: {}
    # Rule 3: exactly one init container and one container; no other volume types.
    - name: sandbox-no-extras
      match:
        any:
          - resources:
              kinds: [Pod]
              namespaceSelector:
                matchExpressions:
                  - {key: agentplatform.io/tenant, operator: Exists}
      validate:
        message: "sandbox pod has extra containers or disallowed volumes"
        deny:
          conditions:
            any:
              - key: "{{ request.object.spec.containers | length(@) }}"
                operator: NotEquals
                value: 1
              - key: "{{ request.object.spec.initContainers | length(@) }}"
                operator: NotEquals
                value: 1
              - key: "{{ request.object.spec.volumes | length(@) }}"
                operator: NotEquals
                value: 5
              - key: "{{ request.object.spec.volumes[?hostPath] | length(@) }}"
                operator: GreaterThan
                value: 0
              - key: "{{ request.object.spec.volumes[?secret] | length(@) }}"
                operator: GreaterThan
                value: 0
              - key: "{{ request.object.spec.volumes[?persistentVolumeClaim] | length(@) }}"
                operator: GreaterThan
                value: 0
    # Rule 4: the release is ready and the pod carries its image and digest.
    - name: release-must-be-ready-and-match
      match:
        any:
          - resources:
              kinds: [Pod]
              namespaceSelector:
                matchExpressions:
                  - {key: agentplatform.io/tenant, operator: Exists}
      context:
        - name: release
          apiCall:
            urlPath: "/apis/agentplatform.io/v1alpha1/namespaces/{{request.namespace}}/agentreleases/{{request.object.metadata.labels.\"agentplatform.io/release\"}}"
            jmesPath: "{ready: status.ready, image: spec.image, digest: status.policyDigest, agent: spec.agent}"
      validate:
        message: "sandbox must reference a ready AgentRelease whose image, agent and policy digest match"
        deny:
          conditions:
            any:
              - key: "{{ release.ready }}"
                operator: NotEquals
                value: true
              - key: "{{ request.object.spec.containers[0].image }}"
                operator: NotEquals
                value: "{{ release.image }}"
              - key: "{{ request.object.metadata.labels.\"agentplatform.io/agent\" }}"
                operator: NotEquals
                value: "{{ release.agent }}"
              - key: "{{ request.object.metadata.annotations.\"agentplatform.io/policy-digest\" }}"
                operator: NotEquals
                value: "{{ release.digest }}"
```

Rule 2 uses Kyverno's `pattern` semantics, so a field it names must be present with that value: `automountServiceAccountToken: false` fails when the field is omitted, which is the intended fail-closed behaviour (an earlier draft defaulted the field with a JMESPath `|| true`, which mis-handles `false`). Rule 3 bounds what Rule 2 cannot express (counts and absent volume types). Ephemeral containers are added through the `pods/ephemeralcontainers` subresource, which no principal holds in tenant namespaces; the conformance test T22 exercises each of these cases directly.

## 7. Identity provider configuration

Keycloak 26.8 is the reference: it accepts Kubernetes projected tokens as client credentials (supported since 26.6), performs standard RFC 8693 token exchange (since 26.2) and issues delegated tokens with `act` (preview in 26.8). Section 7.9 maps the same objects onto Authentik and Entra ID.

### 7.1 Server features and realm

Delegation is a preview feature in Keycloak 26.8 and depends on parameterized scopes and on fine-grained admin permissions version 2. Start Keycloak with exactly:

```
bin/kc.sh start --features=token-exchange-delegation,parameterized-scopes,admin-fine-grained-authz:v2
```

A preview feature is acceptable for the homelab profile; an enterprise deployment either waits for delegation to be supported or isolates it in a realm whose only clients are the agent platform's, so a preview regression cannot affect human sign-in.

Realm `agents`:

| Setting | Value |
| --- | --- |
| Access token lifespan | 300 s |
| Client session idle and max | 600 s and 28800 s |
| Offline session idle | 8 h (bounds the subject token in the vault) |
| Brute force detection | on |
| Consent required | on for the CLI client (section 7.6) |

### 7.2 The cluster as an identity provider

The realm must trust the Kubernetes issuer. First make the cluster's discovery documents readable without credentials:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: service-account-issuer-discovery-unauthenticated
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:service-account-issuer-discovery
subjects:
  - kind: Group
    name: system:unauthenticated
    apiGroup: rbac.authorization.k8s.io
```

Then create an OpenID Connect identity provider entry in the realm named `kubernetes-<cluster>` with:

| Field | Value |
| --- | --- |
| Issuer | `https://kubernetes.default.svc.cluster.local` (read the exact value from `/.well-known/openid-configuration`) |
| JWKS URL | `https://kubernetes.default.svc.cluster.local/openid/v1/jwks` |
| Use JWKS URL | on; cache keys for at least 10 minutes |
| Validate signatures | on |
| Trust email, sync mode | off, `IMPORT` is irrelevant: no users are created from it |

If Keycloak runs outside the cluster, the API server's discovery is not reachable; set `--service-account-jwks-uri` on the API server to a URL Keycloak can reach (a static copy of the JWKS behind the existing ingress, refreshed on key rotation) and use that URL above. Keycloak must trust the cluster CA for the in-cluster URL; mount it into Keycloak's truststore.

### 7.3 Agent clients

One confidential client per agent with no secret. Configure the first one by hand, verify it with the test in 7.8, export it with `kcadm.sh get clients/<id> -r agents`, and give that JSON to the Registry Controller as its template; the attribute keys below are then whatever the export shows, which removes the risk of a mistyped attribute name.

| Field | Value |
| --- | --- |
| Client ID | `agent-<tenant>-<name>` |
| Client authentication | on (confidential) |
| Authenticator | Federated JWT (the 26.6 "federated client authentication"), bound to identity provider `kubernetes-<cluster>` |
| Expected subject | `system:serviceaccount:<tenant>:agent-<name>` |
| Expected audience of the assertion | `https://idp.example.com/realms/agents` (the realm issuer; rfc7523bis) |
| Standard flow, implicit flow, direct access grants | off |
| Service accounts (client credentials) | on |
| Standard token exchange | **on**: the agent client is the actor in delegation, and Keycloak requires the actor client to have it enabled. The sandbox cannot abuse it because it never reaches the IdP's token endpoint (8.3: the token route ends at the APS, which forwards `client_credentials` only) |
| Fine-grained permission (FGAP v2) | the client's service-account user holds `delegate` for the users or groups the agent may act for; without it Keycloak drops the delegation scope silently |
| Default client scopes | `agent-gateway`, `agent-claims-<tenant>-<name>` |
| Optional client scopes | `mcp:<backend>` for each MCP backend in the `Agent`, each with an audience mapper for that backend's resource URL (7.7) |
| Realm roles on the service-account user | `agent-role-<backend>-read` per MCP backend in the `Agent` |

Create with kcadm (attribute keys to be confirmed from the hand-made export):

```bash
kcadm.sh create clients -r agents \
  -s clientId=agent-tenant-a-investigator \
  -s publicClient=false -s serviceAccountsEnabled=true \
  -s standardFlowEnabled=false -s implicitFlowEnabled=false -s directAccessGrantsEnabled=false \
  -s clientAuthenticatorType=federated-jwt \
  -s 'attributes."federated.jwt.identity.provider"=kubernetes-cluster-a' \
  -s 'attributes."federated.jwt.expected.subject"=system:serviceaccount:tenant-a:agent-investigator'
```

### 7.4 Client scopes and protocol mappers

| Scope | Mapper | Claim | Value |
| --- | --- | --- | --- |
| `agent-gateway` (default on every agent client; the SDK requests it by this name) | Audience | `aud` | `agent-gateway` and `agent-policy-service` (two audience mappers; the second lets the APS use the token as an actor token) |
| `agent-claims-<tenant>-<name>` (one per agent, default on its client) | Hardcoded claim | `client_type` | `agent` |
| same | Hardcoded claim | `agent_id` | `<tenant>/<name>` |
| same | Hardcoded claim | `tenant` | `<tenant>` |
| same | Hardcoded claim | `spiffe_id` | `spiffe://<trust-domain>/ns/<tenant>/sa/agent-<name>` |
| `roles` (built in) | Realm roles | `realm_access.roles` | the service-account user's roles |

All four hardcoded claims are added to the access token only (not the ID token), as strings.

### 7.5 Exchanging clients

| Client ID | Type | Secret stored in | Standard token exchange | Delegation |
| --- | --- | --- | --- | --- |
| `agent-gateway` | confidential, client credentials only | Secret `idp-client-agent-gateway` in `ai-gateway`, key `client_secret` | on | off |
| `agent-policy-service` | confidential, client credentials only | Secret `idp-client-agent-policy-service` in `agent-platform`, key `client_secret` | on | on; its client policy restricts `may_act` to clients whose ID starts with `agent-` |
| `registry-controller` | confidential, client credentials only | Secret `idp-client-registry-controller` in `agent-platform` | off | off; holds realm-management roles `manage-clients`, `manage-users`, `view-realm`, plus the FGAP v2 realm-role `map-role-client-scope` permission below |

**Qualification note, 2026-11-06 16:57 UTC: the FGAP v2 scope-mapping
permission is verified.** With `adminPermissionsEnabled: true` on Keycloak
26.8.1, the three realm-management roles above do not authorize
`POST /clients/{id}/scope-mappings/realm` for realm roles. The role-side
`RolePermissionsV2.canMapClientScope` check additionally needs
`map-role-client-scope`. Al applied client policy `registry-controller`
and scope permission `registry-controller-map-role-client-scope` in the
admin-permissions client (resource type Roles).

The read-only evaluator returns PERMIT when supplied both the controller's
service-account user and its client UUID. User-only evaluation defaults to
the admin-permissions client and returns DENY for the client policy. The
controller's own credentials then received **204** for an idempotent POST
of the already present `agent-role-kubernetes-read` scope mapping on
conformance-b; the mapping set was unchanged. The pinned
[Keycloak implementation](https://github.com/keycloak/keycloak/blob/26.8.1/services/src/main/java/org/keycloak/services/resources/admin/ScopeMappedResource.java#L221-L237)
performs its permission check before adding even an existing mapping.
This verifies the current grant without widening authority or disrupting a
client. It does not resolve the cause of the historical 403 observations.

The operator-run [grant script](../../../infrastructure/scripts/ops/grant-map-role-client-scope.sh)
and [verification evidence](agent-runtime-platform-keycloak-scope-verification-2026-11-06.json)
are retained with qualification finding 14. The script skips existing
objects and does not overwrite policy configuration. `manage-realm` is
not granted.

The client ID `agent-gateway` is deliberately identical to the audience the agents listener requires: Keycloak's standard exchange requires the requesting client to appear in the subject token's `aud`, and the audience mapper in 7.4 guarantees it.

**Delegation contract.** Keycloak's token-exchange guide documents client delegation as follows, and the platform follows it exactly rather than either of the two contracts an earlier revision proposed: the requesting client **is** the actor client and authenticates itself; `actor_token` is required and is the actor's own access token (its presence is what selects the delegation flow); the subject token must carry `may_act` naming the actor's service-account user and the actor client in its `aud`, both of which the `delegation:client:<id>` parameterized scope adds at consent; the issued token's `act` is built from `may_act` and its `aud` and scopes are resolved from the actor client's configuration, in a transient session.

| Element | Value in this platform |
| --- | --- |
| Requesting client | the agent client `agent-<tenant>-<name>` |
| How the APS authenticates as it | with the same federated JWT authenticator the sandbox uses: the APS mints a ServiceAccount token for `agent-<name>` through the Kubernetes TokenRequest API (`audience: ${ISSUER_URL}`, `expirationSeconds: 300`, `boundObjectRef` = the calling sandbox pod) and sends it as `client_assertion`. The APS holds no per-agent secret and no signing key; its authority is the `serviceaccounts/token` create permission, which is audited by the API server |
| `actor_token`, `actor_token_type` | the agent access token taken from the request's `Authorization` header; `urn:ietf:params:oauth:token-type:access_token` |
| `subject_token`, `subject_token_type` | the vaulted user token; `urn:ietf:params:oauth:token-type:access_token` |
| `scope` | `mcp:<backend>`, an optional client scope of the agent client whose audience mapper names that backend's resource URL. Whether an optional scope narrows a delegated token's `aud` is proven by T10a; if it does not, the delegated token carries every resource audience the agent's client scopes define and MCP servers check that `aud` contains their URL |
| Issued token | `sub` = user, `act.sub` = the agent's service-account user (the same value as `may_act.sub`), `aud` from the agent client's scopes, `azp` = the agent client |
| Subject token prerequisites | obtained by `agent-cli` (Consent required on) with `scope=openid offline_access agent-policy-service delegation:client:agent-<tenant>-<name>`; the user approved the delegation on the consent screen; the agent's service account holds the FGAP v2 `delegate` permission for that user |
| Agent-mode exchange (no user) | unchanged standard exchange: requester `agent-policy-service` (present in the agent token's `aud`), `subject_token` = the agent token, no actor token, `audience` = the resource client (7.7) |

T10a proves this flow end to end on the pinned Keycloak before any controller code depends on it, asserts the exact `sub`, `act`, `aud`, `azp` and `scope` values, and exports the realm as the authoritative configuration artifact. The two things the guide leaves to the test are whether federated JWT authentication is accepted on the token-exchange grant (it is a client-authentication method, independent of the grant, but it has not been exercised in this combination) and whether an optional scope narrows the delegated audience.

### 7.6 Users, consent and the CLI client

Humans authenticate through the existing realm login (federated to the enterprise directory where one exists). The submitting client is a public client `agent-cli` with PKCE, standard flow on, consent required, and these optional client scopes:

| Scope | Purpose |
| --- | --- |
| `offline_access` | a refresh token for the vault, so a delegated session can outlive one access token |
| `agent-policy-service` | audience mapper adding `agent-policy-service` to `aud`, so the APS accepts the deposit |
| `delegation:client:agent-<tenant>-<name>` | Keycloak's parameterized consent scope for delegation to that agent (requires the `parameterized-scopes` feature); it adds `may_act` and the agent client's audience to the user token; the agent's service account must hold the FGAP v2 `delegate` permission for the user, or the scope is dropped silently and the deposit fails the scope check |

The consent screen therefore names the agent the user is authorising. A token without the matching delegation scope is refused at deposit (section 4.3) and at exchange (the IdP enforces `may_act`).

### 7.7 Resource clients for MCP servers

Keycloak only issues a token with a given `aud` to a client with that ID, so each MCP backend has a bearer-only client whose client ID is its resource URL:

| Client ID | Bearer only | Purpose |
| --- | --- | --- |
| `https://mcp.example.com/kubernetes/mcp` | on | target of `audience=` in exchange requests for the Kubernetes backend |
| `https://mcp.example.com/github/mcp` | on | same for GitHub |

The exchange request (both the gateway's and the APS's) sets `audience` to that client ID; the issued token's `aud` is then the resource URL the MCP server checks.

### 7.8 Verification of the IdP configuration

From any pod with the projected token mounted and network access to the IdP (a test pod in `agent-platform`, not a sandbox), the following must return an access token whose decoded `aud` contains `agent-gateway` and whose `client_type` is `agent`:

```bash
curl -sS -X POST "$ISSUER_URL/protocol/openid-connect/token" \
  -d grant_type=client_credentials \
  -d client_id=agent-tenant-a-investigator \
  -d client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer \
  --data-urlencode "client_assertion=$(cat /var/run/secrets/agent-identity/token)" \
  -d scope=agent-gateway | jq -r .access_token | cut -d. -f2 | base64 -d 2>/dev/null | jq .
```

The same request with the pod's default API-audience token instead of the projected token must fail with `invalid_client`.

### 7.9 Equivalents on other identity providers

| Object here | Authentik (2026.8 or later) | Entra ID |
| --- | --- | --- |
| Cluster as identity provider | Federated OIDC Source pointing at the cluster issuer and JWKS | Federated identity credential on the agent's app registration, issuer = cluster issuer, subject = the ServiceAccount subject |
| Agent client with federated JWT auth | OAuth2 provider; machine-to-machine `client_credentials` with `client_assertion` from the federated source; a service-account user is created per subject | App registration with the federated credential; `client_credentials` with `client_assertion` |
| Hardcoded claims | Scope mappings with expressions | Optional claims or an app role per agent |
| Standard token exchange with `act` | Token exchange (2026.8); delegation requires an Actor object and allows exactly one `audience`; `resource` is rejected, so the gateway and APS send `audience` only | No RFC 8693; use the on-behalf-of jwt-bearer grant, and read `xms_act_fct` and `xms_sub_fct` instead of `act` at MCP servers |
| Resource clients | One provider per MCP server with its own audience | One app registration per MCP server with an Application ID URI equal to the resource URL |
| Consent scope | Consent on the application | Admin consent per agent app; user consent where policy allows |

These are mappings of concepts, not drop-in substitutions. Each provider is supported only through its own adapter in the APS (9.5) and its own row in the conformance matrix: agent authentication (T4, T5), delegated consent and actor attribution (T10, T10a), resource audiences (T12) and revocation (T16) must all pass on that provider before it is listed as supported. Known differences: Authentik allows exactly one `audience` and rejects `resource`; Entra ID has no RFC 8693 exchange, its on-behalf-of grant applies to user principals only, and its `xms_act_fct` and `xms_sub_fct` claims classify the actor and subject rather than identify the actor, so an MCP server behind Entra identifies the agent from `azp` and a registry mapping instead of `act.sub`. The first complete profile is Keycloak; a second provider is added only with its full test row.

## 8. Gateway configuration

One dedicated Gateway named `agents` serves sandboxes over TLS; its routes (token, one per model backend, one per MCP backend) share one JWT policy, one authorization policy, one external-authorization policy per route and one budget policy, and every backend presents its own credential. There is no decision cache and no header transformation: every request is evaluated by the APS, which also performs header hygiene. Field names were checked against the agentgateway v1.5.0 CRD types; the deployment pins 1.7.0 exactly, and fields that exist only from 1.6 or 1.7 are marked.

### 8.1 Gateway and data plane

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: agents
  namespace: ai-gateway
spec:
  gatewayClassName: agentgateway
  listeners:
    - name: agents-https
      protocol: HTTPS
      port: 443
      tls:
        mode: Terminate
        certificateRefs:
          - {kind: Secret, name: agents-gateway-tls}   # cert-manager, ClusterIssuer internal-ca,
                                                       # SANs: token.agents.internal, inference.agents.internal, mcp.agents.internal
      allowedRoutes:
        namespaces: {from: Same}
  infrastructure:
    parametersRef:
      group: agentgateway.dev
      kind: AgentgatewayParameters
      name: agents-data-plane
---
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayParameters
metadata:
  name: agents-data-plane
  namespace: ai-gateway
spec:
  resources:
    requests: {cpu: 250m, memory: 256Mi}
    limits:   {cpu: "2",  memory: 1Gi}
  deployment:
    spec:
      replicas: 2
  service:
    spec:
      clusterIP: 10.43.250.10        # GATEWAY_CLUSTER_IP; a Service's clusterIP is immutable, set it at creation
```

The controller names the data-plane Deployment and Service `agents` and labels the pods `app.kubernetes.io/name: agents`, which every NetworkPolicy in section 5 relies on. If the chart's `service` field does not accept `spec.clusterIP`, apply a Kustomize patch to the generated Service before the first reconcile; the value must never change afterwards. The internal CA's certificate is published by trust-manager (or copied by the Registry Controller) as ConfigMap `agent-gateway-ca` into every tenant namespace. A plain-HTTP listener is permitted only in a development profile and never on a Gateway that tenant namespaces can reach.

### 8.2 Cross-namespace grants

```yaml
apiVersion: gateway.networking.k8s.io/v1beta1
kind: ReferenceGrant
metadata:
  name: agents-gateway-to-keycloak
  namespace: auth
spec:
  from:
    - {group: agentgateway.dev, kind: AgentgatewayPolicy, namespace: ai-gateway}   # JWKS only
  to:
    - {group: "", kind: Service, name: keycloak}
---
apiVersion: gateway.networking.k8s.io/v1beta1
kind: ReferenceGrant
metadata:
  name: agents-gateway-to-platform
  namespace: agent-platform
spec:
  from:
    - {group: gateway.networking.k8s.io, kind: HTTPRoute, namespace: ai-gateway}       # token route
    - {group: agentgateway.dev, kind: AgentgatewayPolicy, namespace: ai-gateway}       # extAuth, rate limit
  to:
    - {group: "", kind: Service, name: agent-policy-service}
    - {group: "", kind: Service, name: ratelimit}
```

### 8.3 Routes

```yaml
# Token route: the only route without JWT authentication. It ends at the APS,
# never at the identity provider, so a sandbox can only ever perform the one
# grant the APS forwards (client_credentials with a projected-token assertion).
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: agents-token
  namespace: ai-gateway
spec:
  parentRefs: [{name: agents, sectionName: agents-https}]
  hostnames: [token.agents.internal]
  rules:
    - matches:
        - path: {type: Exact, value: /v1/token}
          method: POST
      backendRefs:
        - {kind: Service, name: agent-policy-service, namespace: agent-platform, port: 9002}
---
# One inference route per model backend. The path prefix names the backend;
# the backend pins the model (8.4), so the body's model field has no authority.
# The prefix is rewritten away so the model server sees the standard path.
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: agents-inference-llm-main
  namespace: ai-gateway
spec:
  parentRefs: [{name: agents, sectionName: agents-https}]
  hostnames: [inference.agents.internal]
  rules:
    - matches:
        - path: {type: PathPrefix, value: /models/llm-main/v1/}
          method: POST
      filters:
        - type: URLRewrite
          urlRewrite:
            path: {type: ReplacePrefixMatch, replacePrefixMatch: /v1/}
      backendRefs:
        - {group: agentgateway.dev, kind: AgentgatewayBackend, name: llm-main}
---
# One MCP route per backend. The well-known paths are not served to sandboxes:
# they never do OAuth discovery, they already hold a token.
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: agents-mcp-kubernetes
  namespace: ai-gateway
spec:
  parentRefs: [{name: agents, sectionName: agents-https}]
  hostnames: [mcp.agents.internal]
  rules:
    - matches:
        - path: {type: PathPrefix, value: /kubernetes/mcp}
      backendRefs:
        - {group: agentgateway.dev, kind: AgentgatewayBackend, name: mcp-kubernetes}
```

No other route is attached to the `agents` Gateway. A request for any other host or path receives 404 from the gateway and never reaches the APS. An agent whose bundle allows two model backends gets two inference routes in its allow-list; it selects the model by base URL, never by the `model` field, and the gateway's own CEL variable `llm.requestModel` is additionally pinned per route (8.5) in case a backend's model override is not applied to a given request shape.

### 8.4 Backends and their credentials

```yaml
# Model server: the gateway presents the static key the server requires.
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayBackend
metadata:
  name: llm-main
  namespace: ai-gateway
spec:
  ai:
    provider:
      openai:
        model: Qwen3.6-35B-A3B-NVFP4
      host: llm-main.llm.svc.cluster.local
      port: 8000
  policies:
    auth:
      secretRef:
        name: backend-cred-llm-main      # key Authorization: "Bearer <key>"; the gateway strips the prefix itself
---
# External provider example: the gateway holds the provider key; the sandbox never sees it.
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayBackend
metadata:
  name: llm-external
  namespace: ai-gateway
spec:
  ai:
    provider:
      anthropic:
        model: claude-sonnet-5-5
  policies:
    auth:
      secretRef:
        name: backend-cred-llm-external
---
# MCP server. No backend auth here: the APS sets the upstream Authorization
# header on every request (section 9.5), in both delegation modes.
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayBackend
metadata:
  name: mcp-kubernetes
  namespace: ai-gateway
spec:
  mcp:
    failureMode: FailClosed
    sessionRouting: Stateless         # 1.7: replica-independent sessions
    targets:
      - name: kubernetes
        static:
          host: kubernetes-mcp.mcp.svc.cluster.local
          port: 8080
          path: /mcp
          protocol: StreamableHTTP
```

`backend-cred-llm-main` and the model server's own `llm-api-key` carry the same value; vLLM is started with `--api-key $(VLLM_API_KEY)` so that a request without that exact bearer is rejected with 401 even from inside the `llm` namespace.

### 8.5 JWT authentication (inference and MCP routes)

```yaml
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: agents-jwt
  namespace: ai-gateway
spec:
  targetRefs:
    - {group: gateway.networking.k8s.io, kind: HTTPRoute, name: agents-inference-llm-main}
    - {group: gateway.networking.k8s.io, kind: HTTPRoute, name: agents-mcp-kubernetes}
  traffic:
    jwtAuthentication:
      mode: Strict
      preserveToken: true                # the APS needs the token; the APS response removes or replaces it
      providers:
        - issuer: https://idp.example.com/realms/agents       # ISSUER_URL, byte for byte
          audiences: [agent-gateway]
          jwks:
            remote:
              backendRef: {kind: Service, name: keycloak, namespace: auth, port: 8080}
              jwksPath: /realms/agents/protocol/openid-connect/certs
              cacheDuration: 10m
---
# Claim assertions are CEL, not requiredClaims (whose documented purpose is
# presence of registered claims). This policy is the declarative half of the
# "agents only" rule; the APS repeats the check.
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: agents-only
  namespace: ai-gateway
spec:
  targetRefs:
    - {group: gateway.networking.k8s.io, kind: HTTPRoute, name: agents-inference-llm-main}
    - {group: gateway.networking.k8s.io, kind: HTTPRoute, name: agents-mcp-kubernetes}
  traffic:
    authorization:
      action: Allow
      policy:
        matchExpressions:
          - 'jwt.client_type == "agent" && "agent-gateway" in jwt.aud'
---
# Per-route model pin, evaluated by the gateway's own AI parser.
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: agents-inference-llm-main-model-pin
  namespace: ai-gateway
spec:
  targetRefs:
    - {group: gateway.networking.k8s.io, kind: HTTPRoute, name: agents-inference-llm-main}
  traffic:
    authorization:
      action: Allow
      policy:
        matchExpressions:
          - 'llm.requestModel == "Qwen3.6-35B-A3B-NVFP4"'
```

With `preserveToken: true` the validated token stays on the request so the external-authorization call can forward it; the APS then either sets a new `Authorization` (MCP) or lists `authorization` in `headers_to_remove` (inference), so the inbound token never reaches an upstream in either case. Human-issued tokens (no `client_type`, or `aud` without `agent-gateway`) fail the JWT or the `agents-only` policy with 401 or 403.

### 8.6 Header hygiene

```yaml
# No transformation policy. agentgateway's documented traffic-policy order
# runs transformation after external authorization, so a header-stripping
# transformation would remove the attribution headers the APS just added.
# Hygiene lives in the APS response instead:
#   headers (overwrite):      every x-agent-* the APS sets
#   headers_to_remove:        every other x-agent-* name, plus authorization on inference routes
```

The APS never reads an inbound `x-agent-*` header, overwrites every one it emits and removes every one it does not, and the list of names it removes is the complete list in section 3.5. The result is the same whatever order the gateway applies its policies in, and T8 verifies it with forged headers.

### 8.7 External authorization

One policy per route so the APS knows which route it is deciding without parsing the host.

```yaml
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: agents-extauth-inference-llm-main
  namespace: ai-gateway
spec:
  targetRefs:
    - {group: gateway.networking.k8s.io, kind: HTTPRoute, name: agents-inference-llm-main}
  traffic:
    extAuth:
      backendRef: {kind: Service, name: agent-policy-service, namespace: agent-platform, port: 9001}
      failureMode: FailClosed
      # No body: the route names the backend and the backend pins the model.
      grpc:
        contextExtensions:
          route: inference
          backend: llm-main
      # No cache: a cached decision could be reused for a different operation.
---
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: agents-extauth-mcp-kubernetes
  namespace: ai-gateway
spec:
  targetRefs:
    - {group: gateway.networking.k8s.io, kind: HTTPRoute, name: agents-mcp-kubernetes}
  traffic:
    extAuth:
      backendRef: {kind: Service, name: agent-policy-service, namespace: agent-platform, port: 9001}
      failureMode: FailClosed
      forwardBody: {maxSize: 65536}      # JSON-RPC bodies; the SDK caps tool arguments at 32 KiB
      grpc:
        contextExtensions:
          route: mcp
          backend: kubernetes
      # No cache, for the same reason.
```

The gRPC check request carries the `Authorization` header by default; the APS needs it as the actor token for delegated exchange and re-validates it itself. Headers in the APS's `OkHttpResponse` are applied to the upstream request and its dynamic metadata becomes `extauthz.*` in CEL, rate-limit descriptors and logging. Decision caching is deliberately absent: the APS decides on the MCP method and tool name, which are not part of any cache key the gateway could form, so a cached allow for one tool would be reused for another; an earlier draft had a 5 s cache and was wrong. The APS's own per-request cost is bounded by its input caches (9.4).

### 8.8 Tool-level rules

A second, declarative check that does not depend on the APS being correct: only agents holding the backend's read role may call the listed tools, and `tools/list` hides everything else.

```yaml
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: mcp-kubernetes-tools
  namespace: ai-gateway
spec:
  targetRefs:
    - {group: agentgateway.dev, kind: AgentgatewayBackend, name: mcp-kubernetes}
  backend:
    mcp:
      authorization:
        action: Allow
        policy:
          matchExpressions:
            - >-
              jwt.client_type == "agent" &&
              "agent-role-kubernetes-read" in jwt.realm_access.roles &&
              mcp.tool.name in ["events_list", "pods_get", "pods_list_in_namespace",
                                "pods_log", "resources_get", "resources_list"]
```

The list is the union of tools any agent may use on this backend; the per-agent subset is enforced by the APS from the policy bundle. Both must allow a call.

### 8.9 Budgets and abuse limits

```yaml
# Budgets. The HARD ceiling is the APS reservation ledger (9.3 step 10): a
# request is admitted only if spent + in-flight reservations + its reserve fit
# the session and agent-day budgets, in Redis shared by every replica. The
# gateway limits below are a second, soft layer: the global one debits actual
# usage after the response, the local one bounds request rate per sandbox.
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: agents-budget-llm-main
  namespace: ai-gateway
spec:
  targetRefs:
    - {group: gateway.networking.k8s.io, kind: HTTPRoute, name: agents-inference-llm-main}
  traffic:
    rateLimit:
      global:
        backendRef: {kind: Service, name: ratelimit, namespace: agent-platform, port: 8081}
        domain: agents
        failureMode: FailClosed
        descriptors:
          - entries:
              - {name: agent, expression: jwt.agent_id}
            unit: Tokens
      local:
        - requests: 30
          unit: Minutes
          burst: 5
          key: source.address                 # abuse control only; not a concurrency bound
---
# Token route: 60 token requests per minute per source address.
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: agents-token-route-limit
  namespace: ai-gateway
spec:
  targetRefs:
    - {group: gateway.networking.k8s.io, kind: HTTPRoute, name: agents-token}
  traffic:
    rateLimit:
      local:
        - requests: 60
          unit: Minutes
          burst: 10
          key: source.address
```

The rate-limit service is the reference Envoy `ratelimit` with Redis in `agent-platform`. The Registry Controller generates its configuration from every ready release's budget:

```yaml
# ConfigMap ratelimit-config, key agents.yaml, regenerated by the Registry Controller
domain: agents
descriptors:
  - key: agent
    rate_limit: {unit: day, requests_per_unit: 2000000}      # default budget
  - key: agent
    value: tenant-a/investigator
    rate_limit: {unit: day, requests_per_unit: 5000000}
```

Why the gateway's own limits are not the ceiling: agentgateway counts tokens from the response's `usage`, so a request that pushes a key over its budget completes and only the next one is refused; its per-key local `tokens` limits charge an estimate at admission but keep independent counters per replica; and its global limits go through the external service after the response. None of those is a cross-replica hard ceiling. The APS ledger is: before allowing an inference request it reserves `reserve_tokens` (the backend's `maxModelLen`, which the model server itself enforces as the upper bound of prompt plus output, or `max_context_tokens + max_tokens` once the gateway can pin `max_tokens`, see 17.3) against both budgets atomically, and the request is refused with 429 when the reservation does not fit. The number of requests a session can have in flight is therefore `floor((budget - spent - inflight) / reserve_tokens)`, an explicit bound that does not depend on request duration or on how many replicas serve the session. Reservations settle to actual usage when the gateway's access-log record for that decision ID reaches the APS (Alloy forwards a copy of the OTLP stream to the APS receiver), and an unsettled reservation is charged in full after 130 s. A request-rate limit such as the 30-per-minute local rule above does not bound concurrency, because long requests overlap minute windows and local counters are per replica; it is kept as abuse control. The sandbox's own `AGENT_TOKENS_PER_SESSION` counter is advisory and is never consulted by any trusted component; a restored checkpoint restores no budget.

### 8.10 Tracing and access logs

```yaml
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: agents-observability
  namespace: ai-gateway
spec:
  targetRefs:
    - {group: gateway.networking.k8s.io, kind: Gateway, name: agents}
  frontend:
    tracing:
      backendRef: {kind: Service, name: alloy, namespace: monitoring, port: 4317}
      protocol: GRPC
      randomSampling: "true"
      attributes:
        add:
          - {name: agent.id,            expression: extauthz.agent_id}
          - {name: agent.spiffe_id,     expression: extauthz.spiffe_id}
          - {name: agent.tenant,        expression: extauthz.tenant}
          - {name: agent.session_id,    expression: extauthz.session_id}
          - {name: agent.generation,    expression: extauthz.generation}
          - {name: agent.release,       expression: extauthz.release}
          - {name: agent.policy_digest, expression: extauthz.policy_digest}
          - {name: agent.principal,     expression: extauthz.principal}
          - {name: agent.decision_id,   expression: extauthz.decision_id}
          - {name: agent.decision,      expression: extauthz.reason}
          - {name: auth.jti,            expression: jwt.jti}
    accessLog:
      otlp:
        backendRef: {kind: Service, name: alloy, namespace: monitoring, port: 4317}
        protocol: GRPC
      attributes:
        add:
          - {name: agent.id,          expression: extauthz.agent_id}
          - {name: agent.session_id,  expression: extauthz.session_id}
          - {name: agent.decision,    expression: extauthz.reason}
          - {name: agent.decision_id, expression: extauthz.decision_id}
          - {name: mcp.tool,          expression: mcp.tool.name}
          - {name: llm.model,         expression: llm.requestModel}
          - {name: llm.tokens_in,     expression: llm.inputTokens}
          - {name: llm.tokens_out,    expression: llm.outputTokens}
        remove: [request.headers.authorization]
```

The gateway's built-in `gen_ai.*` and `mcp.*` span attributes are emitted without configuration. No attribute above carries a token.

### 8.11 Optional: native exchange for agent-only backends

When every agent allowed on an MCP backend runs in `agent` mode, the exchange can be moved from the APS into the gateway with `spec.backend.auth.oauthTokenExchange` (grant `TokenExchange`, subject token from the validated JWT, `audiences: [<resource URL>]`, client `agent-gateway` with its secret, in-memory cache). This is an optimisation, not the default: it must not be configured on a backend that any `on-behalf-of` agent uses, because the APS-set header and the gateway-set header would conflict. The conformance test T12 covers both configurations.

## 9. Agent Policy Service

The APS is a stateless gRPC service that answers one question per request, "may this pod, holding this token, make this call, and with which upstream credential", and denies whenever any input is missing.

### 9.1 Deployment

| Item | Value |
| --- | --- |
| Image | `registry.example.com/platform/agent-policy-service@sha256:...` (Go, static binary, distroless) |
| Replicas | 2 minimum; stateless apart from caches; HPA on CPU |
| Ports | 9001 gRPC (Envoy `envoy.service.auth.v3.Authorization`), 9002 HTTP (token, grants and sessions API), 4317 OTLP receiver (access-log settlement), 9090 metrics, 8081 health |
| ServiceAccount | `agent-policy-service` in `agent-platform`, token automounted (it talks to the API server) |
| RBAC | a ClusterRole for `agents`, `agentreleases` (agentplatform.io): get, list, watch; `configmaps`: get, list, watch; `pods`: get, list, watch; `tokenreviews` (authentication.k8s.io): create. Per tenant namespace, a Role (maintained by the Registry Controller) granting `serviceaccounts/token` create with `resourceNames` listing that tenant's `agent-*` ServiceAccounts explicitly. Kubernetes RBAC cannot scope by namespace label or name prefix, so the controller creates the RoleBindings in every tenant namespace it manages |
| Shared state | Redis in `agent-platform` (TLS, password from Secret `aps-redis`): `jti` pins, active generations, stopped sessions, vault entries, exchanged-token cache, budget ledgers (spent, reservations, settlements). Any replica can serve any session; the `memory` backend is for single-replica development only |
| Secrets | `idp-client-agent-policy-service` (`client_secret`), `aps-vault-key` (32 random bytes, base64), `aps-redis` |
| Environment | `ISSUER_URL`, `IDP_TOKEN_ENDPOINT`, `IDP_JWKS_URL`, \`IDP\_ADAPTER=keycloak |
| Probes | readiness true only after the pod, Agent, AgentRelease and ConfigMap informers have synced, Redis answers, and the IdP JWKS was fetched once |

### 9.2 Inputs the APS trusts

| Input | Source | Trust |
| --- | --- | --- |
| `Authorization` header | gateway forwards it in the check request (`preserveToken: true`) | re-validated by the APS against the IdP JWKS (signature, `iss`, `aud` contains `agent-gateway`, `exp`); the gateway's validation is not relied upon |
| Source address | `attributes.source.address.socket_address.address` | the pod IP as seen by the gateway; in-cluster traffic is not NATed |
| `route`, `backend` | `attributes.context_extensions` set per policy in 8.7 | configuration, trusted; the backend name is the unit of authorization for both models and MCP servers |
| Request body (MCP routes only) | forwarded up to 64 KiB | parsed for the JSON-RPC `method` and `params.name`; anything unparsable is denied. Inference routes forward no body: the route and backend already fix the model |
| Any `x-agent-*` header | request | ignored entirely |

### 9.3 Decision algorithm

The steps run in this order; the first failure returns the named reason and stops.

1. Parse and validate the bearer token. Failure: `deny.token_invalid`. Missing `client_type == "agent"`, `agent_id`, `tenant` or `jti`: `deny.token_not_agent`.
2. Look up the pod by source address in the pod index (pods with label `agentplatform.io/sandbox=true`). None, or more than one: `deny.pod_unknown`.
3. Compare: `pod.labels.agent == token.agent_id.split("/")[1]` and `pod.namespace == token.tenant`. Mismatch: `deny.pod_agent_mismatch`.
4. Check the token pin: the `jti` was pinned to a pod UID when the APS issued the token (9.7, `POST /v1/token`); if the pin names a different pod: `deny.token_bound_elsewhere`. A token with no pin (issued before an APS restart with the memory backend) is pinned now to this pod, once.
5. Pod phase must be `Running` with no `deletionTimestamp`; the session (`pod.labels.session`) must not be in the stopped set; and the pod must carry the host-side attestation annotation `agentplatform.io/netpol-attested` refreshed within the last 90 s (5.5). Otherwise: `deny.session_inactive`.
6. The pod's `generation` label must equal the session's active generation recorded by the Session Runner (9.7). Otherwise: `deny.generation_stale`. A session with no recorded generation is denied.
7. Load `AgentRelease` named `pod.labels.release` in the pod's namespace. `status.ready` must be true and `status.policyDigest` must equal `pod.annotations["agentplatform.io/policy-digest"]`. Otherwise: `deny.release_unapproved`.
8. Load the policy bundle from ConfigMap `policy-<release>` (cached by digest). For `route == inference`, `backend` must be a key of `bundle.models`; for `route == mcp`, `backend` must be a key of `bundle.mcp`. Otherwise: `deny.route_not_permitted`.
9. For MCP: parse the JSON-RPC body; if `method == "tools/call"`, `params.name` must be in `bundle.mcp[backend].tools`; `initialize`, `tools/list`, `ping`, `notifications/*`, and bodiless `GET` or `DELETE` are allowed; any other method is `deny.route_not_permitted`.
10. For inference: reserve `reserve_tokens` (the backend's `maxModelLen` from the catalogue, or the bundle's pinned `max_context_tokens + max_tokens`) against the session ledger (`budget:session:<id>`) and the agent-day ledger (`budget:agent:<id>:<UTC date>`) in one Redis Lua script: admit only if `spent + inflight + reserve <= budget` on both; store the reservation under the decision ID with a 130 s expiry. Failure: `deny.budget_exhausted`, returned as HTTP 429.
11. Determine the upstream credential. Inference: none; the APS lists `authorization` in `headers_to_remove` and the gateway's backend policy injects the model key. MCP: read `bundle.mcp[backend].delegation`. `on-behalf-of`: the session must have a vault entry, else `deny.delegation_required` (or, when `bundle.identity.fallback == "agent"`, fall through to agent mode). Perform or reuse the exchange of 9.5. `agent`: perform or reuse the agent-mode exchange. Failure: `deny.exchange_failed`.
12. Build the response of 9.6 with reason `allow`, including `tokens_per_session` from the bundle in the dynamic metadata.

Settlement runs outside the request path: the APS's OTLP receiver consumes the gateway access-log stream, matches each record's `agent.decision_id` to a reservation, replaces the reservation with the record's `llm.tokens_in + llm.tokens_out` in `spent`, and emits `aps_budget_settled_total`. A reservation that is never settled expires at its full amount into `spent`.

Any panic, timeout or unexpected error anywhere is `deny.internal`. Every decision is logged once with the fields in section 13.

### 9.4 Caches and indexes

| Cache or index | Key | Lifetime | Invalidation |
| --- | --- | --- | --- |
| Pod index | pod IP | informer-driven | immediate on pod events |
| Agent, AgentRelease, policy ConfigMaps | name | informer-driven | immediate |
| IdP JWKS | `kid` | 10 min | refetch once on unknown `kid`, then fail |
| Token pins (Redis) | `jti` | token `exp` | none needed |
| Active generation (Redis) | session ID | 24 h | set by the Session Runner before each generation is created |
| Stopped sessions (Redis) | session ID | 24 h | set by the Session Runner or the reconciler |
| Exchanged tokens (Redis, encrypted) | (session ID, backend, mode) | until `exp - 30 s` | on session stop, on vault delete |
| Vault entries (Redis, encrypted) | session ID | `expires_at`, at most 8 h | on session stop |

There is no decision cache anywhere: every check runs every step.

### 9.5 Token exchange

Both modes call the IdP token endpoint through the provider adapter selected by `IDP_ADAPTER`. In delegated mode the APS authenticates **as the agent client** (7.5): it first calls the Kubernetes TokenRequest API for ServiceAccount `agent-<name>` in the tenant namespace with `audience: ${ISSUER_URL}`, `expirationSeconds: 300` and `boundObjectRef` naming the calling sandbox pod, and uses the returned token as `client_assertion`; the agent's access token from the request is the `actor_token`. In agent mode the APS authenticates as `agent-policy-service` with HTTP basic and performs a standard exchange. Timeout 5 s, no retry on 4xx, one retry on 5xx or timeout.

Delegated mode:

```http
POST /realms/agents/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&client_id=agent-tenant-a-investigator
&client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer
&client_assertion=<ServiceAccount token for agent-investigator, aud = issuer, bound to the sandbox pod>
&subject_token=<vaulted user access token>
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&actor_token=<agent access token from the request>
&actor_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&scope=mcp%3Akubernetes
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
```

Agent mode is the same request without `actor_token` and `actor_token_type`, and with `subject_token` set to the agent access token.

Before a delegated exchange, if the vaulted access token has fewer than 120 s left and a refresh token exists, the APS refreshes it (`grant_type=refresh_token`, `client_id=agent-cli`, no client secret because the CLI client is public) and stores the new pair. If refresh fails, the vault entry is marked expired and the decision is `deny.delegation_required`.

The response's `access_token` is validated (signature, `iss`, `aud` equals the requested audience, `act.sub` present in delegated mode) before it is cached and returned. On Entra ID the request is replaced by the on-behalf-of grant (`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`, `requested_token_use=on_behalf_of`, `assertion=<subject token>`) and the actor is the APS's own app; the `act.sub` check becomes `xms_act_fct`.

### 9.6 Response

Allowed:

| Part | Content |
| --- | --- |
| `ok_response.headers` (upstream request, overwrite) | `x-agent-id`, `x-agent-spiffe-id`, `x-agent-tenant`, `x-agent-session-id`, `x-agent-generation`, `x-agent-release`, `x-agent-policy`, `x-agent-decision-id`; `x-agent-principal` in delegated mode; `Authorization: Bearer <upstream token>` for MCP |
| `ok_response.headers_to_remove` | every `x-agent-*` name from section 3.5 that the APS did not set in this response (always `x-agent-decision-reason`; `x-agent-principal` when not delegated), and `authorization` on inference routes |
| `dynamic_metadata` | `agent_id`, `spiffe_id`, `tenant`, `session_id`, `generation`, `release`, `policy_digest`, `principal`, `decision_id`, `reason`, `tokens_per_session`, `reserved_tokens` (consumed by the tracing policy in 8.10 and by settlement) |
| Denied for budget | HTTP **429**, header `x-agent-decision-reason: deny.budget_exhausted`, the same JSON body shape as other denials, plus `retry-after: 60` |

Denied: HTTP 403, header `x-agent-decision-reason: <reason>`, body `{"error":"forbidden","reason":"<reason>","decision_id":"<uuid>"}`, the same dynamic metadata. The gateway never forwards the reason header upstream (8.6 strips it); the sandbox receives the 403 body, which tells the agent why without leaking anything about other tenants.

### 9.7 HTTP API (port 9002)

| Method and path | Caller | Authentication | Effect |
| --- | --- | --- | --- |
| `POST /v1/token` | sandbox, through the gateway's token route | the `client_assertion` form field, a projected token, validated with a TokenReview that must return `authenticated: true` and the pod name and UID extras | refuses any `grant_type` other than `client_credentials`, any `client_id` other than the one registered for the pod's agent, and any assertion whose bound pod is not a running sandbox of that agent (403, never forwarded); otherwise forwards the identical form to the IdP token endpoint, pins the issued token's `jti` to the pod UID with TTL = `expires_in`, and returns the IdP's JSON response unchanged |
| `POST /v1/grants` | submitting client, through the humans' gateway | the subject token itself (bearer; `aud` contains `agent-policy-service`; `scope` contains `delegation:client:agent-<tenant>-<agent>`; `may_act.sub` present) | stores the vault entry for `session_id`; 201 with `grant_handle`; 409 if present; 403 on scope or `may_act` mismatch |
| `GET /v1/grants/{handle}` | Session Runner | runner identity (below) | 200 `{session_id, tenant, agent, expires_at}` if the handle exists and belongs to the caller's tenant; never returns token material |
| `DELETE /v1/grants/{handle}` | Session Runner | runner identity | deletes the entry and cached exchanges; 404 counts as success |
| `PUT /v1/sessions/{id}/generation` | Session Runner | runner identity | body `{"generation": n}`; sets the active generation; must be strictly increasing, else 409 |
| `POST /v1/sessions/{id}/stop` | Session Runner or the reconciler | runner identity | adds the session to the stopped set, deletes its vault entry, cached tokens and open reservations |
| `GET /v1/sessions?older_than=15m` | reconciler | runner identity | lists sessions with grants, generations or reservations still held |
| `GET /healthz`, `GET /readyz` | kubelet | none | probes |

Runner identity: the caller presents its projected ServiceAccount token with `audience: agent-policy-service`; the APS validates it with a TokenReview and requires `sub == system:serviceaccount:agent-platform:session-runner` (or the reconciler's account). The tenant of every call is taken from the session or grant record, and the runner's RoleBinding to that tenant is checked through a SubjectAccessReview on `agentreleases` get, so a runner cannot act on another tenant's sessions.

Runner identity: the caller presents its projected ServiceAccount token with `audience: agent-policy-service`; the APS validates it with a TokenReview and requires `sub == system:serviceaccount:agent-platform:session-runner` (or the reconciler's account). The tenant of every call is taken from the session or grant record, and the runner's RoleBinding to that tenant is checked through a SubjectAccessReview on `agentreleases` get, so a runner cannot act on another tenant's sessions.

The vault stores `{access_token, refresh_token, expires_at, tenant, agent, principal_sub}` encrypted with AES-256-GCM under `aps-vault-key`, with the session ID as additional authenticated data. The `memory` backend is for a single replica only; multi-replica deployments use Redis so that any replica can serve any session.

### 9.8 Reference implementation (Go)

The code below is the complete decision path; omitted are the informer setup (standard client-go) and the HTTP API, which are conventional.

```go
// cmd/aps/main.go
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"strconv"
	"strings"
	"time"

	corev3 "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	authv3 "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"github.com/google/uuid"
	"google.golang.org/genproto/googleapis/rpc/status"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/protobuf/types/known/structpb"
	corev1 "k8s.io/api/core/v1"
)

// Every x-agent-* header the platform defines. The response removes each one
// it does not set, so a client-supplied value never reaches an upstream.
var agentHeaders = []string{
	"x-agent-id", "x-agent-spiffe-id", "x-agent-tenant", "x-agent-session-id", "x-agent-generation",
	"x-agent-release", "x-agent-policy", "x-agent-principal", "x-agent-decision-id", "x-agent-decision-reason",
}

var ErrBudget = errors.New("budget exhausted")

const attestationMaxAge = 90 * time.Second

type AgentClaims struct {
	Sub, JTI, AgentID, Tenant, SpiffeID, ClientID, ClientType string
	Exp                                                      time.Time
	Raw                                                      string
}

type Bundle struct {
	Version  int    `json:"version"`
	Tenant   string `json:"tenant"`
	Agent    string `json:"agent"`
	Release  string `json:"release"`
	Identity struct {
		Mode, Fallback string
		Required       bool
	} `json:"identity"`
	Models map[string][]string `json:"models"` // backend -> pinned model names (informational here)
	MCP    map[string]struct {
		Tools      []string `json:"tools"`
		Delegation string   `json:"delegation"`
		Resource   string   `json:"resource"`
	} `json:"mcp"`
	Budgets struct {
		TokensPerSession int `json:"tokens_per_session"`
		TokensPerDay     int `json:"tokens_per_day"`
	} `json:"budgets"`
}

// Deps are injected collaborators; each is a function so tests can fake it.
type Deps struct {
	Verify    func(ctx context.Context, bearer string) (*AgentClaims, error)      // IdP JWKS validation
	PodByIP   func(ip string) (*corev1.Pod, int)                                   // pod and how many matched
	PinOK     func(ctx context.Context, jti, podUID string, exp time.Time) (bool, error) // true if pinned to this pod (pins if absent)
	ActiveGen func(ctx context.Context, session string) (int, bool, error)
	Stopped   func(ctx context.Context, session string) (bool, error)
	ReleaseOK func(ns, name, digest string) (bool, error)                          // ready && digest match
	Bundle    func(ns, release, digest string) (*Bundle, error)
	Reserve   func(ctx context.Context, session, agentID, backend, decision string, b *Bundle) (int, error) // ErrBudget when it does not fit
	HasGrant  func(ctx context.Context, session string) (bool, error)
	Principal func(ctx context.Context, session string) (string, error)
	Exchange  func(ctx context.Context, mode, session, backend, resource, actor string, pod *corev1.Pod) (string, error)
}

type Server struct {
	authv3.UnimplementedAuthorizationServer
	d Deps
}

func (s *Server) Check(ctx context.Context, req *authv3.CheckRequest) (*authv3.CheckResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, 1800*time.Millisecond) // under the gateway's 2 s
	defer cancel()
	decision := uuid.NewString()
	res := s.decide(ctx, req, decision)
	logDecision(decision, req, res) // section 13 fields; never a token value
	return res.toProto(decision), nil
}

type result struct {
	reason    string
	claims    *AgentClaims
	pod       *corev1.Pod
	bundle    *Bundle
	route     string
	reserved  int
	upstream  string // Authorization value for MCP; empty for inference
	principal string
}

// attested reports whether the node attestor has recorded host-side policy for
// this pod within attestationMaxAge (annotation value "<RFC3339>;<chain>").
func attested(pod *corev1.Pod, now time.Time) bool {
	v := pod.GetAnnotations()["agentplatform.io/netpol-attested"]
	ts, _, _ := strings.Cut(v, ";")
	t, err := time.Parse(time.RFC3339, ts)
	return err == nil && now.Sub(t) <= attestationMaxAge
}

func (s *Server) decide(ctx context.Context, req *authv3.CheckRequest, decision string) (r result) {
	defer func() {
		if rec := recover(); rec != nil {
			r = result{reason: "deny.internal"}
		}
	}()
	http := req.GetAttributes().GetRequest().GetHttp()
	ext := req.GetAttributes().GetContextExtensions()
	route, backend := ext["route"], ext["backend"]
	r.route = route

	// 1. token
	bearer := strings.TrimPrefix(http.GetHeaders()["authorization"], "Bearer ")
	if bearer == "" {
		return result{reason: "deny.token_invalid"}
	}
	claims, err := s.d.Verify(ctx, bearer)
	if err != nil {
		return result{reason: "deny.token_invalid"}
	}
	if claims.ClientType != "agent" || claims.AgentID == "" || claims.Tenant == "" || claims.JTI == "" {
		return result{reason: "deny.token_not_agent", claims: claims}
	}
	r.claims = claims

	// 2. pod by source address
	ip := req.GetAttributes().GetSource().GetAddress().GetSocketAddress().GetAddress()
	pod, n := s.d.PodByIP(ip)
	if n != 1 || pod == nil {
		r.reason = "deny.pod_unknown"
		return
	}
	r.pod = pod
	labels := pod.GetLabels()

	// 3. pod and token agree on agent and tenant
	agentName := claims.AgentID[strings.LastIndex(claims.AgentID, "/")+1:]
	if labels["agentplatform.io/agent"] != agentName || pod.GetNamespace() != claims.Tenant {
		r.reason = "deny.pod_agent_mismatch"
		return
	}

	// 4. the token is pinned to the pod it was issued for
	if ok, err := s.d.PinOK(ctx, claims.JTI, string(pod.GetUID()), claims.Exp); err != nil {
		r.reason = "deny.internal"
		return
	} else if !ok {
		r.reason = "deny.token_bound_elsewhere"
		return
	}

	// 5. liveness, including continuous host-side attestation
	session := labels["agentplatform.io/session"]
	stopped, err := s.d.Stopped(ctx, session)
	if err != nil {
		r.reason = "deny.internal"
		return
	}
	if pod.Status.Phase != corev1.PodRunning || pod.GetDeletionTimestamp() != nil || stopped || !attested(pod, time.Now()) {
		r.reason = "deny.session_inactive"
		return
	}

	// 6. generation fence
	gen, _ := strconv.Atoi(labels["agentplatform.io/generation"])
	active, known, err := s.d.ActiveGen(ctx, session)
	if err != nil {
		r.reason = "deny.internal"
		return
	}
	if !known || gen != active {
		r.reason = "deny.generation_stale"
		return
	}

	// 7. release
	release := labels["agentplatform.io/release"]
	digest := pod.GetAnnotations()["agentplatform.io/policy-digest"]
	if ok, err := s.d.ReleaseOK(pod.GetNamespace(), release, digest); err != nil || !ok {
		r.reason = "deny.release_unapproved"
		return
	}
	bundle, err := s.d.Bundle(pod.GetNamespace(), release, digest)
	if err != nil {
		r.reason = "deny.internal"
		return
	}
	r.bundle = bundle

	// 8 to 11. route, operation, budget, credential
	switch route {
	case "inference":
		if _, ok := bundle.Models[backend]; !ok {
			r.reason = "deny.route_not_permitted"
			return
		}
		reserved, err := s.d.Reserve(ctx, session, claims.AgentID, backend, decision, bundle)
		if errors.Is(err, ErrBudget) {
			r.reason = "deny.budget_exhausted"
			return
		}
		if err != nil {
			r.reason = "deny.internal"
			return
		}
		r.reserved = reserved
		r.reason = "allow" // no upstream credential: the gateway's backend policy injects the model key
		return
	case "mcp":
		m, ok := bundle.MCP[backend]
		if !ok {
			r.reason = "deny.route_not_permitted"
			return
		}
		body := http.GetBody()
		var rpc struct {
			Method string `json:"method"`
			Params struct {
				Name string `json:"name"`
			} `json:"params"`
		}
		if len(body) > 0 && json.Unmarshal([]byte(body), &rpc) != nil {
			r.reason = "deny.route_not_permitted"
			return
		}
		switch {
		case rpc.Method == "tools/call":
			if !contains(m.Tools, rpc.Params.Name) {
				r.reason = "deny.route_not_permitted"
				return
			}
		case rpc.Method == "initialize", rpc.Method == "tools/list", rpc.Method == "ping",
			strings.HasPrefix(rpc.Method, "notifications/"),
			len(body) == 0 && (http.GetMethod() == "GET" || http.GetMethod() == "DELETE"):
		default:
			r.reason = "deny.route_not_permitted"
			return
		}
		mode := m.Delegation
		if mode == "on-behalf-of" {
			has, err := s.d.HasGrant(ctx, session)
			if err != nil {
				r.reason = "deny.internal"
				return
			}
			if !has {
				if bundle.Identity.Fallback != "agent" {
					r.reason = "deny.delegation_required"
					return
				}
				mode = "agent"
			}
		}
		// Delegated mode authenticates as the agent client with a TokenRequest-minted
		// assertion bound to this pod and uses claims.Raw as actor_token (7.5, 9.5).
		tok, err := s.d.Exchange(ctx, mode, session, backend, m.Resource, claims.Raw, pod)
		if err != nil {
			r.reason = "deny.exchange_failed"
			return
		}
		r.upstream = "Bearer " + tok
		if mode == "on-behalf-of" {
			r.principal, _ = s.d.Principal(ctx, session)
		}
		r.reason = "allow"
		return
	default:
		r.reason = "deny.route_not_permitted"
		return
	}
}

func (r result) toProto(decision string) *authv3.CheckResponse {
	meta := map[string]any{"decision_id": decision, "reason": r.reason}
	set := map[string]string{"x-agent-decision-id": decision}
	if r.claims != nil {
		meta["agent_id"], meta["tenant"], meta["spiffe_id"] = r.claims.AgentID, r.claims.Tenant, r.claims.SpiffeID
		set["x-agent-id"], set["x-agent-tenant"], set["x-agent-spiffe-id"] = r.claims.AgentID, r.claims.Tenant, r.claims.SpiffeID
	}
	if r.pod != nil {
		l := r.pod.GetLabels()
		meta["session_id"], meta["generation"], meta["release"] = l["agentplatform.io/session"], l["agentplatform.io/generation"], l["agentplatform.io/release"]
		meta["policy_digest"] = r.pod.GetAnnotations()["agentplatform.io/policy-digest"]
		set["x-agent-session-id"], set["x-agent-generation"], set["x-agent-release"] = l["agentplatform.io/session"], l["agentplatform.io/generation"], l["agentplatform.io/release"]
		set["x-agent-policy"] = r.pod.GetAnnotations()["agentplatform.io/policy-digest"]
	}
	if r.bundle != nil {
		meta["tokens_per_session"] = r.bundle.Budgets.TokensPerSession
	}
	if r.reserved > 0 {
		meta["reserved_tokens"] = r.reserved
	}
	if r.principal != "" {
		meta["principal"] = r.principal
		set["x-agent-principal"] = r.principal
	}
	dyn, _ := structpb.NewStruct(meta)

	if r.reason != "allow" {
		body, _ := json.Marshal(map[string]string{"error": "forbidden", "reason": r.reason, "decision_id": decision})
		code, hdrs := typev3.StatusCode_Forbidden, []*corev3.HeaderValueOption{
			hdr("x-agent-decision-reason", r.reason), hdr("content-type", "application/json")}
		if r.reason == "deny.budget_exhausted" {
			code = typev3.StatusCode_TooManyRequests
			hdrs = append(hdrs, hdr("retry-after", "60"))
		}
		return &authv3.CheckResponse{
			Status: &status.Status{Code: int32(codes.PermissionDenied), Message: r.reason},
			HttpResponse: &authv3.CheckResponse_DeniedResponse{DeniedResponse: &authv3.DeniedHttpResponse{
				Status: &typev3.HttpStatus{Code: code}, Headers: hdrs, Body: string(body),
			}},
			DynamicMetadata: dyn,
		}
	}
	var hdrs []*corev3.HeaderValueOption
	var remove []string
	for _, name := range agentHeaders {
		if v, ok := set[name]; ok {
			hdrs = append(hdrs, hdr(name, v))
		} else {
			remove = append(remove, name) // client-supplied values never survive
		}
	}
	if r.upstream != "" {
		hdrs = append(hdrs, hdr("authorization", r.upstream)) // MCP: the exchanged token
	} else {
		remove = append(remove, "authorization") // inference: the backend policy adds the model key
	}
	return &authv3.CheckResponse{
		Status: &status.Status{Code: int32(codes.OK)},
		HttpResponse: &authv3.CheckResponse_OkResponse{OkResponse: &authv3.OkHttpResponse{
			Headers: hdrs, HeadersToRemove: remove,
		}},
		DynamicMetadata: dyn,
	}
}

func hdr(k, v string) *corev3.HeaderValueOption {
	return &corev3.HeaderValueOption{
		Header:       &corev3.HeaderValue{Key: k, Value: v},
		AppendAction: corev3.HeaderValueOption_OVERWRITE_IF_EXISTS_OR_ADD,
	}
}

func contains(xs []string, x string) bool {
	for _, v := range xs {
		if v == x {
			return true
		}
	}
	return false
}

func main() {
	d := buildDeps() // informers, JWKS verifier, Redis ledger, vault, exchanger adapter; see 9.4 to 9.7
	lis, err := net.Listen("tcp", ":9001")
	if err != nil {
		panic(err)
	}
	srv := grpc.NewServer()
	authv3.RegisterAuthorizationServer(srv, &Server{d: d})
	go serveHTTP(d)      // :9002 token, grants and sessions; :8081 health; :9090 metrics
	go serveSettlement(d) // :4317 OTLP receiver for the gateway access-log stream
	if err := srv.Serve(lis); err != nil {
		panic(err)
	}
}
```

The exchange dependency wraps the requests of 9.5 with a per-(session, backend) single-flight lock, so concurrent calls from one sandbox produce one IdP request.

## 10. Session lifecycle

A session is one Temporal workflow that creates exactly one live sandbox generation at a time, drives the agent one boundary per activity, snapshots the workspace after every boundary, and always ends by confirming the sandbox is gone.

### 10.1 States

| State | Entered when | Leaves to |
| --- | --- | --- |
| `SUBMITTED` | workflow started | `PROVISIONING` |
| `PROVISIONING` | the generation is fenced at the APS and the create activity acknowledged | `READY`, or `FAILED` |
| `READY` | pod Running (the egress-guard init container exited 0) | `RUNNING` |
| `RUNNING` | first boundary started | `COMPLETED`, `FAILED`, `TIMED_OUT`, `CANCELLED`, or `PROVISIONING` (replacement after confirmed deletion) |
| `COMPLETED` / `FAILED` / `TIMED_OUT` / `CANCELLED` | terminal agent outcome, boundary limit, the 8 h timer, or cancellation | `CLEANING` |
| `CLEANING` | stop, delete and grant deletion all started, independently | `CLEANED` or `NOT_CONFIRMED` |
| `CLEANED` | all three cleanup steps succeeded | end |
| `NOT_CONFIRMED` | any cleanup step did not succeed, or an old generation's deletion could not be confirmed | end; the reconciler (10.7) converges it |

Three contracts govern recovery:

- **One live generation.** Before a generation is created the Session Runner records it as the session's active generation at the APS (9.7); from that moment every older pod is denied with `deny.generation_stale` even if it still exists. A replacement is created only after the previous generation's deletion is **confirmed**; `NOT_CONFIRMED` ends the session instead of replacing, and the reconciler finishes the deletion later.
- **Committed means durable.** A boundary is committed only when its result and the workspace snapshot that follows it are both in durable storage and recorded in Temporal history. Until then it is one of: *not executed* (the exec never started: safe to run), *executed but not acknowledged* (the guest may have done work: re-run from the last committed snapshot, which is safe only because every admitted effect is read-only outside the sandbox, and which costs a repeated read), or *committed*. If `remote_write` is ever admitted, the second case must end the session with `OUTCOME_UNKNOWN` instead of re-running.
- **Cleanup always converges.** The three cleanup steps run independently and record their outcomes; a failed step never prevents the others; a scheduled reconciler repeats unfinished steps every 5 minutes, which also covers workflows that were terminated (Temporal's terminate skips workflow code) and runner crashes.

A replacement happens at most twice per session (three generations).

### 10.2 Workflow identity and input

| Item | Value |
| --- | --- |
| Workflow type | `SessionWorkflow` |
| Workflow ID | `session:<tenant>:<agent>:<session_id>`; reuse policy `REJECT_DUPLICATE`, so a resubmission with the same session ID is a no-op that returns the original handle |
| Task queue | `sessions-<tenant>` |
| Input | `{tenant, agent, release, session_id, grant_handle (string or null), task (JSON, at most 64 KiB), max_boundaries (default 64)}` |
| Never in input | any token, any credential, any Kubernetes object |
| Execution timeout | 8 h; run timeout 8 h; task timeout 10 s |

### 10.3 Activities

| Activity | Idempotency | Timeouts | Retry |
| --- | --- | --- | --- |
| `preflight` | pure read | 60 s | 3 attempts |
| `set_generation(generation)` | `PUT /v1/sessions/{id}/generation`; strictly increasing, repeat of the same value is accepted | 30 s | 5 attempts |
| `create_sandbox(generation)` | deterministic pod name; `409 AlreadyExists` is followed by a read that must show the same session, generation and release labels, otherwise `IdentityConflict` (non-retryable) | schedule-to-close 600 s | transient API errors only |
| `wait_ready(generation)` | pure read; restores the last committed snapshot into the new pod when there is one | 180 s per attempt | 3 attempts |
| `run_boundary(generation, n)` | exec of exactly one boundary with length-prefixed input and bounded, schema-checked output | start-to-close 300 s, heartbeat 30 s | exactly 1 attempt |
| `snapshot_workspace(generation, n)` | content-addressed upload (SHA-256 of the tar); the boundary is committed only after this returns | 120 s | 3 attempts |
| `stop_session` | `POST /v1/sessions/{id}/stop`, idempotent | 30 s | 5 attempts |
| `delete_sandbox(generation)` | delete then poll until 404 | 600 s window, 2 min per attempt | transient errors; `NOT_CONFIRMED` is a value, not an error |
| `delete_grant` | `DELETE /v1/grants/{handle}`, idempotent (404 is success) | 30 s | 5 attempts |

All activities are synchronous functions executed in the worker's thread pool (the Kubernetes client and the exec websocket are blocking; running them inside `async def` activities would block the worker's event loop).

`preflight` fails the session before anything is created when: the `AgentRelease` is not ready; the tenant namespace's effective NetworkPolicy set is not exactly the four policies of section 5.3 with the controller's published digest; the release's `status.identityMode` is `on-behalf-of` with `status.delegationRequired` true and `grant_handle` is null or `GET /v1/grants/{handle}` does not return 200 for this session ID.

### 10.4 Boundary protocol between runner and sandbox

The runner execs this command for boundary `n` and passes a JSON document on stdin; the SDK prints exactly one JSON document on stdout and exits 0.

```
/app/.venv/bin/python -m agent_runtime.step
stdin:  <decimal byte length>\n<exactly that many bytes of UTF-8 JSON>
        {"boundary": 3, "task": {...}}
stdout: one JSON document, at most 65,536 bytes:
        {"boundary": 3, "kind": "model" | "tool", "done": false, "tool": "pods_get" | null,
         "usage": {"input_tokens": 812, "output_tokens": 95} | null, "summary": "<= 512 chars"}
```

The input is length-prefixed because the exec channel has no end-of-input signal the guest can rely on; the guest reads the header line, then exactly that many bytes, and never waits for EOF. The runner treats the guest's output as an untrusted protocol message: it reads at most 64 KiB (more is `OutcomeUnknown`), parses it against the schema above, and requires `boundary` to equal the requested number and `done` to agree with the exit code. Exit codes: 0 success; 2 completion (`done: true` required); 3 agent error (terminal); 4 the guest's advisory budget exceeded (terminal); anything else, no output, or inconsistent output is an unknown outcome. The SDK writes `/sandbox/state/<n>.started` before any model or tool call and `/sandbox/state/<n>.done` after persisting the result; the runner reads neither except for diagnostics.

### 10.5 Reference implementation (Python, Temporal SDK)

```python
# runner/workflow.py
from __future__ import annotations
import asyncio
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from runner import activities as act
    from runner.types import SessionInput, SessionResult, BoundaryOut

ONE_ATTEMPT = RetryPolicy(maximum_attempts=1)
TRANSIENT = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=30),
                        non_retryable_error_types=["IdentityConflict", "Forbidden", "NotFound"])
FEW = RetryPolicy(maximum_attempts=5)
BUSINESS_DEADLINE = timedelta(hours=8)     # the execution timeout is 8 h 15 min; the difference is reserved for cleanup
MAX_GENERATIONS = 3

async def _value(v: str) -> str:
    return v

@workflow.defn
class SessionWorkflow:
    def __init__(self) -> None:
        self.generation = 0
        self.committed: list[BoundaryOut] = []   # a boundary is committed only once its snapshot is durable
        self.snapshot: str | None = None
        self.state = "SUBMITTED"
        self.cleanup: dict[str, str] = {}

    @workflow.query
    def status(self) -> dict:
        return {"state": self.state, "generation": self.generation,
                "boundaries": len(self.committed), "cleanup": self.cleanup}

    @workflow.run
    async def run(self, inp: SessionInput) -> SessionResult:
        outcome = "FAILED"
        try:
            # asyncio.wait_for is deterministic in Temporal workflows: it is backed by a timer.
            outcome = await asyncio.wait_for(self._session(inp), timeout=BUSINESS_DEADLINE.total_seconds())
        except asyncio.TimeoutError:
            outcome = "TIMED_OUT"
        except asyncio.CancelledError:
            outcome = "CANCELLED"
            await self._cleanup(inp)            # shielded inside; runs to completion
            raise                               # the workflow then closes as cancelled
        except ApplicationError as e:
            outcome = "NOT_CONFIRMED" if e.type == "DeletionNotConfirmed" else "FAILED"
        except ActivityError:
            outcome = "FAILED"
        await self._cleanup(inp)
        return SessionResult(outcome=outcome, cleanup=self.cleanup, generation=self.generation,
                             boundaries=len(self.committed), snapshot=self.snapshot)

    async def _session(self, inp: SessionInput) -> str:
        await workflow.execute_activity(act.preflight, inp, start_to_close_timeout=timedelta(seconds=60),
                                        retry_policy=RetryPolicy(maximum_attempts=3))
        await self._provision(inp)
        boundary = 0
        while boundary < inp.max_boundaries:
            self.state = "RUNNING"
            try:
                out: BoundaryOut = await workflow.execute_activity(
                    act.run_boundary, act.BoundaryIn(inp, self.generation, boundary),
                    start_to_close_timeout=timedelta(seconds=300), heartbeat_timeout=timedelta(seconds=30),
                    retry_policy=ONE_ATTEMPT)
                snapshot = await workflow.execute_activity(
                    act.snapshot_workspace, act.SnapshotIn(inp, self.generation, boundary),
                    start_to_close_timeout=timedelta(seconds=120), retry_policy=RetryPolicy(maximum_attempts=3))
            except ActivityError as e:
                if not _replaceable(e) or self.generation >= MAX_GENERATIONS:
                    raise
                # Not committed. Effects are read-only outside the sandbox, so the boundary is
                # re-run on a fresh generation restored from the last committed snapshot.
                await self._replace(inp)
                continue
            self.snapshot = snapshot
            self.committed.append(out)          # committed: result and checkpoint are both durable
            if out.done:
                return "COMPLETED"
            boundary += 1
        return "FAILED"                          # boundary limit reached

    async def _provision(self, inp: SessionInput) -> None:
        self.generation += 1
        self.state = "PROVISIONING"
        # Fence first: from now on only this generation is authorized, even if an older pod lingers.
        await workflow.execute_activity(act.set_generation, act.GenIn(inp, self.generation, None),
                                        start_to_close_timeout=timedelta(seconds=30), retry_policy=FEW)
        await workflow.execute_activity(act.create_sandbox, act.GenIn(inp, self.generation, self.snapshot),
                                        schedule_to_close_timeout=timedelta(seconds=600), retry_policy=TRANSIENT)
        await workflow.execute_activity(act.wait_ready, act.GenIn(inp, self.generation, self.snapshot),
                                        start_to_close_timeout=timedelta(seconds=180),
                                        retry_policy=RetryPolicy(maximum_attempts=3))
        self.state = "READY"

    async def _replace(self, inp: SessionInput) -> None:
        if await self._delete(inp, self.generation) != "DELETED":
            raise ApplicationError("previous generation not confirmed deleted",
                                   type="DeletionNotConfirmed", non_retryable=True)
        await self._provision(inp)

    async def _delete(self, inp: SessionInput, generation: int) -> str:
        return await asyncio.shield(workflow.execute_activity(
            act.delete_sandbox, act.GenIn(inp, generation, None),
            schedule_to_close_timeout=timedelta(seconds=600), start_to_close_timeout=timedelta(seconds=120),
            retry_policy=TRANSIENT))

    async def _cleanup(self, inp: SessionInput) -> None:
        """Every step runs regardless of the others; outcomes are recorded, never raised."""
        self.state = "CLEANING"
        steps = {
            "stop": workflow.execute_activity(act.stop_session, inp,
                                              start_to_close_timeout=timedelta(seconds=30), retry_policy=FEW),
            "delete": self._delete(inp, self.generation) if self.generation else _value("DELETED"),
            "grant": workflow.execute_activity(act.delete_grant, inp,
                                               start_to_close_timeout=timedelta(seconds=30), retry_policy=FEW)
                     if inp.grant_handle else _value("OK"),
        }
        results = await asyncio.shield(asyncio.gather(*steps.values(), return_exceptions=True))
        for name, res in zip(steps, results):
            self.cleanup[name] = f"FAILED:{type(res).__name__}" if isinstance(res, BaseException) else str(res)
        self.state = "CLEANED" if all(v in ("OK", "DELETED") for v in self.cleanup.values()) else "NOT_CONFIRMED"

def _replaceable(e: ActivityError) -> bool:
    cause = e.cause
    return isinstance(cause, ApplicationError) and cause.type in {"SandboxLost", "ExecFailed", "OutcomeUnknown", "SnapshotFailed"}
```

Cancellation reaches the workflow as `asyncio.CancelledError`; the cleanup steps are gathered under `asyncio.shield` so the Temporal SDK does not cancel them, and each step's outcome is recorded in `cleanup` whatever the others did. The business deadline is a workflow timer (`asyncio.wait_for`), so a session that runs out of time still gets its cleanup inside the execution timeout. `NOT_CONFIRMED` is a result, not an error; the reconciler (10.7) converges it, which also covers the one case workflow code cannot handle: a workflow that an operator terminates rather than cancels.

```python
# runner/activities.py  (synchronous activities; the worker runs them in a thread pool)
from __future__ import annotations
import hashlib, json, time, yaml
from dataclasses import dataclass
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.stream import stream
from temporalio import activity
from temporalio.exceptions import ApplicationError
from runner.types import SessionInput, BoundaryOut
from runner.aps import aps_get, aps_put, aps_post, aps_delete   # HTTP with the runner's projected token

config.load_incluster_config()
CORE = client.CoreV1Api()
NET = client.NetworkingV1Api()
CUSTOM = client.CustomObjectsApi()
LABEL = "agentplatform.io/"
EXPECTED_POLICIES = {"default-deny-all", "sandbox-egress-gateway-only", "sandbox-ingress-none", "tenant-no-other-egress"}
MAX_OUTPUT = 65536

@dataclass
class GenIn:
    inp: SessionInput
    generation: int
    restore: str | None

@dataclass
class BoundaryIn:
    inp: SessionInput
    generation: int
    boundary: int

def pod_name(session_id: str, generation: int) -> str:
    return f"s-{hashlib.sha256(session_id.encode()).hexdigest()[:16]}-g{generation}"

def canonical_policy(p) -> str:
    spec = client.ApiClient().sanitize_for_serialization(p.spec)
    return json.dumps(spec, sort_keys=True, separators=(",", ":"))

@activity.defn
def preflight(inp: SessionInput) -> None:
    ns = inp.tenant
    rel = CUSTOM.get_namespaced_custom_object("agentplatform.io", "v1alpha1", ns, "agentreleases", inp.release)
    status = rel.get("status", {})
    if not status.get("ready"):
        raise ApplicationError("release not ready", type="Forbidden", non_retryable=True)
    pols = {p.metadata.name: canonical_policy(p) for p in NET.list_namespaced_network_policy(ns).items}
    want = CORE.read_namespace(ns).metadata.annotations.get(LABEL + "netpol-digest")
    have = hashlib.sha256(json.dumps(pols, sort_keys=True).encode()).hexdigest()
    if set(pols) != EXPECTED_POLICIES or want != f"sha256:{have}":
        raise ApplicationError("effective NetworkPolicy set differs from the controller's", type="Forbidden", non_retryable=True)
    if status.get("identityMode") == "on-behalf-of" and status.get("delegationRequired", True):
        grant = aps_get(f"/v1/grants/{inp.grant_handle}") if inp.grant_handle else None
        if not grant or grant.get("session_id") != inp.session_id:
            raise ApplicationError("delegated session without a grant", type="Forbidden", non_retryable=True)

@activity.defn
def set_generation(g: GenIn) -> None:
    aps_put(f"/v1/sessions/{g.inp.session_id}/generation", {"generation": g.generation})

@activity.defn
def create_sandbox(g: GenIn) -> str:
    ns, name = g.inp.tenant, pod_name(g.inp.session_id, g.generation)
    pod = yaml.safe_load(CORE.read_namespaced_config_map(f"podtemplate-{g.inp.release}", ns).data["pod.yaml"])
    pod["metadata"]["name"] = name
    pod["metadata"]["labels"][LABEL + "session"] = g.inp.session_id
    pod["metadata"]["labels"][LABEL + "generation"] = str(g.generation)
    for c in pod["spec"]["containers"]:
        c.setdefault("env", []).append({"name": "AGENT_SESSION_ID", "value": g.inp.session_id})
    try:
        created = CORE.create_namespaced_pod(ns, pod)
    except ApiException as e:
        if e.status != 409:
            raise
        created = CORE.read_namespaced_pod(name, ns)
    want = {LABEL + "session": g.inp.session_id, LABEL + "generation": str(g.generation), LABEL + "release": g.inp.release}
    if {k: created.metadata.labels.get(k) for k in want} != want:
        raise ApplicationError("existing pod belongs to another session", type="IdentityConflict", non_retryable=True)
    return created.metadata.uid

@activity.defn
def wait_ready(g: GenIn) -> None:
    ns, name = g.inp.tenant, pod_name(g.inp.session_id, g.generation)
    deadline = time.monotonic() + 170
    while time.monotonic() < deadline:
        activity.heartbeat()
        pod = CORE.read_namespaced_pod(name, ns)
        if pod.status.phase in ("Failed", "Succeeded"):
            raise ApplicationError("sandbox exited before ready (egress guard or image failure)", type="SandboxLost", non_retryable=True)
        if pod.status.phase == "Running":        # Running implies every init container exited 0
            if g.restore:
                _restore(ns, name, g.restore)
            return
        time.sleep(2)
    raise ApplicationError("sandbox not ready", type="SandboxLost")

@activity.defn
def run_boundary(b: BoundaryIn) -> BoundaryOut:
    ns, name = b.inp.tenant, pod_name(b.inp.session_id, b.generation)
    payload = json.dumps({"boundary": b.boundary, "task": b.inp.task}).encode("utf-8")
    if len(payload) > MAX_OUTPUT:
        raise ApplicationError("task too large", type="Forbidden", non_retryable=True)
    frame = f"{len(payload)}\n".encode() + payload       # length-prefixed: the guest never waits for EOF
    try:
        res = _exec(ns, name, ["/app/.venv/bin/python", "-m", "agent_runtime.step"], stdin=frame,
                    heartbeat=activity.heartbeat, max_output=MAX_OUTPUT)
    except ApiException:
        raise ApplicationError("exec could not start", type="SandboxLost")
    if res.truncated or res.rc not in (0, 2, 3, 4) or not res.stdout.strip():
        raise ApplicationError(f"rc={res.rc} truncated={res.truncated}", type="OutcomeUnknown")
    try:
        out = BoundaryOut.parse_strict(json.loads(res.stdout))   # rejects unknown fields and wrong types
    except Exception:
        raise ApplicationError("malformed boundary output", type="OutcomeUnknown")
    if out.boundary != b.boundary or out.done != (res.rc == 2):
        raise ApplicationError("inconsistent boundary output", type="OutcomeUnknown")
    if res.rc == 3:
        raise ApplicationError(out.summary[:512], type="AgentError", non_retryable=True)
    if res.rc == 4:
        raise ApplicationError("guest reported budget exceeded", type="BudgetExceeded", non_retryable=True)
    return out

@activity.defn
def delete_sandbox(g: GenIn) -> str:
    ns, name = g.inp.tenant, pod_name(g.inp.session_id, g.generation)
    try:
        CORE.delete_namespaced_pod(name, ns, grace_period_seconds=30)
    except ApiException as e:
        if e.status != 404:
            raise
    deadline = time.monotonic() + 110
    while time.monotonic() < deadline:
        activity.heartbeat()
        try:
            CORE.read_namespaced_pod(name, ns)
        except ApiException as e:
            if e.status == 404:
                return "DELETED"
            raise
        time.sleep(2)
    return "NOT_CONFIRMED"

@activity.defn
def stop_session(inp: SessionInput) -> str:
    aps_post(f"/v1/sessions/{inp.session_id}/stop", {})
    return "OK"

@activity.defn
def delete_grant(inp: SessionInput) -> str:
    aps_delete(f"/v1/grants/{inp.grant_handle}")          # 404 is success
    return "OK"

@dataclass
class ExecResult:
    rc: int
    stdout: str
    stderr: str
    truncated: bool

def _exec(ns: str, name: str, cmd: list[str], stdin: bytes | None = None, heartbeat=None,
          max_output: int = MAX_OUTPUT) -> ExecResult:
    ws = stream(CORE.connect_get_namespaced_pod_exec, name, ns, command=cmd, container="agent",
                stdin=stdin is not None, stdout=True, stderr=True, tty=False, _preload_content=False)
    if stdin is not None:
        ws.write_stdin(stdin.decode("utf-8"))
    out, err, size, truncated = [], [], 0, False
    while ws.is_open():
        ws.update(timeout=5)
        if heartbeat:
            heartbeat()
        if ws.peek_stdout():
            chunk = ws.read_stdout()
            size += len(chunk.encode("utf-8"))
            if size > max_output:
                truncated = True          # keep draining so the exit code is observed, but keep nothing more
            else:
                out.append(chunk)
        if ws.peek_stderr():
            err.append(ws.read_stderr()[:4096])
    rc = ws.returncode if ws.returncode is not None else -1
    ws.close()
    return ExecResult(rc, "".join(out), "".join(err)[:4096], truncated)
```

`snapshot_workspace` tars `/sandbox/workspace` and `/sandbox/state` through `_exec` (bounded at 64 MiB; a larger workspace is `SnapshotFailed`), uploads to the artifact store keyed by SHA-256, and returns the key; `_restore` streams the tar back through an exec of `tar -x`. The APS helpers send the runner's projected token (`audience: agent-policy-service`) and treat 5xx as retryable, 4xx as `Forbidden`. Nothing here is `async`: the worker is started with `activity_executor=ThreadPoolExecutor(max_workers=16)` and `max_concurrent_activities=16`.

### 10.6 Runner deployment

| Item | Value |
| --- | --- |
| Deployment | `session-runner-<tenant>` in `agent-platform`, label `app.kubernetes.io/name: session-runner`, 1 or more replicas, graceful shutdown 60 s |
| ServiceAccount | `session-runner` with a projected token volume (`audience: agent-policy-service`, 600 s) for APS calls, plus the default token for the API server |
| RBAC | the Registry Controller creates, in every tenant namespace, a Role `session-runner` with: `pods` create, get, list, watch, delete; `pods/exec` get and create (the Python client upgrades a GET; `kubectl` uses POST); `configmaps` get (Kubernetes RBAC has no name-prefix match, so the whole verb is granted in the tenant namespace, where only platform ConfigMaps exist); `agentreleases` get; `networkpolicies` list; `namespaces` get on the tenant namespace, and a RoleBinding to `agent-platform:session-runner`. No other principal holds `pods` create in a tenant namespace. |
| Temporal | mTLS to the Temporal frontend, namespace `agents-<tenant>`, worker versioning enabled so a runner upgrade never replays an incompatible history; payload codec with AES-GCM so task content and summaries are encrypted in history (13.9) |
| Artifact store | S3-compatible bucket `agent-artifacts-<tenant>`, write-once objects named by SHA-256, server-side encryption |
| Worker | `Worker(client, task_queue=f"sessions-{tenant}", workflows=[SessionWorkflow], activities=[...], activity_executor=ThreadPoolExecutor(16), max_concurrent_activities=16)` |

The runner never holds the IdP client secret, the vault key or any upstream credential; its only credentials are its own Kubernetes tokens and the Temporal client certificate.

### 10.7 Cleanup reconciler

A Temporal Schedule in each tenant namespace runs `CleanupReconcilerWorkflow` every 5 minutes with overlap policy `skip`. It:

1. Lists pods with `agentplatform.io/sandbox=true` in the tenant namespace. For each, reads the session label and queries the session workflow: if the workflow is closed (completed, failed, cancelled, terminated or timed out), or the pod's generation is below the active generation recorded at the APS, the pod is an orphan: delete it, confirm 404, record `cleanup_result` with `source: reconciler`.
2. Lists sessions the APS still holds grants or active generations for (`GET /v1/sessions?older_than=15m`), queries each workflow, and calls `stop` and `DELETE /v1/grants/{handle}` for every closed one.
3. Emits `agent_cleanup_reconciled_total` and alerts (13.8) when the same orphan survives two runs.

The reconciler's ServiceAccount is `cleanup-reconciler` in `agent-platform` with the same Role as the runner minus `pods` create and `pods/exec`; the APS accepts it for `stop` and grant deletion only.

### 10.8 Remote writes: the contract required before any is admitted

Neither Temporal history nor workspace snapshots can tell whether an external write happened when the sandbox died mid-call; only the backend can, and only if the write carried a key it can be asked about. This profile admits no `remote_write` tool. When one is needed (tickets, infrastructure changes, business records), it is admitted per backend under exactly this contract, and T31 proves it before the first such tool ships.

| Element | Requirement |
| --- | --- |
| Backend declaration | the MCP backend's registry entry declares `idempotentWrites: true`, the argument name its write tools accept as the idempotency key (`idempotencyKey`), and for each write tool a paired read-by-key tool (`<tool>_status`) that returns the record created for a key or `not_found` |
| Key derivation | the SDK derives \`key = sha256(session\_id |
| APS admission | for a `tools/call` of a write tool the APS requires the header, records `{key, session, boundary, tool, decision_id}` in Redis **before** allowing, refuses a key already recorded for a different (session, boundary), and refuses writes from any generation that is not the first to record that key |
| Commit | the boundary's snapshot must contain the backend's receipt (the record identifier the tool returned); without it the boundary is not committed |
| Unknown outcome | the runner never re-runs a write boundary. On `OutcomeUnknown` it provisions a new generation (fenced as usual) and runs the paired `<tool>_status` with the same key as a `remote_read`: `found` makes the receipt the boundary's result and commits it; `not_found` allows exactly one re-issue with the same key (the backend's own idempotency makes a late duplicate harmless); a third ambiguous answer ends the session as `OUTCOME_UNKNOWN` for operator reconciliation |
| Reconciliation | the reconciler compares recorded keys older than one hour with backend records through the status tool and reports mismatches; backends that cannot be queried by key are not admitted for writes |
| What this still does not give | exactly-once execution. It gives at-most-once-per-key at the backend, exactly-once recording in history, and a bounded, auditable procedure for the gap between them |

Cost of the boundary design, measured rather than argued: starting a process, reusing the persisted token and archiving the workspace at every boundary is paid once per boundary and reported by T29 (Phase A targets: boundary overhead p95 under 2 s, snapshot under 5 s for 64 MiB). If the measurements fail the targets, the Phase D evaluation includes a persistent-process mode in which the agent process survives across boundaries and checkpoints state deltas under the same commit contract; nothing trusted changes in that mode, only the SDK and the runner's exec sequencing.

## 11. Sandbox runtime SDK

The SDK is the only code in the sandbox that touches a token: it turns the projected token into an agent access token through the gateway, puts that token on every model and MCP request, and runs exactly one boundary per invocation.

### 11.1 Package layout

| Module | Purpose |
| --- | --- |
| `agent_runtime/wait.py` | entrypoint: egress probe, then block (section 5.5) |
| `agent_runtime/identity.py` | client assertion and access token cache |
| `agent_runtime/gateway.py` | one `httpx` client per route host with the bearer auth and the fixed `Host` header |
| `agent_runtime/models.py` | OpenAI-compatible chat client bound to the inference route |
| `agent_runtime/mcp.py` | MCP client bound to the MCP route |
| `agent_runtime/tools.py` | tool registration with effect classes |
| `agent_runtime/step.py` | one boundary: load state, call the model or one tool, persist state, print the result |
| `agent_runtime/confine.py` | Landlock rules applied before any agent code runs |
| `/app/agent.yaml` | the agent's manifest (11.7), baked into the image |

Dependencies, pinned in the image lock: `httpx` 0.27.x, `openai` 1.x, `mcp` 1.x (the official Python SDK; its streamable-HTTP transport yields three values and the import name below is the 1.x name), `pyyaml`, `landlock` (optional, 11.6). No Kubernetes client, no DNS resolver use, no raw sockets outside `httpx`.

### 11.2 Identity

```python
# agent_runtime/identity.py
import base64, json, os, pathlib, tempfile, time, threading
import httpx

GATEWAY = os.environ["AGENT_GATEWAY_URL"]            # https://10.43.250.10:443
CA = os.environ.get("AGENT_GATEWAY_CA")              # /etc/agent-platform/ca.crt
TOKEN_HOST = os.environ["AGENT_TOKEN_HOST"]          # token.agents.internal
TOKEN_PATH = os.environ["AGENT_TOKEN_ENDPOINT_PATH"] # /realms/agents/protocol/openid-connect/token
CLIENT_ID = os.environ["AGENT_CLIENT_ID"]            # agent-tenant-a-investigator
ASSERTION_FILE = os.environ["AGENT_TOKEN_PATH"]      # /var/run/secrets/agent-identity/token
TOKEN_CACHE = pathlib.Path("/sandbox/state/token.json")   # survives the per-boundary process; mode 0600
REFRESH_BEFORE = 120                                  # seconds

class AgentIdentity:
    """Holds the current agent access token; thread safe; refreshes before expiry; persists across boundaries."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token: str | None = None
        self._exp = 0.0
        self._http = httpx.Client(base_url=GATEWAY, verify=CA or True, timeout=10.0)

    def token(self) -> str:
        with self._lock:
            if self._token is None:
                self._load()
            if self._token is None or time.time() > self._exp - REFRESH_BEFORE:
                self._refresh()
            return self._token

    def invalidate(self) -> None:
        with self._lock:
            self._token = None
            TOKEN_CACHE.unlink(missing_ok=True)

    def _load(self) -> None:
        try:
            d = json.loads(TOKEN_CACHE.read_text())
            self._token, self._exp = d["access_token"], float(d["exp"])
        except (OSError, ValueError, KeyError):
            self._token = None

    def _refresh(self) -> None:
        assertion = open(ASSERTION_FILE, encoding="utf-8").read().strip()   # re-read: kubelet rotates it
        r = self._http.post(
            TOKEN_PATH,
            headers={"Host": TOKEN_HOST, "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": assertion,
                "scope": "agent-gateway",
            },
        )
        if r.status_code != 200:
            raise RuntimeError(f"token endpoint returned {r.status_code}: {r.json().get('error', '?')}")
        body = r.json()
        token = body["access_token"]
        exp = time.time() + int(body.get("expires_in", 300))
        claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        aud = claims.get("aud")
        if "agent-gateway" not in (aud if isinstance(aud, list) else [aud]):
            raise RuntimeError("issued token is not for the gateway")
        TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=TOKEN_CACHE.parent)
        with os.fdopen(fd, "w") as f:
            os.fchmod(fd, 0o600)
            json.dump({"access_token": token, "exp": exp}, f)
        os.replace(tmp, TOKEN_CACHE)
        self._token, self._exp = token, exp

class BearerAuth(httpx.Auth):
    """Sets Authorization on every request; on one 401 refreshes the token and retries once. 403 is never retried."""

    def __init__(self, identity: AgentIdentity) -> None:
        self.identity = identity

    def auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {self.identity.token()}"
        response = yield request
        if response.status_code == 401:
            self.identity.invalidate()
            request.headers["Authorization"] = f"Bearer {self.identity.token()}"
            yield request

IDENTITY = AgentIdentity()
```

The `scope` requested is `agent-gateway`; the identity provider adds the audiences through the client scope of that name (7.4). The token is persisted under `/sandbox/state` because every boundary is a fresh process; without that, a fast session would hit the token route once per boundary and its 60-per-minute limit. Error contract: a `401` from the gateway means the token expired or was rotated and is retried exactly once after a refresh; a `403` is a policy decision and is reported to the agent loop as a terminal tool or model error; a `429` is reported as a budget error. Nothing else is retried at this layer.

### 11.3 Gateway clients

```python
# agent_runtime/gateway.py
import os, httpx
from agent_runtime.identity import IDENTITY, BearerAuth, GATEWAY, CA

def client_for(host_env: str, timeout: float) -> httpx.Client:
    """An httpx client whose every request goes to the gateway over TLS with a fixed Host header."""
    return httpx.Client(
        base_url=GATEWAY,
        headers={"Host": os.environ[host_env], "User-Agent": "agent-runtime/1"},
        auth=BearerAuth(IDENTITY),
        verify=CA or True,                 # the internal CA; never False
        timeout=timeout,
        follow_redirects=False,            # a redirect would be an attempt to send the token elsewhere
        transport=httpx.HTTPTransport(retries=2),   # connection-level retries only
    )

INFERENCE = client_for("AGENT_INFERENCE_HOST", timeout=120.0)
```

### 11.4 Model client

```python
# agent_runtime/models.py
import os
from openai import OpenAI
from agent_runtime.gateway import INFERENCE, GATEWAY

def chat_client() -> OpenAI:
    # The model is selected by route, not by the body: AGENT_MODEL_ROUTE is /models/<backend> from the bundle.
    # api_key is a placeholder; BearerAuth on the shared httpx client overwrites Authorization.
    base = f"{GATEWAY}{os.environ['AGENT_MODEL_ROUTE']}/v1"
    return OpenAI(base_url=base, api_key="gateway-bearer", http_client=INFERENCE, max_retries=0)  # pragma: allowlist secret
```

Every request still sets `model` to the name from `agent.yaml`, because the OpenAI client requires one; the gateway ignores it for routing (the backend pins the model) and the per-route CEL pin rejects any other value with 403. Streaming is not used: a boundary is one complete response. The serialized request (messages, tool schemas) is bounded by the SDK's context-management rule in 11.8, not by the gateway, since inference bodies are not forwarded to the APS.

### 11.5 MCP client

```python
# agent_runtime/mcp.py   (mcp SDK 1.x; the transport name and its three return values are version-specific)
import asyncio, json, os
from datetime import timedelta
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from agent_runtime.identity import IDENTITY, BearerAuth, GATEWAY, CA

MCP_HOST = os.environ["AGENT_MCP_HOST"]
MAX_ARGS = 32768          # bytes of JSON; the gateway forwards at most 64 KiB to the policy service
MAX_RESULT = 65536

def _http(**kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"Host": MCP_HOST}, auth=BearerAuth(IDENTITY), verify=CA or True,
                             timeout=15.0, follow_redirects=False)

async def call_tool(backend: str, tool: str, arguments: dict, timeout: float = 25.0) -> dict:
    if len(json.dumps(arguments).encode()) > MAX_ARGS:
        raise RuntimeError("tool arguments exceed 32 KiB")
    url = f"{GATEWAY}/{backend}/mcp"
    async with asyncio.timeout(timeout):
        async with streamablehttp_client(url, httpx_client_factory=_http) as (read, write, _session_id):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments)
    if result.isError:
        raise RuntimeError(f"MCP tool {tool} returned an error")
    text = "\n".join(part.text for part in result.content if getattr(part, "type", "") == "text")
    if len(text.encode()) > MAX_RESULT:
        text = text.encode()[:MAX_RESULT].decode("utf-8", errors="ignore")   # truncate before it enters state
    return {"tool": tool, "backend": backend, "text": text}
```

The session is created per call and closed after it (the gateway runs the backend in stateless session mode), so a lost sandbox never leaves a dangling MCP session.

### 11.6 Confinement inside the guest

Before loading agent code, `confine.py` applies a Landlock ruleset: read-only `/app`, `/usr`, `/lib`, `/lib64`, `/etc`, `/var/run/secrets/agent-identity`; read-write `/sandbox`, `/tmp`; everything else denied. The guest kernel shipped by Kata supports it. If the `landlock` module is unavailable the SDK logs a warning and continues: the VM and the NetworkPolicy are the boundary; this is depth, not the wall.

### 11.7 Agent manifest and tool registration

```yaml
# /app/agent.yaml, baked into the image; its SHA-256 is AgentRelease.spec.manifestSha256
schema_version: 1
name: investigator
entrypoint: investigator.agent:create_agent
instructions: investigator/instructions/base.md
model:
  backend: llm-main
  name: Qwen3.6-35B-A3B-NVFP4
  max_tokens: 1024
  temperature: 0
tools:
  - name: list_pods
    effect: remote_read
  - name: get_pod
    effect: remote_read
  - name: write_report
    effect: workspace_write
```

```python
# agent_runtime/tools.py
from dataclasses import dataclass
from typing import Awaitable, Callable

EFFECTS = {"workspace_read", "workspace_write", "remote_read"}   # remote_write is not admitted

@dataclass(frozen=True)
class Tool:
    fn: Callable[..., Awaitable[dict]]
    effect: str

    def __post_init__(self) -> None:
        if self.effect not in EFFECTS:
            raise ValueError(f"effect {self.effect} is not admitted")
        if not callable(self.fn) or not self.fn.__doc__:
            raise ValueError("tools must be async callables with a docstring (it becomes the description)")
```

`create_agent(ctx)` receives a context with `ctx.workspace` (`/sandbox/workspace`), `ctx.instructions` (the loaded text) and `ctx.mcp` (the `call_tool` function), and returns `{"tools": [Tool, ...]}`. A `remote_read` tool may only reach the outside through `ctx.mcp`; a tool that imports `httpx` or `socket` directly is rejected at image build by the static check in section 14.1.

### 11.8 One boundary

```python
# agent_runtime/step.py
import asyncio, inspect, json, os, pathlib, sys, time, yaml
from agent_runtime import confine
from agent_runtime.models import chat_client
from agent_runtime.tools import Tool

STATE_DIR = pathlib.Path("/sandbox/state")
WORKSPACE = pathlib.Path("/sandbox/workspace")
ADVISORY_BUDGET = int(os.environ.get("AGENT_TOKENS_PER_SESSION", "200000"))   # advisory only; the gateway enforces
MAX_TOOL_RESULT = 65536
MAX_CONTEXT_BYTES = 200_000     # context management: oldest tool results are dropped first

def read_request() -> dict:
    """Length-prefixed input: a decimal byte count line, then exactly that many bytes. Never waits for EOF."""
    n = int(sys.stdin.buffer.readline().strip() or b"0")
    if not 0 < n <= 65536:
        sys.exit(5)
    return json.loads(sys.stdin.buffer.read(n))

def clip(value, limit: int):
    """Truncate string leaves of a structure before serialization, so the output is always valid JSON."""
    if isinstance(value, str):
        b = value.encode()
        return value if len(b) <= limit else b[:limit].decode("utf-8", errors="ignore") + "...[truncated]"
    if isinstance(value, dict):
        return {k: clip(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [clip(v, limit) for v in value]
    return value

def load_manifest() -> dict:
    return yaml.safe_load(open("/app/agent.yaml", encoding="utf-8"))

def build_agent(manifest: dict):
    module, _, factory = manifest["entrypoint"].partition(":")
    import importlib
    from agent_runtime.mcp import call_tool
    instructions = open(f"/app/{manifest['instructions']}", encoding="utf-8").read()
    ctx = type("Ctx", (), {"workspace": WORKSPACE, "instructions": instructions, "mcp": staticmethod(call_tool)})()
    agent = getattr(importlib.import_module(module), factory)(ctx)
    tools = {t.fn.__name__: t for t in agent["tools"]}
    declared = {t["name"]: t["effect"] for t in manifest["tools"]}
    if {n: t.effect for n, t in tools.items()} != declared:
        sys.exit(3)  # the image's tools must match its manifest exactly
    return instructions, tools

def schema(tool: Tool) -> dict:
    sig = inspect.signature(tool.fn)
    props = {n: {"type": "string"} for n in sig.parameters}   # tool signatures are string-typed in this profile
    return {"type": "function", "function": {"name": tool.fn.__name__, "description": tool.fn.__doc__.strip(),
            "parameters": {"type": "object", "properties": props,
                           "required": [n for n, p in sig.parameters.items() if p.default is p.empty]}}}

def trim_context(messages: list) -> list:
    """Drop the oldest tool results (never the system or first user message) until the context fits."""
    while len(json.dumps(messages).encode()) > MAX_CONTEXT_BYTES:
        idx = next((i for i, m in enumerate(messages) if i > 1 and m["role"] == "tool"), None)
        if idx is None:
            break
        messages[idx] = {**messages[idx], "content": "[dropped for context size]"}
    return messages

def emit(out: dict, rc: int) -> None:
    out["summary"] = clip(out.get("summary", ""), 512)
    sys.stdout.write(json.dumps(out)[:65536])
    sys.stdout.flush()
    sys.exit(rc)

def main() -> None:
    confine.apply()
    req = read_request()
    n = int(req["boundary"])
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / "state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {"messages": [], "usage": 0, "next": 0}
    if state["next"] != n:
        emit({"boundary": n, "kind": "model", "done": False, "tool": None, "usage": None, "summary": "boundary mismatch"}, 5)
    manifest = load_manifest()
    instructions, tools = build_agent(manifest)
    if not state["messages"]:
        state["messages"] = [{"role": "system", "content": instructions},
                             {"role": "user", "content": json.dumps(req["task"])}]
    (STATE_DIR / f"{n}.started").write_text(str(time.time()))
    last = state["messages"][-1]
    out = {"boundary": n, "kind": "model", "done": False, "tool": None, "usage": None, "summary": ""}
    rc = 0

    if last["role"] == "assistant" and last.get("tool_calls"):
        call = last["tool_calls"][0]
        name = call["function"]["name"]
        try:
            args = json.loads(call["function"]["arguments"] or "{}")
        except ValueError:
            args = None
        if name not in tools or not isinstance(args, dict):
            result, rc = {"error": "unknown tool or bad arguments"}, 3
        else:
            try:
                result = asyncio.run(tools[name].fn(**args))
            except Exception as e:   # tool errors are data for the model, not a crash
                result = {"error": type(e).__name__}
        content = json.dumps(clip(result, MAX_TOOL_RESULT // 4))      # valid JSON after truncation
        state["messages"].append({"role": "tool", "tool_call_id": call["id"], "content": content[:MAX_TOOL_RESULT]})
        out.update(kind="tool", tool=name, summary=f"{name} -> {list(result)[:3] if isinstance(result, dict) else 'ok'}")
    else:
        state["messages"] = trim_context(state["messages"])
        resp = chat_client().chat.completions.create(
            model=manifest["model"]["name"], messages=state["messages"],
            tools=[schema(t) for t in tools.values()], tool_choice="auto",
            max_tokens=manifest["model"].get("max_tokens", 1024), temperature=manifest["model"].get("temperature", 0),
            parallel_tool_calls=False)
        choice = resp.choices[0]
        msg = {"role": "assistant", "content": choice.message.content or ""}
        if choice.message.tool_calls:
            tc = choice.message.tool_calls[0]
            msg["tool_calls"] = [{"id": tc.id, "type": "function",
                                  "function": {"name": tc.function.name, "arguments": tc.function.arguments}}]
        state["messages"].append(msg)
        used = (resp.usage.prompt_tokens or 0) + (resp.usage.completion_tokens or 0)
        state["usage"] += used
        out.update(kind="model",
                   usage={"input_tokens": resp.usage.prompt_tokens, "output_tokens": resp.usage.completion_tokens},
                   summary=(choice.message.content or "tool call"))
        if not choice.message.tool_calls:
            out["done"], rc = True, 2
        elif state["usage"] > ADVISORY_BUDGET:
            rc = 4                      # advisory: the trusted limit is the gateway's

    state["next"] = n + 1
    tmp = state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, state_file)                      # atomic: a crash leaves the previous state intact
    (STATE_DIR / f"{n}.done").write_text(str(time.time()))
    emit(out, rc)

if __name__ == "__main__":
    main()
```

Properties the runner relies on: one model call or one tool call per invocation; length-prefixed input and bounded, always-valid JSON output; `done: true` exactly when the exit code is 2; state written atomically before the result is printed; the `.started` and `.done` markers; exit 3 on agent error, exit 4 only as the guest's advisory budget signal; the first tool call only is executed (`parallel_tool_calls=False` is also sent to the model); tool results and context are truncated structurally, never by slicing serialized JSON. Everything in this process is untrusted from the runner's point of view; the runner validates what comes back (10.4).

## 12. Request flows

Three flows cover every request a sandbox makes; the delegated MCP call is drawn because it is the only one in which four components take part.

### 12.1 Token acquisition

1. The SDK reads `/var/run/secrets/agent-identity/token` (the projected token, `aud` = the IdP issuer).
2. It sends the `client_credentials` request of section 4.2 over TLS to `AGENT_GATEWAY_URL` with `Host: token.agents.internal` and path `/v1/token`, verifying the gateway certificate against the internal CA.
3. The gateway matches route `agents-token` (exact path, POST), applies the per-source limit of 60 per minute, and forwards to the APS. No JWT policy applies to this route.
4. The APS validates the assertion with a TokenReview, reads the bound pod from the review's extras, checks that the pod is a running sandbox whose agent label matches `client_id`, and forwards the identical form to the IdP. Any other grant, client or pod is refused here and never reaches the IdP.
5. The IdP finds client `agent-<tenant>-<name>`, validates the assertion against the cluster JWKS (`iss`, signature, `exp`, `aud` = issuer, `sub` = the expected ServiceAccount), and issues an access token with `aud: [agent-gateway, agent-policy-service]`, `client_type: agent` and the agent claims.
6. The APS pins the token's `jti` to the pod UID and returns the response unchanged. The SDK persists the token under `/sandbox/state/token.json` (mode 0600) so every boundary process reuses it, and refreshes it when fewer than 120 s remain, re-reading the projected token from disk on every refresh.

A sandbox whose ServiceAccount is not registered gets `invalid_client` from the IdP; a sandbox presenting any other token gets the same. Neither reaches the APS.

### 12.2 Model call

1. `POST /models/llm-main/v1/chat/completions` with `Host: inference.agents.internal`, `Authorization: Bearer <agent access token>`, JSON body. The route, not the body, selects the model.
2. Gateway: route `agents-inference-llm-main`; JWT policy validates the token and preserves it; the `agents-only` CEL policy requires `client_type == agent`; the route's model-pin CEL policy requires `llm.requestModel` to equal the pinned model.
3. Gateway calls the APS with `route: inference`, `backend: llm-main`, the token and the source address. No body is forwarded.
4. APS steps 1 to 8 of section 9.3 (token, pod, agent match, `jti` pin, liveness, generation fence, release, backend in bundle); returns `allow` with the `x-agent-*` headers set, every other `x-agent-*` name and `authorization` in `headers_to_remove`, and `tokens_per_session` in the dynamic metadata.
5. Gateway applies the global budgets (agent, session) and the local per-source request limit.
6. Gateway rewrites the path prefix away, attaches the model server's static key from `backend-cred-llm-main`, forwards to the model server, and records `gen_ai.*` usage.
7. The response returns unchanged to the sandbox; the SDK records `usage` into its advisory counter.

### 12.3 Delegated MCP call

&#91;embedded content: delegated MCP call · 5 parties, 12 steps\]

The gateway validates the agent token and asks the policy service; the policy service exchanges the vaulted user token for a delegated token at the identity provider and hands only that token back; the MCP server sees the user as `sub` and the agent as `act`.

1. `POST /kubernetes/mcp` with `Host: mcp.agents.internal`, the agent access token, and a JSON-RPC `tools/call` body (arguments at most 32 KiB).
2. Gateway: route `agents-mcp-kubernetes`; JWT policy (token preserved); `agents-only` CEL policy.
3. Gateway calls the APS with `route: mcp`, `backend: kubernetes`, the token, the source address and the body.
4. APS: pod by source IP; labels match the token; `jti` pinned to this pod; session live; generation active; release ready and digest unchanged; `kubernetes` in the bundle; tool in the bundle's list; delegation `on-behalf-of`; vault entry present.
5. APS exchanges (through the provider adapter and under the contract chosen by T10a): `subject_token` = vaulted user token, actor = the agent, `audience` = `https://mcp.example.com/kubernetes/mcp`. Cached for later calls in the same session.
6. IdP returns a token with `sub` = user, `act.sub` = the agent's subject, `aud` = the resource URL.
7. APS returns `allow`, `Authorization: Bearer <delegated token>`, `x-agent-principal`, the other `x-agent-*` headers, and `headers_to_remove` for every `x-agent-*` name it did not set.
8. Gateway applies the per-backend CEL rule (`agent-role-kubernetes-read` and the tool list) and forwards to the MCP server with the delegated token; the inbound token is gone.
9. The MCP server validates `aud`, requires `act`, maps `act.sub` to the agent through `agent-subjects`, sets `Impersonate-User: <sub>` on its API-server calls, and answers.
10. The result passes back through the gateway to the sandbox.

### 12.4 Agent-mode MCP call

Steps 1 to 4 and 7 to 10 are identical. In step 5 the APS exchanges the agent token itself (`subject_token` = agent token, no actor) for a token whose `aud` is the resource URL; the MCP server sees `sub` = the agent's subject and no `act`, and applies its own role-based rules to the agent.

### 12.5 Failure behaviour

| Condition | Where it stops | What the sandbox sees |
| --- | --- | --- |
| Projected token expired or wrong audience | IdP | `401 invalid_client` from the token route |
| Agent token expired | gateway JWT policy | `401`; the SDK refreshes once and retries once |
| Request from a pod the APS does not know | APS step 2 | `403 {"reason":"deny.pod_unknown"}` |
| Token of agent A from agent B's pod | APS step 3 | `403 deny.pod_agent_mismatch` |
| Token copied to another pod of the same agent | APS step 4 | `403 deny.token_bound_elsewhere` |
| Session stopped or pod terminating | APS step 5 | `403 deny.session_inactive` |
| Old generation's pod after a replacement | APS step 6 | `403 deny.generation_stale` |
| `Agent` edited after approval (policy drift), release unapproved, agent disabled | APS step 7 | `403 deny.release_unapproved` |
| Model backend or MCP backend not in the bundle; tool or JSON-RPC method not permitted | APS step 8 or 9 | `403 deny.route_not_permitted` |
| `model` in the body differs from the route's pinned model | gateway CEL (model pin) | `403` from the gateway |
| Delegated call without a grant | APS step 10 | `403 deny.delegation_required` |
| IdP refuses exchange (consent revoked, user disabled) | APS step 10 | `403 deny.exchange_failed` |
| APS unreachable or slow (over 2 s) | gateway, fail closed, no cache | `403` |
| Agent daily budget or session budget exhausted | gateway rate limit | `429` |
| More than 30 requests per minute from one sandbox | gateway local limit | `429` |
| Tool allowed by the APS but not by the backend CEL rule | gateway MCP policy | JSON-RPC error; the tool is also absent from `tools/list` |

## 13. Observability and audit

Every request is reconstructible from three records that share a decision ID and a trace ID: the gateway access log, the APS decision log and the Session Runner's boundary record; no record ever contains a token.

### 13.1 Correlation keys

| Key | Minted by | Appears in |
| --- | --- | --- |
| `trace_id` (W3C `traceparent`) | gateway, propagated to APS, model server and MCP server; the MCP server also receives it in `_meta` per the 2026-07-28 MCP revision | all three records, backend logs |
| `decision_id` | APS, per check | gateway access log (`agent.decision_id`), APS log, upstream header `x-agent-decision-id` |
| `session_id` | Session Runner | all three records, pod label, Temporal workflow ID |
| `jti` of the agent access token | IdP | gateway (`auth.jti`), APS log |
| `jti` of the upstream token | IdP | APS log only |

### 13.2 APS decision log

One JSON line per check, written to stdout, shipped by the cluster log agent:

```json
{"ts":"2026-10-30T14:02:11.482Z","decision_id":"0b3e...","reason":"allow",
 "tenant":"tenant-a","agent_id":"tenant-a/investigator","spiffe_id":"spiffe://cluster.local/ns/tenant-a/sa/agent-investigator",
 "session_id":"6f1d...","generation":1,"release":"investigator-2026-10-29-a93557ad","policy_digest":"sha256:9c1e...",
 "route":"mcp","backend":"kubernetes","path":"/kubernetes/mcp","method":"tools/call","tool":"pods_get","model":null,
 "delegation":"on-behalf-of","principal":"alice","exchange":{"cached":false,"ms":84,"upstream_jti":"d41a..."},
 "source_ip":"10.42.1.57","pod":"s-3f9a1c0b7e2d4a61-g1","token_jti":"7a0e...","trace_id":"4bf9...","ms":97}
```

Denied decisions carry the same fields with `reason` set and the fields that were established before the failing step; later fields are `null`.

### 13.3 Gateway access log

The OTLP access log of section 8.10 carries the standard HTTP fields plus `agent.id`, `agent.session_id`, `agent.decision`, `agent.decision_id`, `mcp.tool`, `llm.model`, `llm.tokens_in`, `llm.tokens_out`, and the response code. The `authorization` request header is removed from the log at the source.

### 13.4 Session Runner records

| Event | Fields |
| --- | --- |
| `session_started` | tenant, agent, release, session\_id, delegated (bool), grant\_handle (opaque) |
| `sandbox_created` | session\_id, generation, pod, node, boot\_ms (create to ready) |
| `boundary_accepted` | session\_id, generation, boundary, kind, tool, usage.input\_tokens, usage.output\_tokens, cumulative\_tokens, snapshot (sha256) |
| `sandbox_replaced` | session\_id, old\_generation, reason |
| `session_finished` | session\_id, outcome, boundaries, cumulative\_tokens, duration\_ms |
| `cleanup_result` | session\_id, generation, result (`DELETED` or `NOT_CONFIRMED`) |

These are also the facts in Temporal history; the log is the queryable copy.

### 13.5 Metrics

| Metric | Type | Labels |
| --- | --- | --- |
| `aps_decisions_total` | counter | `reason`, `route`, `tenant` |
| `aps_check_duration_seconds` | histogram | `route` |
| `aps_exchange_duration_seconds` | histogram | `mode`, `cached` |
| `aps_exchange_failures_total` | counter | `mode`, `error` |
| `aps_vault_entries` | gauge |  |
| `agentgateway_gen_ai_client_token_usage` (built in) | histogram | `gen_ai.request.model`, plus `agent.id` through the metrics attribute policy |
| `agent_sessions_active` | gauge | `tenant`, `agent` |
| `agent_sandbox_boot_seconds` | histogram | `node` |
| `agent_boundaries_total` | counter | `tenant`, `agent`, `kind`, `outcome` |
| `agent_cleanup_not_confirmed_total` | counter | `tenant` |
| `agent_probe_failures_total` | counter | `tenant` (from pod exit code 3) |

### 13.6 Redaction

No component logs a token value, an `Authorization` header, a client secret, a vault entry or a request body. The CI pipeline of every component runs its tests with log capture and fails if any captured line matches `eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}` (a JWT) or `Bearer [A-Za-z0-9._~+/=-]{20,}`. The same pattern runs as a scheduled query against the SIEM; a hit is a severity-1 incident.

### 13.7 SIEM and retention

| Stream | Retention | Why |
| --- | --- | --- |
| APS decision log | 1 year | the authoritative record of who was allowed what |
| Gateway access log | 1 year | request-level corroboration, token counts |
| Runner records and Temporal history | 1 year (history export), 30 days in Temporal | what the agent did with the results |
| Traces | 30 days | debugging |
| Metrics | 13 months | capacity and trends |

### 13.8 Alerts

| Alert | Condition | Severity |
| --- | --- | --- |
| APS fail-closed | gateway reports ext\_authz errors or timeouts for over 1 minute | 1 |
| Deny spike | `deny.*` rate for one agent above 20 percent of its requests over 5 minutes | 2 |
| Pod mismatch | any `deny.pod_agent_mismatch` or `deny.pod_unknown` | 2 (possible lateral movement attempt) |
| Exchange failures | `aps_exchange_failures_total` rising for 5 minutes | 2 |
| Cleanup not confirmed | any `NOT_CONFIRMED` | 3, reconcile per 14.5 |
| Probe failure | any pod exit code 3 | 1 (egress policy not holding) |
| Budget exhausted | 429 for an agent | 3 |
| Token in logs | redaction query hit | 1 |

### 13.9 Data classification

Token redaction protects credentials, not business data; three classes with different homes, protections and retention apply to everything the platform stores.

| Class | Examples | Where it lives | Protection and retention |
| --- | --- | --- | --- |
| Audit metadata | decision logs, access logs, runner records: identifiers, reasons, counts, digests, timings | SIEM | immutable, 1 year, no content fields |
| Task content | the task input, model messages, tool results, workspace files, boundary summaries, checkpoint archives | Temporal history (through a payload codec with per-tenant AES-GCM keys, so the Temporal server and UI never see plaintext) and the per-tenant artifact bucket (server-side encryption, tenant-scoped access) | 30 days by default, tenant-configurable; never in gateway, APS or runner logs; MCP tool results are task content even when they come from upstream systems |
| Credentials | projected tokens, agent tokens, subject tokens, upstream tokens, static keys | only where section 4.6 allows | never logged, never in history, never in artifacts |

The 512-character boundary summary is task content: it goes into Temporal history under the codec and into the runner's record only as a hash. Access to Temporal history and to the artifact bucket is granted per tenant and audited; the log pipeline drops request and response bodies at the source.

## 14. Operations

Every operational change is a reviewed git change or an IdP console action with a named owner; none requires touching a running sandbox.

### 14.1 Onboarding an agent

- [ ] Build the image with `/app/agent.yaml`, the SDK and the agent package; run the static check: no module under the agent package imports `httpx`, `requests`, `urllib`, `socket`, `aiohttp` or `subprocess` (`grep -rnE "^(import|from) (httpx|requests|urllib|socket|aiohttp|subprocess)" src/ && exit 1`). Tools reach the outside only through `ctx.mcp`.
- [ ] Push by digest and sign: `cosign sign --key cosign.key registry.example.com/agents/<name>@sha256:<digest>`.
- [ ] Open a pull request adding the `Agent` (section 6.1) in `tenant-<tenant>`; merge after owner review. Wait for `status.conditions[Ready]`.
- [ ] Open a pull request adding the `AgentRelease` with `approval.approved: false`; merge. Wait for `status.signatureVerified: true` and `status.policyDigest`.
- [ ] Security review reads the policy bundle ConfigMap (the compiled allow-lists) and the image's `agent.yaml`; approval is a pull request setting `approval.approved: true`, `approvedBy` and `ticket`.
- [ ] Confirm `status.ready: true`.
- [ ] Run the smoke session (test T18) and the per-agent conformance subset (T4, T6, T7, T10 or T11 depending on mode).
- [ ] Record the agent in the auth inventory: client ID, SPIFFE ID, roles, budget, owner, review ticket.

### 14.2 Rotation

| Credential | Procedure | Downtime |
| --- | --- | --- |
| Model server key (`backend-cred-llm-<name>` and `llm-api-key`) | 1. generate a new value; 2. update the model server's Secret and restart it in a maintenance window (vLLM reads `--api-key` at start); 3. update the gateway Secret; the gateway reloads without restart. Sandboxes see 401 from the gateway between steps 2 and 3, so keep the window short and run it when no sessions are active. | minutes |
| IdP client secrets (`agent-gateway`, `agent-policy-service`, `registry-controller`) | enable Keycloak client-secret rotation with a 24 h grace period; update the Kubernetes Secret; APS and gateway reload on the next request. | none |
| APS vault key | the vault holds only entries at most 8 h old; rotate by deploying the new key when no delegated session is active, or implement dual-key decryption for one rotation window. | none |
| Cluster ServiceAccount signing key | rotated by the cluster; the IdP refetches the cluster JWKS; sandboxes' projected tokens are re-issued by the kubelet. | none |
| Agent clients | have no secret; nothing to rotate. | none |
| Gateway TLS (enterprise HTTPS listener) | cert-manager renewal; the SDK trusts the internal CA, not a leaf. | none |

### 14.3 Revocation

| To revoke | Action | Takes effect |
| --- | --- | --- |
| One session | cancel the Temporal workflow (never terminate); `stop_session` marks it stopped and `delete_sandbox` removes the pod | immediately for new requests (APS), seconds for the pod |
| One agent, all sessions | set `Agent.spec.enabled: false` (pull request) | within the APS informer latency, under 5 s; every request from every release of that agent is denied |
| One release | set `AgentRelease.spec.approval.approved: false` | same; running sandboxes of that release are denied |
| A user's delegation to an agent | revoke the consent in the IdP (user account, applications, revoke) | next exchange fails; already-minted upstream tokens expire within 300 s |
| A compromised sandbox | delete the pod, or cancel its session | APS denies on the next request (`deny.pod_unknown` or `deny.session_inactive`); its agent access token is pinned to that pod's UID, so it is refused from any other pod for the rest of its 300 s life |
| An old generation that will not die | nothing to do: it is fenced (`deny.generation_stale`) the moment the next generation was recorded; the reconciler keeps deleting it | immediately |
| Everything (break glass) | scale the APS to zero | the gateway fails closed for all sandbox traffic |

### 14.4 Upgrades

| Component | Procedure |
| --- | --- |
| agentgateway | upgrade the CRDs chart then the controller chart; the data plane rolls with two replicas; run T1, T6, T7, T12 after |
| Kata | kata-deploy rolling upgrade per node: cordon, drain sandboxes (sessions are replaced on another node by the Runner), upgrade, uncordon; run T1 and T2 on the upgraded node |
| Identity provider | export the realm before; upgrade; run 7.8 and T4, T10, T11 |
| APS | rolling update; readiness gates on informer sync; run T17 (fail closed) in staging first |
| Session Runner | deploy with Temporal worker versioning so in-flight histories replay on the old build; run T18 |
| Registry Controller | rolling; it is idempotent, so a replay of reconciliation is harmless |

### 14.5 Reconciling `NOT_CONFIRMED` cleanups

The reconciler of section 10.7 does this automatically every 5 minutes. The manual procedure below is for an orphan that survives two reconciler runs (alert in 13.8):

1. List pods with `agentplatform.io/sandbox=true` in every tenant namespace.
2. For each, read the session label and query the Temporal workflow `session:<tenant>:<agent>:<session>`; if the workflow is closed, the pod is an orphan.
3. Delete orphans; record the pod name, node and age in the operations log.
4. If a pod cannot be deleted (stuck finalizer, node gone), escalate to the node runbook; the APS keeps denying it because its session is stopped.

### 14.6 Incident response

| Signal | Action |
| --- | --- |
| Probe failure (pod exit 3) | treat as a policy-engine fault: stop creating sandboxes on that node (cordon), inspect kube-router on the node, run T1 manually, then uncordon |
| `deny.pod_agent_mismatch` or `deny.pod_unknown` | identify the source pod by IP; cancel its session; preserve its logs; review how it obtained the token |
| Token found in logs | severity 1; rotate the affected credential per 14.2; cancel sessions whose tokens appear; fix the logging site before redeploying |
| APS compromise suspected | scale APS to zero (break glass); rotate `agent-policy-service` secret and the vault key; cancel every delegated session; redeploy from a verified image |
| IdP compromise suspected | follow the IdP's incident procedure; all agent tokens expire within 300 s; disable the `agent-gateway` and `agent-policy-service` clients until the IdP is trusted again |

### 14.7 Capacity

Each sandbox reserves its requests plus the RuntimeClass overhead (`160Mi`, `600m` until measured). The Session Runner refuses to start a session when the tenant's ResourceQuota would be exceeded, and the platform alerts at 80 percent of any node's Kata capacity. Measure boot latency and resident memory on each node type during Phase A and replace the overhead values with measured ones.

## 15. Verification

Thirty conformance tests, each with one exact expected result and most of them adversarial, run against a real cluster from the `agent-platform` namespace by a test harness that can create sandboxes of a dedicated test agent (`tenant-test/conformance`); a phase is accepted only when every test it names passes.

### 15.1 Test agent

The `conformance` agent's image contains the SDK plus a `probe` tool set that the harness drives through the normal boundary protocol: `probe_connect(host, port)`, `probe_http(host_header, path, body)`, `probe_env()`, `probe_files()`. It has `identity.mode: on-behalf-of`, `fallback: agent`, one model (`llm-main`) and one MCP backend (`kubernetes`, tools `pods_list_in_namespace`). Two releases exist: `conformance-ok` (approved, signed) and `conformance-unsigned` (approved, not signed).

### 15.2 Tests

| ID | Requirement | Steps | Expected |
| --- | --- | --- | --- |
| T1 | R1 | From a running sandbox, `probe_connect` to kube-dns (10.43.0.10:53 TCP and UDP), the API server (10.43.0.1:443), the IdP Service, a model server pod IP:8000, an MCP pod IP:8080, 1.1.1.1:443 | every connect fails within 2 s |
| T2 | R1 | Two parts. T2a, the gate: 100 sandbox starts; for each, record the order of (chain present on the host, attestation annotation set, egress guard exit 0, agent container started) from the attestor log, the kubelet log and the pod status; also create one sandbox in a namespace with no NetworkPolicies. T2b, the engine measurement: in a test namespace without the admission pin, run the guard image in `--attack` mode, which opens connections to every forbidden address continuously from the pod's first instruction and keeps any that succeed open, and record successes and how long an early connection stayed usable | T2a: in all 100 starts the agent container started only after the attestation was set, and the unpoliced pod was never attested, never started its agent, and its guard exited 3 on an observed forbidden connection or 4 on attestation timeout (5.5); any violation fails the Phase A gate. T2b: reported, not gated: the success count and the longest usable window are recorded in 16.3 as the engine's measured residual, which no untrusted instruction can exploit while T2a holds |
| T3 | R2 | `probe_files` lists `/var/run/secrets/**`, `/proc/*/environ`, `/sandbox/state/token.json` and the SDK's memory | exactly one file under `/var/run/secrets/agent-identity/` with `aud` = the IdP issuer; the only other token-like string is the agent access token in `token.json` (mode 0600) and the SDK process; nothing else matches the JWT regex |
| T4 | R3 | SDK obtains an access token through the token route over TLS | 200; decoded `aud` contains `agent-gateway` and `agent-policy-service`, `client_type == agent`, `agent_id == tenant-test/conformance`, `exp - iat == 300` |
| T5 | R3 | Same request with (a) the pod's API-audience token, (b) a human user's token, (c) `grant_type=password`, (d) a client secret | (a) 401 `invalid_client`; (b) 401 `invalid_client`; (c) 400 `unsupported_grant_type` or 401; (d) 401 |
| T6 | R4 | From a harness pod in `agent-platform` with a temporary NetworkPolicy exception to the model server: request with no credential, then with the value of `backend-cred-llm-main` | 401, then 200. (Network denial from a sandbox is T1, not this test) |
| T7 | R4 | A chat completion through the gateway with a valid agent token; capture the request at the model server | 200; the model server received the backend key, not the agent token; the path is `/v1/chat/completions`; `usage` is non-zero |
| T8 | R5 | `probe_http` with headers `x-agent-id: tenant-test/other`, `x-agent-principal: mallory`, `x-agent-session-id: 0000`, `x-agent-decision-reason: allow` on an MCP call; capture at the MCP server | the MCP server received the APS-set values; none of the injected values appear; `x-agent-decision-reason` is absent |
| T9a | R6 | Submit sessions for `conformance-unsigned` and for `conformance-ok` after setting `approved: false` | `preflight` fails with `Forbidden` in both cases; no pod is created |
| T9b | R6 | The harness creates sandbox pods **directly**, bypassing the runner, for: an unsigned image; an unapproved release; a drifted release; a mismatched policy digest; a mismatched agent label | every pod is rejected by admission and the error names the Kyverno rule |
| T10 | R7 | Delegated session for user `alice` (consent granted) calling `pods_list_in_namespace` on a namespace alice can read and one she cannot; capture the token at the MCP server | first call succeeds; second returns a Kubernetes 403 from impersonation; the captured token has `sub == alice`, `act.sub == <agent subject>`, `aud == https://mcp.example.com/kubernetes/mcp` exactly |
| T10a | R7 | Delegation contract decision: run the exact exchange of 9.5 under contract A and under contract B against the pinned IdP; also with a wrong consent scope, a wrong agent, a wrong audience and a user of another tenant | exactly one contract yields a token with the claims of 4.4; every wrong variant fails at the IdP. The passing contract and the exported realm become the authoritative configuration |
| T11 | R7 | Same agent, agent-mode session (no grant, fallback `agent`) | the captured token has `sub == <agent subject>` and no `act`; the call is authorized by the agent's role |
| T12 | R4 | Capture at the MCP server during T10 and T11, and with the optional native exchange of 8.11 enabled on a test backend | the agent access token (its `jti`) never appears at the MCP server in any configuration |
| T13 | R8 | Set the test agent's daily budget to 2,000 tokens; run chat completions until refused; restart both gateway replicas; send one more | no request is admitted whose reservation would take spent plus in-flight over 2,000, so observed usage never exceeds 2,000; the refusal is 429 with the APS reason; the request after the gateway restart is still 429 because the ledger lives in the APS's Redis |
| T13b | R8 | Two concurrent sessions of the same agent with a 1,000-token session budget: session 1 exhausts it; the guest in session 1 then edits its state file to zero usage and retries; session 2 continues; restore a checkpoint into a new generation of session 1 | session 1 gets 429 and keeps getting 429 after the edit and after the restore; session 2 is unaffected; ten concurrent requests from session 1 result in at most `floor(remaining / reserve_tokens)` admitted and the rest 429 immediately; settlement releases unused reserve within 5 s of each response; observed usage never exceeds 1,000 |
| T14 | R9 | Run T10; fetch the gateway access log, the APS log and the Runner records for the session | all three share `session_id`; gateway and APS share `decision_id`; the APS record has `principal == alice`, `policy_digest` equal to the release's; no record matches the JWT regex |
| T15 | R10 | During a running session: set `Agent.spec.enabled: false`, measure time to first 403; re-enable; cancel the workflow, measure time to first 403; repeat with 2 APS replicas and warm informers | first 403 within 5 s of the edit; within 1 s of `stop_session`; both measured values recorded |
| T16 | R10 | During a delegated session, revoke alice's consent in the IdP; keep calling every 10 s | 403 `deny.exchange_failed` no later than 300 s after revocation |
| T17 | R11 | Scale the APS to zero while requests continue at 5 per second; scale back | every request from the first second after scale-down is 403 (there is no decision cache to warm); after scale-up, requests succeed |
| T18 | all | The smoke session: a delegated session that lists pods, writes a report to the workspace and completes | workflow result `outcome == COMPLETED`, `cleanup == {stop: OK, delete: DELETED, grant: OK}`, `boundaries` between 2 and 6; the workspace snapshot contains `report.md`; no pod with the session label remains |
| T19 | R3, R7 | Cache separation: alternate an allowed and a forbidden tool on the same MCP path 50 times within 10 s with one token; alternate an allowed and a forbidden model route | every forbidden call is 403; every allowed call is 200; the APS log shows one decision per request |
| T20 | R6 | Release immutability: with a session running, edit the `Agent` to add a tool; then try to edit `AgentRelease.spec.image` | the release shows `policyDrift: true` and `ready: false` within 10 s; the running sandbox gets 403 `deny.release_unapproved`; a new session fails preflight; the `AgentRelease` edit is rejected by the CRD validation rule |
| T21 | R10 | Generation fencing: put a finalizer on generation 1's pod, force a replacement, then remove the finalizer | generation 1's requests are 403 `deny.generation_stale` from the moment generation 2 was recorded; generation 2 works; after the finalizer is removed the reconciler deletes generation 1 within 5 minutes |
| T22 | R6 | Admission completeness: pods with an extra container; a changed init image; an added `hostPath` volume; a different `serviceAccountName`; no sandbox label; `automountServiceAccountToken` true and omitted; `runtimeClassName` omitted; `hostNetwork: true`; an ephemeral-container attach against a valid sandbox | all rejected; the attach fails with forbidden |
| T23 | R10 | Checkpoint failure points: kill the pod (a) before the exec starts, (b) after the MCP call completed but before `.done`, (c) after `.done` but before the snapshot upload, (d) during the upload, (e) after commit | (a) to (d): the boundary is re-run once on a new generation restored from the last committed snapshot and the repeated-read count is reported; (e): the boundary is not re-run; committed boundaries never execute twice |
| T24 | R10 | Cleanup failures: APS down during cleanup; pod deletion blocked by a finalizer; runner killed mid-cleanup; workflow terminated (not cancelled) | in every case the session's cleanup converges within 10 minutes, the outcomes are recorded, and no pod, grant or active generation remains |
| T25 | all | Protocol robustness: the guest prints 10 MiB; invalid JSON; the wrong boundary number; `done: true` with exit 0; hangs forever | the runner stays healthy; each case is `OutcomeUnknown` (or a timeout) and the session follows the recovery contract; worker memory is bounded |
| T26 | R2 | Token binding: copy the agent access token from sandbox 1 to sandbox 2 of the same agent (different session) and to a sandbox of agent B | sandbox 2: 403 `deny.token_bound_elsewhere`; agent B's pod: 403 `deny.pod_agent_mismatch` |
| T27 | R3 | Transport: plaintext HTTP to the gateway address on 443; an HTTPS listener with a certificate from another CA; packet capture on the sandbox veth during T4 | the first two fail; the capture shows no bearer token in cleartext |
| T28 | R1 | Effective NetworkPolicy: add an extra allow-all egress policy to the tenant namespace | the controller reverts it within 60 s; a session submitted while it exists fails preflight with the digest mismatch |
| T29 | R6, ops | Measurements on each node type: sandbox create-to-Running, per-boundary overhead (exec, token reuse, MCP session), snapshot bytes and seconds, token-route request rate, recovery time after a pod kill, worker saturation at 20 concurrent sessions | recorded with the component digests; Phase A targets: create-to-Running p95 under 10 s, boundary overhead p95 under 2 s, snapshot under 5 s for a 64 MiB workspace |
| T30 | quality | Agent-quality suite (separate from conformance): graded outcomes on a fixed task set, evidence quality, behaviour after a denied tool, prompt injection in tool results, cost per completed task | reported per release; required before production use of an agent, not for platform acceptance |

### 15.3 Phase gates

| Phase | Must pass |
| --- | --- |
| A (Kata, network, egress guard, SDK wait) | T1, T2, T3, T27, T28, T29 |
| B (identity provider, gateway, APS in agent mode, runner) | T4, T5, T6, T7, T8, T9a, T9b, T11, T12, T13, T13b, T14, T15, T17, T19, T20, T21, T22, T23, T24, T25, T26 |
| C (delegation) | T10a first, then T10, T16, T18 |
| D (enterprise hardening) | all, on every cluster, plus the per-cluster variant of T4 with that cluster's issuer, and T30 for every agent before production |

**Qualification note, 2026-11-06:** [Run 16](agent-runtime-platform-phase-b-qualification.md#run-16-full-t19-cache-separation-requirement-first-qualifies)
first qualifies full T19; run 18 repeats its 100 MCP requests within 10 seconds
and four model probes, with 104 distinct decisions. Earlier five-cycle results
retain their limited scope. [Run 17](agent-runtime-platform-phase-b-qualification.md#run-17-corrected-admission-batch-first-qualifies-t22)
passes T9a/T9b/T22 with all 50 checks true; run 15 remains a historical error.
[Run 18](agent-runtime-platform-phase-b-qualification.md#run-18-authentic-t5-fixtures-pass-t4-evidence-and-t11-probe-remain-failed)
first passes authentic human/API-audience T5 fixtures, but stays failed on T4's
missing issuance evidence and T11's missing probe invocation.
[Run 19](agent-runtime-platform-phase-b-qualification.md#run-19-t20-qualifies-first-t15-cancellation-timing-remains-failed)
first passes T20 with exact restoration, while T15's first cancellation timing
remains historically failed. The later log-window/timing corrections are qualified
by new reports, not by rewriting these failures.
[Run 20](agent-runtime-platform-phase-b-qualification.md#run-20-protocol-faults-and-bounded-worker-memory-first-qualify-t25)
first passes T25: five real protocol faults through three generations, six healthy
controls, all 191 checks, confirmed checkpoint/delete/fence ordering, and bounded
RSS/high-water on the same worker/process with zero restarts. The memory result
is scoped to the exclusive batch with explicit 64 MiB growth/headroom thresholds
under its 1 GiB limit.
[Run 21](agent-runtime-platform-phase-b-qualification.md#run-21-exact-t4-first-passes-all-nine-selected-tests-pass)
first passes exact T4 with committed claims matching the sole current-Pod/JTI
issuance, and all nine selected tests pass (115 checks).
[Run 22](agent-runtime-platform-phase-b-qualification.md#run-22-active-session-revocation-first-qualifies-t15)
first passes T15 in both rounds (38 checks): real Agent-disable and cancellation
denials on both replicas,
47.015/7.917 ms conservative first-stop-to-same-replica-403 bounds, delayed
deletion, exact restoration and cleanup.
[Run 23](agent-runtime-platform-phase-b-qualification.md#run-23-session-budget-concurrency-and-tampered-state-recovery-qualify-t13b)
first passes T13b (28 checks) against the dedicated byte-token backend: exact
1,000-token limit, three of ten concurrent requests admitted, settlement within
five seconds, independent session and continued refusal after zeroed guest-state
checkpoint recovery. This proves the budget path, not Qwen accounting.
[Run 24](agent-runtime-platform-phase-b-qualification.md#run-24-daily-budget-batch-records-a-timeout)
records T13 TimeoutError with no retained checks; T13 remains open.
[Runs 25–27](agent-runtime-platform-phase-b-qualification.md#run-25-scale-patch-fails-before-the-aps-outage)
remain failed T17 attempts. Runs 25/26 never establish an outage. Run 27 records 900
real responses, all 63 eligible requests 403, continuous 5 Hz and ten seconds with
no APS Pods/endpoints, but fails three operator-receipt/generation checks because
Flux pause/resume transitions are missing. A fresh complete report is required;
these narrower traffic observations do not qualify T17.
T12 remains agent-mode only. These
results do not complete Phase B. Phase A T2a still has ten recorded starts,
not 100; its negative-case exit wording now follows the existing 5.5 distinction
between a detected leak (3) and attestation timeout (4), with neither permitting
agent startup. T27/T29 remain unqualified.

### 15.4 Harness rules

- Tests run from a pod in `agent-platform` with the harness's own ServiceAccount; they never run inside a sandbox except through the boundary protocol.
- Every captured token is compared by `jti` and then discarded; the harness output is subject to the redaction check of 13.6.
- A test that cannot reach its expected state within its timeout fails; there is no "inconclusive".
- The harness records each run as a JSON report with the release digests of every component, kept for a year.

## 16. Security considerations

The sandbox is assumed hostile; every other component is trusted, and the design's value is that a fully compromised sandbox can do nothing beyond its own registered allow-list for the life of its session.

### 16.1 Threat model

| Adversary | Capability assumed | Held by |
| --- | --- | --- |
| Code inside a sandbox (prompt injection, malicious dependency, bug) | arbitrary execution as the agent user, reads the projected token, holds the agent access token, edits its own state and counters | VM boundary; host-side NetworkPolicy proven by the egress guard; gateway and APS checks on every request; trusted budgets; session lifetime |
| A tenant trying to use another tenant's backends | valid agent token of its own | APS denies anything outside the bundle; CEL rules key on roles the other tenant's agents do not hold; namespaces separate registries |
| An operator changing policy outside review | write access to git or the cluster | approval covers an immutable snapshot; a changed `Agent` drifts every release; the digest ties a running sandbox to the policy it started under |
| Network attacker inside the cluster | can read or inject traffic on a node, can spoof source IPs on a tap | TLS from the sandbox to the gateway; a spoofed source cannot complete a TCP handshake, so no request succeeds; NetworkPolicy between gateway and backends |
| A stolen agent access token | used from another pod of the same agent, or from outside | pinned to the first pod's UID (`deny.token_bound_elsewhere`); from any other agent's pod `deny.pod_agent_mismatch`; from outside the cluster the token never reaches the agents listener; it also expires within 300 s |
| A lingering old sandbox after replacement | still running, still holding a token | fenced by the recorded generation (`deny.generation_stale`); deleted by the reconciler |

### 16.2 Invariants that must never be relaxed

1. A sandbox namespace has `default-deny-all` and exactly one egress rule, to the gateway data plane, and `preflight` checks the effective set, not the presence of names. Adding DNS, the API server or any other destination breaks R1.
2. No agent instruction executes before the node attestor has recorded host-side policy for the pod and the platform-owned egress guard has confirmed it; the attestation is continuous and the APS denies a pod whose attestation is missing or stale.
3. The projected token's audience is the IdP issuer and nothing else; the gateway never accepts it directly, and the IdP's token endpoint is reachable only through the APS, which forwards one grant.
4. Every hop that carries a bearer token uses TLS. A plain-HTTP listener never serves a tenant namespace.
5. The agents listener accepts only tokens with `client_type == agent` and `aud` containing `agent-gateway`. Human tokens use a different Gateway.
6. The inbound `Authorization` header is never forwarded upstream. Every upstream credential is either gateway-held or minted by exchange with an audience the registry assigned.
7. The APS fails closed and no component caches an authorization decision; only inputs are cached.
8. An agent access token is pinned to the pod it was issued for, and authority is derived from that pod's session and generation, never from the token alone.
9. A generation is recorded at the APS before its pod is created; a replacement is created only after the previous generation's deletion is confirmed.
10. A boundary is committed only when its result and its checkpoint are durable. An uncommitted boundary may be re-run only while every admitted effect is read-only; a write boundary follows 10.8.
11. Subject tokens exist only inside the APS vault. They are never returned by any API, never written to Temporal, never logged.
12. `remote_write` is admitted only under the contract of 10.8 (idempotency key recorded before dispatch, read-back on unknown outcome), and only for backends that declare idempotent writes.
13. A release is an immutable snapshot; approval never applies to a changed policy. Revocation is a separate, mutable operation.
14. A sandbox is created only through the Session Runner from a ready release's pod template, and admission enforces the complete pod shape, not selected fields.
15. Agent clients at the IdP have no secret. An agent that authenticates with a secret is misconfigured.
16. Budgets are hard ceilings enforced by reservation in the APS ledger before dispatch; nothing the guest reports changes a limit, and nothing the gateway counts after the fact is the ceiling.
17. No component logs a token value or task content.

### 16.3 Residual risks accepted

| Risk | Why accepted | Compensating control |
| --- | --- | --- |
| During its session a compromised sandbox can make every call its bundle allows | that is the agent's authority; removing it removes the agent | tool allow-lists, hard budgets, 8 h maximum, attribution |
| The agent access token is a bearer token for up to 300 s inside its own pod | sender constraint (DPoP, mTLS) adds complexity the first profile does not need | pinned to the pod UID at issuance; TLS; short lifetime; enterprise profile may add client certificates on the agents listener |
| Guest kernel exploit against the VMM | out of scope of software policy | Kata releases tracked, node isolation per tenant when required |
| kube-router's documented fail-open window at pod start | engine behaviour that K3s does not let us switch off | nothing untrusted runs inside it: the agent container starts only after host-side attestation; T2b measures the window on the engine and the figure is recorded here after Phase A; the enterprise profile uses Cilium's start-closed endpoints |
| The attestor is itself software and could be wrong | it is the authority for the gate | the egress guard's forbidden-address probes alarm on any success (exit 3, severity 1); T2a exercises the attestor against a deliberately unpoliced namespace, where it must refuse to attest |
| Gateway-to-backend hops inside the cluster are HTTP within NetworkPolicy-restricted namespaces | the backends are trusted and the hop is not sandbox-reachable | enterprise profile enables TLS to backends (`spec.backend.tls`) |
| A cached upstream token outlives a consent revocation by up to 300 s | upstream tokens are short and the cache is what makes delegated calls affordable | session cancel is immediate; the bound is measured by T16 |
| Budget settlement lags the response by the log-pipeline delay | the reservation already bounds spending; settlement only releases unused reserve | an unsettled reservation charges in full after 130 s, so the lag can only under-admit, never over-admit |
| Keycloak delegation is a preview feature | the documented flow is the only one that produces `act` from consent | realm isolation; T10a on every Keycloak upgrade; agent-mode delegation does not depend on it |
| The IdP, gateway, APS and Temporal are trusted | they are the control plane | their own hardening, secrets management, audit and upgrade procedures (section 14) |
| Re-running an uncommitted read-only boundary repeats a read | reads are side-effect free outside the sandbox; the repeat costs money and may observe different data | at most two replacements per session; T23 reports the repeat count; write boundaries never re-run (10.8) |

### 16.4 What this design deliberately does not do

- It does not inspect prompts or tool results for content. Guardrails can be attached at the gateway later without changing anything here.
- It does not let agents discover tools or servers dynamically; the registry is the only source of what an agent may call.
- It does not attempt to hide the agent's identity from upstreams; the opposite, every upstream sees `sub` and `act`.
- It does not support agent-to-agent calls; an agent that needs another agent's result does so through a human-mediated session or a future, separately reviewed extension.

## 17. References and items to confirm

The behaviours this specification relies on were checked against the sources below; the eight items in 17.3 could not be confirmed from documentation and must be settled by a test on the target cluster before Phase A is accepted.

### 17.1 Standards

| Reference | Used for |
| --- | --- |
| [RFC 8693, OAuth 2.0 Token Exchange](https://datatracker.ietf.org/doc/html/rfc8693) | delegated and agent-mode upstream tokens, `act`, `may_act` |
| [RFC 7523 and rfc7523bis](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-rfc7523bis) | the projected token as a client assertion; assertion audience = issuer |
| [RFC 8707, Resource Indicators](https://datatracker.ietf.org/doc/html/rfc8707) | one audience per upstream |
| [RFC 9728, Protected Resource Metadata](https://datatracker.ietf.org/doc/html/rfc9728) | MCP servers' metadata for human clients (not used by sandboxes) |
| [MCP authorization, 2025-06-18](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-06-18/basic/authorization.mdx) and the [2026-07-28 changelog](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/changelog.mdx) | token passthrough prohibition, resource indicators, stateless sessions, trace context in `_meta` |
| [MCP Enterprise-Managed Authorization](https://github.com/modelcontextprotocol/ext-auth/blob/main/specification/stable/enterprise-managed-authorization/2026-07-28/enterprise-managed-authorization.mdx) | the IdP-managed consent path for a later phase |
| [SPIFFE ID](https://github.com/spiffe/spiffe/blob/main/standards/SPIFFE-ID.md), [JWT-SVID](https://github.com/spiffe/spiffe/blob/main/standards/JWT-SVID.md), [ClusterSPIFFEID template](https://github.com/spiffe/spire-controller-manager/blob/main/docs/clusterspiffeid-crd.md) | the `ns/<ns>/sa/<sa>` naming |
| [Kubernetes service account tokens](https://github.com/kubernetes/website/blob/main/content/en/docs/reference/access-authn-authz/service-accounts-admin.md), [KEP-1393 OIDC discovery](https://github.com/kubernetes/enhancements/blob/master/keps/sig-auth/1393-oidc-discovery/README.md) | projected token claims, rotation, discovery endpoints, RBAC |
| [WIMSE AIMS draft](https://github.com/ietf-wg-wimse/draft-ietf-wimse-aims/blob/main/draft-ietf-wimse-aims.md) | the premise that the model must never hold the agent's credentials |

### 17.2 Products

| Reference | Used for |
| --- | --- |
| [agentgateway policy types v1.5.0](https://github.com/agentgateway/agentgateway/blob/v1.5.0/controller/api/v1alpha1/agentgateway/agentgateway_policy_types.go), [backend types](https://github.com/agentgateway/agentgateway/blob/v1.5.0/controller/api/v1alpha1/agentgateway/agentgateway_backend_types.go), [CEL variables](https://github.com/agentgateway/agentgateway/blob/v1.5.0/schema/cel.md), [releases](https://github.com/agentgateway/agentgateway/releases) | section 8 field names; 1.6 `local[].key` and `requiredClaims`; 1.7 stateless MCP sessions |
| [Kata networking](https://github.com/kata-containers/kata-containers/blob/main/docs/design/architecture/networking.md), [Helm configuration](https://github.com/kata-containers/kata-containers/blob/main/docs/helm-configuration.md), [limitations](https://github.com/kata-containers/kata-containers/blob/main/docs/Limitations.md), [qemu configuration](https://github.com/kata-containers/kata-containers/blob/main/src/runtime/config/configuration-qemu.toml.in), [guest Landlock](https://github.com/kata-containers/kata-containers/blob/main/tools/packaging/kernel/configs/fragments/common/landlock.conf), [CVE-2026-44210](https://db.gcve.eu/vuln/CVE-2026-44210) | section 5 |
| [kube-router how it works](https://github.com/cloudnativelabs/kube-router/blob/master/docs/how-it-works.md) and [troubleshooting](https://github.com/cloudnativelabs/kube-router/blob/master/docs/troubleshoot.md), [K3s network policy](https://github.com/k3s-io/docs/blob/main/docs/networking/networking-services.md), [Kubernetes network policies](https://github.com/kubernetes/website/blob/main/content/en/docs/concepts/services-networking/network-policies.md) | host-side enforcement, fail-open window, no `ipBlock` for ClusterIPs |
| [SPIRE issue 4531](https://github.com/spiffe/spire/issues/4531), [k8s\_psat attestor](https://github.com/spiffe/spire/blob/main/doc/plugin_server_nodeattestor_k8s_psat.md) | why SVIDs are deferred and how they would be issued inside a Kata pod |
| [agent-sandbox types](https://github.com/kubernetes-sigs/agent-sandbox/blob/main/api/v1beta1/sandbox_types.go) and [threat model](https://github.com/kubernetes-sigs/agent-sandbox/blob/main/docs/security/threat_model.md) | optional warm pools; its default NetworkPolicy must be replaced |
| [Keycloak 26.2 standard token exchange](https://www.keycloak.org/2025/05/standard-token-exchange-kc-26-2), [26.6 release notes](https://github.com/keycloak/keycloak/blob/main/docs/documentation/release_notes/topics/26_6_0.adoc), [26.8 release notes](https://github.com/keycloak/keycloak/blob/main/docs/documentation/release_notes/topics/26_8_0.adoc) | section 7 |
| [Authentik token exchange](https://github.com/goauthentik/authentik/blob/main/website/docs/add-secure-apps/providers/oauth2/token_exchange.mdx), [machine to machine](https://github.com/goauthentik/authentik/blob/main/website/docs/add-secure-apps/providers/oauth2/machine_to_machine.mdx) | section 7.9 |
| [Entra on-behalf-of flow](https://github.com/MicrosoftDocs/entra-docs/blob/main/docs/identity-platform/v2-oauth2-on-behalf-of-flow.md), [Entra agent identities](https://github.com/MicrosoftDocs/entra-docs/blob/main/docs/agent-id/agent-identities.md), [agent OAuth protocols](https://github.com/MicrosoftDocs/entra-docs/blob/main/docs/agent-id/agent-oauth-protocols.md) | section 7.9 |
| [AWS AgentCore identity](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity.html) | the token-vault pattern the APS follows |
| [Confidential Containers Trustee](https://github.com/confidential-containers/trustee/blob/main/README.md), [sealed secrets](https://github.com/confidential-containers/confidentialcontainers.org/blob/main/content/en/docs/features/sealed-secrets.md) | the attested-delivery successor to this design's credential model |

### 17.3 To confirm on the target cluster before Phase A

- [ ] `/dev/kvm` is exposed on every node that will run sandboxes, including the DGX Spark under DGX OS.
- [ ] The kubelet's rotated projected token is visible inside the Kata guest through virtio-fs within 60 s of rotation (T3 repeated after 8 minutes).
- [ ] kube-router's per-pod chain naming and comment format on the pinned K3s, so the attestor can find a pod's chain by IP and recognise its reject rule and ipset reference (5.5); and that `--sync-frequency=5s` on the kubelet brings the Downward API annotation file up to date within 5 s.
- [ ] TokenReview on the pinned Kubernetes returns the bound pod's name and UID in `user.extra` (`authentication.kubernetes.io/pod-name`, `pod-uid`) for projected tokens, which `POST /v1/token` relies on.
- [ ] The IdP accepts the projected token as a client assertion with the exact Keycloak 26.6 client settings (7.8); record the exported client JSON as the controller template.
- [ ] The delegation flow of 7.5 on the pinned Keycloak (T10a): federated JWT client authentication is accepted on the token-exchange grant, a TokenRequest-minted ServiceAccount token bound to a pod is accepted as that assertion, and an optional `mcp:<backend>` scope narrows the delegated token's `aud`; record the exact `act`, `aud`, `azp` and `scope` values.
- [ ] With `preserveToken: true`, agentgateway forwards the inbound `Authorization` header to the external-authorization service, and the APS's `headers` and `headers_to_remove` are applied to the upstream request after every other traffic policy (T7, T8, T12).
- [ ] The gateway's access-log record carries `agent.decision_id` and the `llm.tokens_*` attributes for every inference response, including error responses, so settlement can match reservations (T13, T13b).
- [ ] `llm.requestModel` is available to the route's authorization policy after the `URLRewrite` filter, the AI backend's `openai.model` setting overrides the request's model name (T7), and whether `llm.params.max_tokens` can be pinned per route (which would lower `reserve_tokens` from `maxModelLen`).
- [ ] `jwt.realm_access.roles` nested-claim syntax behaves as written in 8.8 on the deployed version.
- [ ] `AgentgatewayParameters.spec.service` accepts a fixed `clusterIP`; otherwise the Kustomize patch of 8.1 is used.
- [ ] Boot latency (including attestation), resident memory per sandbox and per-boundary overhead on each node type (T29).
- [ ] Kyverno's `pattern` evaluation of `serviceAccountName` against a label-derived value behaves as written in 6.5 (T22); if the variable substitution is not supported inside `pattern`, move that check into Rule 4's `deny` conditions.

Each item is owned by the engineer running Phase A and closed with the test ID and date in the auth inventory.

## 18. Review disposition (revision 2)

An external design review of revision 1 raised seven blocking findings, a set of implementation gaps and several architectural suggestions; every item was checked against the research behind this specification, and the table records what was accepted, what was adopted in a different form, and what was declined, with the section that changed.

| Finding | Verdict | Change | Where |
| --- | --- | --- | --- |
| 1. The external-authorization cache could reuse an allow decision for a different tool or model | **Accepted.** The cache key could not include the body fields the APS decides on; the defect was real regardless of what the gateway documentation says about cache keys. | Decision cache removed entirely; the APS caches inputs only; revocation bounds restated without a cache term | 3.7, 8.7, 9.4, T17, T19 |
| 2. A probe in the untrusted image cannot establish the network boundary | **Accepted with a different remedy.** The probe is now a platform-owned init container pinned by digest and enforced by admission, so no agent instruction runs before host-side denial has been observed; the code no longer retries after a leak; T2 is a 100-start adversarial measurement and section 16.3 records its result rather than assuming it. The enterprise profile adds node-level chain attestation. Declined: abandoning the probe, because K3s hard-codes kube-router's default-deny start-up option off, so a trusted observation at pod start is the strongest control available short of patching K3s. | 5.2, 5.4, 5.5, 6.5, 16.3, T2 |  |
| 2a. NetworkPolicy validation must examine effective permissions | **Accepted.** | Controller publishes a digest of the canonical policy set; preflight requires the exact set | 5.3, 10.3, T28 |
| 2b. Transport must be TLS | **Accepted.** | HTTPS listener with an internal CA is the reference profile; plain HTTP is development-only | 3.2, 5.2, 8.1, 16.2, T27 |
| 3. `requiredClaims`, token stripping and transformation order | **Accepted.** The reviewer's reading of the `requiredClaims` schema and of the policy order was not verified from primary sources in this session either; the replacement configuration is correct under both readings. | CEL `agents-only` policy; `preserveToken: true`; transformation policy removed, hygiene moved into the APS response | 8.5, 8.6, 9.6 |
| 3a. Keycloak requester and actor rules may not permit a broker to exchange with the agent as actor | **Accepted as a decision gate.** Neither reading could be verified; two contracts are specified and T10a chooses by evidence before any controller code depends on it. | Contracts A and B, provider adapter | 3.3, 7.3, 7.5, 9.5, T10a |
| 3b. Naming inconsistencies (delegation scope, client scope, tenant prefix, role names) | **Accepted.** | One canonical representation: the tenant name is the namespace name; scope `agent-gateway`; consent scope `delegation:client:...`; roles `agent-role-<backend>-read` | 3, 4, 7 |
| 4. Approval did not bind an immutable policy; admission was partial; `\|\| true` default | **Accepted.** | `policySha256` in the release spec, CRD immutability rules, drift makes a release not ready, optional attestation; admission matches every pod in a tenant namespace and pins the whole shape; the JMESPath default removed | 6.2 to 6.5, T9b, T20, T22 |
| 5. Replacement without confirmed deletion; acceptance before durable checkpoint; cleanup stopping at first failure; no cleanup after terminate | **Accepted.** | Generation fence recorded before creation; replace only after `DELETED`; commit after snapshot; independent, recorded cleanup steps; scheduled reconciler; business deadline as a timer | 10.1, 10.3, 10.5, 10.7, T21, T23, T24 |
| 6. Per-session budget enforced inside the sandbox | **Accepted.** | Per-session descriptor in the global rate limit keyed and limited from APS metadata, with an APS-side fallback if the policy order does not allow it; the guest counter is advisory; the overshoot contract is stated | 3.7, 8.9, 11.8, T13b |
| 7. No end-of-input signal; blocking calls in async activities; unvalidated guest output | **Accepted.** | Length-prefixed framing; synchronous activities in a thread pool; bounded, schema-checked, consistency-checked output | 10.4, 10.5, 11.8, T25 |
| Runner to APS network path; preflight reading undefined status fields; unspecified grant lookup | **Accepted.** | NetworkPolicy rule for the runner; `identityMode` and `delegationRequired` in the release status; `GET /v1/grants/{handle}` | 5.3, 6.2, 9.7 |
| RBAC not expressible as written; exec verb | **Accepted.** | Per-namespace Role and RoleBinding generated by the controller; `pods/exec` get and create | 9.1, 10.6 |
| MCP SDK interface mix | **Accepted.** | Pinned to the 1.x transport with explicit three-value unpacking and `timedelta` timeouts | 11.1, 11.5 |
| Inference bodies exceed the 64 KiB forward limit | **Accepted, resolved structurally.** | Inference bodies are no longer forwarded: the route names the backend, the backend pins the model, and a CEL pin repeats it | 3.2, 8.3, 8.5, 8.7, 9.2 |
| Token cache lost between boundary processes | **Accepted.** | Token persisted under `/sandbox/state`, token-route limit raised to 60 per minute | 3.4, 11.2 |
| Contradictory 401 handling; JSON sliced after serialization | **Accepted.** | One error contract (401 refresh once, 403 terminal, 429 budget); structural truncation before serialization | 11.2, 11.8 |
| agent-sandbox managed policy deleted rather than configured | **Accepted.** | Managed policy switched off through the controller's own setting | 5.2 |
| Token identifies the agent, not the session; "useless from any other pod" was too broad | **Accepted, with a stronger fix than requested.** | `jti` pinned to the first pod at the APS; claims restated precisely | 4.2, 9.3, 14.3, 16.1, T26 |
| IdP portability overstated; Entra claims misdescribed | **Accepted.** | Provider adapters and a conformance matrix; Entra actor identification corrected | 7.9, 9.5 |
| Read-only tools still need resource and data boundaries | **Accepted.** | Argument-level and RBAC boundaries stated per mode; data classification with Temporal payload encryption and artifact-store access rules | 4.4, 13.9 |
| Reduce ownership of the agent framework; evaluate an established framework inside the sandbox | **Recorded as a Phase D evaluation, not adopted now.** The boundary protocol, the manifest check and the admission rules depend on the one-boundary-per-exec model; the framework-facing surface (`create_agent`, `Tool`, `ctx.mcp`, the step contract) is small by design so a framework can be fitted behind it later without changing anything trusted. | 11.7, 15 (T30) |  |
| Keep the APS narrow; generate policy representations from one model | **Accepted in principle.** The bundle is already the single policy model; the controller derives rate-limit configuration and status from it; gateway CEL rules stay coarse and static. | 6.3, 8.8, 9 |  |
| Pin one reproducible deployment profile | **Accepted.** | Exact versions in 3.1; upgrades move the whole set | 3.1, 14.4 |
| Measure the cost of the boundary design | **Accepted.** | T29 with Phase A targets | 15 |
| Strengthen tests; relocate T6, split T9, qualify T17 and T18; add an agent-quality suite | **Accepted.** | T6 moved to a permitted vantage point; T9a/T9b; T17 restated without a cache; T18 kept as smoke with T23/T24 covering recovery; T19 to T30 added | 15 |

Two statements in the review were qualified rather than adopted. First, "the probe cannot establish the boundary": true for a probe shipped in the untrusted image, which is why it is now a trusted init container; a trusted observer running before any untrusted instruction does establish that the host chain existed at that moment, and the residual (connections that could be opened before that moment by something other than the guard) is exactly what T2 measures. Second, the review's descriptions of agentgateway's `requiredClaims` schema, its policy execution order and Keycloak's delegation checks are plausible and consistent with the documentation this specification could reach, but none was confirmed from primary text; the revised configuration is chosen so that it is correct whichever way those details fall, and the remaining uncertainty is carried as explicit test gates (T10a, T7, T8, T13b) rather than as assumptions in either direction.

### Revision 3

A second review round raised four points; two were checked against the cited primary sources and confirmed, two were accepted on their merits.

| Point | Verdict | Change | Where |
| --- | --- | --- | --- |
| Neither delegation contract matched Keycloak's documented flow, and delegation is a preview feature | **Confirmed from the Keycloak token-exchange guide** (requester = actor client, `actor_token` required, actor client needs Standard Token Exchange, FGAP v2 `delegate`, features `token-exchange-delegation` and `parameterized-scopes`). Both earlier contracts are withdrawn. | The APS authenticates as the agent client using a TokenRequest-minted ServiceAccount token bound to the sandbox pod, sends the agent's access token as `actor_token`, and requests `mcp:<backend>`; the sandbox's token route now terminates at the APS so the IdP token endpoint is never reachable from a sandbox; preview status is handled by realm isolation | 3.3, 4.2, 7.1, 7.3, 7.5, 7.6, 8.3, 9.1, 9.5, 9.7, 12.1, T10a |
| A 30-per-minute request limit is not a concurrency bound; local counters are per replica; the gateway counts after the response | **Confirmed from the agentgateway rate-limit page** (post-response counting, per-replica local counters, estimate-at-admission only for per-key local limits). | A reservation ledger in the APS's Redis is the hard ceiling: `reserve_tokens` is charged before dispatch against the session and agent-day budgets, settled from the access-log stream, charged in full if unsettled; concurrency is `floor(remaining / reserve_tokens)`; the gateway limits are a soft second layer; budget denials are 429 | 3.7, 3.8, 8.9, 9.1, 9.3, 9.6, 9.8, 16.2, 16.3, T13, T13b |
| The probe is evidence, not proof; a failed connection may mean an unavailable destination; the window and the zero-leak gate were still inconsistent | **Accepted.** | A node-level attestor verifies the pod's chain from the host and records it on the pod; the egress guard gates on that record through the Downward API (kubelet `--sync-frequency=5s`), and the APS requires a fresh attestation on every request; forbidden-address probes are diagnostics that alarm on success; T2 is split into the gate (T2a) and the engine measurement (T2b); the enterprise profile uses Cilium's start-closed endpoints | 5.2, 5.4, 5.5, 6.5, 9.3, 16.2, 16.3, 17.3, T2 |
| The boundary protocol is costly and its recovery contract excludes remote writes; writes need idempotency and reconciliation regardless | **Accepted.** The cost is measured (T29) with a persistent-process fallback for Phase D; the write contract is now specified so that admitting a write tool is a per-backend decision with a proof, not a change of architecture: key recorded before dispatch, receipt required for commit, read-back on unknown outcome, one re-issue under the same key, reconciliation by key | 10.1, 10.8, 16.2, 16.3 |  |
