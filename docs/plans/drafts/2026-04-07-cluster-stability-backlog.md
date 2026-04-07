# Cluster Stability Backlog

**Status:** Draft
**Created:** 2026-04-07
**Scope:** Cluster platform, networking, storage, workload operating model
**Out of scope for this document:** `ai-agents` and `nexus` architecture cleanup

---

## Goal

Reduce the chance that cluster activity degrades the rest of the household network, while giving the cluster a safer path to bring services back online.

This backlog is intentionally biased toward:

1. preventing cross-site networking surprises,
2. reducing baseline cluster noise,
3. making storage and scheduling topology-aware,
4. preserving required capabilities without assuming every capability must be always-on in the current form.

---

## Operating Assumptions

- The cluster spans two physical locations and uses Tailscale for node-to-node connectivity.
- K3s is intentionally bound to `tailscale0` for inter-node traffic.
- The cluster must remain usable as a homelab that coexists with household and workstation traffic.
- Three inference models must remain deployed and accessible, even if the implementation changes.

---

## Priority Order

| Priority | Item | Why first |
|---|---|---|
| P0 | Automate Tailscale-to-K3s route recovery | Existing known failure mode with direct cluster-wide blast radius |
| P0 | Add site-aware scheduling and node topology labels | Required before making safer placement decisions |
| P0 | Rework stateful storage placement and replication | Most likely source of sustained cross-site traffic |
| P1 | Introduce core, platform, optional, and recovery operating modes | Reduces steady-state cluster pressure |
| P1 | Preserve three model endpoints while redesigning inference operations | Keeps capability while shrinking operational risk |
| P1 | Add real namespace-level network isolation | Limits blast radius of noisy or misconfigured services |
| P2 | Create a lean observability profile | Reduce background traffic and disk churn |
| P2 | Build a controlled service re-enable matrix | Prevents reintroducing instability by accident |

---

## Backlog Items

### 1. Automate Tailscale-to-K3s Route Recovery

**Issue**

Node-to-node pod networking can silently break after a Tailscale restart, upgrade, or interface rebinding event.

**Root cause**

K3s and Flannel are bound to `tailscale0`, but the platform treats Tailscale as a prerequisite rather than a runtime dependency. When Tailscale changes state, Flannel routes may disappear and K3s is not automatically reconciled.

**Why this matters**

This is a cluster-wide availability risk, not just a node-local issue. It can cascade into DNS failures, service crashes, and operator confusion, and it is a known failure mode already documented in the repo.

**Change**

Make route recovery part of the node baseline so Tailscale state changes trigger deterministic K3s recovery and verification.

**Implementation scope**

- Add systemd drop-ins for `k3s` and `k3s-agent` that explicitly order them after `tailscaled`.
- Add a post-Tailscale recovery script that:
  - waits briefly for Tailscale stabilization,
  - restarts `k3s` or `k3s-agent`,
  - checks for expected pod CIDR routes,
  - exits non-zero on failure.
- Install and manage this through Ansible, not by manual node edits.
- Add a validation command or script for operators that checks:
  - `tailscale0` health,
  - pod route presence,
  - CoreDNS reachability from each site,
  - cross-node pod connectivity.
- Add this validation to provisioning and node-maintenance workflows.

**Non-goals**

- changing away from Tailscale-backed inter-node networking,
- changing CNI,
- broader service-level remediation.

**Acceptance criteria**

- a Tailscale restart on any node results in automatic K3s recovery or a clear failed state,
- missing pod routes are detected automatically,
- operators have one standard verification path after Tailscale or node maintenance,
- this behavior is provisioned by Ansible and survives node rebuilds.

**Risks and tradeoffs**

- automatic K3s restarts will briefly disrupt pods on the affected node,
- tying K3s more tightly to Tailscale is correct for this topology, but it increases the importance of clean Tailscale lifecycle handling,
- the recovery script must avoid restart loops.

**Open decisions**

1. Should recovery happen on every `tailscaled` restart, or only on package upgrade / explicit maintenance?
2. Do you want fail-fast behavior if route validation fails, or best-effort recovery plus alerting?
3. Should the verification live as an Ansible task, a shell script in `infrastructure/scripts/`, or both?

**Recommendation**

- restart K3s on every Tailscale restart for now,
- validate routes immediately after restart,
- fail loudly if routes are still missing,
- keep both an Ansible-managed install path and a reusable operator script.

