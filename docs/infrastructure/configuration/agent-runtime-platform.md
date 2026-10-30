# Agent Runtime Platform: cluster stages

This is the Kubani side of the Agent Runtime Platform specification
(revision 3): Kata sandboxes, the tenant and platform NetworkPolicies, the
`Agent`/`AgentRelease` CRDs, Kyverno admission, and the host settings that
sandbox nodes need. The platform's own workloads (Registry Controller, Agent
Policy Service, Session Runner, netpol-attestor, egress guard) are built and
released from the platform repository (X-McKay/zetra) and are not here; see
[repository scope](../repository-scope.md).

Every manifest is **staged and not wired**: merging the change applies
nothing. `kustomize build infrastructure/gitops/infrastructure` is byte-identical
to the build before the change. A stage is enabled by uncommenting its lines,
running `just validate-local`, committing with the stage ID in the message,
pushing, and checking the stage's verification before moving on.

## Where things live

| Path | Contents |
|---|---|
| `infrastructure/gitops/infrastructure/namespace-policy/agent-platform-namespaces.yaml` | Namespaces `agent-platform` (PSA enforce `privileged` for the hostNetwork attestor, audit/warn `restricted`) and `tenant-test` (label `agentplatform.io/tenant: tenant-test`, PSA enforce `restricted`) |
| `infrastructure/gitops/infrastructure/agent-platform-crds/` | `agents.agentplatform.io` and `agentreleases.agentplatform.io`, byte-identical to zetra `deploy/platform/crds/`; the `service-account-issuer-discovery-unauthenticated` ClusterRoleBinding (spec 7.2) |
| `infrastructure/gitops/infrastructure/sources/{kata-deploy,kyverno}.yaml` | OCIRepositories pinned by tag and digest: kata-deploy 4.3.1, Kyverno chart 3.9.2 (v1.19.2) |
| `infrastructure/gitops/infrastructure/kata/` | kata-deploy HelmRelease in `kube-system`; it creates RuntimeClass `kata-qemu-runtime-rs` |
| `infrastructure/gitops/infrastructure/agent-platform-netpol/` | The four tenant policies for `tenant-test` (spec 5.3), plus the upstream halves of the agent paths that no workload directory owns: `vllm`, `mcp`, `temporal` and `monitoring` (Alloy to/from the gateway and the APS) |
| `apps/agent-platform/netpol.yaml`, `apps/ai-gateway/agents/netpol.yaml`, `apps/keycloak/netpol.yaml` | Written with the workloads: the `agent-platform` namespace set (spec 5.3 `aps-ingress`), `agents-ingress-from-sandboxes` and the data-plane egress, and the IdP ingress. Staged in those directories |
| `infrastructure/gitops/infrastructure/kyverno/` | Namespace, NetworkPolicies and HelmRelease; `policies/` (applied by its own Flux Kustomization); `tests/` (`kyverno test` fixtures, never applied) |
| `infrastructure/ansible/roles/k3s_worker/` | `agent_sandbox_node` inventory flag: `/dev/kvm` assertion, kubelet `sync-frequency=5s`, `topology.kubani.io/agent-sandbox=true` label |
| `infrastructure/ansible/playbooks/preflight_checks.yml` | The same `/dev/kvm` assertion in `just preflight` |

## Stages, in enable order

