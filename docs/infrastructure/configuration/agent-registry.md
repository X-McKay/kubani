# Agent registry and provisioner

## What runs

`agent-registry` runs in namespace `agent-platform`. It keeps the record of agents
and their releases in PostgreSQL (database `agent_registry`). It listens on 8080
and answers `GET /healthz`. It accepts only Keycloak tokens of realm `agents`
with audience `agent-registry`. It applies its own database migrations at start.
It is reachable at `https://agents.almckay.io` on the tailnet only.

`registry-provisioner` runs in the same namespace and listens on nothing. Every
30 s it asks the registry which `Agent` and `AgentRelease` objects the cluster
should hold, applies them with server-side apply, and reports what it sees. It
never deletes. It gets its token from Keycloak by presenting its projected
service-account token as a client assertion, so it has no client secret.

Manifests: `apps/agent-platform/workloads/agent-registry.yaml`,
`workloads/registry-provisioner.yaml`, `registry-rbac.yaml`,
`netpol-registry.yaml`, `registry-db-init-job.yaml`, and
`apps/agents/tenant-test/registry-provisioner-rbac.yaml`.

| From | To | Port | Policy on the sending side | Policy on the receiving side |
|---|---|---|---|---|
| Traefik (`kube-system`) | agent-registry | 8080 | none (no egress policy in `kube-system`) | `agent-registry-ingress` |
| registry-provisioner | agent-registry | 8080 | `registry-provisioner-egress` | `agent-registry-ingress` |
| agent-registry | PostgreSQL (`database`) | 5432 | `agent-registry-egress` | `allow-agent-registry-postgresql` |
| agent-registry | Keycloak (`auth`) | 8080 | `agent-registry-egress` | `allow-keycloak-from-agent-platform` |
| registry-provisioner | Keycloak (`auth`) | 8080 | `registry-provisioner-egress` | `allow-keycloak-from-agent-platform` |
| registry-provisioner | API server | 443, 6443 | `registry-provisioner-egress` | none |
| db-init Job (`database`) | PostgreSQL | 5432 | `allow-agent-registry-db-init-egress` | `allow-same-namespace` |

Each of these policies also has an entry in the reviewed network baseline,
`infrastructure/mcp/baseline/effective-network-policies.json`. The MCP registry
tests fail when a policy in `agent-platform`, `auth` or `database` differs from
its entry, so a policy change and its baseline entry go in one commit.

## Settings

agent-registry:

- `REGISTRY_DSN`: PostgreSQL URL of the role `agent_registry`, with no password.
- `PGPASSWORD`: the password, from Secret `agent-registry-db`, key `password`.
- `REGISTRY_ISSUER`: `https://idp.almckay.io/realms/agents`.
- `REGISTRY_AUDIENCE`: `agent-registry`.
- `REGISTRY_JWKS_URL`: the realm's keys, read from the in-cluster Keycloak Service.
- `REGISTRY_FEED_PATH`: the feed file, in ConfigMap `agent-registry-feed`, mounted as a directory.
- `REGISTRY_PORT`: `8080`.

registry-provisioner:

- `PROVISIONER_CLUSTER`: `kubani`.
- `PROVISIONER_REGISTRY_URL`: the registry's in-cluster Service.
- `PROVISIONER_NAMESPACE`: the pod's own namespace.
- `PROVISIONER_TOKEN_URL`: the realm's token endpoint on the in-cluster Keycloak Service.
- `PROVISIONER_TOKEN_PATH`: the projected token file (audience is the realm issuer, 600 s).
- `PROVISIONER_HEARTBEAT_FILE`: `/tmp/heartbeat`; the liveness probe fails when it is older than 180 s.
- `PROVISIONER_INTERVAL_SECONDS`: `30`.

## Order of the roll-out

Two changes to this repository, with zetra's merge between them.

1. The first change lists what does nothing by itself: the service accounts and
   RBAC, the network policies, the feed ConfigMap, the realm file and the
   operator commands. Merging it restarts Keycloak once (step c).
2. zetra's `main` gets the registry and the provisioner. Its release workflow
   builds the two images.
3. Al does steps a and b below.
4. The second change lists `registry-db-init-job.yaml` and the two Secret files
   in `apps/agent-platform/kustomization.yaml`, and `agent-registry.yaml` and
   `registry-provisioner.yaml` in `workloads/kustomization.yaml`, with the
   image digests of step 2 in place of the zero placeholders. It also adds the
   baseline entry of `database/allow-agent-registry-db-init-egress` and the
   capacity ledger lines.

