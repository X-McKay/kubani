---
name: incident-capture
description: Use before restarting a stalled or crashed vLLM engine, or any time forensic evidence about a production incident needs to be captured before the evidence disappears on restart.
---

# Incident Capture

The 2026-09-25 GB10 stall record notes no stack or state was captured before
the pod was recycled — by the time anyone looked, the wedge was gone and
only the hypothesis remained. The rule this skill exists to enforce: **never
restart first.** Capture, then restart.

## Workflow

1. `just incident-capture <engine>` (`main` or `fast`) — non-interactive,
   takes no action on the running pod. Writes to
   `~/kubani-forensics/<UTC timestamp>-<engine>/`.
2. Only after the capture completes, recover with
   `just inference-restart <engine>`. It prints a reminder to capture first
   unless called with `--no-capture` — that flag exists for a second restart
   attempt in the same incident, not to skip capture on the first one.

## What the bundle contains

- `kubectl get pods -n vllm -o wide`
- `kubectl describe pod` for the engine pod
- Engine log tail (2000 lines), plus `--previous` if the container has
  crashed and restarted
- Broker log tail (500 lines)
- `kubectl get events -n vllm --sort-by=.lastTimestamp`
- A `/metrics` snapshot from the engine Service, fetched via `kubectl exec`
  into the broker pod (the engine port isn't exposed outside the cluster)
- `nvidia-smi -q` and the last 50 `journalctl -k -b` lines matching
  `xid|nvrm`, via `ssh sparky` — skipped with a note in the bundle if SSH
  isn't reachable, rather than failing the whole capture
- `kubectl top nodes` and `kubectl top pods -n vllm`

## Draft the record

The script copies `docs/troubleshooting/_template.md` to
`<bundle-dir>/record.md` with the timestamp and engine already filled in.
Finish it while the incident is fresh: how to recognise the failure (compare
against the wedge table in `docs/troubleshooting/vllm-main-engine-hang-gb10.md`
if this is the same signature), what was actually captured, and why the
cluster didn't self-heal (liveness probe only proves the API process is
alive, not that the engine core is responsive — see that runbook for the
GB10 case).

## Red flags: stop

- Restarting before capturing. If the engine is actively blocking a
  maintenance window and there is no time, capture what you can in
  parallel (events and logs are cheap and fast) rather than skipping
  straight to zero evidence.
- Treating "pod is Ready again" as the incident being closed — the record
  isn't done until the why-didn't-it-heal section is filled in.
- Re-running `just inference-restart` with `--no-capture` as the default
  habit. It is for the second attempt in one incident, not a shortcut.
