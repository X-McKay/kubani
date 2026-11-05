# Agent Runtime Platform: handoff, 2026-11-02

State of the Agent Runtime Platform rollout as of **2026-11-03** (section 4
updated by the follow-up session; the rest as written 2026-11-02 23:15 UTC),
written so a fresh session with no prior context can continue implementing the
specification. Read this first, then the two reference docs next to it:

- [Agent Runtime Platform: cluster stages](agent-runtime-platform.md): where
  each manifest lives, stage enable order, deviations from the spec, rollback.
- [Phase A qualification](agent-runtime-platform-phase-a-qualification.md):
  how T1, T2a, T3 and T28 were run and what they found.
- [Claude guards](../operations/claude-guards.md): what a Claude session on
  rig0 may run itself and what it must hand to Al.

The specification is "Agent Runtime Platform — Implementation Specification"
(rev 2 as uploaded, the docs above call the current text revision 3). It is in
the claude.ai project files as `Agent Runtime Platform — Implementation
Specification - v2.md`. It defines requirements R1-R11 and conformance tests
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
- ~~No session has run~~ Sessions run through the Session Runner since
  2026-11-05; **none has completed yet** (blocked on the conformance budget,
  zetra-agents#13).
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

| Item | Where | State / next step |
|---|---|---|
| **Guards durable fix** | kubani#273 **merged 2026-11-03** | The drop-in `.claude/automode.rig0.json` is on main. **Al must still install it on rig0 in a real terminal** (section 6 commands, now reading the file from main) and restart the rig0 session. Until then, rig0 sessions cannot open PRs on the public repos. |
| **Conformance agent** | zetra-agents#10 (branch `claude/project-thread-plqntk`, `0c8c41a`) | Spec 15.1 probe tools; exempt from the forbidden-import check for T1/T8. Checks pass locally. Merge on CI green, then tag `conformance/v0.1.0` from rig0 (signed release), then copy the unapproved AgentRelease into `apps/agents/tenant-test/conformance/` and approve it by PR. |
| **gpu-broker probe fix** | kubani-gpu-broker#5 (branch `claude/project-thread-plqntk`, `c84bece`) | Wake probe sends the engine API key (`api_key_env`); ruff clean, 45 tests pass; not run against a real `--api-key` engine. Merge on CI green: CI then publishes `ghcr.io/x-mckay/kubani-gpu-broker:sha-<merge sha>`, which the reworked #242 must pin in `apps/vllm/broker*-deployment.yaml` (currently `sha-3a7f300`). |
| **vLLM API key** | kubani#242 (draft, `claude/vllm-api-key`) | **Stale**: re-lists Secrets `apps/agents/` already has and carries a stray, badly named file. Rework after the broker image exists. Applying it **restarts both vLLM engines** (main weight load takes minutes), so agree a time with Al. Needed for T6 and the T7 backend-key check. |
| **CT log key backup** | Impl thread | Claude cannot read the key (guard). Al runs the `kubectl ... | sops --encrypt` one-liner posted in the impl thread 2026-11-02 14:34, which writes `/tmp/ctlog-secret.enc.yaml` (ciphertext only); then check it is fully encrypted and open a PR. |
| **Conformance harness (T4, T5)** | Merged (kubani#275, #281); three runs on 2026-11-05 recorded in [agent-runtime-platform-phase-b-qualification.md](agent-runtime-platform-phase-b-qualification.md) | T4 and T5 still fail, now only on the conformance budget: `tokensPerSession 50000` is below the 131072-token reservation for `llm-main`. Next: merge zetra-agents#13, tag `conformance/v0.1.3` from rig0 after Al's "yes push", copy the unapproved AgentRelease into `apps/agents/tenant-test/conformance/`, approve by PR, set `CONFORMANCE_RELEASE`, run the Job again. Also pending: kubani#283 (controller and harness images from zetra `408cfab`), kubani#284 and zetra#27 (federated-jwt attribute keys). |
| **Kyverno PolicyReports gap** | Impl thread | No PolicyReports are written. Ruled out: flags (admissionReports, aggregateReports, enableReporting), RBAC, resourceFilters, network, OpenReports (off). **Confirmed 2026-11-05**: after 28 admitted tenant pods, `ephemeralreports`, `policyreports` and the cluster-scoped kinds are all empty, while the admission log shows `image attestations verification succeeded` and `validation passed`. Remaining suspect: no EphemeralReports for `background: false` policies. Likely fix: `background: true`. |
| Unrelated drafts | kubani#251, zetra#17/#18/#19, zetra-agents#4/#5 (codex branches) | Not part of this rollout; leave alone. |

---

## 5. Phase B conformance plan and roadmap

Al said "proceed with the spec rollout" on 2026-11-02 14:30. The Phase B gate
is **22 tests**. The harness exists for T4 and T5 (section 4) and has not run yet.

1. **Conformance agent** in `tenant-test` (section 4): PR, merge, tag
   `conformance/v0.1.0`, confirm Kyverno admits it.
2. **Harness** in `agent-platform` that runs tests and writes a JSON report.
   First batch: **T4, T5** (token issuance). Then **T7, T8, T11, T19, T26**
   (gateway / APS). T6 and the T7 backend-key check need #242 applied.
3. **Remaining gate tests** in batches; record results in a Phase B
   qualification doc like the Phase A one.
4. Capture ephemeralreports/policyreports on the first admitted tenant pod
   (PolicyReports gap above).

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
