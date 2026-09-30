---
name: host-maintenance
description: Use when planning or running a DGX OS, driver, or kernel update window on sparky (the GB10 inference node) - or any host-level change that requires a reboot of the node serving vLLM.
---

# Host Maintenance (sparky)

A DGX OS / driver / kernel window on sparky takes the only GPU node down.
There is no failover, no hot spare, and DGX OS rollback is a reimage, not a
revert — so everything reversible gets checked before the reboot, not after.
This is stage 1.7 of the inference roadmap and every future driver update.

## Pre-checks (before touching anything)

1. Every `local-path` PVC on sparky must be re-creatable. Model weights have
   a NAS copy (`nas-model-storage-pvc.yaml`); the vLLM compile/cache PVC is
   disposable and rebuilds on next boot. Confirm no PVC on the node holds
   data that exists nowhere else:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl get pv -o json | \
     jq -r '.items[] | select(.spec.nodeAffinity.required.nodeSelectorTerms[]?.matchExpressions[]?.values[]? == "sparky") | .metadata.name'
   ```
2. Image cache: the vLLM image pull is multi-GB. If the target image isn't
   already cached on the node, pull it ahead of the window
   (`just inference-preflight <image>`) so the window isn't spent waiting on
   a pull after reboot.
3. `age.key` and the kubeconfig must be off the node — they have no business
   being there, and a reimage should not be a key-material incident. Confirm:
   ```bash
   ssh sparky test -f ~/git/kubani/age.key && echo "FOUND — remove before reboot" || echo "clean"
   ssh sparky test -f ~/.kube/config && echo "FOUND — remove before reboot" || echo "clean"
   ```
4. Capacity ledger: `just capacity` — know the starting point so the
   post-maintenance reading is comparable.
5. `just node-maintenance sparky pre` runs the capacity check, lists pods and
   local-path PVCs on the host, and warns about `age.key`, then cordons the
   node and prints the manual steps below. It does **not** drain — sparky's
   vLLM engines use the `Recreate` strategy, so draining just adds an extra
   pod cycle; deciding when to let the engines stop is the operator's call,
   not something to automate.

## The window

1. `just node-maintenance sparky pre`.
2. Apt steps **only on the 580 driver branch**. 590.x deadlocks CUDA graph
   capture on GB10 (excluded per the roadmap non-goals) — do not let a
   package manager pull a 590.x driver as a transitive dependency. Pin or
   verify the branch before `apt upgrade`.
3. `systemctl set-default multi-user.target` — the node boots to a text
   console, not `graphical.target`, so nothing wastes GPU memory or cycles
   on a desktop session that will never be used.
4. Reboot.
5. `just node-maintenance sparky post` — uncordons, waits for the node
   Ready, then waits for `vllm-fast` then `vllm` rollout status in that
   order (fast is the cheap canary; if it doesn't come up cleanly, don't
   let main start weight-loading into a bad driver state).

## Verify

1. `nvidia-smi` on the node: driver version matches what was intended,
   clocks look sane, no faults reported at idle.
2. Engine order: fast model first, then main — each with a real completion,
   not just Ready:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl exec -n vllm deploy/gpu-broker -- \
     python3 -c "..."   # or: just inference-restart fast --no-capture (verify-only path)
   ```
   In practice, `just inference-restart <engine>` already ends with a real
   completion check — use it as the verification step once each engine is
   Ready, not a separate hand-rolled curl.
3. Drift bench: `just inference-bench main drift-<date>` (e.g.
   `drift-20260930`), then `just inference-compare main <result>`. Compare
   against the current baseline — a host change is exactly the kind of
   platform drift `docs/infrastructure/inference/release-process.md`'s drift
   runs exist to catch. Never promote a drift result.

## Rollback

**There is no revert.** DGX OS / driver rollback on this hardware is a
reimage. This is why the pre-checks above exist — by the time something
looks wrong post-reboot, the only way back is reimaging the node and
restoring from the NAS copy of the weights plus GitOps for everything else.
Treat the pre-checks as mandatory, not optional housekeeping.

## Red flags: stop

- Skipping the PVC re-creatability check because "it's probably fine" — the
  node has no snapshot to fall back to.
- Leaving `age.key` or a kubeconfig on the node through a reimage.
- Installing anything from the 590.x driver branch on GB10.
- Letting `vllm` (main) start before `vllm-fast` has proven the driver stack
  works.
- Treating "node is Ready" as the verification. Ready says kubelet is
  talking to the API server, not that CUDA graph capture works.
- Skipping the drift bench because the engines came up — the roadmap's
  whole point is that a healthy-looking restart can still be measurably
  worse.
