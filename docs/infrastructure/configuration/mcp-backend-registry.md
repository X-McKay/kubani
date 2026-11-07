# MCP backend registration

The registry connects supported MCP server deployments to the agents gateway, Keycloak and APS. Flux remains responsible for Kubernetes deployment. Backend registration does not grant tools to an agent or approve an AgentRelease.

The first supported profile is `container-sse-v1`, matching the existing postgres-admin deployment. Unsupported transport or authentication profiles fail validation. Existing legacy backends remain handwritten; postgres-admin is the first registry migration.

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
