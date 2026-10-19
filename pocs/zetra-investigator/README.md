# Kubani Kubernetes investigator

A small reviewed Google ADK agent built from `zetra init`. It diagnoses a deliberately broken pod through Kubernetes MCP, compares a healthy pod, and writes a short report with evidence files. It cannot repair workloads. Its three remote tools have a fixed namespace (`zetra-poc-fixtures`); the pod inspection tool accepts only the POC name prefix.

## Develop and test

Use Python 3.12, uv, and just:

```sh
git init  # only for a newly generated local project
uv sync --locked
just validate
```

`factory.py` assembles a standard ADK `LlmAgent`; `toolset.py` registers three reviewed `remote_read` wrappers and one workspace report tool. `dependencies.py` uses the official MCP client. The local evaluation starts an official MCP fixture server and uses the SDK fixture model. It copies the project and selects fixture settings only in that temporary copy. This verifies tool transport and evidence behavior without an LLM, cluster, or credentials; it does not qualify isolation or recovery.

The committed manifest selects the SDK's pinned vLLM profile (`llm.almckay.io`). AgentGateway fronts both that endpoint and the authenticated Kubernetes MCP endpoint. Tool output is untrusted input.

## Deploy the POC

Deployment configuration lives in `deploy/`, outside the SDK. Every command must explicitly select Kubani's `default` kube context. Use the dedicated `zetra-poc`, `zetra-poc-sandboxes`, and `zetra-poc-fixtures` namespaces. Do not reuse a production task queue or release.

The external Temporal worker holds a stable derivation key and shared artifact backing. Each session gets a fresh OpenShell sandbox containing the complete agent and tools. Model and tool boundaries use the SDK's Temporal Activities. Remote reads retain single-attempt execution and unknown-outcome behavior; they are not silently retried. Cleanup results retain the distinction between confirmed deletion and `NOT_CONFIRMED`.

OpenShell authenticates this dedicated gateway with native mTLS users. The worker attaches the deployment-owned provider name `kubani-k8s-read`; it does not put tokens in Workflow inputs or sandbox specifications. Native provider configuration, credential lifecycle, storage and release approval remain operator responsibilities. The existing test identity is POC access, not a production authorization design.

See `deploy/README.md` for the exact deployment recipe and `docs/poc-findings.md` for qualification evidence and speed bumps. Deployment and run Jobs invoke the standard `zetra worker` and `zetra run` commands directly. Use an explicit `--session investigate-<id>` and `--input` with `zetra run`. Retry with the same release and session ID after an interruption; SDK submission deduplicates against the original Temporal execution. Observation files are content-addressed so repeated reads preserve earlier citations. The report tool appends exact evidence links and validates a narrative of at most 150 words; the model does not copy filenames. Console output is a compact result summary, while full results remain in the artifact backing. The SDK CLI handles termination signals and exports verified files under `workspace/`, with handle/result metadata alongside it. No application-specific runtime module is needed.

Never commit TLS keys, credentials, generated releases, session outputs, or local state.
