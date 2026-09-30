#!/usr/bin/env bash
# Capture forensic evidence for a vLLM engine incident before anything is
# restarted. See .claude/skills/incident-capture/SKILL.md — never restart
# first, the 2026-09-25 stall record exists because no stack was captured.
#
#   incident_capture.sh <main|fast>
#
# Writes ~/kubani-forensics/<UTC timestamp>-<engine>/ and drafts
# <dir>/record.md from docs/troubleshooting/_template.md. Prints the
# directory on success. Non-fatal on any single capture step failing (an
# incident is exactly when something else is also broken) — failures are
# noted in the bundle rather than aborting the whole capture.
set -euo pipefail

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[[ $# -eq 1 ]] || usage
ENGINE=$1

NS=vllm
export KUBECONFIG=${KUBECONFIG:-/home/al/.kube/config}

case "$ENGINE" in
  main)
    DEPLOY=vllm
    BROKER_DEPLOY=gpu-broker-main
    ENGINE_SVC=llm-engine
    ;;
  fast)
    DEPLOY=vllm-fast
    BROKER_DEPLOY=gpu-broker
    ENGINE_SVC=fast-model-engine
    ;;
  *)
    echo "engine must be 'main' or 'fast', got '$ENGINE'" >&2
    exit 2
    ;;
esac

TS=$(date -u +%Y%m%dT%H%MZ)
DIR="$HOME/kubani-forensics/${TS}-${ENGINE}"
mkdir -p "$DIR"

note() { echo "$1" | tee -a "$DIR/NOTES.txt" >&2; }

note "capturing incident evidence for engine=$ENGINE deploy=$DEPLOY into $DIR"

kubectl get pods -n "$NS" -o wide >"$DIR/pods.txt" 2>&1 || note "WARN: kubectl get pods failed"

ENGINE_POD=$(kubectl get pod -n "$NS" -l "app=$DEPLOY" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [[ -n "$ENGINE_POD" ]]; then
  kubectl describe pod -n "$NS" "$ENGINE_POD" >"$DIR/engine-describe.txt" 2>&1 || note "WARN: describe engine pod failed"
  kubectl logs -n "$NS" "$ENGINE_POD" --tail=2000 >"$DIR/engine-log.txt" 2>&1 || note "WARN: engine log tail failed"
  if kubectl logs -n "$NS" "$ENGINE_POD" --previous --tail=2000 >"$DIR/engine-log-previous.txt" 2>/dev/null; then
    :
  else
    rm -f "$DIR/engine-log-previous.txt"
    note "no previous container for $ENGINE_POD (not crash-restarted, or --previous unavailable)"
  fi
else
  note "WARN: no running pod found for app=$DEPLOY"
fi

BROKER_POD=$(kubectl get pod -n "$NS" -l "app=$BROKER_DEPLOY" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [[ -n "$BROKER_POD" ]]; then
  kubectl logs -n "$NS" "$BROKER_POD" --tail=500 >"$DIR/broker-log.txt" 2>&1 || note "WARN: broker log tail failed"
else
  note "WARN: no running broker pod found for app=$BROKER_DEPLOY"
fi

kubectl get events -n "$NS" --sort-by=.lastTimestamp >"$DIR/events.txt" 2>&1 || note "WARN: kubectl get events failed"

# /metrics snapshot: the engine port is cluster-internal, so fetch it via
# kubectl exec into the broker pod (requires python3 in the broker image).
if [[ -n "$BROKER_POD" ]]; then
  read -r -d '' METRICS_CHECK <<PY || true
import urllib.request
try:
    with urllib.request.urlopen("http://${ENGINE_SVC}.${NS}.svc.cluster.local:8000/metrics", timeout=15) as resp:
        print(resp.read().decode())
except Exception as exc:  # noqa: BLE001
    import sys
    print(f"metrics fetch failed: {exc!r}", file=sys.stderr)
    raise SystemExit(1)
PY
  if kubectl exec -n "$NS" "$BROKER_POD" -- python3 -c "$METRICS_CHECK" >"$DIR/engine-metrics.txt" 2>"$DIR/engine-metrics.err.txt"; then
    rm -f "$DIR/engine-metrics.err.txt"
  else
    note "WARN: /metrics snapshot failed (see engine-metrics.err.txt)"
  fi
fi

# GPU fault history: only sparky has the GPU today, so these are sparky-
# specific. Skip with a note if SSH isn't reachable rather than failing the
# whole capture.
if ssh -o ConnectTimeout=5 -o BatchMode=yes sparky true 2>/dev/null; then
  ssh sparky nvidia-smi -q >"$DIR/nvidia-smi.txt" 2>&1 || note "WARN: nvidia-smi -q failed on sparky"
  ssh sparky "journalctl -k -b | grep -iE 'xid|nvrm' | tail -50" >"$DIR/kernel-xid.txt" 2>&1 ||
    note "WARN: journalctl Xid grep failed on sparky"
else
  note "SKIP: ssh sparky unreachable, no nvidia-smi / kernel Xid log captured"
fi

kubectl top nodes >"$DIR/top-nodes.txt" 2>&1 || note "WARN: kubectl top nodes failed (metrics-server unavailable?)"
kubectl top pods -n "$NS" >"$DIR/top-pods-vllm.txt" 2>&1 || note "WARN: kubectl top pods -n vllm failed"

# --- Draft the troubleshooting record --------------------------------------
TEMPLATE="docs/troubleshooting/_template.md"
if [[ -f "$TEMPLATE" ]]; then
  sed -e "s/{{DATE}}/$(date -u +%Y-%m-%d)/g" \
      -e "s/{{TIMESTAMP}}/$TS/g" \
      -e "s/{{ENGINE}}/$ENGINE/g" \
      "$TEMPLATE" >"$DIR/record.md"
else
  note "WARN: $TEMPLATE not found; record.md not drafted"
fi

echo "$DIR"
