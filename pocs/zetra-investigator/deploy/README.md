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

The 2Gi artifact claim uses local-path storage pinned to rig0. Worker-process/pod replacement can reuse it on that node; node-loss resilience is outside this POC. The one-shot run Job shares artifacts and release metadata, but receives neither the worker key nor the OpenShell user TLS credentials. The generated template's kind qualification workflow is omitted from this application because this POC uses Kubani and application-specific MCP credentials. Live qualification is manual until its recipe is verified; the validate workflow and wheel build remain available.

A failed Job is not proof that its Temporal workflow stopped. Retry `run` using the exact same session ID and release to inspect/wait on the original execution. A new ID intentionally starts a new investigation. Follow the SDK cleanup result; do not equate a missing client acknowledgement with confirmed deletion.
