# Kubani cluster audit — 2026-05-09

Read-only review of the cluster against the manifests in `infrastructure/`, the live state at the time of writing, and current upstream best practices.

---

## Genuinely broken right now

These are not "suboptimal" — they are actively wrong or unpatched, and worth fixing before anything else on the list.

1. **K3s `v1.28.5+k3s1` is ~1.5 years past upstream EOL.** Kubernetes 1.28 ended support on 2024-10-28; latest is 1.35 ([endoflife.date/kubernetes](https://endoflife.date/kubernetes)). There is no patch stream for any Kubernetes-side CVE since then. The cluster also misses every kubelet, scheduler, controller-manager and kube-apiserver fix from 1.29–1.35. K3s itself ships those upstream patches plus its own; 1.28.x has not had a release in over a year.
2. **cert-manager `v1.13.3`** is on a branch that has not had a release since early 2024. v1.18.6 / v1.19.4 / v1.20.0 (Feb–Mar 2026) ship fixes for CVE-2025-68121 and CVE-2026-24051 ([cert-manager releases](https://cert-manager.io/docs/releases/)). Today's pods are unpatched against both.
3. **`authentik-server` is in a restart cycle** (26 restarts in 16 days; `Back-off restarting failed container` 157× in 16d; readiness probe failing 649× in 19d; "context canceled / failed to proxy to backend" in logs). It currently reports 1/1 Ready, so monitoring won't catch it. The pattern matches Authentik's known issue where the embedded outpost router stalls under brief Postgres latency spikes; chart `2024.10.4` is ~1.5 years old (current is `2026.2.2`) ([goauthentik/helm releases](https://github.com/goauthentik/helm/releases)).
4. **`authentik-tls` Certificate has been `Ready=False` since 2025-12-07** (153 days). Reason: `IncorrectCertificate — Secret was issued for "authentik-cert"`. There are two Certificate resources in the `auth` namespace pointing at the same `authentik-tls` secret; only one wins. The serving cert is actually fine (renews 2026-06-05 via the other Certificate), but cert-manager is permanently in error. This matches the duplicate-Certificate pattern noted in `memory/duplicate_certificate_resources.md`.
5. **Cluster DNS truncation is recurring.** `kubectl get events` at audit time shows `DNSConfigForming — Nameserver limits were exceeded` for `coredns-669dfd6bc6-4xdw4` and `prometheus-prometheus-node-exporter-fql9k` within the last 3 minutes, with the kept nameserver line `1.1.1.1 8.8.8.8 192.168.86.1`. The 2026-04-06 outage fix was incident-specific; the underlying condition (host `/etc/resolv.conf` carrying ≥4 nameservers) re-establishes whenever NetworkManager rewrites it. Today it happens to drop the bad upstream and keep the good ones — next time it may not.
6. **`flux-system` GitRepository is intermittently failing**: `unable to list remote for ssh://git@github.com/X-McKay/kubani: dial tcp: lookup github.com on 10.43.0.10:53: server misbehaving / i/o timeout`, latest 17 minutes ago. Same root cause as #5 (CoreDNS resolving via a bad upstream). Reconciles eventually succeed but it is a precursor to a wider outage.

---

## Executive summary — top changes, priority-ordered

| # | Change | Effort | Payoff |
|---|--------|--------|--------|
| 1 | Plan and execute a K3s upgrade path off 1.28 (1.31 LTS or 1.33+). Pair with cert-manager → 1.20 in the same maintenance window. | **L** | Largest single security and supportability gain. Keeps you on a stream that gets CVE fixes; unblocks every other "modern best practice" recommendation in this doc (PSA latest, Longhorn ≥1.10, Authentik 2026, Flux v2.8 server-side apply features). |
| 2 | Migrate Bitnami workloads off the doomed `charts.bitnami.com` repo. PostgreSQL → CloudNativePG (replaces the chart, the `:latest` hack, and the home-grown backup CronJob). Redis → either `bitnamilegacy` for now or a small in-repo manifest pinning a specific upstream `redis:` tag. | **M-L** | Removes a hard external risk. Bitnami's free chart repo stops getting updates ([Bitnami issue 35164](https://github.com/bitnami/charts/issues/35164)) — you are one Helm-upgrade-on-a-removed-tag away from a stuck reconcile. CNPG also gives you WAL-shipped object-storage backups, replacing the bespoke pg_dumpall CronJob. |
| 3 | Decide and implement an auth posture for the unprotected ingresses. `registry.almckay.io` has zero auth at any layer; `temporal.almckay.io`, `falkordb.almckay.io`, `qdrant.almckay.io`, `llm.almckay.io`, `llm-fast.almckay.io`, `embeddings.almckay.io` rely on app-layer auth or "Tailscale is the perimeter." Either add the `authentik-auth@kubernetescrd` middleware (where the backend tolerates header-based auth) or document the trust boundary. | **S-M** | Plugs the largest residual exposure. `registry:2` with `REGISTRY_STORAGE_DELETE_ENABLED=true` and no auth means anyone reachable can replace your cluster's images. |
| 4 | Fix DNS at the host so the resolv.conf truncation can't recur. Pin nodes to ≤3 trusted resolvers (1.1.1.1, 8.8.8.8, optionally `192.168.86.1`) via systemd-resolved configuration in the `bootstrap` Ansible role; lock the file or NetworkManager dispatcher script that owns it. | **S** | Closes the loop on the 2026-04-06 incident class. Prevents Flux/CoreDNS DNS-on-DNS failure. |
| 5 | Adopt a "don't keep building bespoke solutions" posture: replace the postgres-backup CronJob with CNPG-managed backups (#2 above) **and** the home-grown observability stack with VictoriaMetrics single-binary (Prometheus, Alertmanager, Loki targets are all at 0 replicas anyway). Single-binary VM uses ~5× less RAM than Prometheus at homelab scale and configures via flags ([VictoriaMetrics single-server](https://docs.victoriametrics.com/victoriametrics/single-server-victoriametrics/)). | **M** | Reduces repo surface area meaningfully. Today the `monitoring` HelmReleases (Prometheus 25.27.0, Grafana 8.5.2) reconcile every 10 min for workloads at `replicas: 0`. |

Items #1 and #2 are coupled: Authentik 2026.x and Longhorn ≥1.10 both want a recent kubelet, and Bitnami's removal of `bitnami/postgresql:<tag>` is the kind of hard break that surfaces during the same maintenance window.

---

## Findings by area

### Simplification

#### S1. Retire the home-grown postgres-backup CronJob in favour of CNPG.
- **Current state.** `infrastructure/gitops/apps/postgres-backup/cronjob.yaml` runs `pg_dumpall | gzip` to a 1Gi local-path PVC, retains 3, runs as nonRoot, atomic-renames the file. Solid implementation. But it: depends on the Bitnami postgres image (already EOL-bound, see S6), keeps backups on a single local-path PVC on `strix` (one-disk failure = no backups), and is logically duplicated by the StatefulSet's own storage on the same node.
- **Why it matters.** The bespoke job is fragile to two unrelated changes (Bitnami image removal, strix disk loss) and produces logical dumps only — no PITR.
- **Recommendation.** Migrate `postgresql` to CloudNativePG ([cloudnative-pg.io](https://cloudnative-pg.io/)). Configure `barmanObjectStore` against the NAS (or any S3-compatible target). You get WAL streaming, scheduled base backups, instant snapshots, and PITR — which the current setup does not. The `database/nas-backups` PV (NAS, RWX, 100Gi) is already wired to this namespace; point CNPG at it via an `s3`-compatible gateway, or repurpose for restore staging.
- **Effort.** M. Migration playbook is well-documented ([CNPG migration guide](https://www.enterprisedb.com/blog/migrating-postgresql-cluster-to-cloudnativepg)). The `authentik` and `temporal` databases are the only consumers; both can be re-bootstrapped from the dump if rollback is needed.

#### S2. Replace the Prometheus stack with VictoriaMetrics single-binary, or remove it.
- **Current state.** `monitoring` namespace owns: Prometheus chart 25.27.0, Grafana 8.5.2, Alertmanager (NAS-backed PVC). All three Deployments are at `replicas: 0` per the audit context. Only `prometheus-prometheus-node-exporter` (DaemonSet) is actually running. The HelmReleases continue to reconcile every 10 min and have accumulated v333–v337 / v3–v7 release Secrets.
- **Why it matters.** The current state is a cost (reconciles, repo complexity, six PVCs of various kinds) without a benefit (no metrics being scraped). When you turn it back on, you'll be running a stack that's overkill for one site, four nodes.
- **Recommendation, two options.**
  - **(a) Lighter:** Delete the `monitoring` Kustomization and the `prometheus-prometheus-node-exporter` DaemonSet. Move metrics to VictoriaMetrics single-binary (`victoria-metrics-single` chart, ~50 MiB RAM idle, no Operator, no CRDs) with `vmagent` for scrape and Grafana from the same chart bundle. Drop-in compatible with PromQL ([VictoriaMetrics single-server](https://docs.victoriametrics.com/victoriametrics/single-server-victoriametrics/)).
  - **(b) Even lighter:** Don't run cluster monitoring at all. Use `kubectl top`, the cluster-status / validate / troubleshoot commands you already have, and Tailscale's own metrics for node-level. You're scaled to 0 anyway.
- **Effort.** M for (a), trivial for (b). The decision is whether you want graphs.

#### S3. Delete what's already orphaned. (Cleanup; surfaces hidden state.)
- **Stale ClusterRoleBindings:** `headlamp-admin → headlamp/headlamp` SA in a namespace that doesn't exist; `dynamo-platform-dynamo-operator-{leader-election,dgdr-profiling,manager,dynamo-queue-reader,proxy}` (5 bindings) → a `dynamo` namespace that doesn't exist. All grant `cluster-admin` or wide cluster verbs to ServiceAccounts that have been gone since the agent/UI/Nexus removal in PR #44. Each is a latent privilege-escalation if anything ever recreates that SA name.
- **Released PVs not cleaned up:** the two released NAS graph/vector PVs and `pvc-cbfbf4df-...` (was `monitoring/storage-loki-0`). All `Released` since storage migrations months ago.
- **Stale NetworkPolicy:** `vllm/tmp-allow-egress-model-downloaders` selecting `job-name in (download-qwen36-fp8)` — the job completed 15 days ago; the policy targets a label that no current pod carries.
- **Stale PDB:** `cache/redis-replicas` exists but `replica.replicaCount: 0` in the HelmRelease, so it has nothing to protect.
- **Released NAS PVs with no current claim:** the two retired graph/vector NAS volumes (10Gi each). Worth confirming the data inside is no longer needed before removing.
- **Effort.** S. All of these are `kubectl delete` of a single object once you've decided.

#### S4. Sources directory is a list of HelmRepositories — most are still on the deprecated `v1beta2` API.
- **Current state.** `infrastructure/gitops/infrastructure/sources/*.yaml` mixes `source.toolkit.fluxcd.io/v1beta2` (most) and `source.toolkit.fluxcd.io/v1` (longhorn only).
- **Why it matters.** Flux v2.8 ([Flux releases](https://github.com/fluxcd/flux2/releases)) has `HelmRepository` `v1` GA. v1beta2 still works but each minor Flux upgrade tightens.
- **Recommendation.** Bulk-replace `source.toolkit.fluxcd.io/v1beta2` → `v1` for HelmRepository. Same for the deprecated Traefik CRD (see Sec5). One PR, no behaviour change.
- **Effort.** S.

#### S5. Migrate Traefik IngressRoute manifests off the deprecated `traefik.containo.us` API group.
- **Current state.** 5 IngressRouteTCP manifests still use `apiVersion: traefik.containo.us/v1alpha1` (postgresql, redis, temporal, the graph database, plus the README example). One ingress (prometheus) already uses `traefik.io/v1alpha1`.
- **Why it matters.** `traefik.containo.us` is removed in Traefik v3 ([Traefik v3 migration](https://doc.traefik.io/traefik/migration/v2-to-v3/)). The CRD is currently dual-installed by your K3s-bundled Traefik — you'll lose the old one on the next K3s upgrade.
- **Recommendation.** s/`traefik.containo.us`/`traefik.io`/ in those 5 files.
- **Effort.** S.

#### S6. Cluster-admin grants from K3s helm-bootstrap.
- **Current state.** `helm-kube-system-traefik-crd` and `helm-kube-system-traefik` ClusterRoleBindings grant `cluster-admin` to a job that has long since completed.
- **Why it matters.** These are issued by K3s' embedded helm controller; you can't simply delete them (K3s will recreate). But any future K3s upgrade will re-run those jobs with cluster-admin too. Documented as known K3s behavior — flagging so you're aware that if you ever switch to a non-K3s install, this exposure goes away.
- **Effort.** N/A — informational.

---

### Security

#### Sec1. Most public Ingresses bypass Authentik.
- **Current state.** Out of 10 Ingress resources, only `monitoring/prometheus-ingress`, `monitoring/grafana-ingress`, and `auth/authentik-ingress` have any auth middleware. The others rely on the backend's own auth, or on the assumption that the Tailscale IP they resolve to is not reachable to attackers.

  | Host | Backend | Auth at edge | Backend auth |
  |---|---|---|---|
  | `auth.almckay.io` | authentik-server | n/a (this is the IdP) | self |
  | `grafana.almckay.io` | grafana | **authentik middleware** | grafana |
  | `prometheus.almckay.io` | prometheus | **authentik middleware** | none |
  | `temporal.almckay.io` | temporal-web | **none** | none in current install |
  | `registry.almckay.io` | docker registry:2 | **none** | **none** (no htpasswd, no token-server) |
  | `qdrant.almckay.io` | qdrant | **none** | API key (if configured) |
  | `falkordb.almckay.io` | falkordb browser | **none** | password |
  | `llm.almckay.io` | vllm | **none** | none (no `--api-key`) |
  | `llm-fast.almckay.io` | vllm-fast | **none** | none |
  | `embeddings.almckay.io` | vllm-embeddings | **none** | none |

- **Why it matters.** All `*.almckay.io` resolve via external-dns to the Tailscale IPs (100.x.y.z). This *implicitly* gates access to "anyone on the tailnet." Three problems with that model:
  1. K3s ServiceLB (`svclb-traefik` DaemonSet) binds the Service ports on **every node IP**, including the LAN IP, not only `tailscale0`. Anyone on the LAN can hit `http://192.168.x.y:80` with `Host: registry.almckay.io` and bypass the Tailscale assumption entirely. Verified: `traefik` Service has no `loadBalancerSourceRanges` and the DaemonSet binds `0.0.0.0`.
  2. The registry has zero auth at any layer **and** allows deletion (`REGISTRY_STORAGE_DELETE_ENABLED=true`). LAN access alone is enough to overwrite any image the cluster pulls.
  3. The Temporal Web UI exposes workflow data, including arguments and results, which often contain secrets.
- **Recommendation.**
  - **Registry:** Add a Traefik `BasicAuth` middleware (htpasswd in a SOPS-encrypted Secret) **immediately** — it's the fastest fix. Longer term, use the registry's token-auth or replace with Harbor / Zot.
  - **Temporal Web:** Add `authentik-auth@kubernetescrd` middleware. Authentik's forward-auth flow works fine here.
  - **Graph DB HTTP:** Add Authentik middleware in front of the browser; the RESP port (`falkordb-resp` IngressRouteTCP) keeps its DB-level auth.
  - **vLLM hosts:** Add `--api-key $LLM_API_KEY` to the `vllm serve` args (env from a SOPS Secret) — that's how vLLM is meant to be deployed when Internet-adjacent. OpenAI-compatible clients all support `Authorization: Bearer …`.
  - **Qdrant:** It already speaks API key auth — set `service.api_key` via a Secret, drop the open ingress.
  - **K3s ServiceLB binding:** Either replace ServiceLB with MetalLB (or kube-vip) and bind to specific addresses, or — much simpler — remove the LB ports from non-Tailscale interfaces by setting `--service-lb-namespace` ranges or running `tailscale serve` on the node-side and dropping the LB altogether. Lowest-friction win is `loadBalancerSourceRanges: ["100.64.0.0/10"]` on the `traefik` Service if K3s' Klipper LB respects it — which it does as of K3s 1.30+; another argument for upgrading.
- **Effort.** S per service for Authentik middleware additions; M for the LB-binding fix; S for the vLLM `--api-key` change.

#### Sec2. No Pod Security Admission enforcement on any namespace.
- **Current state.** Of all namespaces, only `flux-system` has any `pod-security.kubernetes.io/*` label (it's `warn=restricted` only, not `enforce`). Every other namespace runs at default PSA (privileged).
- **Why it matters.** The cluster currently has at least one pod running as root with the `default` ServiceAccount and no `securityContext`: `registry-5c7b968f4b-zchlt` (`securityContext: {}`, `serviceAccountName: default`). `download-qwen36-fp8-fj2px` ran as `runAsUser: 0`. There is nothing stopping a future workload from doing the same — or worse, mounting hostPath, sharing host PID, or running privileged.
- **Recommendation.** Per [Kubernetes PSS docs](https://kubernetes.io/docs/concepts/security/pod-security-standards/), label namespaces in tiers:
  - `enforce=baseline` everywhere by default.
  - `enforce=restricted` for `auth`, `cache`, `database`, `temporal`, `vllm`, `monitoring`. Use `audit/warn=restricted` first to see what would break.
  - `enforce=privileged` for `gpu-operator`, `longhorn-system`, `nfs-csi-driver`, `smb-csi-driver`, `kube-system`, `flux-system` (these legitimately need it).
- **Effort.** S to label, but M to actually fix the violations PSA will surface (registry pod, vLLM, several charts that don't set a `securityContext` by default).

#### Sec3. Registry runs as root with default SA, no securityContext, no auth, deletion enabled.
- **Current state.** See Sec1 + the registry deployment manifest at `infrastructure/gitops/infrastructure/registry/deployment.yaml`. `image: registry:2`, no `runAsUser`, no resource limits beyond CPU/memory, `REGISTRY_STORAGE_DELETE_ENABLED=true`, `serviceAccountName: default` (implicit).
- **Recommendation.** Combined fix:
  - Add `securityContext: {runAsNonRoot: true, runAsUser: 65532, readOnlyRootFilesystem: true}` and a writable `emptyDir` for `/var/lib/registry/scratch` if needed.
  - Add htpasswd-based auth via env (`REGISTRY_AUTH=htpasswd`, mount the htpasswd file from a SOPS Secret).
  - Or: replace with [Zot](https://zotregistry.dev/) — single-binary OCI registry, ships with auth, signing, and a UI; tested fit for homelab.
- **Effort.** S for the in-place hardening, M for replacement.

#### Sec4. SOPS+age is fine for this scale — keep it, but lock down the practice.
- **Current state.** `age.key` and `age.key.old.20260318` both exist locally and are gitignored. `.sops.yaml` references one age recipient. SOPS hooks (`check-sops-encryption`, `forbid-sops-age-secret`, `forbid-plain-age-keys`) are present in `.pre-commit-config.yaml` and good.
- **Why it matters.** This is not the part of the system that's broken. ESO ([external-secrets-operator](https://github.com/external-secrets/external-secrets)) is the obvious "scale up" answer but it requires an external store (Vault, Infisical, or a cloud KMS) to back it — that's a larger commitment than the current setup. SOPS is the right call for one operator, one site ([SOPS+age vs ESO comparison, 2026](https://medium.com/@PlanB./external-secrets-operator-vs-sops-finding-the-best-approach-for-kubernetes-apps-720c44f4dc83)).
- **Recommendation.** Keep SOPS+age. Two minor improvements: (a) ensure the old key (`age.key.old.20260318`) is removed once you're confident no `.enc.yaml` files still decrypt only with it; (b) document the recovery path in `docs/infrastructure/configuration/secrets.md` (key location, recipient list, rotation runbook). I noted the secrets doc in `docs/infrastructure/configuration/` exists but didn't read all of it — confirm it covers rotation.
- **Effort.** S.

#### Sec5. Stale RBAC: cluster-admin grants for components that no longer exist.
- See **S3** for the list (`headlamp-admin`, 5× `dynamo-platform-*`).

#### Sec6. Lots of Helm-installed cluster-admin grants from charts.
- **Current state.** `longhorn-support-bundle` → `cluster-admin`. K3s' `helm-kube-system-traefik-crd` → `cluster-admin`. `cluster-reconciler-flux-system` → `cluster-admin`. The latter two are unavoidable given K3s and Flux's bootstrap models. `longhorn-support-bundle` is created by Longhorn for its support-bundle feature; the SA only activates when `longhorn-support-bundle` Job runs, but the binding is permanent.
- **Effort.** Informational.

---

### Maintenance burden

These are the places where you're plausibly going to get paged or have to intervene by hand.

#### M1. Cluster DNS via host resolv.conf is a recurring failure mode. (See "Genuinely broken #5".)
- **What pages you.** Image-pull meltdown when a bad upstream lands in resolv.conf and gets kept by the 3-nameserver kubelet truncation, evicting good resolvers. Already happened 2026-04-06.
- **Self-heal it.** In the `bootstrap` Ansible role, replace whatever currently configures `/etc/resolv.conf` with one of:
  - systemd-resolved with explicit `DNS=` and `FallbackDNS=` (preferred — handles NM rewrites).
  - A NetworkManager dispatcher script that pins `nameserver` lines.
  - A static `/etc/resolv.conf` with `chattr +i` (heaviest, hardest to update).
- The cluster does not need to depend on `192.168.86.1` (the home router) at all — it is only ever needed to reach the registry/services from the LAN, which K3s handles internally via CoreDNS for `*.cluster.local` and via Cloudflare for `*.almckay.io`.

#### M2. authentik-server keeps churning through restarts. (See "Genuinely broken #3".)
- **What pages you.** Eventually a restart cycle that can't recover (e.g. during the Postgres restart at the heart of incident-04-06) — every other auth-protected service goes down.
- **Self-heal it.** The chart upgrade to 2026.2.x changes the embedded outpost behavior. As an interim mitigation, increase `livenessProbe.timeoutSeconds` further (you've already raised it to 10s; try 20s) and reduce `failureThreshold` to fail fast if the process truly hangs rather than restart on transient slowness.

#### M3. `nas-storage` and CSI drivers are in three separate namespaces and three separate Kustomizations.
- **Current state.** `nfs-csi-driver` (chart `4.9.0`), `smb-csi-driver` (chart `1.19.1`), `nas-storage` (PVs + Secret). They're conceptually one feature ("attach to the NAS") but split across the gitops tree.
- **Why it matters.** Each upgrade is three places. Each NetworkPolicy is added separately or not at all (none of these namespaces have NetworkPolicies — they don't need ingress, but they're inconsistent with the operational-namespace policy).
- **Recommendation.** Optional: unify under one `nas` Kustomization. Low priority — current setup works.

#### M4. Helm release Secret accumulation.
- **Current state.** `monitoring/sh.helm.release.v1.prometheus.v333`–`v337` (5 retained), `monitoring/sh.helm.release.v1.grafana.v3`–`v7` (5), `cache/sh.helm.release.v1.redis.v7`–`v11` (5), `gpu-operator/sh.helm.release.v1.gpu-operator.v7`–`v11` (5), `auth/sh.helm.release.v1.authentik.v15`–`v19` (5).
- **Why it matters.** Cosmetic at this scale; makes `kubectl get secrets` noisier.
- **Recommendation.** Lower the HelmRelease history limit (`spec.install.historyLimit: 3`, `spec.upgrade.historyLimit: 3`) on each HelmRelease.
- **Effort.** S (one line per HelmRelease).

#### M5. external-dns is `policy: upsert-only`.
- **Current state.** External-DNS will create + update Cloudflare records but never delete them. So if you remove an Ingress, the DNS record stays.
- **Why it matters.** Today: harmless. Long-term: stale `*.almckay.io` records pointing at Tailscale IPs that may no longer host that service. Mild attack surface (subdomain takeover via Tailscale machine name reuse is unlikely but possible).
- **Recommendation.** Switch to `policy: sync`. Audit Cloudflare for stale records first.
- **Effort.** S.

#### M6. `descheduler` runs every 5 minutes — that's aggressive for a small cluster.
- **Current state.** `descheduler.descheduler-29639265-fnd9f` last ran 2 minutes ago. CronJob at `*/5 * * * *`.
- **Why it matters.** Descheduler can evict pods. On a 4-node cluster the marginal value of running every 5 minutes vs every hour is small; the cost of an ill-timed eviction during an upgrade window is real.
- **Recommendation.** Move to `0 * * * *` or even `0 */6 * * *`.
- **Effort.** S (one line).

#### M7. Two Authentik probes are wired against the same path (`/-/health/live/`) for both startup and liveness; the readiness probe uses a different path.
- **Current state.** `helmrelease.yaml` has `startupProbe.httpGet.path` defaulted by the chart (which uses `/-/health/live/`). After a slow startup, when liveness fires, it's the same handler — so a momentarily slow startup tends to also fail liveness, looping.
- **Why it matters.** Contributes to M2.
- **Recommendation.** Wait for the chart upgrade to do this properly (2026.x reorganized this).

#### M8. Registry data and model storage on `local-path` (single node, single disk).
- **Current state.** `vllm/model-storage` (100Gi, local-path) and `registry/registry-data` (50Gi, local-path) live on whatever node the pod first scheduled to. Loss of that node = data loss.
- **Why it matters.** Nothing about the current config tells you which node a pod is pinned to once the local-path PVC is bound. A node replacement requires manually re-staging.
- **Recommendation.** Move both to Longhorn (single-replica is fine; you already use that pattern for postgres). For vLLM models specifically, point `model-storage` at `nas-model-storage` (already a 500Gi NAS-backed RWX PV) instead of a separate local-path PVC — you already have the manifest for it.
- **Effort.** M (PVC migration with data copy).

---

### Tooling gaps — things you're not using that I'd add

#### T1. Flux image automation for the workloads still owned by this repo.
- **Current state.** No `ImageRepository`, `ImagePolicy`, or `ImageUpdateAutomation` resources exist. vLLM image versions are bumped by hand in Git (per recent commits: `7e8692c chore(gitops): bump vllm main LLM to v0.20.0`).
- **Recommendation.** For workloads where you want auto-bump (everything in `infrastructure/`), add `ImageRepository`+`ImagePolicy` with semver constraints. For workloads where you don't (vLLM — its release semantics are non-trivial), skip it. ([Flux image automation](https://fluxcd.io/flux/components/image/imagerepositories/), [SemVer policies](https://fluxcd.io/flux/components/image/imagepolicies/))
- **Effort.** M to set up; once.

#### T2. Renovate (or equivalent) for chart and CRD bumps.
- **Current state.** No bot. You upgrade charts when you remember to.
- **Why it matters.** Every chart in this repo is at least one minor version behind upstream (cert-manager 1.13 → 1.20, Authentik 2024.10 → 2026.2, Longhorn 1.7 → 1.11, external-dns 8.3.9 → current 8.x, etc). A weekly Renovate PR would surface those automatically.
- **Recommendation.** Enable Renovate on the repo with `kubernetes-manifest` and `helm-values` managers. PR-only — you stay in control of when to merge.
- **Effort.** S (a `renovate.json` and a PAT).

#### T3. Image signing / provenance.
- **Current state.** None. The cluster pulls `vllm/vllm-openai:v0.20.0-aarch64-cu130`, `bitnami/postgresql:latest`, `registry:2` — none verified.
- **Why it matters.** Probably overkill for one-operator homelab — listing because you said to be opinionated. For a homelab, the realistic threat is Bitnami pushing a malicious `:latest` (low; Bitnami is going dark, not malicious), or the Hugging Face hub sending you bad weights (mitigated via `HF_HUB_OFFLINE=1`, which you're already doing — good catch).
- **Recommendation.** Skip cosign/signing now. Revisit if you start hosting workloads that are more interesting than home compute.

#### T4. Tailscale Kubernetes Operator.
- **Current state.** Tailscale runs as a host-level daemon; K3s is bound to `tailscale0` via Ansible drop-in. Works.
- **Recommendation.** **Do not adopt** the [Tailscale K8s Operator](https://tailscale.com/kb/1236/kubernetes-operator) for this cluster. It's designed for the case where you don't already have node-level Tailscale, or you want to expose individual cluster Services as discrete tailnet devices. Your current setup is simpler. Listing it because the question was asked.

#### T5. k8up / VolSync for non-Postgres backups.
- **Current state.** Postgres is backed up by a CronJob. Nothing else (Redis, FalkorDB, Qdrant, Longhorn volumes, model weights) is.
- **Why it matters.** Of those, FalkorDB and Qdrant probably hold work you'd miss. Redis is a cache. Model weights re-downloadable.
- **Recommendation.** [k8up](https://k8up.io/) — Restic-based backup operator. Annotate a PVC, get scheduled snapshots to the NAS. Not as good as CNPG for postgres (no PITR) but excellent for "snapshot a PVC nightly to a different disk." Use *with* CNPG for postgres, not instead of.
- **Effort.** S (chart install + annotation per PVC).

#### T6. CloudNativePG.
- See **S1**.

#### T7. VictoriaMetrics single-binary.
- See **S2**.

#### T8. Pod Security Admission.
- See **Sec2**.

#### T9. OCI HelmRepository.
- **Current state.** All `HelmRepository` resources in `infrastructure/sources/` are HTTP-based.
- **Why it matters.** Several of these projects (Bitnami, longhorn, jetstack, fluxcd) ship OCI charts now. OCI charts are content-addressed and resilient to repo URL changes. ([Flux OCIRepository](https://fluxcd.io/flux/components/source/ocirepositories/))
- **Recommendation.** Optional. Only one I'd actually switch is `bitnami` (because the HTTP repo is the failing piece) — and the answer there is to stop using Bitnami charts at all (S1). Keep the rest as-is.

---

## Things that are good — leave alone

- **Cluster-stability foundations.** Topology labels (`topology.kubani.io/{site,role,usage-class}`) and the tier model (core/platform/optional with `replicas: 0` defaults) are exactly the right shape for a homelab — workloads schedule by *role*, not hostname, so node replacement is mechanical. Documented in `docs/infrastructure/cluster/cluster-stability.md`.
- **K3s + Tailscale binding via systemd drop-in.** This is a non-obvious fix for a real Flannel-route-loss problem; the playbook is checked in. Hard-won, working — leave it.
- **NetworkPolicy default-deny + targeted-allow pattern.** Operational namespaces (`auth`-aside, see below) all have `default-deny-ingress`, `allow-same-namespace`, `allow-traefik-ingress`, and explicit cross-namespace `allow-…` rules per call site. Good model. Better than the "allow-anything-egress" pattern most homelabs land on.
- **SOPS+age + pre-commit hooks.** `gitleaks`, `detect-secrets`, `check-sops-encryption`, `forbid-sops-age-secret`, `forbid-plain-age-keys` is comprehensive coverage at the right layer. Don't switch to a more complex secret system unless you need fine-grained access (and you don't).
- **`postgres-backup` CronJob is well-engineered** — atomic write, partial-file sweep, retention, runs as nonRoot, image pinned by digest, fits inside its NetworkPolicy. The only reason to retire it is to delete the work, not because it's wrong. Quality reference for "how to write a CronJob in this repo."
- **Cert-manager via DNS-01 with Cloudflare.** Right choice for an IDP-fronted environment where HTTP-01 from Let's Encrypt won't work. Token is SOPS-encrypted.
- **Reloader and descheduler** are both small, stable, idiomatic add-ons; neither is doing too much.
- **Justfile + uv + mise + ansible-lint** stack is clean. Pre-commit + `just check` covers the obvious safety nets without being heavy.
- **`docs/troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md`** is a great example of post-incident docs. Do more of those.
- **Authentik is actually wired in** for the few services that use it (Grafana, Prometheus). This is the part most people skip. The fact that *more* services should use it (Sec1) is a different problem.
- **`postgresql-credentials` etc. are referenced via `existingSecret`**, not inline — clean separation between chart values and secret material.
- **Ingress probes / startupProbe tuning for vLLM** with explicit `failureThreshold: 90 * 10s = 15min` for cold model loads is exactly the right level of detail. Few homelabs do this.
- **`docs/infrastructure/repository-scope.md` (referenced in CLAUDE.md)** declaring the scope as infrastructure-only post-PR-#44 is good discipline for not letting agent code creep back in.

---

## Open questions for you

1. **K3s upgrade strategy.** Are you comfortable with an in-place K3s upgrade across 1.28 → 1.31 (LTS) → 1.33+, or would it be simpler to provision a new cluster (k3sup or fresh Ansible run) and migrate workloads? Migration with CNPG-managed Postgres is much easier than with the current StatefulSet.
2. **Trust model for the LAN.** Is your home LAN a trusted zone for the cluster, or should LAN-side reachability of Service ports be considered an exposure (Sec1.1, Sec3)? This determines whether the Authentik-bypass ingresses and the K3s ServiceLB binding-on-all-interfaces are findings or non-issues.
3. **Tailscale ACLs.** Out-of-repo, but: does your tailnet ACL restrict `100.71.65.62:5432` etc to specific users/devices, or is "any device on my tailnet can hit Postgres"? If the latter, the database TCP IngressRoutes are effectively wide open to anyone you've ever shared a Tailscale node with.
4. **Headlamp.** The `headlamp-admin` CRB exists but the namespace doesn't. Is Headlamp coming back, or can the CRB go?
5. **Observability appetite.** Do you actually want metrics? Today's setup is "all of Prometheus, but at 0 replicas." Three valid answers: (a) yes, lighten with VictoriaMetrics single-binary, (b) yes, scale current stack back to 1, (c) no, delete it.
6. **Bitnami timeline tolerance.** Are you comfortable migrating off Bitnami opportunistically (next time something breaks) or do you want a planned migration before the next chart pull fails? `:latest` for the *image* is OK for now (per your known-constraints note); the *chart repo* itself is the time-bomb.
7. **MCP-managed Kubernetes secrets in the agent runtime.** Out-of-repo, but: the deferred MCP tool list shows `mcp__kubernetes__resources_create_or_update` etc. are available to whatever agent runs against this kubeconfig. Cluster-admin? Read-only? Worth knowing for blast-radius.
8. **One-key-rotation after registry hardening.** If the registry has been auth-less for ~144 days (since the ingress was created), do you want to assume any image in there could have been replaced and rebuild from sources before adding auth? (The threat model depends on Q2/Q3.)
9. **Disposition of orphaned dynamo CRBs.** PR #44 removed the agent code but not the bindings — was that intentional (waiting on a follow-up cleanup PR) or an oversight?

---

## Sources cited

- [endoflife.date — Kubernetes](https://endoflife.date/kubernetes)
- [cert-manager — Releases](https://cert-manager.io/docs/releases/)
- [goauthentik — Helm chart releases](https://github.com/goauthentik/helm/releases)
- [Bitnami charts issue #35164 — repo deprecation](https://github.com/bitnami/charts/issues/35164)
- [CloudNativePG](https://cloudnative-pg.io/)
- [VictoriaMetrics — single-server](https://docs.victoriametrics.com/victoriametrics/single-server-victoriametrics/)
- [Flux v2 — OCIRepository](https://fluxcd.io/flux/components/source/ocirepositories/)
- [Flux v2 — ImageRepository / ImagePolicy](https://fluxcd.io/flux/components/image/imagerepositories/)
- [Flux v2 — Image automation guide](https://fluxcd.io/flux/guides/image-update/)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [k8up — Kubernetes Backup Operator](https://k8up.io/)
- [Longhorn — releases / EOL](https://longhorn.io/blog/longhorn-v1.9.0/)
- [Tailscale Kubernetes Operator](https://tailscale.com/kb/1236/kubernetes-operator)
- [Traefik v2 → v3 migration](https://doc.traefik.io/traefik/migration/v2-to-v3/)
- [Zot — OCI registry](https://zotregistry.dev/)
- [SOPS+age vs External Secrets Operator (PlanB, 2026)](https://medium.com/@PlanB./external-secrets-operator-vs-sops-finding-the-best-approach-for-kubernetes-apps-720c44f4dc83)
