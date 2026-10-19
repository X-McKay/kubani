# Kubani POC deployment

These are application/platform inputs, not SDK lifecycle services. Commands explicitly target context `default`. The POC uses the existing cluster Temporal service and Agent Sandbox controller. Do not upgrade shared infrastructure as part of this experiment.

## Isolated OpenShell

```sh
kubectl --context default apply -f deploy/namespaces.yaml
mkdir -p .tools/openshell
helm pull oci://ghcr.io/nvidia/openshell/helm-chart --version 0.1.4 --destination .tools/openshell
# Verify OCI digest printed by Helm:
# sha256:46c21e50abbe88c742ef46e77728e5201398706061b19871eaf3303adac274d6
tar -xzf .tools/openshell/helm-chart-0.1.4.tgz -C .tools/openshell
python deploy/patch-chart.py .tools/openshell/helm-chart
helm upgrade --install zetra-poc .tools/openshell/helm-chart --namespace zetra-poc --kube-context default -f deploy/openshell-values.yaml --wait --timeout 5m
python deploy/stage-ca.py
kubectl --context default apply -f deploy/fixtures.yaml
```

The gateway is single-node on rig0 with a 1Gi local-path volume; this POC makes no HA claim. Chart certgen hooks need the asserted non-root/seccomp patch to satisfy restricted pod admission. The pinned OpenShell driver uses capability-free, non-root workload and supervisor pods. All three namespaces enforce restricted pod admission. Gateway sandbox UID/GID is explicitly 1500 to match the SDK image and static process policy; the capability-free runtime cannot change identities. Live enforcement still requires independent testing.

Native user mTLS must be enabled in gateway configuration; merely mounting TLS certificates does not enable user authentication. There is no public gateway ingress, no anonymous access, and no gateway-wide operator identity.

## Agent image

```sh
DOCKER_CONTEXT=colima DOCKER_DEFAULT_PLATFORM=linux/amd64 uv run --locked zetra build . --tag kubani-investigator:poc
# Registry publication and immutable release creation follow after a successful build.
```

Use a registry digest, not a mutable tag, in the release. Keep generated release metadata and all private state ignored. Native provider setup and worker deployment steps will be added with their validated results. Never pass reusable OAuth credentials to a sandbox or store them in Temporal history.

With a separate sandbox namespace, the native shared-mode supervisor expects a local Secret named `openshell-client-tls` containing `ca.crt`. The staging script copies only this public CA certificate. The worker client certificate and private key stay in the gateway/worker namespace.

## Reviewed worker and one-shot run

After registry publication, bind the exact digest to the captured source:

```sh
uv run --locked zetra release . --image registry.almckay.io/zetra/kubani-investigator@sha256:<digest> --output .tools/release.json
uv run --locked python deploy/render-worker.py .tools/release.json --session investigate-first > .tools/worker.json
kubectl --context default apply --dry-run=server -f .tools/worker.json
kubectl --context default apply -f .tools/worker.json
kubectl --context default -n zetra-poc rollout status deployment/investigator-worker --timeout=120s
kubectl --context default -n zetra-poc logs -f job/run-investigate-first
```

The external worker attaches the native `kubani-k8s-read` provider, which must already exist and be operator-reviewed. Do not apply the worker before provider setup and credential approval. Create the dedicated `zetra-poc` Temporal namespace with one-day POC retention. Create `investigator-worker-key` once with 32 cryptographically random bytes; preserve it across worker replacement. It is a worker-only Secret and is never mounted into the run Job or agent sandbox.

The 2Gi artifact claim uses local-path storage pinned to rig0. Worker-process/pod replacement can reuse it on that node; node-loss resilience is outside this POC. Worker and run Jobs call `python -m zetra` directly; no application runtime
module duplicates SDK orchestration. Worker flags bind release approval and native
provider names. SIGTERM/SIGINT request Temporal drain; pod termination allows
additional shutdown time. Run output is an SDK-owned replaceable export directory
with `handle.json`, full `result.json` and verified files under `workspace/`.
Console output is compact. The one-shot run Job shares artifacts and release metadata, but receives neither the worker key nor the OpenShell user TLS credentials. The generated template's kind qualification workflow is omitted from this application because this POC uses Kubani and application-specific MCP credentials. Live qualification is manual until its recipe is verified; the validate workflow and wheel build remain available.

A failed Job is not proof that its Temporal workflow stopped. Retry `run` using the exact same session ID and release to inspect/wait on the original execution. A new ID intentionally starts a new investigation. Follow the SDK cleanup result; do not equate a missing client acknowledgement with confirmed deletion.

## Native MCP credential provider

The operator-approved test identity is configured once in OpenShell's encrypted
credential store. The agent receives only `MCP_ACCESS_TOKEN` as an opaque native
placeholder. The native gateway obtains and renews the OAuth access token; there
is no application token refresher. The public profile permits only the
Kubernetes MCP path, with the methods required by Streamable HTTP.

