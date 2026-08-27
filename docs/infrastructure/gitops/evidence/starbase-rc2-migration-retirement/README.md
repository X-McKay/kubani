# Starbase RC2 migration retirement evidence

Captured: `2026-08-27T11:28:31Z`

Purpose: retain the final status and available logs for the two successful RC2
migration Jobs before the RC4 inert promotion intentionally removes their
identities from the Flux inventory and pruning deletes the Jobs and pods.

The capture was read-only. It selected non-secret Job and pod identity, image,
placement, completion, retry, and exit fields. No environment variables,
Secret values, mounted files, or database URLs were read. Logs were obtained
with `kubectl logs --timestamps=true`.

## Result

| Job | Node | Succeeded | Failed | Restarts | Exit | Log result |
|---|---|---:|---:|---:|---:|---|
| `starbase-core-migrate-22bfaa3b1e8f` | `asio` | 1 | 0 | 0 | 0 | one 132-byte structured completion line |
| `starbase-gateway-migrate-38db19887578` | `asio` | 1 | 0 | 0 | 0 | command succeeded; empty stream (0 bytes) |

Both Jobs had `Complete=True` with reason `CompletionsReached`. The empty
gateway log is preserved as an explicit zero-byte capture record rather than
being represented as invented output.

Artifacts:

- `core-job-status.json`: sanitized final core Job and pod status;
- `core.log`: exact timestamped core log stream;
- `gateway-job-status.json`: sanitized final gateway Job and pod status; and
- `gateway-log-capture.json`: command outcome and exact empty-stream counts.

The RC4 post-reconcile checklist must confirm both RC2 Job identities are
absent. Their removal is expected pruning, not a lost or failed migration.

Checksums are recorded in `SHA256SUMS`.
