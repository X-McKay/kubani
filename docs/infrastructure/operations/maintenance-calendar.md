# Maintenance Calendar

Recurring operational tasks and the cadence each one runs on.

| Cadence | Task | Notes |
|---|---|---|
| Monthly, first of the month | Drift bench (`just inference-bench main drift-YYYYMM`) | Added to the [scheduled audit](scheduled-audit.md) workflow; a red run posts to ntfy. Never promoted — see the inference release process's "watch for degradation" section |
| Weekly, Mondays 09:00 UTC | Scheduled audit (`just audit`) | `cluster-identity`, `validate`, `validate-network`, `live-service-probes` — see [scheduled-audit.md](scheduled-audit.md) for the full chain and the runner caveats |
| Quarterly | Restore drill | Exercises the PostgreSQL backup/restore path end to end — see [postgresql-backup-recovery.md](postgresql-backup-recovery.md). Alert on failure per roadmap Phase 0.2/5.6 |
| When DGX OS 7.x ships | Move sparky to the 580 driver branch | Stay on 580.x (e.g. 580.159.03) — driver 590.x is **not** supported on GB10 with vLLM CUDA graph capture (roadmap Phase 1 stage 1.7 and non-goal in roadmap section 2). Use the `host-maintenance` skill / [node-maintenance.md](node-maintenance.md) window shape: pre-checks, cordon, reboot, verify, drift bench |
| As Longhorn ships minors | Stepwise minor upgrades | One minor at a time, never a version jump — same discipline as the Authentik ladder below |
| When the Authentik upstream blocker clears | Resume the upgrade ladder past 2026.5.6 | See [authentik-upgrade.md](authentik-upgrade.md) for the current pin and why it is sequential-only |
| Weekly | Review Renovate PRs | PR-only mode, never auto-merged — see [renovate.md](renovate.md). vLLM image PRs need `just inference-preflight` before merge |
| After every stage's 24 h reading | Correct the capacity ledger | The [platform release process](release-process.md)'s mandatory T+24h resource reading is what turns a starting estimate in [capacity.md](../cluster/capacity.md) into an observed one — update the ledger line in the same PR that promotes the stage |

## Related documentation

- [Scheduled audit](scheduled-audit.md)
- [Capacity ledger](../cluster/capacity.md)
- [Node maintenance](node-maintenance.md)
- [Platform release process](release-process.md)
- [Renovate](renovate.md)