---

### 2. Add Site-Aware Scheduling and Node Topology Labels

**Issue**

The cluster spans two physical locations, but placement decisions are not expressed in terms of physical topology.

**Root cause**

Nodes carry hardware and resource metadata, but the platform does not appear to model site as a first-class scheduling dimension. As a result, workloads can be scheduled in ways that are technically valid but operationally expensive over Tailscale.

**Why this matters**

Without explicit site awareness, you cannot make reliable decisions about where stateful services, noisy workloads, or latency-sensitive services should run. It also makes incident analysis harder because placement is driven by hostnames and ad hoc affinities instead of policy.

**Change**

Define site topology in inventory and propagate it into Kubernetes labels so manifests can make deliberate placement decisions.

**Implementation scope**

- Add mandatory node labels in inventory and provisioning for:
  - physical site,
  - network zone,
  - power/availability class,
  - optional workstation or constrained-node class where useful.
- Standardize label names under one namespace such as `topology.kubani.io/*`.
- Update Ansible node labeling so labels are applied and validated automatically during provisioning.
- Introduce scheduling rules based on these labels:
  - stateful services pinned to a primary site,
  - heavy or chatty services kept on same-site dependencies where possible,
  - constrained nodes excluded by default,
  - workstation nodes used only when explicitly allowed.
- Add documentation that explains the intended role of each site:
  - primary durable site,
  - secondary or overflow site,
  - low-power or constrained site if applicable.

**Suggested baseline labels**

- `topology.kubani.io/site`
- `topology.kubani.io/network-zone`
- `topology.kubani.io/power-class`
- `topology.kubani.io/usage-class`

**Non-goals**

- automatic multi-site failover,
- geo-redundancy,
- dynamic traffic engineering between sites.

**Acceptance criteria**

- every node has required topology labels,
- manifests can target a site without using hostnames directly,
- placement of stateful and heavy workloads is explainable from labels,
- provisioning fails or warns clearly when required topology labels are missing.

**Risks and tradeoffs**

- this adds some inventory and manifest complexity,
- poorly chosen labels can become another source of drift,
- if site definitions are too vague, they will not help during incidents.

**Open decisions**

1. What are the actual site names and which one is primary for durable services?
2. Do you want workstation nodes modeled separately from site, or folded into the same topology scheme?
3. Should low-memory nodes like `osprey` be globally excluded from optional workloads by default?

**Recommendation**

- keep topology labels minimal and operational,
- choose one primary site for durable services,
- separate site from node capability,
- stop using hostnames as placement policy except where unavoidable.

---

### 3. Rework Stateful Storage Placement and Replication

**Issue**

Stateful workloads are using storage patterns that are too generic for a two-site cluster and can create unnecessary cross-site traffic, slow recovery, and confusing failure modes.

**Root cause**

Storage choices are mixed across Longhorn, NAS-backed PVs, and local storage, but there is not yet a clear policy that says which data classes belong on which storage types and in which site. Longhorn replication defaults are cluster-oriented, not site-aware.

**Why this matters**

Databases and log stores are usually the first place where “the cluster feels noisy” turns into sustained network traffic. In a cross-site homelab, storage replication and recovery behavior must be intentional.

**Change**

Define an explicit storage policy by workload type and site, and stop relying on generic storage defaults for stateful services.

**Implementation scope**

- Define supported storage classes by role, not just by provisioner:
  - single-site durable block,
  - shared NAS RWX,
  - ephemeral local,
  - optional site-specific Longhorn classes if kept.
- Classify each stateful workload:
  - PostgreSQL: single-site durable primary plus backups,
  - Redis: local durable or disposable depending on usage,
  - Loki/monitoring: local durable with lower operational priority,
  - Qdrant/Neo4j: single-site unless there is a demonstrated need for cross-site availability,
  - model caches: local or NAS, but not accidental replicated block.
- Revisit Longhorn defaults:
  - replica count,
  - node selection,
  - anti-affinity/topology rules,
  - whether Longhorn should be used for databases at all in this topology.
- Audit every PVC and map it to an intended storage policy.
- Add backup and restore procedures as a first-class recovery mechanism instead of treating replication as the whole durability strategy.

**Non-goals**

