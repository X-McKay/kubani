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
