# Revocations

One reviewed file per revocation of a release, `<id>.yaml` in this directory
(zetra `platform/registry/contract/delivery.md`, section 8.1). The renderer
(`infrastructure/scripts/ops/registry_feed.py`) puts them in the catalog feed as
the key `revocations`: a list of these objects in id order, empty when the
directory holds no `*.yaml`. The registry stores each one it has not stored yet
when it applies the feed.

A file is never edited or removed after it is merged. A stored revocation that
the feed states differently makes the registry refuse the whole feed.

Keys, all required except `sessions`:

| Key | Value |
|---|---|
| `schemaVersion` | `1` |
| `id` | equals the file name without `.yaml` |
| `kind` | `agent` (the only kind with an effect in milestone 2) |
| `item` | the agent's name |
| `release` | the release name |
| `reason` | `security` or `quality` |
| `sessions` | `cancel` or `finish`; default `cancel` for `security`, `finish` for `quality` |
| `summary` | one sentence for the record |
| `revokedBy` | who decided |
| `revokedAt` | UTC time, written as text |

Only a `security` revocation with `sessions: cancel` makes the provisioner
cancel the release's running sessions, and only for 24 hours after the registry
stored it.

Example (not a real revocation; written commented out):

```yaml
# schemaVersion: 1
# id: 2026-11-20-db-admin-1a2b3c4d      # equals the file name without .yaml
# kind: agent
# item: db-admin
# release: db-admin-2026-11-20-1a2b3c4d # the release name
# reason: security                      # security | quality
# sessions: cancel                      # cancel | finish
# summary: The release leaks query text into its report.
# revokedBy: al
# revokedAt: 2026-11-20T10:00:00Z
```

The example sits in this README, not in a `.yaml` file, so nothing here is a
revocation until a person adds `infrastructure/registry/revocations/<id>.yaml`.