- cross-site active/active databases,
- transparent storage failover across both locations,
- replacing every storage backend immediately.

**Acceptance criteria**

- each stateful workload has a documented storage strategy,
- no critical database depends on accidental cluster-wide replica placement,
- backup and restore is documented and testable,
- storage placement can be explained in terms of site and workload type.

**Risks and tradeoffs**

- reducing replication may reduce automatic failover,
- moving data to single-site storage increases the importance of backup hygiene,
- storage migrations will need careful sequencing.

**Open decisions**

1. Should PostgreSQL stay on Longhorn, move to a site-pinned local block class, or use a NAS-backed model?
2. Is Longhorn still worth keeping for this cluster, or only for a subset of workloads?
3. Which data stores actually need durability versus fast rebuildability?

**Recommendation**

- optimize for single-site correctness plus backup/restore, not cross-site live replication,
- keep shared NAS for RWX use cases,
- use Longhorn only where its tradeoffs are clearly worth it.

---

### 4. Introduce Core, Platform, Optional, and Recovery Operating Modes

**Issue**

Too many services behave like part of the permanent baseline, which makes the cluster harder to stabilize and harder to reason about during incidents.

**Root cause**

GitOps structure and service organization do not strongly distinguish between “must run for the cluster to be useful” and “nice to have when the cluster is healthy.”

**Why this matters**

In a homelab, the default operating posture should be conservative. Recovery should not require hand-editing individual manifests under stress.

**Change**

Define explicit operating tiers and wire them into GitOps entrypoints so the cluster can run in normal, lean, or recovery mode.

**Implementation scope**

- Classify services into:
  - `core`: ingress, certs, basic storage primitives, required databases,
  - `platform`: identity, UI, observability, supporting services,
  - `optional`: personal apps, experiments, heavyweight extras,
  - `recovery`: smallest supported subset for stabilization.
- Reorganize Flux/Kustomize entrypoints so these tiers are visible and selectable.
- Add overlays or alternate kustomizations for:
  - normal mode,
  - lean mode,
  - recovery mode.
- Define the minimum contract for each mode:
  - what is guaranteed on,
  - what is intentionally off,
  - what checks must pass before promoting to the next mode.
- Add one operator-facing runbook for mode transitions.

**Non-goals**

- per-service auto-scaling policy redesign,
- full environment split into dev/staging/prod,
- application-specific cleanup beyond operating mode boundaries.

**Acceptance criteria**

- recovery mode can be enabled without manually touching many separate manifests,
- optional services are clearly separated from the base platform,
- operators can answer “why is this on?” from the tier model alone,
- there is a documented progression from recovery to normal operation.

**Risks and tradeoffs**

- more GitOps structure can mean more indirection,
- misclassification of services can create hidden dependencies,
- multiple modes need ongoing maintenance.

**Open decisions**

1. Which services are truly core versus platform?
2. Should recovery mode be a distinct overlay or a scale-down profile over the normal manifests?
3. How much manual approval should be required to move from recovery to normal?

**Recommendation**

- keep the tier model simple,
- make recovery mode a first-class overlay,
- require explicit validation to move between modes.

---

### 5. Preserve Three Model Endpoints While Redesigning Inference Operations

**Issue**

Three model endpoints are required, but the current inference layout may be concentrating too much steady-state load and restart sensitivity onto one node and one operational pattern.

**Root cause**

The current setup satisfies the capability requirement, but it does not yet treat three-model serving as an explicit capacity and reliability design problem. “Accessible” and “always-hot in the current architecture” have been treated as equivalent.

**Why this matters**

The requirement is valid. The question is how to keep three endpoints available without letting inference serving dominate cluster behavior or incident recovery.

**Change**

Preserve three stable model endpoints, but explicitly define the serving contract, capacity model, and placement rules behind them.

**Implementation scope**

- Write down the contract for the three endpoints:
  - which endpoints must exist,
  - which workloads use each,
  - how fast each must recover,
  - whether all three must always be hot.
- Evaluate serving strategies while keeping three endpoints stable:
  - current three hot services with stricter budgets,
  - mixed hot/warm approach if acceptable,
  - dedicated inference node policy,
  - backend consolidation behind stable ingress if tooling supports it cleanly.
- Add hard operating constraints:
  - resource budgets,
  - placement constraints,
  - service priority,
  - restart ordering,
  - failure fallback behavior.
