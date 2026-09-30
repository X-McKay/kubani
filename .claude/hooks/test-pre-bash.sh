#!/bin/bash
# Exercises pre-bash.sh against representative commands and asserts the exit
# code (0 = allow, 2 = block). Run with: bash .claude/hooks/test-pre-bash.sh
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/pre-bash.sh"

PASS=0
FAIL=0

# args: description, expected exit code, command text
check() {
    local desc="$1" expected="$2" cmd="$3"
    local payload actual
    payload=$(python3 -c '
import json, sys
print(json.dumps({"tool_input": {"command": sys.argv[1]}}))
' "$cmd")
    echo "$payload" | "$HOOK" >/tmp/pre-bash-test-out.txt 2>&1
    actual=$?
    if [[ "$actual" == "$expected" ]]; then
        echo "PASS  [$desc] exit=$actual"
        PASS=$((PASS + 1))
    else
        echo "FAIL  [$desc] expected=$expected actual=$actual"
        echo "      cmd: $cmd"
        echo "      output: $(cat /tmp/pre-bash-test-out.txt)"
        FAIL=$((FAIL + 1))
    fi
}

# --- allow: documented recovery and safe reads -----------------------------
check "delete pod recovery (allow)" 0 \
  'KUBECONFIG=/home/al/.kube/config kubectl delete pod -n vllm -l app=vllm'

check "get pods in vllm (allow)" 0 \
  'kubectl get pods -n vllm'

check "delete namespaced pod by name (allow)" 0 \
  'kubectl delete pod vllm-abc123 -n vllm'

check "apply transient preflight pod via stdin (allow)" 0 \
  'kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: inference-preflight-20260930120000
  namespace: vllm
EOF'

check "create bench configmap (allow)" 0 \
  'kubectl create configmap inference-bench-20260930120000 -n vllm --from-file=bench.py=bench.py'

check "delete bench job (allow)" 0 \
  'kubectl delete job inference-bench-20260930120000 -n vllm --ignore-not-found'

check "flux reconcile (allow)" 0 \
  'flux reconcile kustomization apps -n flux-system --with-source'

check "delete bench jobs by label selector (allow)" 0 \
  'kubectl delete job -n vllm -l kubani.io/role=inference-bench --ignore-not-found'
check "delete bench configmaps by label selector (allow)" 0 \
  'kubectl delete configmap -n vllm -l kubani.io/role=inference-bench'

check "apply outside operational namespace (allow)" 0 \
  'kubectl apply -f infrastructure/gitops/apps/kustomization.yaml -n default'

check "describe pod (allow, not a modifying verb)" 0 \
  'kubectl describe pod vllm-abc123 -n vllm'

# --- block: rollout restart, bare namespace mutation, dangerous patterns ---
check "rollout restart on vllm (block)" 2 \
  'kubectl rollout restart deployment/vllm -n vllm'

check "rollout restart on any namespace (block)" 2 \
  'kubectl rollout restart deployment/coredns -n kube-system'

check "scale to zero in vllm (block)" 2 \
  'kubectl scale deploy vllm -n vllm --replicas=0'

check "patch configmap in vllm (block)" 2 \
  'kubectl patch configmap model-config -n vllm --type merge -p {}'

check "delete pod in monitoring without allowlist match (block)" 2 \
  'kubectl delete pod grafana-abc -n monitoring'

check "apply arbitrary manifest into vllm (block)" 2 \
  'kubectl apply -f manifest.yaml -n vllm'

check "delete namespace (block, dangerous pattern)" 2 \
  'kubectl delete namespace vllm'

check "force push to main (block)" 2 \
  'git push --force origin main'

check "-nx compact namespace form, disallowed verb (block)" 2 \
  'kubectl delete configmap model-config -nvllm'

echo
echo "pass=$PASS fail=$FAIL"
[[ "$FAIL" -eq 0 ]]
