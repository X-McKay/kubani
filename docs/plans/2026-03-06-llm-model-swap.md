# LLM Model Swap: Qwen3-14B → Qwen3.5-9B-NVFP4 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Qwen3-14B-FP4 with AxionML/Qwen3.5-9B-NVFP4 as the primary LLM and consolidate the separate VLM into the same model.

**Architecture:** Blue-green fast cutover — pre-download the model, update all manifests and configs, push to git for Flux to reconcile. The new model is multimodal (text + vision), smaller (9B vs 14B), and supports 128K context.

**Tech Stack:** vLLM, Kubernetes/Flux GitOps, Python (pydantic-settings), YAML configs

**Design doc:** `docs/plans/2026-03-06-llm-model-swap-design.md`

---

### Task 1: Pre-download Model to Cluster Storage

**Context:** The model must be on local disk before the swap to minimize downtime. The vLLM pod mounts `/models` from the `model-storage` PVC on the `sparky` node.

**Step 1: Download the model**

SSH into sparky and use huggingface-cli to download:

```bash
# From a pod on sparky with the model-storage PVC mounted, or via SSH
# Option A: Run a temporary pod
KUBECONFIG=/home/al/.kube/config kubectl run model-download \
  --namespace=vllm \
  --image=python:3.12-slim \
  --restart=Never \
  --overrides='{
    "spec": {
      "nodeSelector": {"kubernetes.io/hostname": "sparky"},
      "containers": [{
        "name": "model-download",
        "image": "python:3.12-slim",
        "command": ["bash", "-c", "pip install huggingface_hub && huggingface-cli download AxionML/Qwen3.5-9B-NVFP4 --local-dir /models/Qwen3.5-9B-NVFP4"],
        "volumeMounts": [{"name": "models", "mountPath": "/models"}],
        "env": [{"name": "HF_HOME", "value": "/models"}]
      }],
      "volumes": [{"name": "models", "persistentVolumeClaim": {"claimName": "model-storage"}}]
    }
  }'
```

**Step 2: Verify download completed**

```bash
KUBECONFIG=/home/al/.kube/config kubectl logs model-download -n vllm --follow
# Wait for completion, then verify files exist:
KUBECONFIG=/home/al/.kube/config kubectl exec -n vllm model-download -- ls -lah /models/Qwen3.5-9B-NVFP4/
```

Expected: Model files present (~6GB total), including `config.json`, `*.safetensors`, `tokenizer.json`

**Step 3: Clean up download pod**

```bash
KUBECONFIG=/home/al/.kube/config kubectl delete pod model-download -n vllm
```

---

### Task 2: Update vLLM Model ConfigMap

**Files:**
- Modify: `infrastructure/gitops/apps/vllm/model-config.yaml:9-19`

**Step 1: Update the ConfigMap values**

Change these fields in `model-config.yaml`:

```yaml
data:
  # Main LLM model configuration
  LLM_MODEL_NAME: "Qwen3.5-9B-NVFP4"
  LLM_MODEL_PATH: "AxionML/Qwen3.5-9B-NVFP4"
  LLM_GPU_MEMORY_UTILIZATION: "0.50"

  # Context length - 128K (Qwen3.5 supports up to 262K natively)
  LLM_MAX_MODEL_LEN: "131072"

  # Speculative decoding - native MTP for Qwen3.5
  LLM_SPECULATIVE_CONFIG: '{"method":"qwen3_next_mtp","num_speculative_tokens":2}'

  # Fast model configuration (unchanged)
  FAST_MODEL_NAME: "Qwen/Qwen3-0.6B"
  FAST_GPU_MEMORY_UTILIZATION: "0.15"
  FAST_MAX_MODEL_LEN: "32768"

  # Embeddings model configuration (unchanged)
  EMBEDDINGS_MODEL_NAME: "Qwen/Qwen3-Embedding-0.6B"
  EMBEDDINGS_GPU_MEMORY_UTILIZATION: "0.10"
  EMBEDDINGS_MAX_MODEL_LEN: "8192"
```

**Step 2: Sync the ai-agents ConfigMap**

Update `infrastructure/gitops/apps/ai-agents/k8s-monitor/model-config.yaml:13`:

```yaml
data:
  # Main LLM model configuration (must match vllm deployment)
  LLM_MODEL_NAME: "Qwen3.5-9B-NVFP4"

  # Fast model for simple agents (must match fast-model vllm deployment)
  FAST_MODEL_NAME: "Qwen/Qwen3-0.6B"

  # Embeddings model configuration (must match vllm-embeddings deployment)
  EMBEDDINGS_MODEL_NAME: "Qwen/Qwen3-Embedding-0.6B"
```

---

### Task 3: Update vLLM Deployment Manifest

**Files:**
- Modify: `infrastructure/gitops/apps/vllm/deployment.yaml:47-58`

**Step 1: Update the vLLM serve command with new flags**

