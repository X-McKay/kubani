#!/usr/bin/env bash
# Restart a wedged or upgraded vLLM engine the safe way: delete the pod (the
# Deployment uses Recreate, so this is a clean restart that leaves the spec
# Flux owns untouched), wait for the rollout, then prove it serves with one
# real completion through the broker. Never `kubectl rollout restart` — Flux
# reverts the restartedAt annotation within its reconcile interval, which is
# what doubled the 2026-09-25 outage (docs/troubleshooting/vllm-main-engine-hang-gb10.md).
#
#   inference_restart.sh <main|fast> [--no-capture]
#
# --no-capture suppresses the "capture forensics first" reminder. It exists
# for a second restart attempt within the same incident, not as a default —
# see .claude/skills/incident-capture/SKILL.md.
set -euo pipefail

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[[ $# -ge 1 ]] || usage
ENGINE=$1
shift
NO_CAPTURE=0
while [[ $# -gt 0 ]]; do
  case $1 in
    --no-capture) NO_CAPTURE=1; shift ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done

NS=vllm
export KUBECONFIG=${KUBECONFIG:-/home/al/.kube/config}

case "$ENGINE" in
  main)
    DEPLOY=vllm
    BROKER_DEPLOY=gpu-broker-main
    MODEL_KEY=LLM_MODEL_NAME
    ;;
  fast)
    DEPLOY=vllm-fast
    BROKER_DEPLOY=gpu-broker
    MODEL_KEY=FAST_MODEL_NAME
    ;;
  *)
    echo "engine must be 'main' or 'fast', got '$ENGINE'" >&2
    exit 2
    ;;
esac

if [[ "$NO_CAPTURE" -ne 1 ]]; then
  echo "Reminder: capture forensics before restarting a wedged engine —" >&2
  echo "  just incident-capture $ENGINE" >&2
  echo "Proceeding with the restart in 5s (Ctrl-C to abort, or re-run with --no-capture to skip this notice)..." >&2
  sleep 5
fi

MODEL_NAME=$(kubectl get configmap model-config -n "$NS" -o jsonpath="{.data.$MODEL_KEY}")
[[ -n "$MODEL_NAME" ]] || { echo "model-config missing $MODEL_KEY" >&2; exit 1; }

echo "deleting pod(s) for deployment/$DEPLOY in $NS..."
kubectl delete pod -n "$NS" -l "app=$DEPLOY"

echo "waiting for rollout..."
kubectl rollout status "deployment/$DEPLOY" -n "$NS" --timeout=15m

BROKER_POD=$(kubectl get pod -n "$NS" -l "app=$BROKER_DEPLOY" --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].metadata.name}')
[[ -n "$BROKER_POD" ]] || { echo "no running broker pod for app=$BROKER_DEPLOY" >&2; exit 1; }

echo "verifying with a real completion through broker pod $BROKER_POD (model=$MODEL_NAME)..."
# Model name is injected via Python's json.dumps of an argv-passed string
# (not shell/heredoc interpolation) so nothing in the model name can break
# out of the generated script.
read -r -d '' CHECK <<'PY' || true
import json, sys, urllib.request

model = sys.argv[1]
payload = json.dumps({
    "model": model,
    "messages": [{"role": "user", "content": "Say OK"}],
    # Reasoning models spend a small budget on thinking first; disable it
    # for the check (Qwen3 chat template kwarg) and leave room anyway.
    "max_tokens": 32,
    "chat_template_kwargs": {"enable_thinking": False},
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8080/v1/chat/completions",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read().decode()
        print(body)
        data = json.loads(body)
        msg = data["choices"][0]["message"]
        reply = msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning") or ""
        print(f"REPLY: {reply!r} (completion_tokens={data.get('usage', {}).get('completion_tokens')})", file=sys.stderr)
        if not reply:
            raise SystemExit("completion returned no text")
        sys.exit(0)
except Exception as exc:  # noqa: BLE001
    print(f"completion check failed: {exc!r}", file=sys.stderr)
    sys.exit(1)
PY

# Requires python3 in the gpu-broker image. If a future broker image drops
# it, switch this to a debug-container exec (kubectl debug) with the same
# script.
kubectl exec -n "$NS" "$BROKER_POD" -- python3 -c "$CHECK" "$MODEL_NAME"
echo "engine $ENGINE ($DEPLOY) is serving."
