# Human token fixture

`conformance-alice` is a synthetic local user in the `agents` realm. It has no
assigned backend, agent or administrative roles. Its generated login credential
is stored in `alice-credentials.enc.yaml`; this file is intentionally outside
Kustomization and is never installed as a cluster Secret.

The operator helper uses the existing public `agent-cli` client and its standard
PKCE S256 authorization-code login and consent flow. It does not enable password
grants on that client or change any existing user's password. User creation and the
read-only role/group check before each mint read the SOPS bootstrap administrator
credential. The check rejects any group membership or role beyond the standard
realm/account defaults, including privileges inherited through composite roles.

From the repository root, create the fixture once:

```sh
export SOPS_AGE_KEY_FILE=/home/al/git/kubani/age.key
python infrastructure/scripts/ops/conformance-human-token.py --create-user
```

Immediately before a harness run containing T5, mint its short-lived token:

```sh
export KUBECONFIG=/home/al/.kube/config
python infrastructure/scripts/ops/conformance-human-token.py \
  --output /tmp/conformance-human-token.enc.yaml --apply
```

This writes only SOPS ciphertext to disk, then decrypts it in memory to install
`agent-platform/conformance-human-token`. The script prints identity and expiry
metadata, never tokens or passwords. The harness independently verifies the
access-token signature against the issuer's public JWKS and checks the exact
subject and client. An absent, expired or mismatched token makes T5 an error.
Start the Job promptly; the realm's access-token lifetime is five minutes.

After the Job finishes, delete this temporary token Secret:

```sh
kubectl delete secret -n agent-platform conformance-human-token --ignore-not-found
```

The fixture password remains encrypted for the next run. Do not commit an
expiring access-token Secret. Requirements: Python with PyYAML and PyJWT[crypto],
`sops`, and `kubectl` when applying the token Secret.