| Stage | What it does | What to uncomment | Verify |
|---|---|---|---|
| P0 | CRDs only. Inert: nothing reconciles them yet | `- agent-platform-crds/` in `infrastructure/kustomization.yaml` (the CRB line inside stays commented) | `kubectl get crd agents.agentplatform.io agentreleases.agentplatform.io`; T20's `AgentRelease.spec.image` edit is rejected |
| P1 | Namespaces `agent-platform` and `tenant-test` | `- agent-platform-namespaces.yaml` in `namespace-policy/kustomization.yaml` | `kubectl get ns tenant-test --show-labels` shows the tenant label and PSA `enforce=restricted` |
| A0 | Sandbox node host settings | Inventory: `agent_sandbox_node: true` on the chosen worker(s); then `just preflight` and `just provision-host <host>` | Preflight passes the `/dev/kvm` assertion; `/etc/rancher/k3s/config.yaml` has `sync-frequency=5s`; node has `topology.kubani.io/agent-sandbox=true`. **This restarts k3s-agent on that host** (normal configure path; `just firewall-apply` never touches it) |
| A1 | Kata | `- kata-deploy.yaml` in `sources/kustomization.yaml`, `- kata/` in `infrastructure/kustomization.yaml` | `kubectl get runtimeclass kata-qemu-runtime-rs -o yaml` shows overhead 160Mi/600m and both node selectors; node labelled `katacontainers.io/kata-runtime=true`; a throwaway restricted pod with `runtimeClassName: kata-qemu-runtime-rs` in a non-tenant namespace reaches Running and `uname -r` differs from the host |
| A2 | Close `tenant-test` | `- agent-platform-netpol/` in `infrastructure/kustomization.yaml` (only `tenant-test.yaml` is active inside) | `kubectl get netpol -n tenant-test` lists exactly the four policies; then Phase A tests T1, T2, T3, T27, T28, T29 with the zetra egress guard and attestor |
| P2 | Cluster OIDC discovery readable by the IdP | `- issuer-discovery-rbac.yaml` in `agent-platform-crds/kustomization.yaml`, together with the IdP's `kubernetes-<cluster>` provider entry | `curl -k https://<apiserver>/openid/v1/jwks` without credentials returns the JWKS; spec 7.8 checks |
| B1 | Kyverno install | `- kyverno.yaml` in `sources/kustomization.yaml`, `- kyverno/` in `infrastructure/kustomization.yaml` | `flux get hr -n kyverno`; the resource webhook's `namespaceSelector` is `agentplatform.io/tenant Exists` (`kubectl get validatingwebhookconfigurations -o yaml`) |
| B2 | Sandbox admission policies | First replace the placeholders and decide the Rule 1 transparency-log question (below); then add `flux-system/agent-platform-policies-kustomization.yaml` (below) to `flux-system/kustomization.yaml` | `kubectl get clusterpolicy` Ready; T9b and T22 on the cluster |
| B3 | Upstream halves of the gateway and runner paths | `upstreams.yaml` in `agent-platform-netpol/kustomization.yaml`, together with the `agents` Gateway (`apps/ai-gateway/agents/`) and the platform workloads (`apps/agent-platform/`, `apps/keycloak/`), whose own NetworkPolicies carry the other halves | T1 again (nothing new reachable from a sandbox), T4, T6, T7, T8, T13 (settlement reaches the APS); the `ai` gateway's existing checks still pass |

Why this order: the tenant namespace is closed (A2) before anything could
schedule a sandbox in it; Kata exists (A1) before the Phase A tests need it;
Kyverno is installed (B1) before its policies (B2) because the policies'
CRDs come from the chart; and the cross-namespace paths (B3) open only when
the pods they name exist. Every B3 policy names pods that do not exist yet
(`app.kubernetes.io/name: agents`, `agent-policy-service`, `session-runner`, ...),
so enabling it early changes no live traffic, but there is no reason to.

### B2: the policies Kustomization

The ClusterPolicies cannot be in the infrastructure Kustomization: their CRDs
come from the Kyverno HelmRelease, so a server-side dry run on a fresh cluster
would fail and block every infrastructure change. Same pattern as
`flux-system/tetragon-policies-kustomization.yaml`:

```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: agent-platform-policies
  namespace: flux-system
spec:
  interval: 10m0s
  retryInterval: 2m0s
  timeout: 5m0s
  path: ./infrastructure/gitops/infrastructure/kyverno/policies
  prune: true
  sourceRef:
    kind: GitRepository
    name: flux-system
  dependsOn:
    - name: infrastructure
```

Before B2, in `kyverno/policies/agent-sandbox-admission.yaml`:

- Replace the egress-guard digest placeholder (all zeros) with the released
  digest, and the throwaway cosign key with the organisation's public key.
  Both placeholders fail closed: with them in place no tenant pod is admitted.
- Confirm the projected-token audience equals the IdP's real `ISSUER_URL`
  (written as `https://idp.almckay.io/realms/agents`).
