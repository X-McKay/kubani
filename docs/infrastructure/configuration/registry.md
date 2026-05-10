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

- Only bcrypt/htpasswd hashes are stored in Git.
- Plaintext passwords must exist only long enough to distribute them to the intended user or automation system.
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

## Rotation

Rotate either account by editing the encrypted secret in place:

```bash
sops infrastructure/gitops/infrastructure/registry/basic-auth-secret.enc.yaml
```

The `users` entry must remain a newline-delimited htpasswd list.

After editing:

```bash
kubectl kustomize infrastructure/gitops/infrastructure/registry >/dev/null
git add infrastructure/gitops/infrastructure/registry/basic-auth-secret.enc.yaml
git commit -m "Rotate registry basic auth credentials"
```

If the external auth policy changes later, the next step up from this design is registry-native token auth or a Harbor migration with Authentik-backed OIDC.
