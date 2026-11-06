# T28 automatic policy repair

These templates are inactive and absent from all Kustomizations. The Job stays
suspended until an exclusive root-owned qualification window. Deploy the reviewed
T28 controller receipt and runner preflight-detail implementations together first;
verify production runner, reconciler and harness installed image digests match.
No session, release, Flux reconciliation or other policy mutation may overlap.

Render only these exact placeholders into a fresh local directory:

- `POLICY_REPAIR_RUNNER_IMAGE`: published, installed-source-verified runner RepoDigest.
- `CONFORMANCE_RELEASE`: exact approved, signature-verified Ready conformance release
  with NoDrift and optional delegation explicitly false (or agent identity mode).
- `POLICY_REPAIR_DIGEST`: canonical digest from the reviewed renderer below.
- `CONTROLLER_POD_NAME`: the one current stable Ready Registry Controller Pod;
  record its UID, imageID and restart count before and after qualification.

Obtain the canonical digest independently from the built controller image, with
network disabled; do not copy the live namespace annotation as the expectation:

```sh
docker run --rm --network none --entrypoint /app/.venv/bin/python \
  "$VERIFIED_CONTROLLER_IMAGE" -I -c \
  'from agent_platform.netpol import netpol_digest; print(netpol_digest())'
```

The dedicated temporary `conformance-policy-repair` ServiceAccount alone gets
NetworkPolicy create/get/list/delete in tenant-test. It cannot edit workload
resources, Secrets, releases, or namespace metadata. Cluster scope is only GET
of the named tenant-test Namespace. Its platform log read is restricted to the
one rendered controller Pod name. The ordinary conformance-harness ServiceAccount
receives no new policy mutation permissions. Existing TLS and codec Secrets are
mounted directly into the restricted Job; no operator reads their contents.

After inspecting the rendered manifests, create the temporary RBAC and suspended
Job. Verify the tenant has no sandbox Pods and the canonical four policies match
the independent digest. Before unsuspending, arm a read-only NetworkPolicy watch and preserve its
resourceVersion plus each added policy name/UID, bound to this exact Job UID
and exclusive window. This independent receipt is mandatory because a crash
before the final report can lose the harness's in-memory cleanup identity.
Unsuspend only this exact Job. The runner's T28 code
creates one random run-owned extra policy, submits an ordinary session, and
requires automatic controller repair within 60 seconds plus the actual preflight
refusal identifying that same policy UID. It never pauses the controller or
triggers manual reconciliation. If repair wins before preflight observes drift,
preserve the failed race report. An independent policy cleanup lease and exact
UID deletion prevent a stalled session start from extending the fault window;
operator deletion always fails qualification.

Preserve the raw report and Job/Pod/controller identity receipts before deleting
resources. Confirm the exact extra policy is absent, the canonical digest is
restored, the session has ended and no tenant sandbox remains. If the Job crashes,
use its recorded exact policy name/UID and ordinary workflow cancellation for
bounded cleanup; never delete a replacement UID or claim operator cleanup as
controller repair. Finally delete this Job and every object in the rendered
RBAC file, including the temporary ClusterRole/ClusterRoleBinding. No completion
or source-test result alone qualifies T28.
