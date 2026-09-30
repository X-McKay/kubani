#!/usr/bin/env bash
# Pre/post checklist for a host maintenance window (driver/kernel/OS update).
# See .claude/skills/host-maintenance/SKILL.md for the full procedure —
# this script is the cordon/uncordon and verification half of it, not a
# substitute for reading that skill before a sparky window.
#
#   node_maintenance.sh <host> pre    # capacity + PVC/age.key checks, cordon
#   node_maintenance.sh <host> post   # uncordon, wait Ready, verify vllm engines
#
# Deliberately does NOT drain: sparky's vLLM engines use the Recreate
# strategy, so draining just adds an extra pod cycle on top of the reboot,
# and when to let the engines stop is the operator's call.
set -euo pipefail

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[[ $# -eq 2 ]] || usage
HOST=$1
MODE=$2

HERE=$(cd "$(dirname "$0")" && pwd)
export KUBECONFIG=${KUBECONFIG:-/home/al/.kube/config}

case "$MODE" in
  pre)
    echo "=== capacity ledger ==="
    python3 "$HERE/capacity.py" || echo "(non-fatal: capacity check reported an issue — review before proceeding)"

    echo
    echo "=== pods on $HOST ==="
    kubectl get pods -A --field-selector "spec.nodeName=$HOST" -o wide

    echo
    echo "=== local-path PVCs bound on $HOST ==="
    kubectl get pv -o json | jq -r --arg host "$HOST" '
      .items[]
      | select(.spec.nodeAffinity.required.nodeSelectorTerms[]?.matchExpressions[]?.values[]? == $host)
      | [.metadata.name, (.spec.claimRef.namespace // "-"), (.spec.claimRef.name // "-")]
      | @tsv' | { echo -e "PV\tNAMESPACE\tCLAIM"; cat; } | column -t -s $'\t'

    echo
    echo "=== age.key / kubeconfig check on $HOST ==="
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" test -f ~/git/kubani/age.key 2>/dev/null; then
      echo "WARNING: age.key found on $HOST — remove it before the reboot (see .claude/rules/secrets.md)."
    elif ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" true 2>/dev/null; then
      echo "WARNING: could not SSH to $HOST to check for age.key — verify manually."
    else
      echo "clean: no age.key found on $HOST"
    fi

    echo
    echo "=== cordoning $HOST ==="
    kubectl cordon "$HOST"

    cat <<EOF

Manual steps from here (see .claude/skills/host-maintenance/SKILL.md):
  1. Apt steps on the 580 driver branch ONLY (590.x deadlocks CUDA graph
     capture on GB10) — verify the branch before upgrading.
  2. systemctl set-default multi-user.target
  3. Reboot.
  4. Once the host is back: $HERE/node_maintenance.sh $HOST post
EOF
    ;;

  post)
    echo "=== uncordoning $HOST ==="
    kubectl uncordon "$HOST"

    echo
    echo "=== waiting for node Ready ==="
    kubectl wait --for=condition=Ready "node/$HOST" --timeout=10m

    if [[ "$HOST" == "sparky" ]]; then
      echo
      echo "=== fast model first, then main ==="
      kubectl rollout status deployment/vllm-fast -n vllm --timeout=15m
      kubectl rollout status deployment/vllm -n vllm --timeout=15m
      echo
      echo "Verify each with a real completion:"
      echo "  just inference-restart fast --no-capture   # or a plain completion check"
      echo "  just inference-restart main --no-capture"
    fi

    cat <<EOF

Next: run the drift bench to confirm no platform regression from the
window (docs/infrastructure/inference/release-process.md):
  just inference-bench main drift-$(date -u +%Y%m%d)
  just inference-compare main <result>
Never promote a drift result.
EOF
    ;;

  *)
    echo "mode must be 'pre' or 'post', got '$MODE'" >&2
    exit 2
    ;;
esac
