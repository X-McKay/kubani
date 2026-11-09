# MCP backend registration

The registry connects supported MCP server deployments to the agents gateway, Keycloak and APS. Flux remains responsible for Kubernetes deployment. Backend registration does not grant tools to an agent or approve an AgentRelease.

The registry supports generated `container-sse-v1` deployments such as postgres-admin and a bounded `existing-streamable-http-v1` registration for Kubernetes MCP. The latter verifies referenced resources while preserving their handwritten GitOps ownership. Unsupported transport or authentication profiles fail validation; other unregistered backends remain outside registry verification.

## Add one server

From the repository root:

```sh
just mcp add example-monitor
```

This creates only `infrastructure/mcp/backends/example-monitor.yaml`. It does not deploy anything, create credentials, change identity configuration or modify another backend. Existing names/files are never overwritten.

Fill the definition's required values: pinned image, container arguments, service port/resources, exact tool/role policy and dependencies. Use existing Secret references, never credentials in the definition. Keep new credentials SOPS-encrypted in explicit `.enc.yaml` files. Database-specific SQL and bootstrap Jobs remain separately reviewed dependencies; a server with no database dependency does not need a database bootstrap.

Environment credentials use Kubernetes-style references, for example:

```yaml
secretEnv:
- name: DATABASE_URI
  secretKeyRef:
    name: example-monitor
    key: DATABASE_URI
```

The referenced SOPS-encrypted manifest must be listed in `secrets`. Servers without credentials can leave both lists empty. Optional `upstreams` entries declare namespace, Pod selector and port; generation adds both sides of the network path. The initial profile supports cluster-local upstreams, not arbitrary external egress.

Then generate and verify the complete registration:

```sh
just mcp render --write
just mcp-check
just test-mcp-registry
```

Review the definition and generated diff together in a normal PR. For supported entries, generation handles shared gateway auth targets and network integration; no manual shared-policy-list edits are needed. CI checks generated output and the full rendered configuration. Existing backends must retain their effective permissions.

Generated files and their ownership inventory are not hand-edited. Backend removal/renaming is deliberately refused in this version: plan migration of references and active releases explicitly. The tool does not silently delete identities, Secrets or live resources.

## Identity setup and deployment

Local identity operations use the existing SOPS administrator credential and refuse conflicting configuration. `just mcp` supplies the existing pinned operator dependency, including PyJWT required by the shared authentication helper. Set your usual age key and kubeconfig without placing credentials in shell arguments or registry files:

```sh
export SOPS_AGE_KEY_FILE=/home/al/git/kubani/age.key
export KUBECONFIG=/home/al/.kube/config
just mcp identity plan example-monitor
```

A plan is read-only. For a reviewed new backend, explicitly apply missing role/resource/scope/optional APS-attachment operations:

```sh
just mcp identity apply example-monitor
just mcp identity plan example-monitor
```

Each write is followed by an exact readback. Conflicts are refused instead of overwritten; a failed operation may have partially completed, so inspect again before retrying. Existing APS attachments and human delegation are not changed. This workflow does not edit the Keycloak realm-import ConfigMap or restart Keycloak.

Merge the reviewed GitOps change and allow Flux to reconcile. Verify bootstrap Job completion where declared, then inspect every registration layer:

```sh
just mcp status example-monitor
```

Status uses read-only Kubernetes and Keycloak calls. It checks desired resource configuration, current readiness/route/policy conditions, bootstrap dependencies and exact identity setup. Secret existence checks retrieve only names, never values or annotations. A nonzero result means registration is incomplete, conflicting, or could not be verified.

## Functional verification

Registration completeness is not proof that the backend's tools work. A TCP-ready container may still have incorrect upstream privileges. Use an ordinary session of a separately approved agent whose capabilities include the new backend, through agentgateway and APS. Inspect the actual tool results/report and confirm session cleanup.

For the postgres-admin migration, use the existing approved db-admin v0.1.1 release: require all four diagnostics available, its deterministic report to match saved evidence, and confirmed sandbox deletion. Preserve failures; do not weaken the checks to obtain a pass.

A changed bootstrap SQL hash must not silently reuse the existing completed Job revision. Introduce a reviewed revision and verify the new operation explicitly; the registry never deletes/restarts Jobs to force SQL execution.

## Boundaries