- Decide how Rule 1 verifies signatures. As written in the spec (a public key
  and no `rekor`/`ctlog` settings), Kyverno also checks the transparency log
  and fetches sigstore's TUF root; the CLI run here failed on exactly that.
  Either the signing pipeline uploads to public Rekor and
  `kyverno/netpol.yaml` gains egress to sigstore, or the rule gets
  `rekor: {ignoreTlog: true}` and `ctlog: {ignoreSCT: true}` (key-only).
- Give the admission controller pull credentials for `registry.almckay.io`
  (basic auth) through `verifyImages[].imagePullSecrets`, as a SOPS Secret.

## Deviations from the specification text

| Spec | Here | Why |
|---|---|---|
| 5.1 values `runtimeClass.nodeSelector`, separate RuntimeClass patch | `shims.qemu-runtime-rs.runtimeClass.{overhead,nodeSelector}` in chart values; the chart owns the RuntimeClass | kata-deploy 4.x moved these keys; one owner avoids Flux and Helm fighting over the object. The rendered RuntimeClass matches spec 5.1 plus `topology.kubani.io/agent-sandbox` |
| 5.1 "keep every other default" | `shims.disableAll: true`, only `qemu-runtime-rs` | The 4.x default creates seven more RuntimeClasses nothing uses |
| 5.1 DaemonSet | kata-deploy 4.x default `deploymentMode: job` | No always-on privileged pod. A newly labelled node needs `flux reconcile hr kata-deploy -n kube-system --force` |
| 3.7 Kata overhead 160Mi | kept at 160Mi | Upstream 4.3.1 defaults this shim to 320Mi because QEMU's host RSS alone is about 160Mi on aarch64. Measure with T29 and raise it if needed |
| 5.3 `llm-` / `mcp-ingress-from-gateway-only` (`podSelector: {}`) | `allow-agents-gateway-ingress` rules in `vllm` and `mcp` | Kubani's model namespace is `vllm`. NetworkPolicies are additive, and these namespaces already admit Traefik, the `ai` gateway and same-namespace traffic, so a policy can only add the `agents` data plane. Sandboxes still reach neither (T1) |
| 8.9 settlement path | `allow-alloy-to-aps-settlement` egress in `monitoring` | `monitoring` is DNS-only egress for every pod, so the Alloy-to-APS copy of the access log (and with it budget settlement) needs an explicit rule; the APS ingress side is in `apps/agent-platform/netpol.yaml` |
| 6.5 Rule 2 `command` list | Exact JSON-array comparison in Rule 3 | Measured with the v1.19.2 CLI: a multi-element scalar list pattern never matches |
| 6.5 Rule 2 `volumes` list | `(name)` conditional anchors; Rule 3 pins the sorted name set | Same array semantics: the plain five-element list rejected the valid template |
| 6.5 Rule 2 `privileged: "!true"` | `=(privileged): "!true"` | The plain form fails when the field is absent. The 5.2 template omits it and the zetra renderer sets `false`; the fixtures cover both |
| 6.5 (RBAC only) | Extra ClusterPolicy `agent-sandbox-deny-ephemeral-containers` | Also stops cluster-admin `kubectl debug` (T22, last case) |

`kyverno/policies/agent-sandbox-admission.yaml` matches every Pod
operation, not only CREATE, which is spec 6.5 as written. The attestor's
annotation PATCH (spec 5.5) is therefore an UPDATE that the same rules check,
including Rule 1 (signature re-check) and Rule 4. A pod whose release stops
being ready can no longer be re-attested. That fails safe, because the APS
also denies it, but watch for it in T2a.

## Tests run for this change

- `kyverno test infrastructure/gitops/infrastructure/kyverno/tests` with the
  CLI built from Kyverno v1.19.2: 47 tests pass. Covered: the valid pod
  (`privileged` omitted and `false`), extra container, changed init image,
  added `hostPath` volume, wrong `serviceAccountName`, missing sandbox label,
  `automountServiceAccountToken` true and omitted, `runtimeClassName` omitted,
  `hostNetwork: true`, `privileged: true`, changed agent command, release
  unapproved or drifted, policy-digest mismatch, agent-label mismatch, and
  the ephemeral-container attach. Rule 1 (signatures) needs a registry and is
  covered only on the cluster (T9b). Inverting the expectations makes the
  suite fail, so the cases do discriminate.