With loopback port forwards and the worker's private native client TLS files in
an ignored directory:

```sh
kubectl --context default -n zetra-poc port-forward service/zetra-poc-openshell 18091:8080
# Separate terminal:
uv run --locked python deploy/setup-provider.py --address 127.0.0.1:18091 --tls-dir .tools/tls
kubectl --context default apply -f deploy/temporal-access.yaml
```

`setup-provider.py` is a Kubani operator command, not normal agent startup. It
uses the explicitly approved Authentik test credential only if refresh has not
been configured. Its existing-ready branch and initial native setup were tested;
the complete fresh-bootstrap helper still needs an independent disposable-gateway
test. It refuses to silently update an existing profile or configure initial
refresh while sandboxes exist. Never reconfigure refresh to rotate a token:
Configure starts a new authorization epoch and invalidates active handles. Native
automatic refresh or Rotate preserves the opaque handle used by a warm process.
A workspace-imported profile requires `profile_workspace="default"`; provider
creation accepts no initial token when native refresh can supply it. Static
`stable_placeholder` mode is incompatible with gateway-managed refresh.

The existing test identity has broader read access than the agent's wrappers.
AgentGateway limits the backend to read tools and Kubernetes MCP uses the `view`
role; the fixed fixture namespace is enforced by reviewed application code,
not by an OpenShell JSON-RPC argument filter. Production needs its own scoped
agent identity and backend authorization, rather than this shared test identity.

The Temporal ingress rule admits only the POC worker/run/qualification pod labels from the POC
namespace to TCP7233. New pod network policy propagation briefly refused the
first client connection. The Job now uses Kubernetes `OnFailure` with two bounded
retries and the same explicit session ID. SDK submission checks the original
Temporal request on retry; model/tool Activities still have one attempt.

## Live qualification

```sh
kubectl --context default -n temporal port-forward service/temporal-frontend 17234:7233
uv run --locked python evals/qualify_kubani.py \
  --session investigate-normal-unique-id --scenario normal \
  --temporal-address 127.0.0.1:17234 --openshell-address 127.0.0.1:18091 \
  --tls-dir .tools/tls
uv run --locked python evals/probe_credentials.py \
  --address 127.0.0.1:18091 --tls-dir .tools/tls
```

Every qualification uses a fresh session ID and verifies the accepted immutable
release/run. Scenarios `worker`, `sandbox`, and `cancel` require an otherwise idle
dedicated Temporal namespace. `sandbox` parks the worker after an accepted effect,
removes that exact sandbox, and then tests native Temporal rebind. Cancellation and
unknown outcomes intentionally make the ordinary client command fail after
preserving the result; this is not a failed cleanup assertion.

For deterministic abrupt worker loss, run the dedicated test-only Job:

```sh
uv run --locked python evals/inflight_loss.py --session investigate-loss-model-unique --kind model
uv run --locked python evals/inflight_loss.py --session investigate-loss-tool-unique --kind tool
```

It uses the release in `.tools/release.json`, the deployed immutable worker image,
and a separate queue/runtime per test. The supervisor gates its child worker after
a real sandbox execution uploads a valid candidate receipt, before Temporal
accepts completion. It kills that exact process with SIGKILL before the Activity
deadline and starts an ungated replacement. The test requires a native Activity
timeout, unchanged accepted cursor, exactly one effect dispatch, OUTCOME_UNKNOWN,
confirmed deletion, Kubernetes absence and successful history replay. A candidate
artifact cannot select progress. The gate and supervisor exist only in test code;
the SDK has no fault-hook API. Worker startup has a separate 60-second
limit, submission 30 seconds, creation 120 seconds, readiness 300 seconds, and
the effect gate 90 seconds. Creation and readiness require exact native
`create_session` and `wait_session_ready` Activity completions, recorded with
history event IDs and times in the summary. Readiness starts at native creation
completion; the gate starts at native readiness completion. A closed Workflow or
failed phase stops the test immediately. This requires an SDK/worker image with
these separate Activities. The Job allows 1,800 seconds and host observation
1,860 seconds, including the preserved 660-second failure cleanup allowance.
 The old timing-based hard-loss path is removed; its failed observations remain
in the qualification report.

The controls verify exact evidence links, original receipt prefixes, single
Activity attempts, Temporal replay, native deletion and Kubernetes absence of
sandbox/pods/workspace claims. The credential control uses two temporary native
sandboxes and checks an unchanged warm process across rotation. It is a native
control, not another durable agent execution. Generated results and histories
stay under ignored `.tools/`; committed findings contain only compact evidence.
Fault injection uses native Temporal/Kubernetes/OpenShell operations; the harness
is optional test code and does not become a platform service or SDK recovery
engine.
