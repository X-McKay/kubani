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

check "-f on another tool in the same line is not a force push (allow)" 0 \
  'git fetch -q origin main && helm template x chart -f values.yaml >/dev/null && git push -u origin fix/x'

check "force push to a feature branch (allow)" 0 \
  'git push --force-with-lease origin fix/x'

check "force push with main only in an earlier segment (block)" 2 \
  'git fetch origin main; git push -f origin main'

check "-nx compact namespace form, disallowed verb (block)" 2 \
  'kubectl delete configmap model-config -nvllm'

# --- 2026-11-02 boundary: platform namespaces open, control plane guarded --
check "get in flux-system then echo created (allow, old false positive)" 0 \
  'kubectl get secret -n flux-system sops-age -o name && echo "created earlier"'

check "apply into tenant-test (allow)" 0 \
  'kubectl apply -f t9b-pod-signed.yaml -n tenant-test'

check "apply into agent-platform (allow)" 0 \
  'kubectl -n agent-platform apply -f aps.yaml'

check "delete pod in auth (allow)" 0 \
  'kubectl delete pod keycloak-0 -n auth'

check "patch in temporal (allow)" 0 \
  'kubectl patch deploy envoy-mtls -n temporal --type merge -p {}'

check "global flags before verb in kube-system (block)" 2 \
  'kubectl --context homelab -n kube-system delete pod coredns-abc'

check "apply into kyverno (block)" 2 \
  'kubectl apply -f policy.yaml -n kyverno'

check "create in flux-system (block)" 2 \
  'kubectl create configmap x -n flux-system --from-literal=a=b'

check "second segment mutates guarded namespace (block)" 2 \
  'kubectl get pods -n tenant-test; kubectl delete cm model-config -n vllm'

check "delete clusterpolicy (block)" 2 \
  'kubectl delete clusterpolicy sandbox-shape'

check "create secret anywhere (block)" 2 \
  'kubectl create secret generic x -n tenant-test --from-literal=k=v'

check "create token (block)" 2 \
  'kubectl create token registry-controller -n agent-platform'

check "daemon-reexec (block)" 2 \
  'sudo systemctl daemon-reexec'

check "gh variable set (block)" 2 \
  'gh variable set REGISTRY_USERNAME --body x -R X-McKay/zetra-agents'

check "flux uninstall (block)" 2 \
  'flux uninstall --silent'

check "registry user creation (block)" 2 \
  'bash infrastructure/scripts/add_registry_user.sh kyverno'

check "cosign key generation (block)" 2 \
  'cosign generate-key-pair'

check "release tag push (allow)" 0 \
  'git push origin investigator/v0.1.4'

check "flux get (allow)" 0 \
  'flux get kustomizations -A'

echo
echo "pass=$PASS fail=$FAIL"
[[ "$FAIL" -eq 0 ]]
