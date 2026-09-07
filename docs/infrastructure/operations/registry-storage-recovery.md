# Registry storage ownership recovery

Status: prepared procedure; **not executed**. This is a shared registry repair,
not permission to deploy Starbase2. Obtain operator approval before step 2.

## Observed publication failure

On 2026-09-07 UTC an authorized Starbase2 image push authenticated successfully
but failed while initiating a layer upload with HTTP 500. Registry logs reported:

```text
filesystem: mkdir /var/lib/registry/docker/registry/v2/repositories/starbase2: permission denied
```

The registry process is UID/GID `65532:65532`. Its existing `docker`,
`docker/registry`, `v2`, `repositories` and `blobs` directories are `root:root`
with mode `0755`. The configured `fsGroup: 65532` has not made these hostPath
directories writable. `/v2/` health probes still succeed because they do not
verify storage writes. The Core release manifest remained absent after failure;
the worker push was not attempted against the same known storage fault.

Observed target (revalidate immediately before repair):

- Context: `default`, namespace `registry`, Deployment `registry`.
- PVC: `registry-data`.
- PV: `pvc-0d33f0ba-b637-46ed-8de3-9e7f4e556a79`.
- Storage node: `strix` (PV affinity, not new workload placement).
- Host path: `/var/lib/rancher/k3s/storage/pvc-0d33f0ba-b637-46ed-8de3-9e7f4e556a79_registry_registry-data`.

Do not switch the registry to root, weaken restricted pod admission, or make
the volume world-writable. No Deployment or active Flux root change is proposed.
The repair changes existing filesystem ownership to the already-declared
non-root identity. It does not remove blobs, tags, repositories or credentials.

## 1. Revalidate without changing data

With an explicit kubeconfig, inspect the PVC/PV binding, node affinity and
running registry identity. Confirm they still match the target above. On
`strix`, verify `getfacl`, `setfacl` and passwordless operator sudo are available
(all were present during preflight). Inspect the complete `docker` tree before
execution; stop if there are symlinks, special files, unexpected mount points,
owners other than root or 65532, or special permission bits. The read-only
full-tree inventory found 11,329 root:root directories at `0755` and 10,000
root:root regular files at `0644`, no other file types and no nested mounts.
Recheck immediately before the authorized maintenance because content can change.

Coordinate with other publishers and garbage collection before changing
ownership. Keep them paused through snapshot and verification. Image reads can
continue; no registry restart or broad Flux suspension is required for this
metadata change. If publishers cannot be quiesced, reschedule maintenance.

## 2. Approved ownership repair on strix

Run only after approval and target/inventory verification. These commands are
for a root shell on the storage node, not inside the restricted registry pod.
Keep the ACL/ownership snapshot on the node with root-only access.

```sh
set -eu
registry_tree=/var/lib/rancher/k3s/storage/pvc-0d33f0ba-b637-46ed-8de3-9e7f4e556a79_registry_registry-data/docker
registry_recovery=/root/registry-storage-recovery-20260907
test -d "$registry_tree"
test ! -L "$registry_tree"
umask 077
mkdir "$registry_recovery"
getfacl --recursive --physical --absolute-names "$registry_tree" > "$registry_recovery/before.acl"
test -s "$registry_recovery/before.acl"
find "$registry_tree" -xdev \( -type d -o -type f \) -uid 0 -gid 0 \
  -exec chown --no-dereference --from=0:0 65532:65532 {} +
getfacl --recursive --physical --absolute-names "$registry_tree" > "$registry_recovery/after.acl"
```

The exclusive `mkdir` prevents overwriting prior recovery metadata. Do not
discard a partial failure and rerun blindly: inspect the recorded snapshot and
current owners first. Only root:root regular files/directories on this filesystem
are changed. Existing modes and file contents must remain unchanged; verify
the before/after ACL inventory before resuming publication. Do not generalize
this command to the parent K3s storage directory or other PVCs.

## 3. Verify and resume publication

From the registry container, confirm UID 65532 can write the repository and blob
directories. Retry the already-authorized Core upload only after checking that
its destination tag is still absent. Then publish the qualified worker image.
Retain registry-returned digests; fetch manifests by digest and match their
configuration identities to the qualified local images. Verify an existing
image remains readable. Resume other publishers after these checks.

If the repair must be undone, quiesce publishers/GC again and run
`setfacl --restore=/root/registry-storage-recovery-20260907/before.acl` as root on
`strix`, then verify restored metadata. This restores captured ownership/modes;
it does not remove content created after the snapshot or make the original
non-root write failure go away. Do not delete newly published images as an
implicit rollback. Escalate unexpected data errors rather than attempting
garbage collection or recreating the PVC.
