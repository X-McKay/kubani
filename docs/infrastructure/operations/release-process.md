# Platform Release Process

The shared process behind every hot-path or data-bearing change on this
cluster: vLLM, gpu-broker, agentgateway, Traefik, Authentik, PostgreSQL,
Longhorn, and host driver or OS changes on any node. It exists because a
change to any of these can take real traffic down, corrupt data, or wedge
silently, and the same shape of discipline — measure before, change one
thing, measure after, be ready to revert — pays off on all of them.

`docs/infrastructure/inference/release-process.md` is the **inference
profile** of this process: same shape, plus vLLM-specific tooling and
gates. Treat this document as the parent and that one as a specialisation;
when they seem to disagree, the inference doc wins for vLLM changes.

## Scope

Applies to any change to:

- vLLM (image, serve flags, `model-config`)
- gpu-broker (config, sleep/wake policy)
- agentgateway (routes, models, policies, once it exists — Phase 2)
- Traefik (entry points, middleware, TLS)
- Authentik (providers, blueprints, version)
- PostgreSQL (version, extensions, backup configuration)
- Longhorn (version, replica count, storage class defaults)
- Host driver or OS changes on any node (kernel, NVIDIA driver, DGX OS)

Manifest changes that do not touch serving behaviour or data durability
(resource limits, labels, probe timing tweaks) follow the ordinary
[deploying-services.md](../gitops/guides/deploying-services.md) workflow
instead — this process is for changes with a real chance of an outage or
data loss.

## The shape

Every release, regardless of profile, goes through the same eight steps:

1. **Change record** — one file, written before anything changes.
2. **Preflight** — validate the candidate with no production impact.
3. **Baseline** — know the current numbers before you touch anything.
4. **Ring 1 canary** — the least critical instance first.
5. **Gate** — a number crosses a threshold, not an impression.
6. **Soak** — the gate holding under real traffic for a defined window.
7. **Decision** — promote, hold and investigate, or revert.
8. **Rollback** — a `git revert`, verified the same way the rollout was.

### Rings

Ring 0 = preflight (no cluster impact). Ring 1 = canary — the smallest
blast radius that proves the change (the `fast` vLLM model, a shadow
gateway hostname, one node of a multi-node service). Ring 2 = production —
the change is live where it matters (the `main` vLLM model, the real
hostname, every node). A stage moves to the next ring only after its gate
passes and its soak window elapses. These are the same ring definitions as
roadmap section 9.1; they are not redefined per profile.

### Rules that apply to every stage

Carried over from `docs/plans/ideas/2026-09-29-inference-platform-roadmap.md`
section 9.1, because they are process rules, not vLLM-specific ones:

1. **One PR, one variable, one ring.** A stage is a single Flux-applied
   commit whose message records the prior value. Nothing is applied
   imperatively except pod deletion for recovery and transient
   bench/preflight pods.
2. **Gates are numbers, not impressions.** "Pod is Ready" and "`/health`
   is 200" are never gates on their own.
3. **Rollback is a revert.** `git revert <stage sha>` then reconcile the
   affected Flux `Kustomization`. Flux owns the spec — never `kubectl
   rollout restart` or hand-edit a live object; Flux reverts a hand-edit
   within its 10-minute reconcile interval, which is exactly what doubled
   the 2026-09-25 outage (see
   `docs/troubleshooting/vllm-main-engine-hang-gb10.md`). Rollback is
   verified the same way the rollout was: a real completion or request,
   then the gate.
4. **Everything new gets requests and limits**, lands on the platform node
   (rig0) unless it must run per-node, and is added to
   [the capacity ledger](../cluster/capacity.md) before the PR merges.
5. **Stop the line** on: any Xid in `journalctl -k` on a GPU node, a soak
   stall, a FAIL verdict, node memory above its ceiling in the capacity
   ledger on any node, or an alert that was not expected. Revert first,
   diagnose second.

## Mandatory change-record fields

Every change record, in every profile, must fill in:

- **Rollback commit SHA** — recorded *before* the stage is applied, not
  after. If you cannot name the commit that undoes this stage before you
  apply it, the stage is not ready.
- **Capacity ledger check** — does this stage add or resize a workload?
  If so, the ledger line in `docs/infrastructure/cluster/capacity.md` is
  part of the same PR, not a follow-up.
- **Resource readings** — three readings against the signal table in
  roadmap section 9.3, at **T+15 min**, **T+2 h**, and **T+24 h** after the
  stage goes live. The T+24 h reading is what corrects the capacity
  ledger's starting-value estimate to an observed one.

See the [template](#change-record-template) below; it has a field for
each of these.

## Gateway profile

Once agentgateway exists (Phase 2), any change that touches routing
through it — a new backend, a policy change, a hostname cutover — uses
this profile in addition to the base shape:

- **Shadow hostname first.** Stand the change up on a hostname nothing
  points at yet (`ai.almckay.io` during Phase 2) before touching a
  production hostname.
- **Failover test.** Scale the backing broker (e.g.
  `gpu-broker-main`) to 0 replicas for one minute and confirm the gateway
  fails over to the configured alternate instead of erroring.
- **Cutover per hostname, not all at once.** `llm-fast.almckay.io` first,
  then `llm.almckay.io`, then `embeddings.almckay.io` — each is its own
  stage with its own gate and soak window.
- **401 count as a gate.** Zero unexpected 401s from known clients over
  the soak window. A client that should have a virtual key and does not
  is a stage blocker, not a follow-up.
- Traefik's IP does not change on a gateway cutover (only the Ingress
  backend does), so rollback has no DNS propagation delay — reverting the
  Ingress commit is immediate once Flux reconciles.

## `releases/` directories

Each profile keeps its own change records under its own `releases/`
directory, so a reader looking at one profile is not wading through the
other's history:

- `docs/infrastructure/inference/releases/` — vLLM, gpu-broker (exists
  today; see `docs/infrastructure/inference/release-process.md`)
- `docs/infrastructure/operations/releases/` — every other profile
  (Traefik, Authentik, PostgreSQL, Longhorn, host OS/driver, agentgateway
  once it lands); see [releases/README.md](releases/README.md)

## Change record template

```markdown
# <YYYY-MM-DD> <change title>

**Status:** planned | in progress | released | rolled back
**Profile:** inference | gateway | platform
**Scope:** <which component(s): vLLM, gpu-broker, agentgateway, Traefik,
Authentik, PostgreSQL, Longhorn, host>
**Window:** <when the change applies / any downtime expected>

## Change
| | Before | After |
|---|---|---|
| Version / image | | |
| Flags / config | | |

## Why
<problem this solves, evidence, upstream refs>

## Risks and rollback
**Rollback commit SHA:** `<sha>` — filled in before the stage is applied.
<known issues; what rollback actually does>

## Capacity ledger check
<does this add or resize a workload? line added to capacity.md: yes/no/n-a>

## Stages
1. Preflight: `<command>` → <result>
2. Ring 1 (<canary>): <change> → gate <PASS/WARN/FAIL>
3. Ring 2 (<production>): <change> → gate <PASS/WARN/FAIL>
...

## Resource readings
| | T+15 min | T+2 h | T+24 h |
|---|---|---|---|
| Node memory % (affected nodes) | | | |
| Pod restarts | | | |
| Other signal from roadmap 9.3 relevant to this change | | | |

## Decision
<kept / reverted, and why; ledger corrected from the T+24h reading: yes/no>
```

## Related documentation

- [Inference release process](../inference/release-process.md) — the vLLM
  profile, with its own tooling and gates
- [Capacity ledger](../cluster/capacity.md)
- [Platform releases](releases/README.md)
- [Scheduled audit](scheduled-audit.md) — the drift bench this process
  feeds into monthly
- `docs/plans/ideas/2026-09-29-inference-platform-roadmap.md` sections
  9.1–9.6 — the rollout rules this document generalises
