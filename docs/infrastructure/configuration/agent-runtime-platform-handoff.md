# Agent Runtime Platform: handoff, 2026-11-02

State of the Agent Runtime Platform rollout, with **sections 4 and 5.1 updated
through the 2026-11-06 run 14 at 16:38:43 UTC**. Other sections retain
their historical dates. This handoff lets a fresh session continue implementing the
specification. Read this first, then the two reference docs next to it:

- [Agent Runtime Platform: cluster stages](agent-runtime-platform.md): where
  each manifest lives, stage enable order, deviations from the spec, rollback.
- [Phase A qualification](agent-runtime-platform-phase-a-qualification.md):
  how T1, T2a, T3 and T28 were run and what they found.
- [Claude guards](../operations/claude-guards.md): what a Claude session on
  rig0 may run itself and what it must hand to Al.

The specification is "Agent Runtime Platform — Implementation Specification"
(rev 2 as uploaded, the docs above call the current text revision 3). It is
committed here as [agent-runtime-platform-spec.md](agent-runtime-platform-spec.md),
copied verbatim from the claude.ai project file `Agent Runtime Platform —
Implementation Specification - v2.md`. It defines requirements R1-R11 and conformance tests
(T1-T17 core, plus T18+ added later; the Phase B gate is 22 tests).

---

## 1. Repositories and layout

