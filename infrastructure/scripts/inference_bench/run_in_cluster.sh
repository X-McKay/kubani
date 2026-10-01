#!/usr/bin/env bash
# Run bench.py as an ephemeral Job on the inference node and save the result.
#
#   run_in_cluster.sh <profile> <label> [bench.py args...]
#   run_in_cluster.sh main baseline-v0.27.1
#   run_in_cluster.sh fast candidate-v0.30.0 --suites quality,perf,sleepwake --soak-seconds 0
#
# Why a Job and not a workstation run: the client sits next to the engine, so
# numbers are not polluted by LAN/Tailscale latency, and the Job reuses the
# engine's own (already cached) image, which ships python3. The Job is
# transient test tooling, not cluster state, so it is applied imperatively and
# deleted afterwards. Its egress is allowed by the allow-inference-bench-egress
# NetworkPolicy (label kubani.io/role: inference-bench).
#
# Result: docs/infrastructure/inference/benchmarks/<profile>/<UTC>_<label>.json
set -euo pipefail

usage() { sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[[ $# -ge 2 ]] || usage
PROFILE=$1 LABEL=$2
shift 2
[[ $LABEL =~ ^[a-z0-9][a-z0-9.-]*$ ]] || { echo "label must match [a-z0-9.-]+" >&2; exit 2; }

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
PROFILES="$HERE/profiles.json"
NS=vllm
export KUBECONFIG=${KUBECONFIG:-/home/al/.kube/config}

jq -e --arg p "$PROFILE" '.profiles[$p]' "$PROFILES" >/dev/null ||
  { echo "unknown profile '$PROFILE' (have: $(jq -r '.profiles|keys|join(", ")' "$PROFILES"))" >&2; exit 2; }
prof() { jq -r --arg p "$PROFILE" ".profiles[\$p].$1" "$PROFILES"; }
DEPLOY=$(prof deployment)
BROKER_DEPLOY=$(prof broker_deployment)

# --- Capture exactly what is being measured -----------------------------------
DEP_JSON=$(kubectl get deploy "$DEPLOY" -n "$NS" -o json)
IMAGE=$(jq -r '.spec.template.spec.containers[0].image' <<<"$DEP_JSON")
READY=$(jq -r '.status.readyReplicas // 0' <<<"$DEP_JSON")
[[ $READY -ge 1 ]] || { echo "deployment $DEPLOY has no ready replicas" >&2; exit 1; }
ENGINE_POD=$(kubectl get pod -n "$NS" -l "app=$DEPLOY" --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].metadata.name}')
POD_IMAGE=$(kubectl get pod -n "$NS" "$ENGINE_POD" -o jsonpath='{.spec.containers[0].image}')
[[ $POD_IMAGE == "$IMAGE" ]] ||
  { echo "running pod image $POD_IMAGE != deployment image $IMAGE (rollout in progress?)" >&2; exit 1; }
# vllm serve flags, one per element, from the shell-wrapped args block.
ARGS_JSON=$(jq -c '[.spec.template.spec.containers[0].args[0] | split("\n")[]
  | gsub("^\\s+|\\s*\\\\$"; "") | select(startswith("--"))]' <<<"$DEP_JSON")
CONFIG_JSON=$(kubectl get configmap model-config -n "$NS" -o json | jq -c '.data')
BROKER_IP=$(kubectl get pod -n "$NS" -l "app=$BROKER_DEPLOY" --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].status.podIP}')
META=$(jq -nc --arg image "$IMAGE" --argjson args "$ARGS_JSON" --argjson config "$CONFIG_JSON" \
  --arg pod "$ENGINE_POD" --arg node "$(kubectl get pod -n "$NS" "$ENGINE_POD" -o jsonpath='{.spec.nodeName}')" \
  --arg git "$(git -C "$REPO" rev-parse --short HEAD)$(git -C "$REPO" diff --quiet || echo -dirty)" \
  --arg flux "$(kubectl get kustomization apps -n flux-system -o jsonpath='{.status.lastAppliedRevision}' 2>/dev/null)" \
  '{image:$image, args:$args, model_config:$config, engine_pod:$pod, node:$node, repo_git:$git, flux_revision:$flux}')

echo "profile=$PROFILE label=$LABEL"
echo "image=$IMAGE pod=$ENGINE_POD broker=$BROKER_IP"

# --- Launch --------------------------------------------------------------------
ID="inference-bench-$(date -u +%Y%m%d%H%M%S)"
cleanup() {
  kubectl delete job "$ID" -n "$NS" --ignore-not-found --wait=false >/dev/null
  kubectl delete configmap "$ID" -n "$NS" --ignore-not-found >/dev/null
}
trap cleanup EXIT

kubectl create configmap "$ID" -n "$NS" \
  --from-file=bench.py="$HERE/bench.py" --from-file=profiles.json="$PROFILES" >/dev/null
kubectl label configmap "$ID" -n "$NS" kubani.io/role=inference-bench >/dev/null

# Extra bench.py args arrive newline-joined through --arg rather than
# `jq --args "$@"`: jq 1.7+ keeps parsing tokens that start with `--` as its
# own options after --args (`--suites` became "Unknown option"), and the `--`
# terminator means "positional" in 1.7 but "files" in 1.6, so neither form is
# portable across the workstation and rig0.
EXTRA_ARGS=$(printf '%s\n' "$@")
BENCH_ARGS=$(jq -nc --arg p "$PROFILE" --arg l "$LABEL" --arg a "http://$BROKER_IP:8081" --arg extra "$EXTRA_ARGS" \
  '["python3","/bench/bench.py","--profile",$p,"--label",$l,"--admin-url",$a]
   + ($extra | split("\n") | map(select(. != "")))')

kubectl apply -f - >/dev/null <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: $ID
  namespace: $NS
  labels: {kubani.io/role: inference-bench}
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 10800
  ttlSecondsAfterFinished: 3600
  template:
    metadata:
      labels: {kubani.io/role: inference-bench}
    spec:
      restartPolicy: Never
      securityContext:
        runAsNonRoot: true
        runAsUser: 65534
        seccompProfile: {type: RuntimeDefault}
      nodeSelector: {topology.kubani.io/usage-class: inference}
      tolerations:
        - {key: nvidia.com/gpu, operator: Equal, value: "true", effect: NoSchedule}
      containers:
        - name: bench
          image: $IMAGE
          imagePullPolicy: IfNotPresent
          command: $BENCH_ARGS
          securityContext:
            allowPrivilegeEscalation: false
            capabilities: {drop: ["ALL"]}
          env:
            - name: HOME
              value: /tmp
            - name: PYTHONUNBUFFERED
              value: "1"
            - name: BENCH_META_JSON
              value: '$(sed "s/'/''/g" <<<"$META")'
            - name: GPU_BROKER_ADMIN_TOKEN
              valueFrom:
                secretKeyRef: {name: gpu-broker-admin, key: admin-token, optional: true}
          resources:
            requests: {cpu: 500m, memory: 512Mi}
            limits: {cpu: "2", memory: 2Gi}
          volumeMounts:
            - {name: bench, mountPath: /bench, readOnly: true}
      volumes:
        - name: bench
          configMap: {name: $ID}
EOF

echo "job $ID launched; waiting for pod..."
kubectl wait --for=condition=Ready pod -n "$NS" -l "job-name=$ID" --timeout=300s >/dev/null 2>&1 ||
  kubectl wait --for=jsonpath='{.status.phase}'=Succeeded pod -n "$NS" -l "job-name=$ID" --timeout=10s >/dev/null 2>&1 || true

LOG=$(mktemp)
kubectl logs -f -n "$NS" "job/$ID" | tee "$LOG" >&2 || true

OUT_DIR="$REPO/docs/infrastructure/inference/benchmarks/$PROFILE"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/$(date -u +%Y%m%dT%H%MZ)_$LABEL.json"
# kubectl logs merges stdout and stderr without ordering guarantees, so a
# "[HH:MM:SS] ..." log line can land inside the JSON block; drop those.
sed -n '/==INFERENCE-BENCH-RESULT-BEGIN==/,/==INFERENCE-BENCH-RESULT-END==/p' "$LOG" | sed '1d;$d' \
  | grep -v '^\[[0-9:]*\] ' >"$OUT"
rm -f "$LOG"
if ! jq -e .schema "$OUT" >/dev/null 2>&1; then
  rm -f "$OUT"
  echo "no result produced; job status:" >&2
  kubectl get job "$ID" -n "$NS" -o jsonpath='{.status}' >&2; echo >&2
  exit 1
fi
echo
echo "result: ${OUT#"$REPO"/}"
jq -r '.gates | to_entries[] | "  gate \(.key): \(if .value then "pass" else "FAIL" end)"' "$OUT"
jq -e '[.gates[]] | all' "$OUT" >/dev/null