Until the second change the three workload files are in the tree and in no
kustomization, so Flux applies none of them.

## Steps only Al runs

Do them in this order. Run from the repository root with `KUBECONFIG=/home/al/.kube/config`.

Done on 2026-11-18, by Claude on Al's explicit word for that one time: step a,
and step b parts 1 to 6. The live realm then gave a `registry-reader` token
with audience `agent-registry`, `client_id` and the one role. Part 7 is not
done: the realm had no user of Al's, only `conformance-alice`. A person's user
appears at their first sign-in, so run part 7 after it.

### a. The database role password

One alphanumeric value, two Secrets (namespaces `database` and `agent-platform`),
staged outside the repository. This follows "Rotating a Credential" in
`.claude/rules/secrets.md`. The encrypt form was tried on 2026-11-17 with a
placeholder value and an output file outside the repository: the creation rule
matches the staged file name and only `stringData` is encrypted.

```bash
umask 077; STAGE=$(mktemp -d); PW=$(openssl rand -hex 24)
for pair in database:db agent-platform:ap; do
  mkdir "$STAGE/${pair#*:}"
  printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: agent-registry-db\n  namespace: %s\ntype: Opaque\nstringData:\n  password: %s\n' \
    "${pair%%:*}" "$PW" > "$STAGE/${pair#*:}/secret.enc.yaml"
done
D=infrastructure/gitops/apps/agent-platform
SOPS_AGE_KEY_FILE=age.key sops --encrypt "$STAGE/db/secret.enc.yaml" > $D/agent-registry-db-database.enc.yaml
SOPS_AGE_KEY_FILE=age.key sops --encrypt "$STAGE/ap/secret.enc.yaml" > $D/agent-registry-db.enc.yaml
shred -u "$STAGE"/db/secret.enc.yaml "$STAGE"/ap/secret.enc.yaml; rmdir "$STAGE"/db "$STAGE"/ap "$STAGE"; unset PW
grep -c '^sops:' $D/agent-registry-db-database.enc.yaml $D/agent-registry-db.enc.yaml
```

Commit both files in the change that lists `registry-db-init-job.yaml` in
`apps/agent-platform/kustomization.yaml`, or in an earlier one. The Job gives up
for good after 300 s without its Secret, and Flux does not run a failed Job of
the same name again.

The registry pod waits in `CreateContainerConfigError` until its Secret exists
and starts by itself once it does. No restart is needed.

To change the password later: change both Secret files and raise
`PASSWORD_GENERATION` in `registry-db-init-job.yaml` in one commit, then rename
the Job as `tests/test_registry_manifests.py` asks. The new Job sets the role's
password and Reloader restarts the registry. Changing the Secrets alone gives
the registry a password PostgreSQL does not know.

### b. The live realm

Keycloak never updates an existing realm from the file, so apply the same
changes with kcadm. These commands were run on 2026-11-17 against a local
Keycloak of the cluster's image, starting from the realm file on `main`. The
result was compared with a fresh import of the changed file: the roles, the
scope, both clients and `agent-cli` came out the same, apart from one attribute
Keycloak adds to a client only at import (`post.logout.redirect.uris`). The
federated sign-in of the provisioner client (6) could not be tried locally,
because it needs the cluster's own identity provider `kubernetes-kubani`.

The reader client's secret is in no file of this repository. Keycloak generates
it when the client is created, and step 5 copies it to
`~/.config/kubani/registry-reader.secret`, which the operator commands read
(`just agent status`). The copy is never shown. To replace the secret, run
`K create clients/$RID/client-secret -r agents >/dev/null` and the copy line again.

Two things the commands depend on:

- `K get client-scopes -q name=...` does not filter: it returns every scope. The
  `scope` helper picks the id by name. Do not replace it with `-q` and `head -1`,
  which attaches the mappers to whichever scope is listed first.
- A client created without scope lists gets the realm's default scopes and its
  service account gets `default-roles-agents`. Both clients are created with
  the lists the file has, and the default role is taken off.

Start a shell for it with `WHO=<your Keycloak username> bash -eu`, paste the
block, then `exit`. A failed step ends that shell and leaves yours open.

