# Secrets for the Phase 0/3 integrations

**Landed 2026-10-01** (PRs #188, #198, #199, #200): all five Secrets exist and
the four integrations below are live. This page stays as the rotation
procedure. Two lessons from the first run: ntfy needs bcrypt cost 10 or
higher (the script enforces it), and an OAuth2 provider created by an
Authentik blueprint needs an explicit `grant_types` list.

Four integrations are wired in Git and need credentials that only an
operator holding `age.key` can mint:

| Secret | Namespace | Used by | Effect once present |
|---|---|---|---|
| `ntfy-auth` | monitoring | ntfy (`NTFY_AUTH_*`) | ntfy requires login: user `al` (phone app, admin) and user `alertmanager` with a publish-only token; `auth-default-access` becomes deny-all |
| `alertmanager-ntfy-config` | monitoring | the Alertmanager bridge | the bridge config moves from a ConfigMap to a Secret so it can carry the ntfy token |
| `qdrant-metrics-credentials` | monitoring | Prometheus `qdrant` job | `/metrics` scraped with a read-only key as a Bearer token |
| `qdrant-readonly-credentials` | database | Qdrant | `QDRANT__SERVICE__READ_ONLY_API_KEY` (same value as above) |
| `grafana-oidc-client` | auth | Authentik blueprint (`!Env`) | the `Kubani Grafana` OAuth2 provider and `grafana` application exist, so Grafana's Authentik login stops answering 400 |

## Procedure (on rig0, where `age.key` lives)

```bash
cd ~/git/kubani && git pull
bash infrastructure/scripts/ops/make_integration_secrets.sh ~/kubani-secrets-out
```

The script generates the values (openssl), hashes the ntfy passwords with
bcrypt (via `docker run httpd:2.4-alpine htpasswd`), copies the Grafana client
id/secret out of `apps/monitoring/oauth-secret.enc.yaml`, and SOPS-encrypts
five files into the output directory. Plaintext exists only in a `mktemp`
directory that is shredded on exit; nothing is printed.

Then, from a branch:

```bash
cp ~/kubani-secrets-out/monitoring-ntfy-auth.enc.yaml                infrastructure/gitops/apps/monitoring/ntfy-auth.enc.yaml
cp ~/kubani-secrets-out/monitoring-alertmanager-ntfy-config.enc.yaml infrastructure/gitops/apps/monitoring/alertmanager-ntfy-config.enc.yaml
cp ~/kubani-secrets-out/monitoring-qdrant-metrics.enc.yaml           infrastructure/gitops/apps/monitoring/qdrant-metrics.enc.yaml
cp ~/kubani-secrets-out/database-qdrant-readonly.enc.yaml            infrastructure/gitops/infrastructure/qdrant/readonly-secret.enc.yaml
cp ~/kubani-secrets-out/auth-grafana-oidc-client.enc.yaml            infrastructure/gitops/apps/authentik/grafana-oidc-client.enc.yaml
```

Uncomment the five `UNCOMMENT once the SOPS file exists` lines in the three
kustomizations, run `just validate-local`, commit, open the PR, merge, and
`just flux-reconcile`. Afterwards:

- The phone app signs in to `https://ntfy.almckay.io` as `al` with the
  password from `sops -d .../ntfy-auth.enc.yaml` (key `al-password`) and
  subscribes to `kubani-alerts` and `kubani-watchdog`.
- `just alerts` still works; the Watchdog alert should arrive within a
  minute of the bridge restarting (reloader rolls it on the Secret change).
- Prometheus target `qdrant` goes `up`; Qdrant restarts once (new env).
- Grafana → "Sign in with authentik" completes; add the rotation date to the
  auth inventory in `configuration/authentik-app-access.md`.

Rotation follows `.claude/rules/secrets.md` step 6: re-run the script, replace
the files, and let reloader restart the consumers.

`ONLY_NTFY=1 bash infrastructure/scripts/ops/make_integration_secrets.sh ~/kubani-secrets-out`
re-mints only the two ntfy-related files (user hashes and the shared publish
token) without rotating the Qdrant key. ntfy requires bcrypt cost 10 or
higher; the script enforces it.

## Agent Runtime Platform

Minted 2026-10-31 (random values, encrypted to the `.sops.yaml` age
recipient, plaintext shredded): every row below except
`keycloak-authentik-broker` (needs the Authentik application, step 2) and the
two `*-temporal-tls` Secrets (issued by the Temporal CA, step 5). The
bootstrap admin username is `bootstrap-admin`. `llm-api-key` is committed but
not yet listed in `apps/vllm/kustomization.yaml`; the vLLM `--api-key` change
below lists it.

Everything below belongs to the staged directories `apps/keycloak/`,
`apps/agent-platform/` and `apps/ai-gateway/agents/` (stage order in
`docs/infrastructure/configuration/agent-runtime-platform.md`). Each `.enc.yaml`
line in those kustomizations is commented out; uncomment it in the same
commit that adds the SOPS file. Generate values on rig0, write plaintext
outside the repo, encrypt, shred (`.claude/rules/secrets.md`, "Rotating a
Credential"). Values are alphanumeric unless stated (base64 keys use the
standard alphabet).

| Secret | Namespace | Keys | File | Spec | Used by |
|---|---|---|---|---|---|
| `keycloak-db` | auth | `username` (`keycloak`), `password` | `apps/keycloak/keycloak-db.enc.yaml` | 7 | Keycloak `KC_DB_*` |
| `keycloak-bootstrap-admin` | auth | `username`, `password` | `apps/keycloak/keycloak-bootstrap-admin.enc.yaml` | 7.1 | temporary master-realm admin; replace with a permanent admin, then delete that user |
| `keycloak-client-secrets` | auth | `agent-gateway`, `agent-policy-service`, `registry-controller` | `apps/keycloak/keycloak-client-secrets.enc.yaml` | 7.5 | realm import placeholders `${KC_CLIENT_SECRET_*}`; each value equals the matching `idp-client-*` Secret below |
| `keycloak-authentik-broker` | auth | `client-id`, `client-secret` | `apps/keycloak/keycloak-authentik-broker.enc.yaml` | 7.6 | realm `authentik` identity provider (human login brokered to Authentik) |
| `idp-client-agent-gateway` | ai-gateway | `client_secret` | `apps/ai-gateway/agents/idp-client-agent-gateway.enc.yaml` | 7.5, 8.11 | optional native exchange on the agents gateway; same value as `keycloak-client-secrets/agent-gateway` |
| `idp-client-agent-policy-service` | agent-platform | `client_secret` | `apps/agent-platform/idp-client-agent-policy-service.enc.yaml` | 7.5, 9.1 | APS (`IDP_CLIENT_SECRET_FILE`) |
| `idp-client-registry-controller` | agent-platform | `client_secret` | `apps/agent-platform/idp-client-registry-controller.enc.yaml` | 7.5 | Registry Controller (`REGISTRY_KEYCLOAK_SECRET_FILE`) |
| `aps-vault-key` | agent-platform | `key`: 32 random bytes, base64 (`openssl rand -base64 32`) | `apps/agent-platform/aps-vault-key.enc.yaml` | 9.1, 9.7 | APS grant vault (AES-256-GCM) |
| `aps-redis` | agent-platform | `password` | `apps/agent-platform/aps-redis.enc.yaml` | 9.1 | aps-redis, APS, ratelimit |
| `backend-cred-llm-main` | ai-gateway | `Authorization`: `Bearer <key>`, key = 32 random bytes base64url | `apps/ai-gateway/agents/backend-cred-llm-main.enc.yaml` | 4.5 | `agents-llm-main` backend |
| `backend-cred-llm-fast` | ai-gateway | `Authorization`: `Bearer <key>` | `apps/ai-gateway/agents/backend-cred-llm-fast.enc.yaml` | 4.5 | `agents-llm-fast` backend |
| `llm-api-key` | vllm | `VLLM_API_KEY_MAIN`, `VLLM_API_KEY_FAST` (the two keys above, without `Bearer `) | `apps/vllm/llm-api-key.enc.yaml` | 4.5 | vLLM `--api-key` (pending change below) |
| `session-runner-temporal-tls` | agent-platform | `tls.crt`, `tls.key`, `ca.crt` | `apps/agent-platform/session-runner-temporal-tls.enc.yaml` | 10.6 | runner mTLS to Temporal |
| `cleanup-reconciler-temporal-tls` | agent-platform | `tls.crt`, `tls.key`, `ca.crt` | `apps/agent-platform/cleanup-reconciler-temporal-tls.enc.yaml` | 10.7 | reconciler mTLS to Temporal |
| `session-payload-key-tenant-test` | agent-platform | `key`: 32 random bytes, base64 | `apps/agent-platform/session-payload-key-tenant-test.enc.yaml` | 10.6, 13.9 | runner and reconciler payload codec for tenant-test (one Secret per tenant) |

The spec's `backend-cred-<saas>` for GitHub is not a new Secret: the agents
gateway's `agents-mcp-github` backend reuses `ai-gateway/github-mcp-pat`.

### Operator steps that are not Secrets

1. **Keycloak database** (before stage KC1), as `postgres` on the
   `database/postgresql` instance, password from `keycloak-db`:
   ```sql
   CREATE ROLE keycloak LOGIN PASSWORD '<from keycloak-db>';
   CREATE DATABASE keycloak OWNER keycloak;
   ```
   Run it through `kubectl exec` with the password read from `sops -d` into a
   shell variable, never into a file in the repo.
2. **Authentik application for the broker** (before KC1): an OAuth2 provider
   and application with slug `keycloak-agents`, confidential, redirect URI
   `https://idp.almckay.io/realms/agents/broker/authentik/endpoint`,
   `grant_types` listed explicitly (lesson above), scopes openid/profile/email.
   Declare it as a blueprint in `apps/authentik/blueprints-configmap.yaml`
   reading `!Env` values from `keycloak-authentik-broker` (same pattern as
   Grafana), and add the `idp.almckay.io` row to the auth inventory in
   `docs/infrastructure/configuration/authentik-app-access.md`.
3. **Internal CA trust**: DONE 2026-10-31. The public root certificate
   (SHA-256 24:54:62:F3:...:0C:F5:0A) is in `apps/agent-platform/ca-bundle.yaml`.
   Redo this step only if cert-manager re-issues `agents-internal-root-ca`.
4. **cosign public key** (before stage AP4; superseded by keyless signing via
   the private Sigstore, see agent-runtime-platform.md "Keyless signing"): `cosign generate-key-pair`
   outside the repo; the private key goes to the build pipeline's secret
   store, never here; paste `cosign.pub` into
   `apps/agent-platform/registry-controller.yaml` (ConfigMap
   `registry-cosign-public-key`).
5. **Temporal** (before AP5): namespace `agents-tenant-test`, mTLS on the
   frontend issuing the two client certificates above, and the cleanup
   Schedule (command in `apps/agent-platform/cleanup-reconciler.yaml`).
6. **K3s anonymous discovery** (before 7.8 can pass): if Keycloak gets 401
   from `https://kubernetes.default.svc.cluster.local/openid/v1/jwks`, the
   API server runs with `--anonymous-auth=false`; see
   `apps/keycloak/deployment.yaml` for the two options.

### Pending change: vLLM `--api-key` (spec 4.5, 8.4)

Not applied; `apps/vllm/` is unchanged. The patch, for its own reviewed stage:

- `apps/vllm/deployment.yaml` (main engine): add env `VLLM_API_KEY` from
  Secret `llm-api-key` key `VLLM_API_KEY_MAIN`, and `--api-key "$VLLM_API_KEY"`
  to the `vllm serve` arguments. Same for `fast-model-deployment.yaml` with
  `VLLM_API_KEY_FAST`. (Spec 4.5 names namespace `llm`; here it is `vllm`.)
- vLLM then answers 401 to any `/v1/*` request without that bearer. Today
  the gpu-brokers forward unauthenticated requests from the live `ai`
  Gateway (`models.yaml`), `llm*.almckay.io`, the benchmark Job and the
  broker's own `/v1` calls, so the same commit must: make every `ai`
  backend in `../models.yaml` present the key (`policies.auth.secretRef`,
  a change to the live gateway), confirm the brokers forward the
  `Authorization` header to the engine unchanged (and that their own
  wake/health calls use non-`/v1` paths or the key), and update every
  other direct consumer.
- Rotation (spec 14.2): vLLM reads `--api-key` only at start, so restart the
  engine in a maintenance window with no active sessions (delete the pod;
  never `rollout restart`, see `.claude/rules/kubernetes.md`), then update
  the gateway Secrets, which the gateway reloads without restart.
