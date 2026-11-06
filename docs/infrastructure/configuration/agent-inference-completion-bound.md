# Agent inference completion bound

The two agent inference routes accept only POST to
`/models/{llm-main,llm-fast}/v1/chat/completions`, rewritten to the standard
chat endpoint. They require the configured model, omitted `n` or `n=1`, no
`best_of`, and omitted or false `use_beam_search`. The main/fast catalogue
reservations and engine context limits remain unchanged.

The policy uses `Require`: agentgateway v1.7.0 combines independent `Allow`
policies with OR, so an agent claim allow rule otherwise bypasses a model-pin
allow rule. `json(request.body)` evaluates the complete client body. Bad JSON,
missing required model, invalid completion counts and unavailable oversized
bodies fail closed; client headers do not supply the count. Broad legacy or
batch endpoints cannot reach the AI backend through these routes.

This closes the known multiple-completion amplification of a single-context
APS reservation. It does not establish Qwen token accounting correctness or
qualify T13/T13b; those tests separately exercise the enforced byte-token
backend. Human inference routes are outside the agent budget path and unchanged.

Run `just test-inference-completion-bound` (Docker required). The regression
loads the checked-in route and model policies into agentgateway v1.7.0 image
`sha256:60216aafb03d37f94e952ff3d51d2f630a65b10ecaebdc0a864882f92610c45b`,
with an independent permissive agent allow rule and a loopback model stub.
It checks permitted defaults and `n=1`, wrong models, count types/values,
malformed/duplicate JSON, a body exceeding the test buffer, spoofed headers,
beam/best-of inputs and non-chat paths, including absence of upstream calls
for denials. The test lowers only its local buffer to 8192 bytes to exercise
the same unavailable-body path. It uses no cluster credentials or real model.
Before the fix, the actual gateway forwarded `n=2` and wrong models with 200;
the expanded regression also demonstrated broad paths and candidate options.

Source references for the pinned versions:

- [Gateway authorization composition](https://github.com/agentgateway/agentgateway/blob/v1.7.0/crates/agentgateway/src/http/authorization.rs)
- [Complete request body buffering](https://github.com/agentgateway/agentgateway/blob/v1.7.0/crates/agentgateway/src/cel/types.rs)
- [OpenAI request forwarding](https://github.com/agentgateway/agentgateway/blob/v1.7.0/crates/agentgateway/src/llm/mod.rs)
- [vLLM 0.30 chat and batch request fields](https://docs.vllm.ai/en/v0.30.0/api/vllm/entrypoints/openai/chat_completion/protocol/)