```bash
: "${WHO:?start this shell with WHO set to your Keycloak username}"
KC=$(kubectl get pod -n auth -l app.kubernetes.io/name=keycloak -o jsonpath='{.items[0].metadata.name}')
K() { kubectl exec -n auth "$KC" -- /opt/keycloak/bin/kcadm.sh "$@"; }
scope() { K get client-scopes -r agents --fields id,name --format csv --noquotes | awk -F, -v n="$1" '$2 == n {print $1}'; }
kubectl exec -n auth "$KC" -- sh -c '/opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD"' >/dev/null
# 1. three roles
K create roles -r agents -s name=registry-reader -s 'description=Agent registry: read agents and releases'
K create roles -r agents -s name=registry-operator -s 'description=Agent registry: read, and record releases and approvals'
K create roles -r agents -s name=registry-provisioner -s 'description=Agent registry: read the desired state and report what each cluster holds'
# 2. client scope and its two mappers: the audience, and client_id for a client's own token
K create client-scopes -r agents -s name=agent-registry -s protocol=openid-connect -s 'attributes."include.in.token.scope"=true' -s 'attributes."display.on.consent.screen"=true' -s 'attributes."consent.screen.text"=Use the agent registry'
SID=$(scope agent-registry); [ ${#SID} = 36 ]
K create client-scopes/$SID/protocol-mappers/models -r agents -b '{"name":"audience agent-registry","protocol":"openid-connect","protocolMapper":"oidc-audience-mapper","config":{"included.custom.audience":"agent-registry","access.token.claim":"true","id.token.claim":"false","introspection.token.claim":"true","userinfo.token.claim":"false"}}'
K create client-scopes/$SID/protocol-mappers/models -r agents -b '{"name":"client id","protocol":"openid-connect","protocolMapper":"oidc-usersessionmodel-note-mapper","config":{"user.session.note":"client_id","claim.name":"client_id","jsonType.label":"String","access.token.claim":"true","id.token.claim":"false","introspection.token.claim":"true","userinfo.token.claim":"false"}}'
# 3. map the three roles into the scope (the role objects need their ids)
BODY=$(for r in registry-reader registry-operator registry-provisioner; do K get roles/$r -r agents; done | tr -d '\n' | sed 's/}{/},{/g; s/^/[/; s/$/]/')
K create client-scopes/$SID/scope-mappings/realm -r agents -b "$BODY"
# 4. optional scope on agent-cli
CLI=$(K get clients -r agents -q clientId=agent-cli --fields id --format csv --noquotes); [ ${#CLI} = 36 ]
K update clients/$CLI/optional-client-scopes/$SID -r agents -b '{}'
# 5. registry-reader: Keycloak generates the secret; it goes to a private file and is not shown
K create clients -r agents -s clientId=registry-reader -s publicClient=false -s clientAuthenticatorType=client-secret -s serviceAccountsEnabled=true -s standardFlowEnabled=false -s implicitFlowEnabled=false -s directAccessGrantsEnabled=false -s fullScopeAllowed=false -s 'defaultClientScopes=["basic","roles","agent-registry"]' -s 'optionalClientScopes=[]'
RID=$(K get clients -r agents -q clientId=registry-reader --fields id --format csv --noquotes); [ ${#RID} = 36 ]
K remove-roles -r agents --uusername service-account-registry-reader --rolename default-roles-agents
K add-roles -r agents --uusername service-account-registry-reader --rolename registry-reader
(umask 077; mkdir -p ~/.config/kubani; K get clients/$RID/client-secret -r agents --fields value --format csv --noquotes > ~/.config/kubani/registry-reader.secret)
# 6. registry-provisioner-kubani (no secret; federated JWT)
K create clients -r agents -s clientId=registry-provisioner-kubani -s publicClient=false -s clientAuthenticatorType=federated-jwt -s 'attributes."jwt.credential.issuer"=kubernetes-kubani' -s 'attributes."jwt.credential.sub"=system:serviceaccount:agent-platform:registry-provisioner' -s serviceAccountsEnabled=true -s standardFlowEnabled=false -s implicitFlowEnabled=false -s directAccessGrantsEnabled=false -s fullScopeAllowed=false -s 'defaultClientScopes=["basic","roles","agent-registry"]' -s 'optionalClientScopes=[]'
K remove-roles -r agents --uusername service-account-registry-provisioner-kubani --rolename default-roles-agents
K add-roles -r agents --uusername service-account-registry-provisioner-kubani --rolename registry-provisioner
# 7. registry-operator for Al's own user
K add-roles -r agents --uusername "$WHO" --rolename registry-operator
```

