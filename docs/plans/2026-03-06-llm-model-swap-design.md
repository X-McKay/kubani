# Design: Replace Qwen3-14B with Qwen3.5-9B-NVFP4

**Date:** 2026-03-06
**Status:** Approved

## Summary

Replace the primary LLM (Qwen3-14B-FP4) and consolidate the separate VLM (Qwen3-VL-8B-Instruct) into a single multimodal model: AxionML/Qwen3.5-9B-NVFP4. This is a smaller, newer-generation model with native vision support, 128K context, and NVFP4 quantization.

## Motivation

- Qwen3.5 is a newer generation with improved capabilities
- Multimodal (text + vision) eliminates the need for a separate VLM deployment
- 9B params (NVFP4) uses less VRAM than 14B (FP4), freeing GPU for future use
- 128K native context (4x current 32K)
- Apache 2.0 license

## Architecture Change

**Before:** 4 vLLM instances (Main 60% + Fast 15% + Embed 10% + VLM separate)
**After:** 3 vLLM instances (Main 50% + Fast 15% + Embed 10%) — VLM consolidated into main

Fast model (Qwen3-0.6B) and embeddings (Qwen3-Embedding-0.6B) are unchanged.

## vLLM Configuration

### Current flags
```
--served-model-name "nvidia/Qwen3-14B-FP4"
--gpu-memory-utilization 0.60
--enable-auto-tool-choice
--tool-call-parser hermes
--max-model-len 32768
--speculative-config '{"method":"ngram","prompt_lookup_max":4,"num_speculative_tokens":5}'
```

### New flags
```
--served-model-name "Qwen3.5-9B-NVFP4"
--gpu-memory-utilization 0.50
--enable-auto-tool-choice
--tool-call-parser qwen3_coder
--reasoning-parser qwen3
--max-model-len 131072
--quantization modelopt
--speculative-config '{"method":"qwen3_next_mtp","num_speculative_tokens":2}'
```

### Key flag changes
| Flag | Old | New | Reason |
|------|-----|-----|--------|
| `served-model-name` | `nvidia/Qwen3-14B-FP4` | `Qwen3.5-9B-NVFP4` | New model identity |
| `gpu-memory-utilization` | 0.60 | 0.50 | Smaller model needs less VRAM |
| `tool-call-parser` | `hermes` | `qwen3_coder` | Qwen3.5 uses different tool format |
| `reasoning-parser` | (none) | `qwen3` | Required for Qwen3.5 thinking mode |
| `max-model-len` | 32768 | 131072 | 4x context increase (128K) |
| `quantization` | (none) | `modelopt` | Required for NVFP4 checkpoint |
| `speculative-config` | ngram | `qwen3_next_mtp` | Native MTP for Qwen3.5 |

### Container image
May need bump from `nvcr.io/nvidia/vllm:25.12-py3` if qwen3_5 architecture or qwen3_coder parser isn't supported. Willing to update.

## Config & Code Updates

All references to `nvidia/Qwen3-14B-FP4` change to `Qwen3.5-9B-NVFP4`:

| File | Field |
|------|-------|
| `config/default.yaml` | `llm.model` |
| `config/production.yaml` | `llm.model` |
| `config/local.yaml` | `llm.model` |
| `infrastructure/gitops/apps/vllm/model-config.yaml` | ConfigMap value |
| `infrastructure/gitops/apps/ai-agents/k8s-monitor/model-config.yaml` | ConfigMap value (synced) |
| `infrastructure/gitops/apps/kubani-ui/deployment.yaml` | `MODEL_NAME` env var |
| `kubani/framework/config.py` | `LLMConfig.model` default |
| `platform/skill-dev-tools/src/skill_dev_tools/llm/client.py` | Default model |

### VLM consolidation
- Nexus orchestrator: Point `VLM_API_URL` to main LLM endpoint, `VLM_MODEL` to `Qwen3.5-9B-NVFP4`
- Remove separate VLM deployment manifest if present in gitops

### Thinking mode
Qwen3.5 has thinking enabled by default (no `/think` soft switch). The framework already strips `<think>` tags — no code change needed. Non-thinking mode available via `chat_template_kwargs: {"enable_thinking": false}` if needed later.

## Rollout Procedure (Blue-Green Fast Cutover)

### Phase 1: Pre-download (zero downtime)
1. SSH into `sparky`
2. Download AxionML/Qwen3.5-9B-NVFP4 to `/models/Qwen3.5-9B-NVFP4`
3. Verify files (~6GB)

### Phase 2: Update manifests & configs
1. Update vLLM deployment.yaml with new flags
2. Update all config files with new model name
3. Update framework code defaults
4. Update Nexus VLM references
5. Remove VLM deployment (if exists)
6. Commit all changes

### Phase 3: Fast cutover (brief downtime)
1. Push to git — Flux reconciles
2. vLLM pod recreates (Recreate strategy)
3. Model loads from local disk (~1-2 min)

### Phase 4: Verify
1. Pod status — no CrashLoopBackOff
2. vLLM logs — model loaded, correct served name
3. Text completion via API
4. Tool calling (qwen3_coder parser)
5. Vision input (image in message)
6. Kubani UI — send message through Nexus
7. Thinking tag stripping works

## Rollback Plan
- Keep Qwen3-14B-FP4 files on disk
- Git revert → Flux redeploys old config
- Old model loads from existing files (~4 min)

## References
- [AxionML/Qwen3.5-9B-NVFP4](https://huggingface.co/AxionML/Qwen3.5-9B-NVFP4)
- [Qwen3.5 vLLM Recipe](https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3.5.html)
- [vLLM ModelOpt Quantization](https://docs.vllm.ai/en/stable/features/quantization/modelopt/)
- [Qwen3.5-9B Base Model](https://huggingface.co/Qwen/Qwen3.5-9B)