| Repo | Visibility | Role |
|---|---|---|
| [X-McKay/zetra](https://github.com/X-McKay/zetra) | public | All platform process source under `platform/`: `aps` (Agent Policy Service, Go), `controller` (Registry Controller, kopf), `runner` (Temporal Session Runner), `agent-runtime` (SDK), `egress-guard`, `netpol-attestor`, `contracts`. The old OpenShell SDK sits beside it unchanged. CRDs in `deploy/platform/crds/`. |
| [X-McKay/kubani](https://github.com/X-McKay/kubani) (this repo) | private | GitOps and Ansible only: Kata, Kyverno, Keycloak, agentgateway, `apps/agent-platform/`, `apps/agents/<tenant>/<agent>/` (applied Agent + AgentRelease; approval is a PR here). |
| [X-McKay/zetra-agents](https://github.com/X-McKay/zetra-agents) | public | One agent per `agents/<name>/` (manifest, Agent def, Dockerfile). `release.yml` builds, signs keylessly, attests and publishes an **unapproved** AgentRelease + policy bundle as a GitHub release. Old POC in `legacy/`. Tag ruleset `release-tags` on `*/v*` is admin-bypass-only. Nothing there is applied to a cluster. |
| X-McKay/kubani-gpu-broker | public | vLLM sleep/wake lease broker, checked out on rig0 at `~/git/kubani-gpu-broker`. Not in the cloud sessions' repo scope. |
| X-McKay/zetra-template | — | Untouched until OpenShell is retired. |

Platform images live in `registry.almckay.io/platform/` (pushed unsigned;
Kyverno only verifies `registry.almckay.io/agents/*` in tenant namespaces, so
that is fine for now). Agent images live in `registry.almckay.io/agents/`.

Planning artifacts (claude.ai): gap analysis
<https://claude.ai/artifact/HoFgt7HUfMfgmjRLpDtJhy>, enterprise governance and
private Sigstore design <https://claude.ai/artifact/QtAKe5f1FRw3FQQYWjaVKB>.
Open plan PR: kubani#246 (supply chain and governance plan doc).

---

## 2. What is live

All Flux Kustomizations were Ready at 2026-11-02 13:30.

| Stage | Live | Key facts |
|---|---|---|
| P0, P1 | CRDs, `agent-platform` and `tenant-test` namespaces | |
| A0-A2 | rig0 is the sandbox node (`agent_sandbox_node`), Kata 4.3.1 RuntimeClass `kata-qemu-runtime-rs`, `tenant-test` closed by the four tenant NetworkPolicies, netpol-attestor | Phase A passed T1, T2a, T3, T28 (2026-10-31) |
| B1 | Kyverno chart 3.9.2 (v1.19.2), webhook scoped to `agentplatform.io/tenant` namespaces | |
| B2 | Sandbox-shape and ephemeral-container deny in Enforce; **Rule 1 keyless signature check in Enforce, fail-closed** | T9b run 4 passed 2026-11-01 21:17: unsigned image denied, signed v0.1.2 admitted. If Rekor or the registry is down, new tenant pods are refused. |
| Private Sigstore | Fulcio/Rekor/TUF at `fulcio/rekor/tuf.almckay.io`, trust roots in ConfigMap `kyverno/private-sigstore` | Complete 2026-11-01 18:11. Fulcio root SOPS-minted, fp `7A:2B:2F:90...65:29`, valid to 2031-11-01. The createcerts job is disabled because it regenerates the CA on every run. |
| B3 | Keycloak 26.8 (`idp.almckay.io`, `agents` realm, Kubernetes provider for projected SA tokens), aps-redis, ratelimit, APS, Registry Controller, Session Runner + 5-min cleanup Schedule over Temporal mTLS, agents Gateway (7 routes, 6 backends), Alloy access-log pipeline | `ai.almckay.io` unaffected. |
| Agents | `tenant-test/investigator` Agent Ready; release v0.1.2 **approved** (kubani#270), `signatureVerified` with 5 attestations, ratelimit 5M tokens/day. `tenant-test/conformance` Agent applied (kubani#272), no release yet. | |

### Not proven yet

- ~~No token has been issued~~ **Proven 2026-11-05 13:03 UTC**: the APS issued
  the first agent token after the Keycloak client attributes were corrected
  (`jwt.credential.issuer` / `jwt.credential.sub`, see the
  [Phase B qualification](agent-runtime-platform-phase-b-qualification.md)).
- ~~No session has run~~ **Completed 2026-11-05 14:05 UTC**: seven conformance
  sessions ran to `COMPLETED` through the Session Runner (run 5).
- ~~No sandbox has passed its network check~~ **Passed 2026-11-05**:
  `egress-guard ok: attested, gateway reachable` on every sandbox.
- The investigator release is **on-behalf-of with delegation required**, which
  is Phase C (RFC 8693), so it cannot run a session in Phase B as is. That is
  why the conformance agent exists.

---

## 3. Merged PRs by stage

| Stage | PRs |
|---|---|
| Code + staging | kubani#233, zetra#12, kubani#235 (rig0 sandbox flag) |
| Phase A | kubani#236 (CRDs, namespaces, kata-deploy, netpols, attestor), #237 (qualification doc) |
| Phase B prep | kubani#238 (Ansible `k3s_node_name` + join token), #239 (Kyverno B1), #240 (agentgateway 1.7.0 by digest), #241 (SOPS secrets), #243 (agents Gateway) |
| Governance / keyless | zetra#16 (keyless verification), kubani#244 (Rule 1 keyless, Audit), #245, #247 (ARC 0.15.0 runners for zetra-agents under Kata) |
| Runners | kubani#250 (runner/dind images mirrored), #252, #253 (dind sockets and `/var/lib/docker` on Memory emptyDirs: virtio-fs breaks unix sockets and BuildKit under Kata) |
| Sigstore | kubani#254 (13 images mirrored), #255 (`registries.yaml` on all 4 nodes), #256 (trillian netpol), #257 (SOPS Fulcio CA), #258 (`kyverno/private-sigstore`) |
| Keyless releases | zetra-agents#6 (keyless `release.yml`), #7 (python 3.12.16-slim by digest; vuln gate on fixable findings only), #8 (publish via REST). **investigator/v0.1.3** (run 41358415016) is the first fully published keyless release. |
| B2 | kubani#259 (policies + kyverno registry user), #260 (shape-rule anchors fix), #261 (Rule 1 Enforce, fail-closed) |
| B3 | kubani#262 (Keycloak, aps-redis, ratelimit), #263 (APS + Registry Controller), #264 (numeric port), #265 (controller image), #266 (Session Runner), #267 (investigator Agent + unapproved release), #268 (realm roles, attestation via env roots), #269 (gateway routes + Alloy), #270 (approve investigator v0.1.2), zetra#20 (controller fixes on zetra main) |
| Conformance | kubani#272 (conformance Agent + signer pin widened to conformance tags) |
| Guards | kubani#271 (hook + `.claude/automode.rig0.json`) |
| Ops | kubani#248 (rig0 swap, eviction, earlyoom off), #249 (Qdrant scrape) |

---

## 4. Open work in flight

Latest qualified rollout: kubani `aa5223cc` (kubani#276 and #325), run 14.
The unsigned admission fixture was subsequently staged unapproved by #326. The historical
state in section 2 is not the current readiness record. The latest live
check found investigator `Ready=True`; the grant for creating missing
realm scope mappings remains unverified, as described below.

| Item | Where | State / next step |
|---|---|---|
| **Guards durable fix** | kubani#273 **merged 2026-11-03** | The drop-in `.claude/automode.rig0.json` is on main. **Al must still install it on rig0 in a real terminal** (section 6 commands, now reading the file from main) and restart the rig0 session. Until then, rig0 sessions cannot open PRs on the public repos. |
| **Conformance agents** | **Approved and Ready**: `conformance-2026-11-06-fe7ac791` (`conformance/v0.1.6`) and `conformance-b-2026-11-06-e54fc106` (`conformance-b/v0.1.0`), #317 and #318; conformance-b Kyverno signer pin #319 | Both releases ran in runs 10 to 13. zetra-agents#16 supplies `probe_token_stash` and `probe_http(auth="stash")`; conformance-b has its own Agent and client identity. No further approval is needed for these already-approved releases. |
| **Broker decision** | **Retain brokers through T6/T7** | Selected during the 2026-11-06 session. Main sleep and auto-sleep remain disabled; fast retains 120-second level-1 auto-sleep; leases remain disabled. gpu-broker#5 is merged (`cba41ff`), and #276 selects its authenticated wake-probe image. No broker retirement is part of this rollout. |
| **vLLM API key and model capture** | **Deployed and T6/T7 qualified in run 14** (#276, #325) | Direct engine 401/200; successful captured completions use the backend key, contain no agent JWT, and report nonzero usage. Main capture is ARM64 `ef1a16f-arm64`. Existing gateway routes, authenticated fast watchdog and one fast sleep/wake cycle passed. Temporary T6 policies removed. |
| **CT log key backup** | **Done 2026-11-05**: `infrastructure/sigstore/ctlog-secret.enc.yaml` | Exported by Al on rig0 with the README procedure; four data keys and the MAC are ciphertext to the repo's age recipient. Deliberately not applied by Flux (`createctconfig` rewrites the Secret on CA rotation); re-export after each rotation. |
| **Conformance harness and T26** | **Run 14 passes nine selected tests, 94 checks; T26 first passed in run 13** | All three runner consumers use `ef1a16f` at `sha256:fd922ae7ec5ecc0eeb03cb14b6674d33ebfdbce40a9e43d7f3bda78cf5c52617`. zetra#42 admission and #43 full T19 harness are merged for the next batch; conformance v0.1.7 release is in progress. T4/T5/T12/T19 historical coverage limits remain explicit. |
| **MCP route** | **Works since 2026-11-05 21:14 UTC** | Agent-mode exchange needs the `mcp:*` scopes on `agent-policy-service` plus `scope=mcp:<backend>` (#299, zetra#29, APS `d4f2e05` by #301). With `fullScopeAllowed: false`, agent clients also need realm scope mappings for backend roles. Controller `624a0ba` (zetra#31) syncs these; the existing mappings are readable, but permission to create missing mappings remains unverified under FGAP v2. |
| **Registry Controller FGAP v2 permission** | **Grant unverified**; latest live check found investigator `Ready=True`, transition 2026-11-06 07:55:09 UTC | Historical POSTs to `/clients/{id}/scope-mappings/realm` failed with 403. Al applied `registry-controller-map-role-client-scope`; recent logs show only GET 200 for all three clients, with no POST observed. The controller skips existing mappings, so current readiness does not prove creation permission. Use Keycloak's admin-console permission evaluate tool; do not codify the grant script as a proven fix or widen permission without Al's decision. See qualification finding 14 and spec 7.5. |
| **Release build reliability** | dind OOMs during the 2026-11-06 degraded egress window; both required releases subsequently built | Run release tags one at a time and retry after egress recovers. The dind process responsible for growth is still unidentified; see qualification finding 15. |
| **Kyverno PolicyReports** | **Resolved 2026-11-05 21:04 UTC** (not a gap) | Reports are written: polling `ephemeralreports -n tenant-test` every second during a probe session showed two admission EphemeralReports (pass 1, pass 5, owner the sandbox pod) from the pod's first second, a third on its update, and the aggregated PolicyReport at 21:04:13. Sandbox pods live about 25 s and the reports are owned by the pod, so every listing taken after a run was empty. `background: false` is fine; the admission log and events are the durable evidence for sandboxes. The -v4 diagnostic (#298) is reverted. |
| Unrelated drafts | kubani#251, zetra#17/#18/#19, zetra-agents#4/#5 (codex branches) | Not part of this rollout; leave alone. |

---

## 5. Phase B conformance plan and roadmap

### 5.1 Next batch: admission and full T19 after T6/T7

Updated 2026-11-06 after run 14 (16:31:41 to 16:38:43 UTC). Nine selected
harness tests passed: T4, T5, T6, T7, T8, T11, T12, T19 and T26; all 94
checks are true. **This is not full Phase B acceptance.** Historical T19
passes cover five MCP cycles; the full 50 cycles within 10 seconds and model
routes await the reviewed new probe release. T12 covers agent-mode APS
exchange only. T4 needs all exact claim assertions; T5 needs a genuine human
token and actual API-audience case. Earlier failures remain recorded.

**T26, token binding: first qualified in run 13.** The workspace snapshot
channel carries the stashed token without putting it in task text. The
harness verifies the stash token's `jti`, then seeds another conformance
session and one conformance-b session from the snapshot. In run 13 both
recipients completed in generation 1 with three boundaries: the same-agent
request received 403 `deny.token_bound_elsewhere`, and conformance-b
received 403 `deny.pod_agent_mismatch`. All 13 checks are true; no APS log
was unreadable. The raw report records identifiers and snapshot hashes,
never the token.

Runs 10 to 12 exposed three distinct faults. The old tenant runner first
dropped `seed` (#320 aligned the consumers). Seed restore then copied donor
runtime state into a new session (zetra#39 limits seeds to `workspace/`,
finding 17). Finally image `12369f4` copied the corrected source without
reinstalling the runner wheel, so the worker still imported old code.
[zetra#40](https://github.com/X-McKay/zetra/pull/40) rebuilds and verifies the
installed package, and [kubani#323](https://github.com/X-McKay/kubani/pull/323)
aligns harness, tenant runner and cleanup reconciler on `e05c9ca` at digest
`sha256:4c0dca3e8687e338d24008ba263516839f0fb0663ae9f0d68f7a06036fb77bf9`.
Run 13 exercises that installed-package fix (finding 18), not merely the
source-copy diagnostic that preceded it.

**MCP capture remains live.** `capture:bc37532` on the Kubernetes MCP server
records method, path, status, APS-set `x-agent-*` headers and identifying
bearer claims, never the bearer or a body. Run 13 preserves T8's server
half and the agent-mode T11/T12 evidence. It does not exercise delegated
or native exchange. Run 11's model-summary and extra-call flakes and run
12's skipped MCP tool remain failed observations.

**T6/T7 passed in run 14; brokers are retained.** Al authorized the merges,
releases and downtime. Merged #276 supersedes closed #242 and deploys
`cba41ff` brokers, engine API keys, gateway/watchdog credentials, benchmark
authentication and the ARM64 capture sidecar. Main traffic follows
`llm-api:8000 -> broker -> llm-engine:8001 -> capture -> 127.0.0.1:8000`;
direct engine/probe port 8000 remains intact. Capture emits backend-key
equality only, never a key or its hash. #325 aligns all runner consumers.

The direct engine returned 401 then 200; both T7 chat completions were 200,
used the backend key instead of an agent JWT and reported nonzero usage at
the gateway and committed boundaries. Existing AI/main/fast/embeddings
routes, authenticated fast watchdog probes and one level-1 fast sleep/wake
cycle passed. Both temporary T6 policies were removed and no sandbox
remained. Main sleep remains disabled, fast auto-sleep remains enabled,
and GPU leases remain disabled. See the run 14 report and component digest
inventory in [qualification](agent-runtime-platform-phase-b-qualification.md).

**Registry Controller creation permission remains unverified.** The latest
recorded check found investigator `Ready=True` (07:55:09 UTC transition)
and only successful reads of existing realm scope mappings. The controller
skips existing mappings, so readiness does not prove that Al's
`map-role-client-scope` grant permits creation. Inspect effective permission
in Keycloak's admin-console evaluate tool before codifying the grant or
widening authority.

**Order**: qualify the reviewed full T19 probe (zetra#43, zetra-agents#17)
and admission cases T9a/T9b/T22 (zetra#42). #326 stages a deliberately unsigned
fixture with approval disabled; verify SignatureRejected and NoDrift before
its separate negative-test approval. Keep fixture mutations serialized with
T26. Continue T15/T20 revocation/drift and T25 protocol robustness, then the
remaining budget, recovery, cleanup and delegated-correlation requirements.
No missing case may be counted as a pass. The Keycloak grant script remains
uncommitted until its creation permission is actually verified.

The original 2026-11-02 rollout roadmap is retained below as history; its
first two steps have since progressed through the fourteen recorded runs.

1. **Conformance agent** in `tenant-test` (section 4): PR, merge, tag
   `conformance/v0.1.0`, confirm Kyverno admits it.
2. **Harness** in `agent-platform` that runs tests and writes a JSON report.
   First batch: **T4, T5** (token issuance). Then **T7, T8, T11, T19, T26**
   (gateway / APS). T6 and the T7 backend-key check originally depended on
   #242, now superseded by #276 with brokers retained.
3. **Remaining gate tests** in batches; record results in a Phase B
   qualification doc like the Phase A one.
4. ~~Capture ephemeralreports/policyreports on the first admitted tenant pod~~
   Done 2026-11-05: reports exist while the pod lives (see the Kyverno row above).

After Phase B:

- **Phase C**: RFC 8693 delegation (needed for the investigator release),
  Authentik app for the `keycloak-authentik-broker` (deferred).
- **Promotion and governance**: per-tenant dirs in `apps/agents/` with
  CODEOWNERS, two-tier Kyverno policies, promotion by digest
  dev → staging → prod. **Blocked on Al's answer** (section 8).
- **`agentctl dev` / `agentctl validate`** in zetra.
- Re-sign platform images keylessly.
- **Retire OpenShell**, then update zetra-template; keep the plaintext Temporal
  frontend until the zetra POC/Web/system worker no longer need it.

---

## 6. Operational constraints and lessons

**Nodes** (Al, 2026-10-31): rig0 is Al's primary workstation **and** the
sandbox node: desktop apps take priority, cluster workloads yield (~24 GiB
reserved, 16 GiB swap, kubelet eviction soft 6 / hard 2 GiB). strix has no
desktop and hosts Postgres, Traefik, registry, Prometheus (memory limits at
198% of capacity: burst risk). asio is the control plane, keep it light.
sparky is the dedicated GPU node (lost API server 3x on 2026-11-01, cause
unknown, back-burnered).

**Registry rule** (standing): use `registry.almckay.io` wherever possible;
mirror upstream images by digest to
`registry.almckay.io/mirror/<host>/<path>`. Anonymous pulls only via ClusterIP
`10.43.150.95:5000` from containerd; the public hostname needs a login, and
every login can push. rig0 `systemd-resolved` drops a share of DNS lookups,
another reason to mirror.

**Who runs what**:
- Al runs Ansible: `vault_password.sh` reads the macOS Keychain, so Claude
  cannot. Use `ANSIBLE_CONFIG=infrastructure/ansible/ansible.cfg` from repo root.
- **Release tag pushes** come only from the rig0 session, after Al types
  "yes push <tag>" in that thread (cloud sessions get 403).
- The rig0 session accepts approvals only typed by Al in its own thread.
- Claude cannot approve PRs (same GitHub account) but squash-merges on Al's
  explicit request.
- Cluster access goes through a Remote Control session on rig0
  (`~/git/kubani`). Always `KUBECONFIG=/home/al/.kube/config`.

**Guards** (see [claude-guards.md](../operations/claude-guards.md)). Hook
`.claude/hooks/pre-bash.sh` is loaded from the **main checkout**
`~/git/kubani`, which must be on `main` (it was on `arc-github-app` on
2026-11-02 15:21, so #271's hook was not live). Allows kubectl writes in
`tenant-*`, `agent-platform`, `auth`, `temporal`; flux reconcile; release tag
pushes; `sops --encrypt`. Always blocks writes in `flux-system`,
`kube-system`, `kyverno`, `vllm` (pod-restart exceptions), `database`,
`cache`, `ai-gateway`, `monitoring`, `registry`, `longhorn-system`;
cluster-wide policy/webhook/CRD/RBAC writes; secret/token/registry
user/htpasswd/age/cosign key creation; `daemon-reexec`; `gh variable|secret
set`; `flux uninstall`. Running a script written for Al counts as a bypass and
is denied. To install the durable auto-mode rules, Al runs on rig0:

```bash
cd ~/git/kubani && git status --short && git checkout main && git pull --ff-only
jq -e . .claude/automode.rig0.json >/dev/null && sudo install -D -m 0644 .claude/automode.rig0.json /etc/claude-code/managed-settings.d/50-kubani-automode.json
claude auto-mode config | jq '.allow[-5:]'
```

Stop if `git status` shows uncommitted changes. Invalid JSON in a managed file
stops Claude Code from starting, so keep the `jq` check.

**Secrets**: SOPS only (`.enc.yaml`), values minted randomly by Claude on rig0
and shredded (Al's choice 2026-10-31). Rotation must restart the consumer:
`secretKeyRef` env vars do not hot-reload. No cosign key, ever: signing is
keyless against the private Sigstore.

**Keycloak**: 26.8, `agents` realm, built-in Kubernetes identity provider for
projected SA tokens (fixed the JWKS blocker). The registry-controller client
needs the realm-roles scope and `fullScopeAllowed` (#268); Al patched the live
realm with kcadm on 2026-11-02 13:07.

**Temporal**: a separate Envoy mTLS endpoint in the `temporal` namespace for
the Session Runner (certs from cert-manager); the plaintext frontend stays for
the zetra POC until it retires.

**Sigstore / signing**: cosign 2.6.1 rejects `--trusted-root`, so the
controller verifies attestations with env roots. Tool images: cosign v2.4.1,
syft v1.54.1, grype v0.120.1, all mirrored. The CT log was reset once on Al's
explicit OK.

**Lessons**:
- **Dry-run the full stage** before merging (kubani#264 was a missed numeric
  port).
- **Build the controller image with `--no-cache`**: its uv cache can reuse a
  stale package.
- Kyverno: the API server drops `hostIPC/hostPID/hostNetwork: false`, so shape
  rules use conditional anchors `=(hostIPC): false`. Kyverno CLI is not
  available anywhere, so policy tests run on the cluster.
- Under Kata, virtio-fs breaks unix sockets and BuildKit: use Memory emptyDirs.
- Files copied to rig0 lose the execute bit; run them with `bash`.
- `!`-prefixed commands only run inside a Claude Code terminal, not in a
  cloud thread.
- `realm-agents.json` is parsed strictly on every Keycloak start and reloader
  restarts the pod on each change: free-form notes go only inside `attributes`
  maps (an `x-note` on a `scopeMappings` entry cost a 36-minute IdP outage on
  2026-11-05, #303/#306). `agent-platform-workloads` depends on `keycloak`, so a
  broken import also freezes agent-platform rollouts.
- Spec bugs found during implementation are fixed in PRs and recorded under
  "Deviations" in [agent-runtime-platform.md](agent-runtime-platform.md).

---

## 7. How to pick this up

1. Ask Al whether he has run the section 6 guard commands on rig0 (#273 is
   merged); if not, that is the first unblocker.
2. With a restarted rig0 session: open and merge the zetra-agents conformance
   PR and the gpu-broker PR (on Al's "merge"), then tag `conformance/v0.1.0`
   after Al's typed "yes push conformance/v0.1.0".
3. Watch the conformance pod's admission and capture the Kyverno reports.
4. Build the harness and run T4, T5.
5. Rework #242 and schedule the vLLM restart with Al.

---

## 8. Open questions for Al

- **Approvers**: which GitHub users/teams approve agent releases per tenant,
  and who approves platform-wide changes? ("just me" is a valid answer.)
- **Guards**: has the managed-settings drop-in been installed on rig0 (#273 is merged)?
- **#242 window**: when can both vLLM engines restart?
- **CT log key**: run the export one-liner from the impl thread (2026-11-02 14:34).

---

## 9. Side items

- 35 stale snap mount units on rig0; Qdrant is unpinned on rig0.
- strix memory requests 66%, limits 198% (2026-11-02).
- sparky API-server loss cause unknown (back-burner).
- `~/.claude/settings.json.bak` on rig0 (14:02) is invalid JSON.
- rig0 memory deep dive: project file `rig0/2026-10-31-rig0-memory-deep-dive.md`.