Each `[ ${#...} = 36 ]` fails when a lookup did not return exactly one id. The
steps create objects, so a second run stops at the first `create`: continue
from the step that failed, with `SID` set again by its own line.

What a token then carries, as seen locally:

| Token | `aud` | Realm roles | Other |
|---|---|---|---|
| `registry-reader`, client credentials | `agent-registry` | `registry-reader` | `client_id`, no `preferred_username` |
| A person through `agent-cli` with scope `agent-registry` | `agent-registry` | the person's registry roles | `preferred_username`, no `client_id` |
| A person through `agent-cli` without the scope | none | none | refused by the registry |

The registry tells a service from a person by `client_id`. A client token
without that claim is taken for a person and is refused as a provisioner, which
is why the scope has the second mapper.

### c. Merging the realm file restarts Keycloak once

Reloader restarts the Keycloak pod when the realm ConfigMap changes. Identity
sign-in is interrupted for a short time. Merge when no agent session is starting.
The restart does not change the live realm: Keycloak imports the file only into
a database that has no realm `agents`.

Seen on 2026-11-18, when the first change merged: the new Keycloak pod was
created at 05:05:59Z and Ready at 05:06:55Z. From 05:06:13Z to 05:08:04Z
`ratelimit-config` was rewritten many times by the Python Kubernetes client,
while the Registry Controller logged its agent resync against Keycloak, and
Reloader rolled the `ratelimit` Deployment on each write (39 pods created in
those two minutes). It ended with both replicas Ready and needed nothing done.

## How to check it works

```bash
just agent state                          # platform pods and agents; both new pods Running
just agent status                         # the registry's view; needs the reader secret file of step b
curl -sS -o /dev/null -w '%{http_code}\n' https://agents.almckay.io/healthz   # 200
KUBECONFIG=/home/al/.kube/config kubectl -n agent-platform logs deploy/registry-provisioner --tail=5
```

Read the provisioner's newest lines for a recent pass. Check the line's format
against the image once it is built.

## Milestone 2: delivery (session interface, evaluator, revocations)

The contract is zetra's `platform/registry/contract/delivery.md` (sections 3, 6, 8
and 12) and `platform/session-api/contract/sessions.md`. This repository holds
the manifests. Every image is pinned by digest to what zetra's release workflow
built from `54d66d2` (run 44337682384).
The registry, the provisioner and the session interface have since moved to the
build from `d057abe` (run 44343931258), which milestone 3's feed needs.

### What was added

