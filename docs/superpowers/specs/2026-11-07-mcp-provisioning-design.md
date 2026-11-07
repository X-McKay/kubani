# Explicit MCP credential preparation and bootstrap preflight

## Decision and scope

Implement local `just mcp provision plan NAME` and `just mcp provision apply NAME` using the existing SOPS, registry and Flux workflow. The root agent selected this bounded approach. Apply prepares new encrypted GitOps credentials; Flux alone deploys Secrets and executes the explicitly reviewed database bootstrap Job. This is credential preparation and database bootstrap preflight, not a generic database policy generator. Existing gateway and identity configuration remain managed by current render/check and identity commands.

Alternatives considered: generate per-backend copies of the monitor SQL (requires a separate ownership/adoption protocol and substantial PostgreSQL security review), or directly execute database administration from the operator CLI (introduces another privileged mutation path). Retaining reviewed SQL/Job inputs is the smallest useful integrated increment.

## Declaration and command contract

Add one optional strict top-level declaration:

```yaml
provision:
  profile: postgres-secret-pair-v1
  roleSecret: infrastructure/gitops/apps/mcp/example-role.enc.yaml
  workloadSecret: infrastructure/gitops/apps/mcp/example.enc.yaml
  username: example_monitor
  database: postgres
  host: postgresql.database.svc.cluster.local
  port: 5432
  policyDescription: Reviewed metadata-only monitor role and interface grants
```

Both paths must appear in existing `secrets`. Role Secret identity is derived from the reviewed bootstrap Job's unique MCP_PASSWORD Secret reference (key must be `password`, namespace is bootstrap namespace). Workload Secret identity is derived from the unique DATABASE_URI workload reference (key must be `DATABASE_URI`, namespace `mcp`). Reject other mappings or ambiguous references. Require bootstrap; SQL path/hash, Job identity/revision and ConfigMap remain declared in existing bootstrap fields. `policyDescription` is informational reviewed intent, never executable privileges and never proof of SQL behavior. Username/database must be bounded PostgreSQL identifiers; host must be a cluster-local service DNS name; port must agree with the declared upstream. Reject unknown profile/fields and collisions across backend credential pairs.

`plan` is offline, read-only, and needs no age private key, identity administrator or kubeconfig. Output sanitized metadata: profile, desired Secret identities/paths/keys; create versus preserve/conflict; reviewed SQL path/hash and Job/revision; policy description; administrator Secret references; missing dependencies and manual next steps. No random credentials are generated during plan. Nonzero status denotes conflict or missing prerequisite, while planned absent credential pair is actionable rather than a validation error.

`apply` repeats preflight and creates a pair only when both paths are absent. Generate one random URL-safe password in memory, derive the URI from validated components, and encrypt each manifest through SOPS stdin using repository `.sops.yaml` and destination filename. Do not pass credentials in argv, log subprocess output, print raw exceptions, or write plaintext temporary files. Do not read age keys directly. Encrypt both successfully before publishing either. Exclusive destination creation refuses existing files and symlinks. If publication partially fails, report a sanitized partial state and refuse subsequent partial-pair adoption; do not overwrite or delete existing credentials automatically. Atomic publication of two filesystem paths cannot be promised.

If both files exist, structurally validate their encrypted metadata and required keys and preserve bytes exactly without decryption, re-encryption or credential comparison. This is preservation, not verification that existing passwords/URI match. If exactly one exists, refuse. No rotation, import, overwrite, deletion, live Secret adoption, kubectl apply, SQL execution, identity mutation or automatic render is part of apply.

## Validation boundary and dependency preflight

Keep `model.load_registry()` and ordinary render/check/identity/status strict by default. Introduce `load_registry(root, *, provisioning=False)` with a narrowly scoped provisioning mode: only paired absent Secret paths explicitly covered by a valid provision declaration may be absent. Validate all other declaration fields, SQL hashes, Job identities, paths and existing encrypted files exactly as before. Do not weaken strict checks or invent placeholder files. `add` checks name/path collisions without requiring unrelated incomplete scaffold definitions to validate; refuse existing path through exclusive creation as today.

Provision preflight inventories raw GitOps source metadata and explicit Kustomization inclusions without requiring a successful full build with the planned absent files. Check both credential references, all Job Secret references including administrator credentials, ConfigMap linkage, SQL hash/revision, path safety, recipient policy, and duplicate Secret identities across sources. Resolve the existing administrator reference through `infrastructure/gitops/apps/postgresql/secret.enc.yaml`: `database/postgresql-credentials:postgres-password`, inspecting encrypted metadata/key names only. Require non-pair dependencies already declared and present encrypted or explicitly rendered source resources; list exact missing dependencies without printing values. Check planned files are included by the source Kustomization and bootstrap/configMapGenerator remain reachable. Validate SQL hash changes against inventory's existing reviewed revision guard. Full existing render/check remains mandatory after apply.

Postgres-admin receives only a provision stanza matching its existing pair; all existing SQL, Job, encrypted files, runtime objects and generated effective configuration remain unchanged. Its complete pair plans/applies as preserve/no-op. Current reviewed SQL resets the login password on Job execution; the new command never executes/restarts that Job, and does not claim SQL reruns preserve credentials. New backend authors must separately review bounded bootstrap SQL and its role/adoption behavior before introducing a Job.

## Practical usage and limits

Create a backend definition, explicitly author/review its bootstrap SQL and pinned bounded Job, declare intended roles/grants in the policy description, add both future Secret paths to the source Kustomization and definition, then run provision plan/apply. Run render --write, check, registry tests, and review the complete diff. Use existing identity plan/apply; merge and let Flux reconcile; verify Job completion and status, then an approved ordinary functional session.

No claim of live readiness follows from local preparation. Missing external administrator Secret sources must be reported rather than silently generated. Existing plaintext or structurally invalid SOPS resources fail closed. Broad qualification work remains paused.

Implementation clarification: preflight follows explicit local resource paths
from the Flux source root, including the databases source, without implementing
Kustomize transformations. Full render/check remains authoritative for effective
Job equality and ConfigMap contents. PostgreSQL's Service is Helm-provided;
preflight matches the declared upstream service, namespace and port and makes no
DNS, live Service or credential verification claim.
