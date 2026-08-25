# Cluster audit follow-up — 2026-05-09

Companion to [docs/reviews/2026-05-09-cluster-audit.md](../../reviews/2026-05-09-cluster-audit.md). The original audit's "genuinely broken" list is fully closed. This file tracks what's left from the broader findings sections plus loose ends from the night's work.

> **2026-08-24 amendment:** this page remains the historical incident record.
> The indefinite Authentik hold below has been superseded by the controlled
> [2026.5 upgrade and recovery plan](../../infrastructure/operations/authentik-upgrade.md).
> The original warning remains valid against direct jumps and downgrade-based
> recovery.

---

## What got done

Eleven commits in one session (`23e7be5..a1d6c4a`):

| Commit | Subject |
|--------|---------|
| `23e7be5` | K3s kubelet pinned to a stable upstream resolv.conf (closes audit #5/#6) |
| `d8839d2` | authentik 2024.10.4 → 2026.2.2 (failed — hit upstream migration bug, rolled back) |
| `f6deb6f` | authentik pinned at 2025.10.3 (closes audit #3) |
| `4524d72` | cert-manager v1.13.3 → v1.20.2 (closes audit #2) |
| `9ba3d89` | Traefik IngressRouteTCP `containo.us` → `traefik.io` (audit S5 prerequisite) |
| `e2f83ad` | Traefik HelmChartConfig v3 `expose: { default: true }` schema fix |
| `59ede8b` | Longhorn 1.7.2 → 1.8.2 |
| `61648fa` | Longhorn 1.8.2 → 1.9.2 |
| `8edb863` | Longhorn 1.9.2 → 1.10.2 |
| `69faabd` | Longhorn 1.10.2 → 1.11.2 |
| `a1d6c4a` | Ansible inventory `k3s_version: v1.34.7+k3s1` (closes audit #1) |

Plus a live cluster patch (no commit) — the `auth/authentik-tls` Secret's `cert-manager.io/certificate-name` annotation was repointed at the live `Certificate/authentik-tls` to clear the 153-day-stuck Ready=False (closes audit #4). Memory file `duplicate_certificate_resources.md` documents the pattern + fix recipe for any future occurrence.

Subsequent follow-up work after the original audit session:

| Commit | Subject |
|--------|---------|
| `da1ff09` | HelmRelease `maxHistory: 3`, external-dns `policy: sync`, descheduler hourly (closes Tier 1) |
| `03ef87c` | Registry ingress BasicAuth via SOPS-encrypted htpasswd secret + docs (partially closes Tier 3 registry hardening) |

Current working tree follow-up:

- Ansible/K3s/GitOps ownership cleanup: K3s upgrades and Flux bootstrap/repair are explicit operations, Flux CLI/controller/root drift fails closed by default, and Ansible no longer rewrites ongoing GitOps state during normal provisioning.
- Registry pod hardening: `registry` uses a dedicated ServiceAccount with token automount disabled, runs as non-root UID/GID `65532`, drops all capabilities, disallows privilege escalation, uses RuntimeDefault seccomp, and keeps the root filesystem read-only with only `/var/lib/registry` writable.
- Pod Security Admission: `registry` enforces `restricted`; host-integrated infra namespaces explicitly enforce `privileged`; app/platform namespaces use `audit=restricted` and `warn=restricted` while restricted-readiness violations are reviewed.
- Browser ingress SSO: `temporal.almckay.io`, `falkordb.almckay.io`, and `qdrant.almckay.io` use Authentik Traefik `forwardAuth`; `registry.almckay.io` intentionally remains on registry-compatible BasicAuth.

Plus live cluster cleanup (no commit):

- deleted stale `headlamp-admin` and 5 `dynamo-platform-dynamo-operator-*` ClusterRoleBindings
- deleted the two released NAS graph/vector PVs and `pvc-cbfbf4df-1485-4fb1-86ff-9c637234ee0d`
- deleted orphaned `vllm/tmp-allow-egress-model-downloaders` NetworkPolicy
- deleted orphaned `cache/redis-replicas` PodDisruptionBudget

---

## Cluster baseline now

- **K3s**: `v1.34.7+k3s1` on all 4 nodes (containerd `2.2.3-k3s1`)
- **Longhorn**: `1.11.2`, all 3 volumes attached + healthy
- **cert-manager**: `v1.20.2`, all 10 Certificates Ready=True
- **Authentik**: chart `2025.10.3` (pinned — see `What NOT to do` below)
- **Traefik**: v3 (auto-bundled with K3s 1.34), all routes use `traefik.io/v1alpha1`
- **DNS**: K3s kubelet uses static `/etc/rancher/k3s/upstream-resolv.conf`; host has `kubani-dns.conf` resolved drop-in with `Domains=~.`

---

## What's left, by effort tier

### Tier 2 — Cleanup, one PR each

- **Renovate** (or equivalent): every chart in this repo is at least one minor behind upstream. PR-only mode keeps you in control.

### Tier 3 — Targeted security

- **vLLM `--api-key`**: drop in via env from a SOPS Secret if Internet-adjacent; harmless if Tailscale-only.
- **Restricted-readiness cleanup**: PSA dry-run currently reports restricted warnings for `falkordb`, `qdrant`, `postgres-backup`, `vllm`, and `temporal-db-init`. Keep these namespaces in audit/warn until each workload is hardened or intentionally exempted.
- **K3s ServiceLB binding** still on all node interfaces, not just Tailscale. Either `loadBalancerSourceRanges: ["100.64.0.0/10"]` on the `traefik` Service (if Klipper LB respects it now on K3s 1.34) or replace ServiceLB with MetalLB.

### Tier 4 — Architectural decisions

These need a "do we want this?" answer before scoping.

- **PostgreSQL → CloudNativePG**. Replaces both the Bitnami chart (going dark) and the homegrown `postgres-backup` CronJob; gains WAL streaming + PITR. M-L migration with a planned cutover.
- **Monitoring stack decision**. Currently Prometheus/Grafana/Alertmanager are at `replicas: 0` but the HelmReleases reconcile every 10 min. Three valid answers: (a) delete the stack entirely + run only `node-exporter` if anything, (b) replace with `victoria-metrics-single` chart (~50 MiB RAM idle, drop-in PromQL), (c) scale back to 1 and use it.
- **Bitnami migration**. `bitnami/postgresql` and `bitnami/redis` `:latest` work for now but the chart repo at `charts.bitnami.com/bitnami` is going dark. CNPG covers postgres; redis can move to a small in-repo manifest pinning a specific upstream `redis:` tag, or [bitnamilegacy](https://hub.docker.com/r/bitnamilegacy) until it's not maintained.
- **Flux image automation** (`ImageRepository` + `ImagePolicy` + `ImageUpdateAutomation`) for the workloads still owned in this repo. Worth doing for cluster services; skip for vLLM where release semantics are non-trivial.
- **Storage migration off local-path**: `vllm/model-storage` (100Gi) and `registry/registry-data` (50Gi) are on `local-path` (single-node, single-disk). Move to Longhorn for resilience, or point `vllm/model-storage` at the existing `nas-model-storage` PV.

### Tier 5 — Hold for upstream

- **Authentik 2026.x upgrade**. Blocked by [authentik issue #21617 + 5 related](authentik_upgrade_blocker.md memory file). Six open issues track the `0056_user_roles` migration regression on every upgrade path that crosses 2025.10 → 2025.12+. `2026.2.3-rc1` (April 2026) does not address it. Don't retry the bump until upstream actually closes the issue with a fix-in-version-X note.

---

## Open questions still blocking decisions

These got asked at the bottom of the original audit. Some are now answered:

1. **Trust model for the LAN.** Is the home LAN a trusted zone for the cluster, or should LAN-side reachability of Service ports be considered an exposure? Determines whether the registry / vLLM / etc. ingresses are findings or non-issues.
2. **Tailscale ACL audit.** Out-of-repo. Does the tailnet ACL restrict `100.71.65.62:5432` etc. to specific users/devices, or is "any device on my tailnet can hit Postgres"?
3. **Headlamp coming back?** Answered for now by cleanup: the stale CRB is gone. Revisit only if Headlamp returns.
4. **Observability appetite.** Do you actually want metrics/dashboards? Determines whether to delete, replace, or revive the monitoring stack.
5. **Bitnami timeline tolerance.** Migrate off Bitnami opportunistically (next time something breaks) or planned migration before the next chart pull fails?
6. **MCP-managed kubectl scope.** What permissions does the agent runtime hold against this kubeconfig? Worth knowing for blast-radius.
7. **One-key rotation after registry hardening.** Answered: trust the existing registry contents and move forward from the authenticated baseline.

---

## What NOT to do

Things tonight's session learned the hard way.

- **Don't bump Authentik past 2025.10.3** until upstream ships a fix for the `0056_user_roles` migration. Tonight's attempt at 2026.2.2 left the DB in a partial-migration state and required `dropdb` + `pg_restore`. The retry path is reproducible (covered in `authentik_upgrade_blocker.md` memory) but not free.
- **Don't undo the systemd-resolved `kubani-dns.conf` drop-in** thinking the K3s `--resolv-conf` change made it redundant. They're layered: K3s pins the cluster side, the resolved drop-in keeps the host healthy for `apt`, `tailscale up`, etc.
- **Don't skip Longhorn minor versions** on future upgrades — they're stepwise for a reason. Each minor migrates CRs.
- **Don't run K3s install script without `INSTALL_K3S_EXEC=agent` on workers.** The default is server mode, which creates a wrong systemd unit alongside the real one. Tonight asio briefly had both.
- **Pre-pull images on every node** before any chart upgrade that has helm pre-upgrade hooks. The Charter IPv6 prefix has flaky reachability to Cloudflare CDN, which surfaces as "network is unreachable" / "lookup ... Try again" during pulls. `ssh <node> 'sudo /usr/local/bin/k3s crictl pull <image>'` per node is the workaround.

---

## Backups

Saved to `/home/al/backups/`:

- `authentik-pre-2026.2-20260509-213823.dump` (2.2 MB) — pre-Authentik-upgrade `pg_dump -Fc`
- `cert-manager-state-pre-1.20.2-20260509-225621.yaml` (14 KB) — Certificate + ClusterIssuer YAML snapshot
- `k3s-upgrade-20260509-231228/` — full pre-K3s-upgrade snapshot:
  - `k3s-state.db` (489 MB) — K3s SQLite state
  - `pg-dumpall.sql.gz` (60 MB) — every database
  - `longhorn-volumes.txt` — volume inventory
  - `nodes.txt`, `pods.txt`, `workloads.txt` — cluster state at the time

Recommended retention: ~1 week from each. After that, the running cluster IS the source of truth.

---

## Suggested order if picking this up cold

If you want to chip away at this in small sessions:

1. **Restricted-readiness cleanup** for namespaces currently in PSA audit/warn
2. **K3s ServiceLB exposure decision** (Tailscale-only source ranges vs MetalLB)
3. **Decide observability** (open question 4 → Tier 4 monitoring decision)
4. **Decide Bitnami → CNPG migration** (open question 5 → Tier 4 postgres + Bitnami)
5. **Image automation + Renovate** (Tier 4 / Tier 2)
6. **Wait for Authentik upstream fix**, then plan that bump (Tier 5)

The remaining items are improvement work rather than immediate breakage. The
highest-value next security decision is the ServiceLB exposure boundary.
