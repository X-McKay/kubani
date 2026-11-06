# T27 temporary TLS transport qualification

These templates are inactive, suspended and absent from every Kustomization.
They require the reviewed T27 runner and signed `conformance-transport` fixture,
plus the ordinary approved `conformance` release used for exact T4. No release,
Agent, approval, host privilege or automatic Job is added here. Controller-derived
SignatureVerified/attestations/NoDrift/Ready must precede an exclusive live run.

Render the six explicit placeholders into a private local directory:
`TRANSPORT_RUNNER_IMAGE`, `TRANSPORT_RELEASE`, `T4_RELEASE`, `TRANSPORT_RUN_ID`,
`TRANSPORT_SESSION_ID`, `T4_SESSION_ID`. The image is a published digest-pinned
runner image shared by the production runner/reconciler, temporary worker and
harness. Generate all three UUIDs freshly; session IDs must differ. Replace only
`${...}` placeholders and preserve Kubernetes `$(..._RELEASE)` argument expansion.
Do not substitute an old runner lacking the T27 adapters. Inspect all four
rendered files and keep both Jobs suspended until preparation is complete.

The worker and harness remain on the database node because the artifact PVC is
RWO. Only the worker mounts it writable. Worker identity/mounts are the ordinary
session-runner ones; it accepts only the two control-bound inputs on a unique
queue. The harness mounts Temporal TLS, the tenant payload key and read-only
artifacts, with no APS/backend key, human token, exec rights or host mount.
New workload RBAC is only `get` on the exact control ConfigMap, `get` on the exact
two releases and tenant Pod `list`. Existing harness namespace permissions supply
APS logs and worker inventories. Neither workload can write operator receipts.

The operator creates the fresh control object and temporary Role/RoleBindings,
applies both suspended Jobs, starts the worker and verifies one Ready Pod with
zero restarts and the same imageID as production. Start the harness only when no
other conformance batch is active. Its two workflows first run the deterministic
TLS probe, then ordinary conformance T4. T4 uses its existing exact claim/JTI/APS
issuance evaluator. The temporary wrapper holds the real first exec before any
token request and the same Pod after the final real exec until capture stops.
No synthetic activity result or production fault option is used.

The before-exec gate waits at most 240 seconds; the final gate waits 120 seconds
within the ordinary activity deadline. Missing a window is a failed attempt,
followed by normal cleanup and a fresh binding for any retry. Root/operator owns
the concrete bounded host actions. Existing authorization covers read-only
preparation; inspect the resolved command before escalation/capture. Never launch
a privileged Pod or repurpose the attestor. A rejected approval review must be
resolved or the attempt stopped, not bypassed.

On the `capture_start_required` event, save only `gate` to a mode-0600 JSON file.
The host helper is `runner.conformance_transport_host` from the reviewed ZetRA
checkout/image; use an explicit existing kubeconfig and the locked runner Python
environment. Repo inventory identifies rig0 as the local operator workstation
(`ansible_connection: local`), not an assumed SSH alias. Required host tools are
kubectl, crictl, nsenter, ip, tcpdump and `/usr/bin/timeout`; read-only CRI/netns
inspection needs scoped host privilege. Root's 2026-11-06 prerequisite check found
these tools and active k3s-agent, but that inventory is not T27 qualification.

```sh
python -m runner.conformance_transport_host prepare --kubeconfig EXACT_KUBECONFIG \
  --gate PRIVATE_GATE.json --binding FRESH_PRIVATE_BINDING.json --allow-host-metadata
```

Preparation binds the exact Pod UID/IP/node, CRI sandbox/netns inode, guest eth0
and host veth peer indices. Resolve and inspect those concrete values before:

```sh
sudo python -m runner.conformance_transport_host capture --kubeconfig EXACT_KUBECONFIG \
  --gate PRIVATE_GATE.json --binding FRESH_PRIVATE_BINDING.json \
  --directory FRESH_PRIVATE_CAPTURE_DIRECTORY --owner al \
  --allow-host-metadata --allow-host-capture
```

This opens only one bound veth capture with filter
`host EXACT_POD_IP and host 10.43.250.10 and tcp port 443`, promiscuous mode off.
The helper rechecks identity throughout and drops tcpdump to the unprivileged
local owner. Raw pcap stays mode0600 inside a mode0700 local directory, bounded by
4096 packets/32 MiB and an independent 115-second timeout plus 5-second hard kill.
The supervisor remains bounded if the Python helper is killed; ordinary signal
cleanup stops its exact process group. The start receipt `pid` is the supervisor
PID. No raw bytes, bearer, private key or arbitrary command error is printed.

When the private `capture-start.json` is ready, the operator publishes its exact
JSON as the new ConfigMap `data.capture-start`. Use an atomic JSON Patch testing
the previously captured control UID, current resourceVersion and original config;
require the key absent before adding it. Never update an existing receipt or
replace the control object. The worker's immutable receipt read releases T4.
On `capture_stop_required`, create only the local capture directory's `stop`
marker. While the same Pod is held Running, the helper stops capture and writes
`capture-complete.json`; publish it as a new `data.capture-complete` with the same
UID/resourceVersion/config guards. Only sanitized metadata/digest goes into the
ConfigMap. Capture failure still releases ordinary cleanup and cannot pass.

Retain the original report and sanitized receipts. Verify that full T4 execution
and its sole matching issuance are covered, no packet loss/gaps/ambiguous streams
exist and every captured connection shows TLS handshake/application records.
The parser searches complete reassembled streams for clear bearer/JWT patterns.
Missing or unreadable evidence fails. Keep raw pcap only on the private operator
host until verification, at most 24 hours, then remove it plus the local binding
and receipts; never commit/upload packet bytes. Retain the sanitized SHA256,
counts/times and report according to spec15.4.

After any outcome, cancel still-running exact workflows while the test worker is
available, wait for normal cleanup and confirm no bound sandbox remains. Remove
the two Jobs, exact control ConfigMap and temporary Role/RoleBindings. The
operator independently handles cleanup after harness failure; no forced Pod
replacement or weakened confirmed-deletion rule is permitted. Local tests and
inactive templates do not claim a live T27 pass.