- Gateway identity, backend and exact tool allowlists are enforced; this does not claim generic validation of SQL/tool arguments.
- Agent tool grants, release signatures/attestations/approval and signer trust remain separate controls.
- Kubernetes policies are additive. Validation accounts for existing shared gateway/DNS rules and refuses unexplained broader access; a narrow generated rule cannot cancel a broad existing allow.
- No new controller or continuously privileged reconciler is installed.
- General platform qualifications remain paused. This workflow's bounded integration checks do not complete them.

## Verified migration

PR [#394](https://github.com/X-McKay/kubani/pull/394) merged the registry. All eight Flux Kustomizations reached Ready at the merged revision. Postgres-admin retained its Deployment UID, Pod UID and exact Pod template; its existing approved db-admin release retained the same UID and spec. No identity mutation or workload restart was needed.

The documented identity plan returned no operations and unchanged role/resource/scope IDs. Live registration status passed all 20 layers, including the shared human-gateway exclusion. The command intentionally continues to label functional testing as `not-tested`; the separate ordinary session supplied that evidence.

The db-admin v0.1.1 session completed in generation 1 with 11 boundaries. All four latest diagnostics were available, retrieved artifacts passed content-hash verification, and report facts equaled their corresponding evidence. Cleanup was CLEANED with stop OK, delete DELETED and grant OK; no tenant sandbox Pods remained. Private reports and receipts are retained locally, including intermediate incomplete status results.

Incremental onboarding was also exercised through the actual CLI in a disposable checkout: create a second definition, complete it, render, check and refuse a duplicate without overwrite. Existing backend definitions and effective permissions were preserved. No synthetic service was deployed to production.

Independent Sol reviews, targeted regression suites, all seven GitOps builds, infrastructure tests and CI passed. Three local loopback tests required a sandbox-permitted retry; their original restriction failures were retained. Secret scanning remains unchanged: conventional Secret key references and typed metadata digests avoid false positives without new exceptions.

### Explicit PostgreSQL credential preparation

`just mcp provision plan NAME` checks local prerequisites without an age private
key, kubeconfig, identity administrator, network access, or random credential
generation. `just mcp provision apply NAME` prepares a new encrypted Secret pair;
Flux remains responsible for deploying it and running the reviewed bootstrap Job.
Neither command executes SQL or restarts a Job.

A backend may declare this bounded profile (both paths must also be in `secrets`):

```yaml
provision:
  profile: postgres-secret-pair-v1
  roleManifest: infrastructure/gitops/apps/mcp/example-role.enc.yaml
  workloadManifest: infrastructure/gitops/apps/mcp/example.enc.yaml
  username: example_monitor
  database: postgres
  host: postgresql.database.svc.cluster.local
  port: 5432
  policyDescription: Reviewed metadata-only monitor role and interface grants
```

The role Secret name is derived from the bootstrap Job's unique `MCP_PASSWORD`
reference, with key `password` and the bootstrap namespace. The workload Secret
name comes from its unique `DATABASE_URI` reference in namespace `mcp`, with key
`DATABASE_URI`. Host service, namespace and port must match a declared upstream.
Policy description is reviewed intent, never generated privileges or proof of SQL
behavior. Authors must separately review the bounded SQL, grants, ownership and
role adoption behavior, pin its hash, and declare the versioned Job and ConfigMap.

For an incremental backend:

1. Run `just mcp add NAME` and complete its definition. Existing unfinished
   scaffolds do not prevent adding another definition.
2. Author and review the bootstrap SQL and bounded, pinned Job. Declare bootstrap
   metadata and the profile, and add both future Secret paths and Job to the
   source Kustomization. Include the SQL through its declared ConfigMap generator.
3. Run `just mcp provision plan NAME`. Resolve every reported missing source or
   encrypted dependency, including administrator references. The existing
   administrator source is `infrastructure/gitops/apps/postgresql/secret.enc.yaml`,
   `database/postgresql-credentials:postgres-password`; it is never generated.
4. Run `just mcp provision apply NAME` with SOPS and the repository age recipient
   policy available. Both files must be absent or both must already exist.
5. Run `just mcp render --write`, `just mcp check`, and `just test-mcp-registry`.
   Review the complete GitOps diff, then use the separate identity plan/apply
   workflow. Merge through review and let Flux reconcile. Verify Job completion,
   registration status, and an approved ordinary functional session.

Apply creates one random password in memory and sends each manifest to SOPS on
stdin. It encrypts both successfully before exclusively creating either file.
Plaintext is never written to temporary files or passed in process arguments.
Two-path publication cannot be atomic: a failure after the first publication is
reported as `partial`, with the encrypted paths already published. Inspect and
resolve this state through a separately reviewed recovery; retries refuse partial
pairs and never import, overwrite, rotate or automatically delete credentials.
Existing complete pairs preserve bytes without decryption or SOPS invocation;
this does **not** verify that their password and URI match or work.

Preflight follows explicit local resource inclusions from the repository Flux
source root, checks credential identities, encrypted keys, SQL hash/revision and
ConfigMap source linkage, and reports duplicate raw Secret identities. It is a
source prerequisite check, not a Kustomize evaluator. Unsupported/unsafe paths
fail closed. Full render/check verifies effective Job and ConfigMap contents and
remains mandatory. PostgreSQL's Service is Helm-provided; matching its declared
upstream is no DNS, live Service, database policy, or credential verification.
The postgres-admin profile preserves its existing pair, SQL, Job and generated
runtime configuration. Its reviewed SQL resets the login password on Job
execution; local preparation does not execute that SQL or promise rerun safety.

## Existing Kubernetes Streamable HTTP registration

`infrastructure/mcp/backends/kubernetes.yaml` uses the bounded
`existing-streamable-http-v1` profile. It registers the existing Kubernetes
workload and four agent gateway objects without generating replacements or
changing their GitOps ownership. It preserves the existing server image tag;
registration does not claim a new digest pin. `add` still scaffolds only the
container SSE profile.

Each public reference selects a document by its exact API version, kind,
namespace and name, then binds its complete object with `canonicalSHA256`.
The hash is SHA-256 over UTF-8 JSON with sorted keys, compact separators,
ASCII escaping, no NaN and no final newline. It excludes YAML comments and
formatting, but includes every object field. It hashes the selected object,
not every backend in a shared file. The workload manifest must retain exactly
its six reviewed objects. Missing, duplicate, changed, unsafe or symlinked
references fail offline validation; complete Kustomize output must contain
exactly the same objects. Review source and declaration hash changes together;
a hash is a review binding, not protection against simultaneous edits to both.
The profile additionally enforces read-only kubeconfig configuration, the view
role binding, six exact tools and the existing HTTP gateway contract.

`infrastructure/mcp/baseline/kubernetes-view.json` records only the existing
built-in ClusterRole's API version, kind, name, rules and aggregation rule.
Its declaration hash is checked offline. Live registration status compares
that projection exactly, so aggregated permission changes report drift.
The snapshot is a status-only external dependency: it is never rendered,
owned or applied by the registry. Refresh it only after reviewing the actual
permission change. Registration status still reports `functional: not-tested`;
it does not establish tool execution or agent qualification.

The Kubernetes role, resource audience and optional scope use the standard
identity descriptor. Registration introduces no identity extension, Secrets,
SQL, provisioning, network grants or human gateway exclusion. Existing shared
authentication and complete network baselines remain enforced.

### Kubernetes verification (registration-time snapshot)

At registration, all 326 application and 203 infrastructure rendered objects
were identical to the pre-registration baseline. Existing generated runtime YAML, auth targets,
human access, PostgreSQL descriptor and all fixture budgets are unchanged.
That checkpoint had ten of 13 offline preflights passing, with only the three
intentional conformance budget failures; every Kubernetes dependency grant passed.
The later model-free fixture correction brings the matrix to 13/13; see the
[current preflight evidence](agent-onboarding-preflight.md#explicit-model-free-fixtures-2026-11-08).

The actual investigator live preflight passed all 18 registration layers,
including ServiceAccount, role binding and effective view permissions. Identity
planning returned no operations and the same role/resource/scope IDs. Deployment
spec/UID, Pod UID, container IDs, image IDs and restart counts were unchanged.
No identity apply, workload replacement, image release or agent session occurred.
Functional tools, human consent and release qualification remain untested by this
registration check.

The existing Reloader controller injects a public ConfigMap hash into the server
container. Status accepts only its exact observed marker, derived from the reviewed
ConfigMap and bound to the exact Deployment, annotation, container and mount.
The algorithm was verified against deployed Reloader v1.2.0's
[ConfigMap hashing implementation](https://github.com/stakater/Reloader/blob/v1.2.0/internal/pkg/util/util.go)
and its digest implementation. Wrong hashes, duplicate markers, unrelated
environment variables and live ConfigMap changes remain drift. Initial mismatch
and test failures are retained in local evidence; no broad normalization was added.
