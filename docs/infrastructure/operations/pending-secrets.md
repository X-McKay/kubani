# Pending secrets for the Phase 0/3 integrations

Four integrations are wired in Git but wait for credentials that only an
operator holding `age.key` can mint. The manifests reference Secrets that do
not exist yet, so the references stay commented in the kustomizations and
these workloads keep their previous behaviour until the files land:

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
