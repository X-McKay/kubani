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

## Steps only Al runs

Do them in this order. Run from the repository root with `KUBECONFIG=/home/al/.kube/config`.

### a. The database role password

One alphanumeric value, two Secrets (namespaces `database` and `agent-platform`),
staged outside the repository. This follows "Rotating a Credential" in
`.claude/rules/secrets.md`. The encrypt form is `(unverified form)` for these paths.

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
shred -u "$STAGE"/db/secret.enc.yaml "$STAGE"/ap/secret.enc.yaml; rm -r "$STAGE"; unset PW
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
changes with kcadm. All commands `(unverified form)` except the sign-in.

The reader client's secret is in no file of this repository. Keycloak generates
it when the client is created, and step 5 copies it to
`~/.config/kubani/registry-reader.secret`, which the operator commands read
(`just agent status`). The copy is never shown. To replace the secret, run
`K create clients/$RID/client-secret -r agents >/dev/null` and the copy line again.

```bash
KC=$(kubectl get pod -n auth -l app.kubernetes.io/name=keycloak -o jsonpath='{.items[0].metadata.name}')
K() { kubectl exec -n auth "$KC" -- /opt/keycloak/bin/kcadm.sh "$@"; }
kubectl exec -n auth "$KC" -- sh -c '/opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD"' >/dev/null
# 1. three roles
K create roles -r agents -s name=registry-reader -s 'description=Agent registry: read agents and releases'
K create roles -r agents -s name=registry-operator -s 'description=Agent registry: read, and record releases and approvals'
K create roles -r agents -s name=registry-provisioner -s 'description=Agent registry: read the desired state and report what each cluster holds'
# 2. client scope and its audience mapper
K create client-scopes -r agents -s name=agent-registry -s protocol=openid-connect -s 'attributes."include.in.token.scope"=true' -s 'attributes."display.on.consent.screen"=true' -s 'attributes."consent.screen.text"=Use the agent registry'
SID=$(K get client-scopes -r agents -q name=agent-registry --fields id --format csv --noquotes | head -1)
K create client-scopes/$SID/protocol-mappers/models -r agents -b '{"name":"audience agent-registry","protocol":"openid-connect","protocolMapper":"oidc-audience-mapper","config":{"included.custom.audience":"agent-registry","access.token.claim":"true","id.token.claim":"false","introspection.token.claim":"true"}}'
# 3. map the three roles into the scope (the role objects need their ids)
BODY=$(for r in registry-reader registry-operator registry-provisioner; do K get roles/$r -r agents; done | tr -d '\n' | sed 's/}{/},{/g; s/^/[/; s/$/]/')
K create client-scopes/$SID/scope-mappings/realm -r agents -b "$BODY"
# 4. optional scope on agent-cli
CLI=$(K get clients -r agents -q clientId=agent-cli --fields id --format csv --noquotes | head -1)
K update clients/$CLI/optional-client-scopes/$SID -r agents -b '{}'
# 5. registry-reader: Keycloak generates the secret; it goes to a private file and is not shown
K create clients -r agents -s clientId=registry-reader -s publicClient=false -s clientAuthenticatorType=client-secret -s serviceAccountsEnabled=true -s standardFlowEnabled=false -s implicitFlowEnabled=false -s directAccessGrantsEnabled=false -s fullScopeAllowed=false
RID=$(K get clients -r agents -q clientId=registry-reader --fields id --format csv --noquotes | head -1)
K update clients/$RID/default-client-scopes/$SID -r agents -b '{}'
K add-roles -r agents --uusername service-account-registry-reader --rolename registry-reader
(umask 077; mkdir -p ~/.config/kubani; K get clients/$RID/client-secret -r agents --fields value --format csv --noquotes > ~/.config/kubani/registry-reader.secret)
# 6. registry-provisioner-kubani (no secret; federated JWT)
K create clients -r agents -s clientId=registry-provisioner-kubani -s publicClient=false -s clientAuthenticatorType=federated-jwt -s 'attributes."jwt.credential.issuer"=kubernetes-kubani' -s 'attributes."jwt.credential.sub"=system:serviceaccount:agent-platform:registry-provisioner' -s serviceAccountsEnabled=true -s standardFlowEnabled=false -s implicitFlowEnabled=false -s directAccessGrantsEnabled=false -s fullScopeAllowed=false
PID=$(K get clients -r agents -q clientId=registry-provisioner-kubani --fields id --format csv --noquotes | head -1)
K update clients/$PID/default-client-scopes/$SID -r agents -b '{}'
K add-roles -r agents --uusername service-account-registry-provisioner-kubani --rolename registry-provisioner
# 7. registry-operator for Al's own user
K add-roles -r agents --uusername <al's keycloak username> --rolename registry-operator
```

A new client also gets the realm's default scopes (`profile`, `email`,
`web-origins`, `acr`). The file lists only `basic`, `roles` and `agent-registry`
for both new clients. Remove the others with `K delete clients/<id>/default-client-scopes/<scope id>
-r agents` `(unverified form)`, then compare with `K get clients/<id> -r agents`.

### c. Merging the realm file restarts Keycloak once

Reloader restarts the Keycloak pod when the realm ConfigMap changes. Identity
sign-in is interrupted for a short time. Merge when no agent session is starting.
The restart does not change the live realm: Keycloak imports the file only into
a database that has no realm `agents`.

## How to check it works

```bash
just agent state                          # platform pods and agents; both new pods Running
just agent status                         # the registry's view; needs the reader secret file of step b
curl -sS -o /dev/null -w '%{http_code}\n' https://agents.almckay.io/healthz   # 200
KUBECONFIG=/home/al/.kube/config kubectl -n agent-platform logs deploy/registry-provisioner --tail=5
```

Read the provisioner's newest lines for a recent pass. Check the line's format
against the image once it is built.
