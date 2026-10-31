# Agent Runtime Platform: Phase A qualification, 2026-10-30/31

Record of the first Phase A run on the cluster: stages P0, P1, P2, A0, A1,
A2, AP1 (without the CA bundle and ReferenceGrant) and AP6 from
[agent-runtime-platform.md](agent-runtime-platform.md), then T1, T2a, T3
and T28. Every timestamp is UTC. Nothing from Phase B was enabled
(no Kyverno, Keycloak, agents Gateway, agentgateway upgrade, or vLLM
`--api-key`).

## What ran

| Item | Value |
|---|---|
| Kubani | `main` at `ce6276c` (PR #235 A0 inventory, PR #236 Phase A GitOps) |
| Platform | X-McKay/zetra `158a170`, images built on rig0 (linux/amd64) |
| K3s | v1.34.7+k3s1 on all four nodes; asio is the only server |
| Gateway API CRDs | v1.4.0, standard channel |
| NetworkPolicy engine | K3s embedded kube-router; iptables 1.8.10 (nf_tables), legacy tables empty |
| Service / cluster CIDR | 10.43.0.0/16 / 10.42.0.0/16; 10.43.250.10 was free |
| Sandbox node | rig0 (`/dev/kvm` character device; sparky also has one, not enabled) |
| Kata | kata-deploy chart 4.3.1 (`sha256:8eab352a…61d2e`), RuntimeClass `kata-qemu-runtime-rs`, guest kernel 6.18.56 (host 6.14.0-37-generic) |

Images (`registry.almckay.io/platform/`, none signed yet: no organisation
cosign key exists):

| Image | Digest |
|---|---|
| egress-guard | `sha256:7f4abefb518b75401bf2cd78f1ae9d00b20881e1a181fbd367d2c1384cfff8ca` |
| netpol-attestor | `sha256:b6f9b17a672dcab0bcd206d9c42c8bb72663594f94775871b0add20e905ee7e5` |
| registry-controller | `sha256:2cf48cdadda90439a9eb9f12d9c7f84dc1e89d94284ae5420220a813cbe347a7` |
| agent-policy-service | `sha256:afb62b1b36430d43a27b9354fe521f9f7254cee899dfcb8456d1376a55772640` |
| session-runner | `sha256:525258de160248974b2d487542459e429926512ef4efbd11070213d93cef570c` |
| test-agent (qualification only) | `sha256:6c4469544e06c1412911597ef75b36108d135820abad2be705cada1c98a07584` |

The test agent is `python:3.12.14-slim` with zetra `platform/agent-runtime`
installed at `/app/.venv` (so the 5.2 command `agent_runtime.wait` runs) and a
TCP probe script at `/app/probe.py`. It runs as uid 1500.

## Method

Each sandbox pod was rendered with the zetra contracts package
(`render_pod_template` + `instantiate`, a fresh UUIDv4 session ID per pod)
for a test Agent `phase-a-probe` (identity mode `agent`, no models or MCP
backends) and AgentRelease `phase-a-probe-r1` with the test-agent digest.
Platform config: issuer `https://idp.almckay.io/realms/agents`, gateway
`10.43.250.10`, the egress-guard digest above, default forbidden list
`10.43.0.1:443,10.43.0.10:53`. Pods were created directly with the
kubernetes client (no Kyverno, no Session Runner in Phase A).

Phase A has no Registry Controller and no agents Gateway, so these
stand-ins were created by hand for the run, labelled `phase-a-test=true`,
and deleted afterwards:

- `tenant-test`: ServiceAccount `agent-phase-a-probe`, ConfigMap
  `agent-gateway-ca` (a throwaway self-signed CA), and Role/RoleBinding
  `netpol-attestor` (`pods patch`, what the controller writes per tenant).
- The namespace annotation `agentplatform.io/netpol-digest` set to the
  `agentctl render-netpol --namespace tenant-test` digest
  `sha256:f82b7072b315158970f47acae42bc9c9f1e392955313c3502695fae93440f61b`.
- `ai-gateway`: Pod `phase-a-gateway-standin` (label
  `app.kubernetes.io/name: agents`, a TCP listener on 443), Service `agents`
  with `clusterIP: 10.43.250.10`, and NetworkPolicy
  `phase-a-standin-ingress-from-sandboxes` (ingress from tenant-test
  sandboxes on 443).
- Namespace `phase-a-unpoliced` (no NetworkPolicies) for the T2a control.

## Stage checks

| Stage | Result |
|---|---|
| P0 | Both CRDs present |
| P1 | `tenant-test` has `agentplatform.io/tenant=tenant-test` and PSA `enforce=restricted` |
| A0 | rig0: `sync-frequency=5s` in `/etc/rancher/k3s/config.yaml`, label `topology.kubani.io/agent-sandbox=true`, Ready (see Findings 1) |
| A1 | HelmRelease `kata-deploy` Ready (`Helm upgrade succeeded … v2`); rig0 labelled `katacontainers.io/kata-runtime=true`; RuntimeClass overhead `600m`/`160Mi`, node selectors `katacontainers.io/kata-runtime`, `topology.kubani.io/agent-sandbox`, `kata-deploy.katacontainers.io/default`. Smoke pod (restricted, `agent-platform`) Ready in 2 s, guest `uname -r` 6.18.56 vs host 6.14.0-37-generic |
| A2 | `kubectl get netpol -n tenant-test`: exactly the four policies |
| AP6 | `netpol-attestor` Running on rig0, `MatchConfig(pod_chain_prefix='KUBE-POD-FW-', policy_chain_prefix='KUBE-NWPLCY-', reject_targets=('REJECT',), egress_policy_name='sandbox-egress-gateway-only', require_policy_comment=True)` |

## T1: nothing but the gateway is reachable from a sandbox

Sandbox `tenant-test/s-e10a56f336778b71-g1`, created 02:49:33, attested
3.86 s, egress guard exit 0 at 4.89 s (`egress-guard ok: attested, gateway
reachable`), Ready 5.91 s, on rig0. Probe run 02:59:56 from the agent
container, 2 s connect timeout per target:

| Target | What it is | Result | Seconds |
|---|---|---|---|
| `10.43.250.10:443` | agents gateway (stand-in) | **connected** | 0.006 |
| `10.43.0.1:443` | API server | refused | 0.0 |
| `10.43.0.10:53` | kube-dns Service (TCP) | refused | 0.0 |
| `10.42.2.10:53` | CoreDNS pod | refused | 0.0 |
| `100.92.107.71:6443` | asio API server, node IP | refused | 0.0 |
| `100.77.107.81:10250` | rig0 kubelet | refused | 0.0 |
| `100.77.107.81:22` | rig0 SSH, Tailscale IP | refused | 0.0 |
| `192.168.86.25:22` | rig0 SSH, LAN IP | refused | 1.001 |
| `192.168.86.1:80` | LAN router | refused | 1.024 |
| `1.1.1.1:443` | internet | refused | 1.024 |
| `8.8.8.8:53` | internet DNS (TCP) | refused | 1.024 |
| `169.254.169.254:80` | link-local metadata | refused | 1.024 |
| `10.43.226.153:80` | `ai` gateway Service | refused | 1.024 |
| `10.42.1.20:80` | `ai` gateway pod | refused | 1.024 |
| `10.43.171.120:9978` | agentgateway control plane | refused | 1.024 |
| `10.43.127.251:8000` | vLLM fast-model-api | refused | 1.024 |
| `10.43.195.127:8000` | vLLM embeddings-api | refused | 1.024 |
| `10.43.60.128:8080` | kubernetes-mcp | refused | 1.024 |
| `10.43.9.142:6333` | Qdrant | refused | 1.024 |
| `10.43.236.122:5432` | PostgreSQL | refused | 1.024 |
| `10.43.45.194:6379` | Redis | refused | 1.024 |
| `10.43.86.252:6379` | FalkorDB | refused | 1.024 |
| `10.43.26.158:7233` | Temporal frontend | refused | 1.024 |
| `10.43.150.95:5000` | registry | refused | 1.024 |
| `10.43.35.171:80` | Authentik | refused | 1.024 |
| `10.42.1.167:80` | stand-in gateway pod, non-allowed port | refused | 1.024 |

UDP DNS (03:01:19), one `example.com A` query each with a 2 s timeout: no
answer from `10.43.0.10`, `10.42.2.10`, `8.8.8.8`, `192.168.86.1` or
`127.0.0.1` (the pod's `dnsConfig` nameserver).

**Pass.** Every forbidden TCP connect failed within 2 s (max 1.024 s). The
~1 s values after the first seven are consistent with the kernel's ICMP
rate limit on the REJECT replies (one burst, then one per second); they are
still well inside the bound. UDP can only time out, which it did at 2 s.

kube-router chain for that pod on rig0 (comments and order as kube-router
writes them on this K3s):

```
-A KUBE-POD-FW-M6RSOM3JQ6VG6MRG -m comment --comment "common bi-directional traffic policy rules" -j KUBE-NWPLCY-COMMON
-A KUBE-POD-FW-M6RSOM3JQ6VG6MRG -d 10.42.1.168/32 -m comment --comment "rule to permit the traffic traffic to pods when source is the pod\'s local node" -m addrtype --src-type LOCAL -j ACCEPT
-A KUBE-POD-FW-M6RSOM3JQ6VG6MRG -d 10.42.1.168/32 -m comment --comment "run through nw policy sandbox-ingress-none" -j KUBE-NWPLCY-TZJO3BBFIVHC3XKI
-A KUBE-POD-FW-M6RSOM3JQ6VG6MRG -m comment --comment "run through nw policy default-deny-all" -j KUBE-NWPLCY-624QSUCKWLUQ5VXH
-A KUBE-POD-FW-M6RSOM3JQ6VG6MRG -s 10.42.1.168/32 -m comment --comment "run through nw policy sandbox-egress-gateway-only" -j KUBE-NWPLCY-OZGEODSEW5NTPJ26
-A KUBE-POD-FW-M6RSOM3JQ6VG6MRG -m comment --comment "rule to log dropped traffic POD name:s-e10a56f336778b71-g1 namespace: tenant-test" -m mark ! --mark 0x10000/0x10000 -m limit --limit 10/min --limit-burst 10 -j NFLOG --nflog-group 100
-A KUBE-POD-FW-M6RSOM3JQ6VG6MRG -m comment --comment "rule to REJECT traffic destined for POD name:s-e10a56f336778b71-g1 namespace: tenant-test" -m mark ! --mark 0x10000/0x10000 -j REJECT --reject-with icmp-port-unreachable
-A KUBE-POD-FW-M6RSOM3JQ6VG6MRG -j MARK --set-xmark 0x0/0x10000
-A KUBE-POD-FW-M6RSOM3JQ6VG6MRG -m comment --comment "set mark to ACCEPT traffic that comply to network policies" -j MARK --set-xmark 0x20000/0x20000
```

The egress policy chain matches by ipset (`-m set --match-set KUBE-SRC-… src
-m set --match-set KUBE-DST-… dst -m tcp --dport 80|443`). This closes the
spec 17.3 item on chain naming, comment format, reject rule and ipset
reference for this K3s version.

## T2a: egress guard and attestation over 10 starts

Ten fresh template sandboxes in `tenant-test`, one after another, each deleted
after it became Ready. Times are seconds from create.

| Created | Pod | Attested | Guard exit | Guard done | Ready |
|---|---|---|---|---|---|
| 03:06:28 | s-b266a5474e13a11f-g1 | 4.64 | 0 | 5.92 | 6.69 |
| 03:06:36 | s-956217739ce18f86-g1 | 4.11 | 0 | 5.39 | 6.41 |
| 03:06:43 | s-a305f9a95dad2baf-g1 | 4.37 | 0 | 5.13 | 6.16 |
| 03:06:50 | s-083da6dad900753e-g1 | 4.37 | 0 | 5.14 | 6.16 |
| 03:06:57 | s-50f1f0ddec268495-g1 | 4.63 | 0 | 6.16 | 7.19 |
| 03:07:05 | s-255900cb300ce96c-g1 | 3.85 | 0 | 5.39 | 6.41 |
| 03:07:12 | s-1b1338de4619c6da-g1 | 3.86 | 0 | 5.14 | 6.16 |
| 03:07:19 | s-0463a90f5db2ed33-g1 | 4.37 | 0 | 5.14 | 6.16 |
| 03:07:26 | s-f441eaaaa4f9e5f3-g1 | 4.63 | 0 | 6.16 | 7.19 |
| 03:07:34 | s-8a34b5acef7077cc-g1 | 3.60 | 0 | 5.13 | 6.15 |

Attested 10/10 (min 3.60, median 4.37, max 4.64 s); guard exit 0 10/10;
Ready 10/10 (6.15–7.19 s). The guard finished 0.8–1.5 s after the attestor's
PATCH, which bounds annotation-to-Downward-API-file propagation under the
`sync-frequency=5s` setting (spec 17.3).

Control (02:27:53): the same template in `phase-a-unpoliced`, which has no
NetworkPolicies. Guard exit **3** at 3.86 s with `LEAK 10.43.0.1:443`; no
`netpol-attested` annotation was written. **Pass.**

## T3: the only identity material is the projected token, and it rotates

Read from the agent container of the T1 sandbox:

| | 03:05:59 | 03:14:05 |
|---|---|---|
| uid | 1500 | 1500 |
| `/var/run/secrets/kubernetes.io` present | no | no |
| Files under `/var/run/secrets` | `agent-identity/token` (+ its `..<ts>` data dir) | same |
| Token SHA-256 (first 16 hex) | `72bc06cd4bb2b18f` | `e7cf4305403586fc` |
| Token file mtime | 03:05:25 | 03:13:23 |
| `aud` | `https://idp.almckay.io/realms/agents` | same |
| `iss` / `sub` | `https://kubernetes.default.svc.cluster.local` / `system:serviceaccount:tenant-test:agent-phase-a-probe` | same |
| `exp - iat` | 600 s | 600 s |
| Bound objects (`kubernetes.io` claim) | namespace, node, pod, serviceaccount | same |

Token values were never printed; only hashes and claims. The kubelet
reissued the token 478 s after the previous one (80% of 600 s) and the new
file was visible in the Kata guest through virtio-fs on the next read.
Environment variables whose names contain TOKEN/SECRET/KEY are the 5.2
`AGENT_TOKEN_*` settings, `GPG_KEY` (the Python base image's release-signing
key ID, public) and the `KUBERNETES_SERVICE_*` variables the kubelet always
injects (an address the sandbox cannot reach, T1). **Pass**, and it closes
the spec 17.3 rotated-token item.

## T28: the runner's preflight sees policy drift

The runner's 10.5 preflight algorithm (`runner.activities.netpol_digest`
and `EXPECTED_POLICIES` from zetra `platform/runner`) over the live
tenant-test policies, against the namespace annotation:

| Time | Case | Live digest | Preflight |
|---|---|---|---|
| 02:26:00 | baseline, after `flux reconcile` | `f82b7072…0f61b` (equals annotation) | passes |
| 02:26:10 | extra allow-all egress policy added | `eb7c11dc…abd7c`, five names | refuses |
| 02:26:11 | extra policy removed | `f82b7072…` | passes |
| 02:26:12 | `sandbox-egress-gateway-only` gains TCP 8080 | `a351c375…81a57` | refuses |
| 02:26:13 | `sandbox-ingress-none` deleted | `e8cbdf30…706cd`, three names | refuses |
| 02:26:16 | after `flux reconcile kustomization infrastructure` (2 s) | `f82b7072…` | passes |

**Pass for Phase A.** The live digest equals `agentctl render-netpol`, and
any extra, edited or missing policy fails preflight. Reverting drift within
60 s is the Registry Controller's job (Phase B). Until then Flux reverts it
on its 10-minute interval, or immediately on a manual reconcile.

## Findings

1. **`just provision-host <worker>` does not work, and the worker roles use the
   wrong node name on rig0.** With `--limit rig0`, the control-plane play does
   not run, so `k3s_join_token` is undefined ("Control plane variables not
   available"). A0 was applied with
   `-e k3s_join_token=…` read from rig0's existing config. The play then
   failed at `k3s_worker : Wait for node to be registered in cluster` with
   `nodes "RIG0" not found`, because `ansible_hostname` is `RIG0` on rig0 and
   the node is `rig0`. `node_config` uses `ansible_hostname` too, including
   `kubernetes.io/hostname`, so the play was not re-run. The sandbox label was
   applied by hand with the command the role would have run. Fix: use
   `inventory_hostname` in `k3s_worker` and `node_config`, and give
   `provision-host` the token. Separate PR.
2. **Flux strips a `netpol-digest` annotation written with kubectl's default
   field manager.** It was gone within one Flux interval. Written with a
   distinct field manager, it survives reconciles. The Registry Controller
   writes with its own manager, so this should hold in Phase B. Confirm it
   there.
3. **kube-router renames a pod's `KUBE-POD-FW-*` chain on every full sync.**
   The T1 pod went through five chain names in its first five minutes. The
   attestor re-attested each new name, both on its 30 s refresh and as soon
   as the chain changed. Tooling must not cache the chain name.
4. **The kata-deploy install restarted containerd (k3s-agent) on rig0 once**,
   as documented. The first Helm action reported `Running 'install'` and the
   release settled as `v2` (`Helm upgrade succeeded`). All four nodes stayed
   Ready.
5. **Signing is pending.** No organisation cosign key exists, so none of the
   images are signed. That blocks B2 Rule 1, not Phase A.
6. **Not covered here:** T27 and T29 (gateway reachability through the real
   agents Gateway, and per-boundary overhead), sparky as a sandbox node, and
   the Kyverno cluster tests (T9b, T22). They come with B1–B3.
