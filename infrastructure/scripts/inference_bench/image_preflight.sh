#!/usr/bin/env bash
# Verify a candidate vLLM image on the inference node before any rollout.
#
#   image_preflight.sh <image> [--module <python-module>]... [--flag <--serve-flag[=value]>]...
#   image_preflight.sh vllm/vllm-openai:v0.30.0-aarch64-cu129 --module b12x --flag --moe-backend=b12x
#
# Runs a throwaway pod (one time-sliced GPU) on the inference node with the candidate image
# (which also pre-pulls it there, so the real rollout and any rollback are
# fast), then reports package versions, whether each optional module is
# importable, and whether each serve flag and choice exists in this build's
# `vllm serve --help=all`. Exit 1 if any module or flag is missing.
set -euo pipefail

[[ $# -ge 1 ]] || { sed -n '2,5p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
IMAGE=$1
shift
MODULES=() FLAGS=()
while [[ $# -gt 0 ]]; do
  case $1 in
    --module) MODULES+=("$2"); shift 2 ;;
    --flag) FLAGS+=("$2"); shift 2 ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done
export KUBECONFIG=${KUBECONFIG:-/home/al/.kube/config}
NS=vllm
POD="inference-preflight-$(date -u +%Y%m%d%H%M%S)"
trap 'kubectl delete pod "$POD" -n "$NS" --ignore-not-found --wait=false >/dev/null' EXIT

# Checks run in the image; arguments arrive as env to avoid quoting games.
read -r -d '' CHECK <<'PY' || true
import importlib.util, json, os, re, subprocess, sys
out = {"python": sys.version.split()[0]}
for pkg in ("vllm", "torch", "torchvision", "torchaudio", "flashinfer", "transformers"):
    try:
        mod = __import__(pkg)
        out[pkg] = getattr(mod, "__version__", "?")
    except Exception as exc:  # noqa: BLE001
        out[pkg] = f"import failed: {exc!r}"[:200]
try:
    import torch
    out["torch_cuda"] = torch.version.cuda
except Exception:
    pass
missing = []
for m in filter(None, os.environ.get("MODULES", "").split(",")):
    ok = importlib.util.find_spec(m) is not None
    out[f"module {m}"] = "present" if ok else "MISSING"
    missing += [] if ok else [m]
flags = list(filter(None, os.environ.get("FLAGS", "").split(",")))
proc = subprocess.run(["vllm", "serve", "--help=all"], capture_output=True, text=True)
helptext = proc.stdout
cli_failed = proc.returncode != 0 or not helptext.strip()
if cli_failed:
    print(f"vllm CLI failed (exit {proc.returncode})")
    for line in proc.stderr.strip().splitlines()[-15:]:
        print(line)
    for f in flags:
        out[f"flag {f}"] = "UNKNOWN (CLI failed)"
else:
    for f in flags:
        name, _, value = f.partition("=")
        # The flag must end at whitespace, "=" or ",": a plain \b would let
        # --kv-cache-memory pass as accepted because --kv-cache-memory-bytes exists.
        m = re.search(re.escape(name) + r"(?=[\s=,])[^\n]*(?:\n(?!\s*--)[^\n]*)*", helptext)
        if not m:
            out[f"flag {f}"] = "NOT FOUND"
            missing.append(f)
            continue
        block = m.group(0)
        # A value can only be validated when the help enumerates choices,
        # either as argparse's {a,b,c} list or as '- "x"' bullets. Flags such
        # as --attention-backend and --reasoning-parser stopped listing their
        # choices in v0.30.0, so their values are reported, not judged.
        enumerates = re.search(r"\{[^}\n]*\}", block) or re.search(r'- "[^"]+"', block)
        if not value:
            out[f"flag {f}"] = "accepted"
        elif not enumerates:
            out[f"flag {f}"] = "accepted (value not validated: help lists no choices)"
        elif re.search(r"(?<![\w-])" + re.escape(value) + r"(?![\w-])", block):
            out[f"flag {f}"] = "accepted"
        else:
            out[f"flag {f}"] = "NOT FOUND (flag exists, value missing from choices)"
            missing.append(f)
for k, v in out.items():
    print(f"{k:40s} {v}")
sys.exit(1 if (missing or cli_failed) else 0)
PY

kubectl apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $POD
  namespace: $NS
  labels: {kubani.io/role: inference-bench}
spec:
  restartPolicy: Never
  # A GPU slice and the nvidia runtime, not CPU-only: since v0.30.0 even
  # "vllm serve --help=all" infers the device type at argument-parse time and
  # dies without one ("Failed to infer device type"). Time-sliced, so this
  # does not take a slot from the engines.
  runtimeClassName: nvidia
  nodeSelector: {topology.kubani.io/usage-class: inference}
  tolerations:
    - {key: nvidia.com/gpu, operator: Equal, value: "true", effect: NoSchedule}
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534
    seccompProfile: {type: RuntimeDefault}
  containers:
    - name: preflight
      image: $IMAGE
      imagePullPolicy: IfNotPresent
      command: ["python3", "-c", $(jq -Rs . <<<"$CHECK")]
      securityContext:
        allowPrivilegeEscalation: false
        capabilities: {drop: ["ALL"]}
      env:
        - {name: HOME, value: /tmp}
        - {name: MODULES, value: "$(IFS=,; echo "${MODULES[*]:-}")"}
        - {name: FLAGS, value: "$(IFS=,; echo "${FLAGS[*]:-}")"}
      resources:
        requests: {cpu: 250m, memory: 1Gi}
        limits: {cpu: "2", memory: 4Gi, nvidia.com/gpu: "1"}
EOF

echo "pod $POD: pulling $IMAGE on the inference node (first pull of a vLLM image takes minutes)..."
for _ in $(seq 1 180); do
  PHASE=$(kubectl get pod "$POD" -n "$NS" -o jsonpath='{.status.phase}')
  [[ $PHASE == Succeeded || $PHASE == Failed ]] && break
  sleep 10
done
kubectl logs -n "$NS" "$POD" | grep -v -i "warning\|^INFO"
[[ $(kubectl get pod "$POD" -n "$NS" -o jsonpath='{.status.phase}') == Succeeded ]]