| | What | Where |
|---|---|---|
| A | The session interface for tenant `tenant-test`: Deployment, Service and ServiceAccount `session-api-tenant-test` (port 8080; the runner's Temporal settings, payload key and artifact store, read only), a Role that allows `get` on `agents` and `agentreleases` in `tenant-test`, and an Ingress path `/v1/tenants/tenant-test/sessions` on `agents.almckay.io` (the registry keeps `/`). A Temporal client certificate for it and its identity added to the mTLS endpoint | `workloads/session-api-tenant-test.yaml`, `apps/agents/tenant-test/session-api-rbac.yaml`, `registry-rbac.yaml`, `workloads/temporal-mtls.yaml` |
| B | The evaluator: Deployment and ServiceAccount `registry-evaluator`; token from Keycloak by client assertion, no Kubernetes RBAC | `workloads/registry-evaluator.yaml`, `registry-rbac.yaml` |
| C | `PROVISIONER_SESSION_API_URL` on the provisioner (it cancels a revoked release's sessions) | `workloads/registry-provisioner.yaml` |
| D | `REGISTRY_GITHUB_ISSUER`, `REGISTRY_GITHUB_JWKS_URL`, `REGISTRY_REPORT_AUDIENCE` on the registry | `workloads/agent-registry.yaml` |
| E | Network policies for the three paths into the session interface, its own egress, the evaluator's egress, the provisioner's egress to the session interface, the registry's egress to GitHub's keys on 443, and the matching Keycloak and Temporal ingress; each with its baseline entry | `netpol-registry.yaml`, `apps/keycloak/netpol.yaml`, `infrastructure/agent-platform-netpol/upstreams.yaml`, `infrastructure/mcp/baseline/effective-network-policies.json` |
| F | The `agentreleases.agentplatform.io` CRD with `spec.declaration`, copied from zetra | `infrastructure/agent-platform-crds/` |
| G | `infrastructure/registry/revocations/` and the feed key `revocations` | `infrastructure/registry/revocations/README.md`, `infrastructure/scripts/ops/registry_feed.py` |
| H | The agents gateway's two model-pin policies accept the engine's served name or its catalog alias (`main`, `fast`). This widens an authorization rule and was committed on its own | `apps/ai-gateway/agents/policies-auth.yaml`, `tests/test_agents_gateway_model_alias.py` |

Two facts about E:

- The Temporal endpoint (`temporal-mtls`) is an Envoy TCP proxy. It admits a
  client by the SPIFFE identity in its certificate and has no list of methods, so
  the session interface got an identity (`session-api-tenant-test`) and a network
  path, and no method list exists to extend. Changing its ConfigMap makes
  Reloader restart the endpoint once; the runner and reconciler reconnect.
- GitHub Actions runners (`arc-runners`) already reach `https://agents.almckay.io`:
  their egress policy allows the internet on 443 and Traefik on 443 and 8443, and
  CoreDNS answers every `*.almckay.io` name with Traefik's address. No rule was
  added for them.

### Steps only a person runs

Automation does none of these.

1. In the realm `agents`, create the realm role `registry-evaluator` and the
   client `registry-evaluator-kubani`, the same way as the provisioner's client
   in step b above (federated JWT, no secret, no default role). Start the shell
   as in step b.

   ```bash
   : "${KC:?set KC and the K and scope helpers as in step b}"
   K create roles -r agents -s name=registry-evaluator -s 'description=Agent registry: claim evaluations, run them through the session interface and post verdicts'
   BODY=$(K get roles/registry-evaluator -r agents | tr -d '\n' | sed 's/^/[/; s/$/]/')
   SID=$(scope agent-registry); [ ${#SID} = 36 ]
   K create client-scopes/$SID/scope-mappings/realm -r agents -b "$BODY"
   K create clients -r agents -s clientId=registry-evaluator-kubani -s publicClient=false -s clientAuthenticatorType=federated-jwt -s 'attributes."jwt.credential.issuer"=kubernetes-kubani' -s 'attributes."jwt.credential.sub"=system:serviceaccount:agent-platform:registry-evaluator' -s serviceAccountsEnabled=true -s standardFlowEnabled=false -s implicitFlowEnabled=false -s directAccessGrantsEnabled=false -s fullScopeAllowed=false -s 'defaultClientScopes=["basic","roles","agent-registry"]' -s 'optionalClientScopes=[]'
   K remove-roles -r agents --uusername service-account-registry-evaluator-kubani --rolename default-roles-agents
   K add-roles -r agents --uusername service-account-registry-evaluator-kubani --rolename registry-evaluator
   ```

   The realm file `apps/keycloak/realm-agents.json` is not changed by this
   package. Keycloak never re-imports it into an existing realm, and a change to
   it restarts Keycloak; mirror the role and the client into it in a separate
   change if a fresh import must produce them.

2. For each agent repository whose merges to `main` should become releases
   (delivery.md section 3.4):
   - a deploy key with write access, its private half held as the Actions secret
     `RELEASE_TAG_KEY`. A tag pushed with the workflow's own token starts no
     workflow, which is why a key is needed;
   - the deploy key allowed past the repository's tag ruleset, so it may create
     `<agent>/v<version>` tags;
   - two Actions variables: `AGENT_REGISTRY_URL=https://agents.almckay.io` and
     `AGENT_REGISTRY_AUDIENCE=https://agents.almckay.io`.

   Until the secret exists the tag workflow prints the tags it would have
   created and succeeds, and a release is still made by pushing the tag by hand.
   Without the two variables the release workflow publishes as before and
   reports nothing to the registry.

### Order of the roll-out

Each image below was built by zetra's release workflow from `54d66d2`, the
commit `infrastructure/agent-platform-crds/kustomization.yaml` also names.

One change carried all five steps. That was safe for two reasons. Flux applies
the `infrastructure` root, which holds the CRD, before the workloads root. And no
agent was registry-owned at the time, so nothing wrote a carried declaration
while the controller was still rolling. With a registry-owned agent present, keep
the order below across separate changes.

1. The CRD first (`infrastructure/agent-platform-crds/`): the provisioner writes
   `spec.declaration`, and the API server drops a field its schema lacks. Check
   `kubectl get crd agentreleases.agentplatform.io -o yaml` shows `declaration`
   before the next step.
2. The Registry Controller's new image (`workloads/registry-controller.yaml`). It
   compiles a release from the declaration the release carries and takes the rate
   limit from the release the Agent names as current. It must run before the
   provisioner writes a carried declaration, or the old controller would compile
   that release from the live Agent.
3. The registry and the provisioner, in one change: `agent-registry.yaml` with
   the three GitHub settings, the new feed, and `registry-provisioner.yaml` with
   `PROVISIONER_SESSION_API_URL`, both on the new images.
4. The session interface (`session-api-tenant-test.yaml`, its RBAC, its Temporal
   certificate and the endpoint's new identity, the network policies).
5. The evaluator, last; it needs the session interface up. Until the operator's
   Keycloak steps above are done it gets no token, logs a failed pass each
   interval and keeps running. It starts work on the first pass after its client
   exists.

The session runner's image needs no new pin for this milestone: the only change
to its library is an optional argument the session interface passes when it
starts a session.

### Hand-over rehearsal of 2026-11-18

Whether Flux lets go of an object, keeps it, and takes it back, tried on a
ConfigMap that carried `kustomize.toolkit.fluxcd.io/prune: disabled`:

| | Change | Result |
|---|---|---|
| R1 (#432) | ConfigMap `agent-platform/handover-rehearsal` added, created 2026-11-18T06:06:14Z, carrying `kustomize.toolkit.fluxcd.io/prune: disabled` | In the `apps` inventory (354 entries) |
| R2 (#433) | Removed from the kustomization | The object stayed; inventory 353 |
| R3 (#434) | Added back | The same object was adopted (same creation time); inventory 354 |
| R4 (#435) | Removed again | The object was kept and was absent from the inventory (353); then deleted by name |

## Milestone 4: skills with scripts

The contract is zetra's `platform/registry/contract/skills.md`. A skill is a
directory of instructions an agent's image carries; a skill may hold scripts,
and a script runs inside the agent's container only when the release requests
the effect `sandbox_execute` and its tenant grants it.

### What was added

| | What | Where |
|---|---|---|
| A | Both resource definitions, copied from zetra `589ec5c`: `spec.capabilities.effects` on the Agent and in a release's declaration, and `spec.skills` on a release | `infrastructure/agent-platform-crds/` |
| B | The Registry Controller, the registry, the session interface and the session runner (all nine places the runner's image is named) built from zetra `589ec5c`, run 44369420437. The provisioner and the evaluator did not change | `apps/agent-platform/workloads/` |
| C | `just agent approve <release>` compares `spec.skills` between the committed file and the live object, prints one line for each effect the release requests and returns the lines as `covers` | `infrastructure/scripts/ops/agent_ops/approve.py` |

One change carried A and B. Flux applies the `infrastructure` root, which holds
the definitions, before the workloads root, and no release lists a skill or
requests an effect yet. The order to keep once one does: the definitions, then
the controller, the registry and the runner, then the tenant's grant, then the
release.

None of this changes an existing release. A policy bundle gains `effects` only
when the list is not empty, so no `policySha256` moves, and a sandbox Pod gains
`AGENT_EFFECTS` only when its bundle has effects. The sandbox admission policy
does not constrain the agent container's environment, so it needs no change.

### The grant is a person's change

No tenant grants the effect. A release that requests it is not Ready, with
reason `EffectNotGranted`, which comes before `NotApproved`; `just agent
approve` refuses it because the release is not waiting solely on approval, and
no session starts for it.

To grant it, add one annotation to the tenant's Namespace in
`infrastructure/namespace-policy/agent-platform-namespaces.yaml`, in its own
pull request:

```yaml
metadata:
  annotations:
    agentplatform.io/granted-effects: sandbox_execute
```

What the grant allows, in the words every approval of the effect shows:
`effect sandbox_execute: skill scripts run inside the agent's container and can
read the session's identity token`. It applies to every agent of the tenant
whose approved release requests the effect. Removing the annotation makes those
releases not Ready at the controller's next reconcile.

`just agent register` rewrites only the signer line of that Namespace, so the
annotation stays.

### How to check it works

```bash
KUBECONFIG=/home/al/.kube/config kubectl get crd agentreleases.agentplatform.io \
  -o jsonpath='{.spec.versions[0].schema.openAPIV3Schema.properties.spec.properties.skills.maxItems}'
KUBECONFIG=/home/al/.kube/config kubectl -n tenant-test get agentreleases \
  -o custom-columns=NAME:.metadata.name,READY:.status.ready,DIGEST:.status.policyDigest
```

The first prints `16`. The second shows the same releases Ready, with the same
digests, as before the roll.
