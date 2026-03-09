# vLLM Reasoning Parser Configuration

**Status:** TODO
**Priority:** Medium
**Effort:** Small (~30 minutes)
**Created:** 2026-01-23

## Problem

The vLLM deployments for Qwen3 models are missing the `--reasoning-parser qwen3` flag, which prevents per-request thinking mode control via the API.

### Current Behavior

- **Expected:** `extra_body: {"chat_template_kwargs": {"enable_thinking": false}}` should disable thinking mode
- **Actual:** Parameter is silently ignored, thinking mode is always enabled
- **Impact:**
  - Cannot disable thinking mode via API calls
  - Multi-config skill evaluations show identical token usage for thinking vs no-thinking configs
  - ~65% unnecessary token usage when thinking is not needed

### Root Cause

vLLM deployments are missing the `--reasoning-parser qwen3` flag in their startup arguments. This flag was introduced in vLLM 0.9.0 and is required for the `chat_template_kwargs.enable_thinking` parameter to work.

## Temporary Workaround

**Implemented in:** `platform/cli/src/kubani_dev/llm_client.py`

A `/nothink` soft switch workaround has been added to the LLM client:
- Prepends `/nothink\n\n` to user messages when `enable_thinking=False` for Qwen3 models
- Reduces token usage by ~65% (227 tokens → 79 tokens in testing)
- Generates empty `<think>\n\n</think>` tags instead of full reasoning

**Limitations:**
- Still includes empty thinking tags in response
- Not as clean as proper vLLM configuration
- Only works for Qwen3 models (model name detection)

## Permanent Solution

### Required Changes

Update both vLLM deployments to include the `--reasoning-parser qwen3` flag:

**File 1:** `infrastructure/gitops/apps/vllm/deployment.yaml` (main model)

```yaml
args:
  - |
    exec vllm serve "$LLM_MODEL_PATH" \
      --served-model-name "$LLM_MODEL_NAME" \
      --host 0.0.0.0 \
      --port 8000 \
      --gpu-memory-utilization "$LLM_GPU_MEMORY_UTILIZATION" \
      --enable-auto-tool-choice \
      --tool-call-parser hermes \
      --max-model-len "$LLM_MAX_MODEL_LEN" \
      --speculative-config "$LLM_SPECULATIVE_CONFIG" \
      --reasoning-parser qwen3  # ADD THIS LINE
```

**File 2:** `infrastructure/gitops/apps/vllm/fast-model-deployment.yaml` (fast model)

```yaml
args:
  - |
    exec vllm serve "$FAST_MODEL_NAME" \
      --served-model-name "$FAST_MODEL_NAME" \
      --host 0.0.0.0 \
      --port 8000 \
      --gpu-memory-utilization "$FAST_GPU_MEMORY_UTILIZATION" \
      --max-model-len "$FAST_MAX_MODEL_LEN" \
      --enable-auto-tool-choice \
      --tool-call-parser hermes \
      --enforce-eager \
      --reasoning-parser qwen3  # ADD THIS LINE
```

### Verification Steps

After deployment:

1. **Test thinking enabled (default):**
   ```bash
   curl -X POST https://llm.almckay.io/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "Qwen3.5-9B-NVFP4",
       "messages": [{"role": "user", "content": "Explain photosynthesis in 2 sentences"}],
       "max_tokens": 500
     }'
   ```
   **Expected:** Response contains `<think>...full reasoning...</think>`

2. **Test thinking disabled:**
   ```bash
   curl -X POST https://llm.almckay.io/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "Qwen3.5-9B-NVFP4",
       "messages": [{"role": "user", "content": "Explain photosynthesis in 2 sentences"}],
       "max_tokens": 500,
       "extra_body": {"chat_template_kwargs": {"enable_thinking": false}}
     }'
   ```
   **Expected:** Response does NOT contain `<think>` tags at all

3. **Re-run skill evaluations:**
   ```bash
   kubani skill eval skills/development/temporal-troubleshooting --mode full --parallel
   ```
   **Expected:**
   - Large model configs should show significant token difference (thinking vs no-thinking)
   - Small model configs should show different latencies (thinking should be slower)

### Cleanup After Fix

Once vLLM deployments are updated and verified:

1. Remove `/nothink` workaround from `llm_client.py`:
   - Remove `_apply_nothink_workaround()` method
   - Remove call to workaround in `chat()` method
   - Keep the `extra_body` parameter (will now work properly)

2. Update comment in `_chat_openai()` method

3. Re-run skill evaluations to baseline the new behavior

## References

- **vLLM Reasoning Outputs:** https://docs.vllm.ai/en/latest/features/reasoning_outputs/
- **vLLM Qwen3 Reasoning Parser:** https://docs.vllm.ai/en/v0.9.0/api/vllm/reasoning/qwen3_reasoning_parser.html
- **Qwen3 Thinking Budget:** https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html#thinking-budget
- **Qwen3 vLLM Deployment Guide:** https://qwen.readthedocs.io/en/latest/deployment/vllm.html
- **GitHub Issue - enable_thinking parameter:** https://github.com/QwenLM/Qwen3/issues/1286

## Testing Notes

**From investigation on 2026-01-23:**

- Container version: `nvcr.io/nvidia/vllm:25.12-py3` (should support vLLM 0.9.0+)
- Current behavior: `extra_body` parameter silently ignored
- `/nothink` soft switch works but only reduces tokens, doesn't remove tags
- Multi-config evaluation showed no token difference between thinking configs (confirms parameter is ignored)

## Related Work

- **Skill evaluation framework:** Depends on this fix to properly test thinking vs no-thinking modes
- **Token usage optimization:** ~65% reduction when thinking is disabled
- **Temporal-troubleshooting skill:** Created during investigation, awaiting promotion to production