- Separate model-serving policy from generic app deployment:
  - inference should have its own operational runbook,
  - model changes should go through capacity review.
- Add a simple capacity worksheet:
  - GPU memory budget,
  - RAM budget,
  - model cache IO,
  - expected background traffic,
  - startup time and recovery expectations.

**Non-goals**

- reducing to fewer than three accessible model endpoints,
- changing model selection itself unless separately approved,
- building a complex inference mesh without clear benefit.

**Acceptance criteria**

- three model endpoints remain available by design,
- the chosen serving pattern has documented capacity limits,
- inference services have explicit placement rules,
- model serving can be restarted or recovered without guesswork.

**Risks and tradeoffs**

- keeping three endpoints hot may still be expensive,
- warm or staged startup models improve stability but may hurt latency,
- dedicated inference placement may reduce flexibility elsewhere.

**Open decisions**

1. Do all three endpoints need to be hot at all times?
2. Should one node be treated as inference-dedicated?
3. Is endpoint stability more important than backend implementation stability?

**Recommendation**

- preserve three endpoints,
- keep endpoint contracts stable,
- revisit whether all three need to be permanently hot,
- isolate inference operationally from the rest of the platform.

---

### 6. Add Real Namespace-Level Network Isolation

**Issue**

Workloads can likely communicate more broadly than necessary, which increases blast radius when a service is noisy, compromised, or misconfigured.

**Root cause**

Current network policies are too narrow and do not provide default-deny behavior across operational namespaces.

**Why this matters**

In a cross-site cluster, unrestricted east-west traffic is a direct reliability problem. It also makes debugging harder because unexpected traffic is allowed by default.

**Change**

Move to namespace-level default-deny ingress and egress, then explicitly allow required service paths.

**Implementation scope**

- Create a baseline policy set for each operational namespace:
  - deny all ingress,
  - deny all egress,
  - allow DNS,
  - allow same-namespace traffic where needed,
  - allow ingress-controller-to-service traffic,
  - allow specific app-to-db/cache/service paths.
- Introduce these policies gradually, namespace by namespace, starting with the least risky.
- Document the expected dependencies for each namespace before writing allow rules.
- Add smoke tests to verify approved traffic flows still work.
- Treat new cross-namespace traffic as a reviewed dependency, not an implicit convenience.

**Non-goals**

- zero-trust service mesh,
- deep L7 policy,
- immediate lock-down of every namespace in one pass.

**Acceptance criteria**

- every operational namespace has explicit baseline network policy,
- approved service paths work,
- unexpected east-west communication is blocked by default,
- dependency paths are documented.

**Risks and tradeoffs**

- policy rollout can break existing traffic if dependencies are incomplete,
- debugging will be more policy-aware,
- operational docs must stay current.

**Open decisions**

1. Which namespace should be the pilot rollout?
2. Do you want egress controls introduced immediately, or ingress first then egress?
3. How strict should same-namespace traffic be?

**Recommendation**

- roll out namespace by namespace,
- use full default-deny ingress and egress from the start in the pilot namespace,
- keep allow rules narrowly scoped and documented.

---

### 7. Create a Lean Observability Profile

**Issue**

Observability is valuable, but the cluster needs a lower-cost mode that preserves essential visibility without keeping full monitoring intensity online during recovery or stabilization.

**Root cause**

Monitoring and logging are configured as normal always-on services, without a clear low-impact profile tailored for homelab recovery mode.

**Why this matters**

During recovery, you need signal, not maximal telemetry. Over-collecting adds background traffic, disk churn, and operational overhead.

**Change**

Define a lean observability mode with reduced scrape scope, lighter retention, and a small set of required dashboards and alerts.

**Implementation scope**

- Define two observability profiles:
  - full,
  - lean/recovery.
- In lean mode:
  - reduce scrape targets to core infrastructure and a few key services,
  - lower scrape frequency for noncritical targets,
  - shorten retention,
  - disable nonessential extras where safe.
- Define the must-have signals for recovery:
  - node readiness,
  - pod failures,
  - ingress health,
  - storage health,
  - basic service availability,
  - route/network symptoms where practical.
- Review host-level scraping over Tailscale and reduce it where it adds more cost than value.
- Keep a minimal Grafana or dashboard set specifically for recovery operations.

**Non-goals**

