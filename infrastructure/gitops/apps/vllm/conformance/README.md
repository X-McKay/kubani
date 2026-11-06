# Model authentication qualification

The retained brokers front authenticated engines. Main requests take
`llm-api:8000 -> gpu-broker-main -> llm-engine:8001 -> capture -> 127.0.0.1:8000`.
The engine's named `http` port, startup/readiness/liveness probes, metrics,
and `llm-engine:8000` remain direct. Fast keeps its existing broker route
and level-1 auto-sleep; main sleep remains disabled.

The main capture container reads only `VLLM_API_KEY_MAIN` from `llm-api-key`.
It records `backend_key_match`, request metadata, and no credential or body.
The harness can list/get pods and read logs in `vllm`; it cannot read Secrets
or exec into pods through this Role.

For T6, project `agent-platform/conformance-model-key`, key `key`, read-only
into the trusted conformance harness and set:

```yaml
- name: T6_MODEL_URL
  value: http://llm-engine.vllm.svc.cluster.local:8000/v1/models
- name: BACKEND_KEY_FILE
  value: /var/run/secrets/model-backend/key
```

The encrypted harness Secret is a copy of the MAIN engine key. Rotate it
together with `vllm/llm-api-key` and the main gateway backend credential.
No sandbox receives this Secret, and no ServiceAccount receives Secret API
read permission. T7 reads container `capture` on pods labeled `app=vllm` in
namespace `vllm`.

`t6-netpol.yaml` is deliberately absent from the GitOps kustomization. Apply
its two policies only for the qualification run, then delete them even if
the run fails. They permit only the `agent-platform` conformance harness to
reach main engine port 8000; tenant sandbox policies remain unchanged.

Before running T6/T7, wait for both engines and brokers to be ready. Check
the existing `ai`, `llm`, `llm-fast`, and embeddings routes; the fast watchdog
must continue completing probes. Exercise a fast level-1 sleep/wake through
the broker and confirm a successful completion after wake. Do not enable
main sleep as part of this rollout.

T6 must report 401 without the backend key and 200 with it. T7 must report a
successful chat completion with nonzero usage and a matching capture record
at `/v1/chat/completions` where `backend_key_match` is true and the agent
token was not forwarded. Remove the temporary T6 policies after collecting
the report, then rerun the existing sandbox isolation check.
