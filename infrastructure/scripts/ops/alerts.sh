#!/usr/bin/env bash
# Print active Alertmanager alerts and silences. Part of Phase 0 monitoring
# (docs/plans/ideas/2026-09-29-inference-platform-roadmap.md section 0.2).
#
#   alerts.sh
#
# Reads Alertmanager through curl in the Grafana pod: it sits inside the
# monitoring namespace (allow-same-namespace admits it), while the API
# server's service proxy is rejected by default-deny ingress, and the
# Alertmanager image itself has no shell.
set -euo pipefail

NS=monitoring
SVC=alertmanager
PORT=9093
export KUBECONFIG=${KUBECONFIG:-/home/al/.kube/config}

am() { kubectl exec -n "$NS" deploy/grafana -c grafana -- curl -sf --max-time 15 "http://$SVC:$PORT/api/v2/$1"; }

ALERTS=$(am alerts) || { echo "failed to reach Alertmanager at $SVC:$PORT from the grafana pod" >&2; exit 1; }
SILENCES=$(am silences) || { echo "failed to fetch silences" >&2; exit 1; }

ALERTS_JSON="$ALERTS" SILENCES_JSON="$SILENCES" python3 - <<'PY'
import json
import os


def fmt_row(cols, widths):
    return "  ".join(str(c)[:w].ljust(w) for c, w in zip(cols, widths))


alerts = json.loads(os.environ["ALERTS_JSON"])
widths = [28, 8, 10, 25, 50]
print(fmt_row(["NAME", "SEVERITY", "STATE", "SINCE", "SUMMARY"], widths))
if not alerts:
    print("(no active alerts)")
for a in sorted(alerts, key=lambda a: a.get("labels", {}).get("alertname", "")):
    labels = a.get("labels", {})
    print(fmt_row([labels.get("alertname", "?"), labels.get("severity", "-"),
                   a.get("status", {}).get("state", "-"), a.get("startsAt", "-"),
                   a.get("annotations", {}).get("summary", "-")], widths))

silences = [s for s in json.loads(os.environ["SILENCES_JSON"])
            if s.get("status", {}).get("state") == "active"]
print()
print(f"active silences: {len(silences)}")
swidths = [40, 20, 25]
if silences:
    print(fmt_row(["MATCHERS", "CREATED BY", "ENDS"], swidths))
for s in silences:
    matchers = ",".join(f"{m['name']}={m['value']}" for m in s.get("matchers", []))
    print(fmt_row([matchers, s.get("createdBy", "-"), s.get("endsAt", "-")], swidths))
PY