Replace the `args` block (lines 49-58) with:

```yaml
          args:
            - |
              exec vllm serve "$LLM_MODEL_PATH" \
                --served-model-name "$LLM_MODEL_NAME" \
                --host 0.0.0.0 \
                --port 8000 \
                --gpu-memory-utilization "$LLM_GPU_MEMORY_UTILIZATION" \
                --enable-auto-tool-choice \
                --tool-call-parser qwen3_coder \
                --reasoning-parser qwen3 \
                --quantization modelopt \
                --max-model-len "$LLM_MAX_MODEL_LEN" \
                --speculative-config "$LLM_SPECULATIVE_CONFIG"
```

Key changes from current:
- `--tool-call-parser hermes` → `--tool-call-parser qwen3_coder`
- Added `--reasoning-parser qwen3`
- Added `--quantization modelopt`

**Step 2: Reduce startup probe threshold**

The 9B model loads faster than 14B. Update line 72:

```yaml
          startupProbe:
            httpGet:
              path: /health
              port: http
            # Allow up to 10 minutes for model loading (smaller model + NVFP4)
            failureThreshold: 60
            periodSeconds: 10
```

---

### Task 4: Update Nexus Orchestrator VLM Configuration

**Files:**
- Modify: `infrastructure/gitops/apps/nexus/orchestrator-deployment.yaml:68-71`
- Modify: `kubani/nexus/tools/vision.py:1-5,22-25,27`

**Step 1: Point VLM env vars to main LLM endpoint**

In `orchestrator-deployment.yaml`, change lines 68-71:

```yaml
        - name: VLM_API_URL
          value: "https://llm.almckay.io/v1"
        - name: VLM_MODEL
          value: "Qwen3.5-9B-NVFP4"
```

**Step 2: Update vision.py defaults and docstring**

In `kubani/nexus/tools/vision.py`, update lines 1-5:

```python
"""Vision tool for the Nexus PI agent.

Sends a screenshot (base64 PNG) to Qwen3.5-9B-NVFP4 via the OpenAI-compatible
vLLM API and returns a structured description of the screen.

Usage:
    from kubani.nexus.tools.vision import analyze_screen
    # Add to workspace_tools list in activities.py
"""
```

Update lines 23-25:

```python
VLM_API_URL = os.environ.get("VLM_API_URL", "https://llm.almckay.io/v1")
VLM_API_KEY = os.environ.get("VLM_API_KEY", "dummy")
VLM_MODEL = os.environ.get("VLM_MODEL", "Qwen3.5-9B-NVFP4")
```