- removing observability,
- redesigning the entire metrics stack,
- replacing Prometheus/Loki.

**Acceptance criteria**

- there is a documented lean observability profile,
- recovery mode uses less storage and network overhead than full mode,
- essential recovery signals remain available,
- observability can be promoted from lean to full in a controlled way.

**Risks and tradeoffs**

- too little telemetry can hide useful signals,
- profile switching adds another operational mode to maintain,
- reduced retention can limit historical debugging.

**Open decisions**

1. Which dashboards are truly required in recovery mode?
2. Is Loki part of recovery mode or only full mode?
3. Which remote or host-level exporters are worth scraping across sites?

**Recommendation**

- keep Prometheus in lean mode,
- reduce scrape scope aggressively,
- decide whether Loki belongs in recovery mode based on actual troubleshooting value.

---

### 8. Build a Controlled Service Re-enable Matrix

**Issue**

Bringing services back online ad hoc makes it easy to reintroduce instability, overload dependencies, or miss validation checkpoints.

**Root cause**

There is no explicit, reviewed, dependency-aware sequence for bringing the cluster from recovery to normal operation.

**Why this matters**

The difference between a stable recovery and a second outage is often just sequencing and validation discipline.

**Change**

Create a service re-enable matrix that defines service purpose, dependencies, footprint, risk, and bring-up order.

**Implementation scope**

- For each service, capture:
  - purpose,
  - tier,
  - dependencies,
  - resource footprint,
  - storage sensitivity,
  - site sensitivity,
  - allowed operating modes,
  - rollback or disable method.
- Define a standard bring-up sequence:
  - network and ingress primitives,
  - storage primitives,
  - required databases,
  - identity and essential platform services,
  - lean observability,
  - inference endpoints,
  - optional and personal workloads.
- Add validation gates between stages:
  - cluster health,
  - dependency health,
  - site traffic sanity,
  - resource headroom.
- Define stop conditions:
  - what signals mean “pause here, do not continue.”
- Put this in operator-facing documentation and treat it as the default recovery path.

**Non-goals**

- full incident automation,
- service-specific application redesign,
- replacing human judgment during recovery.

**Acceptance criteria**

- every major service has an entry in the matrix,
- the bring-up order is documented and dependency-aware,
- each stage has validation criteria,
- rollback steps exist for each major service class.

**Risks and tradeoffs**

- the matrix will age if not maintained,
- some service dependencies may be discovered late,
- too much process can slow simple recoveries.

**Open decisions**

1. Which services belong before inference and which after?
2. Do you want one global matrix or separate ones for platform, data, and optional workloads?
3. What concrete metrics define “resource headroom is sufficient”?

**Recommendation**

- start with one global matrix,
- keep stage gates simple and operational,
- treat re-enable order as part of the platform, not tribal knowledge.

---

## Suggested Implementation Phases

### Phase 1: Stabilize the Network Base

- Item 1: Automate Tailscale-to-K3s route recovery
- Item 2: Add site-aware scheduling and node topology labels

### Phase 2: Make Stateful Services Topology-Safe

- Item 3: Rework stateful storage placement and replication
- Item 6: Add real namespace-level network isolation

### Phase 3: Reduce Steady-State Pressure

- Item 4: Introduce core, platform, optional, and recovery operating modes
- Item 7: Create a lean observability profile

### Phase 4: Restore Capability Safely

- Item 5: Preserve three model endpoints while redesigning inference operations
- Item 8: Build a controlled service re-enable matrix

---

## Open Questions

1. Which nodes belong to each physical site, and which site should host the primary stateful workloads?
2. Which services are truly household-critical versus “nice to have when the cluster is healthy”?
3. For the three-model requirement, what is the actual availability target:
   - always hot,
   - warm within minutes,
   - or reachable through a stable endpoint with controlled cold start?
4. Which workloads are allowed to use cross-site storage or cross-site high-frequency traffic?
5. Which node should be considered the dedicated inference host, if any?

---

## Definition of Done for This Backlog

This backlog is complete when:

- the cluster has an explicit two-site operating model,
- network recovery from Tailscale events is automated,
- stateful storage placement is intentional,
- optional workloads are no longer treated as inseparable from the base platform,
- three model endpoints remain available under a documented capacity plan,
- and service bring-up is governed by a repeatable recovery sequence.
