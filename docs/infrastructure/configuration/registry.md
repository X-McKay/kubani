# Registry Access

This cluster uses the in-cluster Docker Distribution registry exposed at `registry.almckay.io`.

## Auth Model

- External access is protected by a Traefik `BasicAuth` middleware.
- The credential source is the SOPS-encrypted Secret at `infrastructure/gitops/infrastructure/registry/basic-auth-secret.enc.yaml`.
- The middleware and ingress wiring live next to the registry manifests in `infrastructure/gitops/infrastructure/registry/`.

This is intentionally **not** fronted by Authentik. Authentik's Traefik forward-auth pattern is a good fit for browser-backed apps, but Docker registry clients use `docker login` and the registry auth challenge flow rather than interactive SSO redirects.

## Accounts

Two registry accounts are maintained:

- `human`: for interactive `docker login`, pull, push, and manual troubleshooting
- `automation`: for CI, builders, and any non-interactive image publishing

Do not reuse these passwords outside the registry.

## Internal vs External Access

- External clients authenticate to `https://registry.almckay.io`.
- Cluster nodes continue to use the internal mirror endpoints configured in [infrastructure/ansible/files/registries.yaml](/home/al/git/kubani/infrastructure/ansible/files/registries.yaml:1), which resolve to the registry Service IP and do not depend on the external ingress path.

That separation keeps node-local image pulls stable while restricting the external ingress.

## Secret Handling

- `basic-auth-secret.enc.yaml` stores only bcrypt/htpasswd hashes; Traefik reads this one.
- `credentials-secret.enc.yaml` (`registry-credentials` in the `registry` namespace) stores the matching plaintext passwords so they can be retrieved later. Keep the two in sync whenever you rotate.
- Commit only the encrypted `*.enc.yaml` secret, never a decrypted file or inline plaintext credential.
- If a secret is rotated before it is first pushed, rewrite the local commit history so obsolete credentials never leave local history.

## Login and Storage

Use Docker's credential helper or native credential store where possible instead of keeping registry passwords in `~/.docker/config.json`.

Interactive login:

```bash
docker login registry.almckay.io -u human
```

Non-interactive login:

```bash
printf '%s\n' "$REGISTRY_PASSWORD" | docker login registry.almckay.io -u automation --password-stdin
```

## Retrieving a Password

From the repo, decrypt the credentials Secret:

```bash
SOPS_AGE_KEY_FILE=age.key sops -d infrastructure/gitops/infrastructure/registry/credentials-secret.enc.yaml
```

From the cluster:

```bash
KUBECONFIG=/home/al/.kube/config kubectl -n registry get secret registry-credentials \
  -o jsonpath='{.data.human-password}' | base64 -d
```

Keys: `human-username`, `human-password`, `automation-username`, `automation-password`.

## Rotation

Rotate either account by editing the encrypted secret in place:

```bash
sops infrastructure/gitops/infrastructure/registry/basic-auth-secret.enc.yaml
```

The `users` entry must remain a newline-delimited htpasswd list. Generate a new
line with `htpasswd -nbB <user> '<password>'`, then store the same plaintext in
`credentials-secret.enc.yaml` so the two Secrets stay in sync.

After editing:

```bash
kubectl kustomize infrastructure/gitops/infrastructure/registry >/dev/null
git add infrastructure/gitops/infrastructure/registry/basic-auth-secret.enc.yaml
git commit -m "Rotate registry basic auth credentials"
```

If the external auth policy changes later, the next step up from this design is registry-native token auth or a Harbor migration with Authentik-backed OIDC.