- `kustomize build` of every touched root as committed, and of the whole
  infrastructure tree with every stage uncommented; `kubeconform -strict`
  (Kubernetes 1.34 schemas plus the Flux and Kyverno CRD schemas) on the
  result.
- `helm template` of the kata-deploy values has **not** been run: the chart
  tarball could not be downloaded in the authoring environment. Run it
  before A1:
  `helm template kata-deploy oci://ghcr.io/kata-containers/kata-deploy-charts/kata-deploy --version 4.3.1 -n kube-system -f <values from helmrelease.yaml> | yq 'select(.kind == "RuntimeClass")'`.

## Spec 17.3: confirm on the cluster before Phase A

Each item is closed with the test ID and date in the auth inventory
(`authentik-app-access.md`).

| Item | How to check | Closed by |
|---|---|---|
| `/dev/kvm` on every sandbox node, including the DGX Spark under DGX OS | `just preflight` with `agent_sandbox_node: true` on the host (asserts a character device) | A0 preflight, then T1 on that node |
| Rotated projected token visible in the Kata guest via virtio-fs within 60 s | Read the token in the guest, wait 8 minutes, read it again | T3 (repeated after 8 min) |
| kube-router per-pod chain naming, comment format, reject rule and ipset reference on the pinned K3s; `--sync-frequency=5s` refreshes the Downward API file within 5 s | `iptables-save -t filter` on the sandbox node after a sandbox starts; time from annotation patch to file change | T2a |
| TokenReview returns pod name and UID in `user.extra` for projected tokens | TokenReview of a sandbox's projected token | T4 |
| IdP accepts the projected token as a client assertion with the exact client settings | Spec 7.8; export the client JSON | T4, T5 |
| Keycloak delegation flow (federated JWT on token exchange, pod-bound TokenRequest token, `mcp:<backend>` narrows `aud`) | Spec 9.5 exchange against the pinned Keycloak | T10a |
| `preserveToken: true` forwards `Authorization` to ext_authz; APS headers apply last | Capture at the MCP server | T7, T8, T12 |
| Access log carries `agent.decision_id` and `llm.tokens_*`, including on errors | Inspect the OTLP stream at the APS settlement receiver | T13, T13b |
| `llm.requestModel` after `URLRewrite`; `openai.model` override; per-route `max_tokens` pin | Gateway policy evaluation with a mismatched model | T7 |
| `jwt.realm_access.roles` nested-claim syntax | Allowed and forbidden tool by role | T19 |
| `AgentgatewayParameters.spec.service` accepts a fixed `clusterIP` | Create the `agents` Gateway; `kubectl get svc agents -n ai-gateway` | T27 (address reachable), T1 |
| Boot latency, memory per sandbox, per-boundary overhead per node type; whether 160Mi overhead holds | Measurements | T29 |
| Kyverno `pattern` with a label-derived `serviceAccountName` | **Confirmed with the v1.19.2 CLI** (wrong SA fails at `/spec/serviceAccountName`, valid passes); repeat on the cluster | T22 |

## Upgrades (spec 14.4)

**Kata:** bump `sources/kata-deploy.yaml` (tag and digest) in its own PR.
Before it merges, cordon and drain the sandbox nodes. The Runner replaces
sessions on other nodes. Merge; Flux runs the install Jobs one node at a time
(`job.parallelism: 1`); then uncordon. Run T1 and T2 on each upgraded node.
The HelmRelease has `upgrade.remediation.retries: 0`, so a failed upgrade
stops instead of rolling back on its own.

**Kyverno:** bump `sources/kyverno.yaml`, rebuild the CLI at the same
version, and rerun `kyverno test` before merging.

## Rollback

- B2: remove the Flux Kustomization. Its `prune: true` deletes the policies,
  and tenant pod admission falls back to RBAC and PSA only.
- B1: comment out `- kyverno/`. Do B2 first, or the policies are orphaned
  with no webhook to serve them.
- A1: comment out `- kata/` after deleting every sandbox pod. Uninstall runs
  the chart's cleanup on every node labelled `katacontainers.io/kata-runtime`.
- P0: confirm `kubectl get agents,agentreleases -A` is empty first. Deleting
  a CRD deletes its objects.
