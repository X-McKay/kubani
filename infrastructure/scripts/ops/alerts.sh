#!/usr/bin/env bash
# Print active Alertmanager alerts and silences. Part of Phase 0 monitoring
# (docs/plans/ideas/2026-09-29-inference-platform-roadmap.md section 0.2).
#
#   alerts.sh
set -euo pipefail

NS=monitoring
export KUBECONFIG=${KUBECONFIG:-/home/al/.kube/config}

POD=$(kubectl get pod -n "$NS" -l "app.kubernetes.io/name=alertmanager" --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].metadata.name}')
[[ -n "$POD" ]] || { echo "no running alertmanager pod in $NS" >&2; exit 1; }

read -r -d '' QUERY <<'PY' || true
import json
import sys
import urllib.request


def fetch(path):
    with urllib.request.urlopen(f"http://127.0.0.1:9093/api/v2/{path}", timeout=15) as resp:
        return json.loads(resp.read().decode())


def fmt_row(cols, widths):
    return "  ".join(c.ljust(w) for c, w in zip(cols, widths))


try:
    alerts = fetch("alerts")
except Exception as exc:  # noqa: BLE001
    print(f"failed to fetch alerts: {exc!r}", file=sys.stderr)
    sys.exit(1)

rows = []
for a in alerts:
    labels = a.get("labels", {})
    name = labels.get("alertname", "?")
    severity = labels.get("severity", "-")
    state = a.get("status", {}).get("state", "-")
    since = a.get("startsAt", "-")
    summary = a.get("annotations", {}).get("summary", "-")
    rows.append([name, severity, state, since, summary])

widths = [12, 8, 10, 22, 40]
headers = ["NAME", "SEVERITY", "STATE", "SINCE", "SUMMARY"]
print(fmt_row(headers, widths))
if not rows:
    print("(no active alerts)")
for r in rows:
    print(fmt_row([str(c)[:w] for c, w in zip(r, widths)], widths))

print()
try:
    silences = fetch("silences")
except Exception as exc:  # noqa: BLE001
    print(f"failed to fetch silences: {exc!r}", file=sys.stderr)
    sys.exit(1)

active_silences = [s for s in silences if s.get("status", {}).get("state") == "active"]
print(f"active silences: {len(active_silences)}")
swidths = [30, 20, 22]
sheaders = ["MATCHERS", "CREATED BY", "ENDS"]
print(fmt_row(sheaders, swidths))
for s in active_silences:
    matchers = ",".join(f"{m['name']}={m['value']}" for m in s.get("matchers", []))
    print(fmt_row([matchers[:30], s.get("createdBy", "-")[:20], s.get("endsAt", "-")[:22]], swidths))
PY

kubectl exec -n "$NS" "$POD" -- python3 -c "$QUERY"