Update line 27 — replace `/no_think` with proper thinking control (Qwen3.5 doesn't support soft switches):

```python
_ANALYSIS_PROMPT = """Analyze this screenshot and return a JSON object with exactly these fields:
```

Note: The `enable_thinking: false` should be passed via `chat_template_kwargs` in the API request body instead. Update the payload in the `analyze_screen` function (around line 65):

```python
    payload = {
        "model": VLM_MODEL,
        "messages": [...],
        "max_tokens": 2048,
        "temperature": 0.1,
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": False},
        },
    }
```

Actually, since this uses raw httpx (not openai client), the `chat_template_kwargs` goes directly in the request body:

```python
    payload = {
        "model": VLM_MODEL,
        "messages": [...],
        "max_tokens": 2048,
        "temperature": 0.1,
        "chat_template_kwargs": {"enable_thinking": False},
    }
```

---

### Task 5: Update Application Config Files

**Files:**
- Modify: `config/default.yaml:83`
- Modify: `config/production.yaml:74`
- Modify: `config/local.yaml:80`

**Step 1: Update default.yaml line 83**

```yaml
  model: Qwen3.5-9B-NVFP4
```

**Step 2: Update production.yaml line 74**

```yaml
  model: Qwen3.5-9B-NVFP4
```

**Step 3: Update local.yaml line 80**

```yaml
  model: Qwen3.5-9B-NVFP4
```

---

### Task 6: Update Framework and Tool Code Defaults

**Files:**
- Modify: `kubani/framework/config.py:283`
- Modify: `platform/skill-dev-tools/src/skill_dev_tools/llm/client.py:37`

**Step 1: Update LLMConfig default model**

In `kubani/framework/config.py` line 283:

```python
    model: str = Field(
        default="Qwen3.5-9B-NVFP4",
        description="Default model identifier",
    )
```

**Step 2: Update skill-dev-tools LLM client default**

In `platform/skill-dev-tools/src/skill_dev_tools/llm/client.py` line 37:

```python
        model: str = "Qwen3.5-9B-NVFP4",
```

---

### Task 7: Update Kubani UI Deployment

**Files:**
- Modify: `infrastructure/gitops/apps/kubani-ui/deployment.yaml:38`

**Step 1: Update MODEL_NAME env var**

```yaml
            - name: MODEL_NAME
              value: "Qwen3.5-9B-NVFP4"
```

---

### Task 8: Update Nexus .env.example

**Files:**
- Modify: `kubani/nexus/.env.example`

**Step 1: Add VLM configuration to .env.example**

Add after line 23 (`LLM_API_URL=...`):

```
# VLM (uses same vLLM instance as LLM - Qwen3.5 is multimodal)
VLM_API_URL=https://llm.almckay.io/v1
VLM_MODEL=Qwen3.5-9B-NVFP4
```

---

### Task 9: Commit All Changes

**Step 1: Review all changes**

```bash
git diff --stat
git diff
```

Verify only expected files changed and no secrets leaked.

**Step 2: Commit**

```bash
git add \
  infrastructure/gitops/apps/vllm/model-config.yaml \
  infrastructure/gitops/apps/vllm/deployment.yaml \
  infrastructure/gitops/apps/ai-agents/k8s-monitor/model-config.yaml \
  infrastructure/gitops/apps/nexus/orchestrator-deployment.yaml \
  infrastructure/gitops/apps/kubani-ui/deployment.yaml \
  config/default.yaml \
  config/production.yaml \
  config/local.yaml \
  kubani/framework/config.py \
  kubani/nexus/tools/vision.py \
  kubani/nexus/.env.example \
  platform/skill-dev-tools/src/skill_dev_tools/llm/client.py \
  docs/plans/2026-03-06-llm-model-swap-design.md \
  docs/plans/2026-03-06-llm-model-swap.md

git commit -m "feat: replace Qwen3-14B with Qwen3.5-9B-NVFP4 multimodal model

- Swap primary LLM from nvidia/Qwen3-14B-FP4 to AxionML/Qwen3.5-9B-NVFP4
- Consolidate separate VLM (Qwen3-VL-8B) into main model (Qwen3.5 is multimodal)
- Update vLLM flags: qwen3_coder tool parser, qwen3 reasoning parser, modelopt quantization
- Increase context length from 32K to 128K
- Reduce GPU memory from 60% to 50% (smaller model)
- Switch speculative decoding from ngram to qwen3_next_mtp
- Update all config files, framework defaults, and deployment manifests"
```

---

### Task 10: Push and Deploy

**Step 1: Push to trigger Flux**

```bash
git push origin main
```

**Step 2: Force Flux reconciliation (optional, faster than waiting)**

```bash
KUBECONFIG=/home/al/.kube/config kubectl annotate --overwrite kustomization apps -n flux-system reconcile.fluxcd.io/requestedAt="$(date +%s)"
```

---

### Task 11: Verify Deployment

**Step 1: Watch pod recreation**

```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -n vllm -w
```

Expected: Old vllm pod terminates, new one starts (Recreate strategy).

**Step 2: Check vLLM startup logs**

```bash
KUBECONFIG=/home/al/.kube/config kubectl logs -n vllm -l app=vllm --follow --tail=100
```

Expected: Model loads successfully, served as `Qwen3.5-9B-NVFP4`, no errors.

**Step 3: Test text completion**

```bash
curl -s https://llm.almckay.io/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen3.5-9B-NVFP4","messages":[{"role":"user","content":"Hello, what model are you?"}],"max_tokens":100}' | jq '.choices[0].message.content'
```

Expected: Response mentioning Qwen3.5.

**Step 4: Test tool calling**

```bash
curl -s https://llm.almckay.io/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"Qwen3.5-9B-NVFP4",
    "messages":[{"role":"user","content":"What is the weather in London?"}],
    "tools":[{"type":"function","function":{"name":"get_weather","parameters":{"type":"object","properties":{"city":{"type":"string"}}}}}],
    "max_tokens":200
  }' | jq '.choices[0].message.tool_calls'
```

Expected: Tool call to `get_weather` with `city: "London"`.

**Step 5: Test vision (multimodal)**

```bash
# Use a small test image (1x1 red pixel base64)
curl -s https://llm.almckay.io/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"Qwen3.5-9B-NVFP4",
    "messages":[{"role":"user","content":[{"type":"text","text":"What color is this image?"},{"type":"image_url","image_url":{"url":"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="}}]}],
    "max_tokens":100
  }' | jq '.choices[0].message.content'
```

Expected: Response describing a red image.

**Step 6: Test via Kubani UI**

Navigate to `https://kubani.almckay.io` and send a message through the Nexus chat interface. Verify response comes back.

**Step 7: Check all dependent pods restarted cleanly**

```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents
KUBECONFIG=/home/al/.kube/config kubectl get pods -n nexus
KUBECONFIG=/home/al/.kube/config kubectl get pods -n kubani-ui
```

Expected: All pods running, no CrashLoopBackOff.

---

### Rollback (if needed)

If anything goes wrong:

```bash
git revert HEAD
git push origin main
# Flux will redeploy with old Qwen3-14B config
# Old model files are still on disk — loads in ~4 min
```
