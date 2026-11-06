# Private Sigstore

Keyless signing for agent images (governance doc, plan step 2:
https://claude.ai/artifact/QtAKe5f1FRw3FQQYWjaVKB). A release workflow in a
tenant repo gets a short-lived certificate from **Fulcio** for its GitHub
Actions OIDC identity, signs and attests the image, and records both in
**Rekor**. Kyverno Rule 1 (`../kyverno/policies/agent-image-signature.yaml`)
and the Registry Controller verify against these roots only. Nothing trusts
public Sigstore.

| Component | Namespace | Endpoint |
|---|---|---|
| Fulcio v1.9.0 | `fulcio-system` | https://fulcio.almckay.io |
| Rekor v1.5.4 | `rekor-system` | https://rekor.almckay.io |
| CT log | `ctlog-system` | in-cluster only (`http://ctlog.ctlog-system.svc/sigstorescaffolding`) |
| Trillian + MySQL | `trillian-system` | in-cluster only |

All of it runs on strix (`topology.kubani.io/role: database`). TUF and the
timestamp authority are off; see "Distributing the trust roots".

Fulcio accepts only `https://token.actions.githubusercontent.com` (type
`github-workflow`, audience `sigstore`). It will certify any GitHub workflow
that can reach it; trust is decided at verification time by the tenant's
subject pin in `../kyverno/tenant-signers.yaml`.

## Files

| File | What |
|---|---|
| `../sources/sigstore.yaml` | OCIRepository, scaffold chart 0.6.117 by digest |
| `namespaces.yaml` | four namespaces, PSA baseline, `prune: disabled` |
| `helmrelease.yaml` | values (mirror registries, issuer, signer, sizing) |
| `fulcio-server-secret.enc.yaml` | Fulcio's root CA cert and key (SOPS) |
| `rekor-signer.enc.yaml` | Rekor's ECDSA P-256 log key (SOPS) |
| `trillian-mysql-auth.enc.yaml` | MySQL root and `mysql` user passwords (SOPS) |
| `trillian-mysql-pvc.yaml` | 10 GiB Longhorn volume for both logs' Merkle trees |
| `ingress.yaml` | Traefik ingresses for Fulcio and Rekor (Let's Encrypt) |
| `netpol.yaml` | default-deny ingress plus the component paths |

## Key material

| Key | Where it lives | If lost |
|---|---|---|
| Fulcio CA (root, P-256, valid to 2031-11-01) | SOPS, `fulcio-server-secret.enc.yaml` | new root; images signed under the old one fail Rule 1 until re-released or the old root is kept in the bundle |
| Rekor log key | SOPS, `rekor-signer.enc.yaml` | new log identity; old inclusion proofs no longer verify |
| Trillian MySQL data | `trillian-mysql-data` PVC | empty logs; every entry and SCT unprovable |
| CT log key | `ctlog-system/ctlog-secret`, made by `createctconfig`; backed up in SOPS, `ctlog-secret.enc.yaml` (**not** in `kustomization.yaml`, see below) | old SCTs fail verification |

The chart's `createcerts` job is disabled. It does not skip an existing
Secret: it writes a brand-new CA on every run, and the chart re-runs it on
every install. On first boot that left Fulcio, its Secret and the CT log's
trusted roots on different CAs.

`createctconfig` keeps an existing CT log key and adds the Fulcio root that
`fulcio-server` serves at the moment it runs. So after changing the CA:
restart `fulcio-server` first (bump `kubani.io/fulcio-ca` in
`helmrelease.yaml`), then re-run `createctconfig` and restart `ctlog`
("Rotating the Fulcio CA").

The Fulcio key is stored as unencrypted PKCS#8 inside the SOPS file; Fulcio
ignores `password` for an unencrypted key, but the chart requires the field.

### Rotating the Fulcio CA

1. Mint a new root outside the repo (P-256, `CA:true, pathlen:1`,
   `keyUsage: keyCertSign, cRLSign`), write `cert`, `private` (PKCS#8),
   `public`, `password` into a staged `secret.enc.yaml`, encrypt it over
   `fulcio-server-secret.enc.yaml`, `shred -u` the plaintext.
2. Bump `kubani.io/fulcio-ca` in `helmrelease.yaml`; merge.
3. Once the new `fulcio-server` pod is Ready:
   ```bash
   export KUBECONFIG=/home/al/.kube/config
   kubectl -n ctlog-system delete job sigstore-ctlog-createctconfig --ignore-not-found
   flux reconcile helmrelease sigstore -n flux-system --force   # recreates the job
   kubectl -n ctlog-system wait --for=condition=complete job/sigstore-ctlog-createctconfig --timeout=5m
   kubectl -n ctlog-system delete pod -l app.kubernetes.io/name=ctlog
   ```
   To also drop old roots from the CT log, delete `ctlog-system/ctlog-secret`
   and `ctlog-public-key` before the reconcile. That makes a new CT log key,
   so only do it before anything relies on existing SCTs.
4. Publish the new root in `kyverno/private-sigstore`, keeping the old one
   alongside it until every image signed under it has been re-released.

### Backing up the CT log key

Export it into SOPS from a node (never into a file in the repo before
encryption):

```bash
export KUBECONFIG=/home/al/.kube/config
stage=$(mktemp -d)/secret.enc.yaml   # name matches the .sops.yaml rule
kubectl get secret -n ctlog-system ctlog-secret -o yaml \
  | yq 'del(.metadata.uid, .metadata.resourceVersion, .metadata.creationTimestamp, .metadata.managedFields, .metadata.ownerReferences)' > "$stage"
SOPS_AGE_KEY_FILE=age.key sops --encrypt "$stage" \
  > infrastructure/gitops/infrastructure/sigstore/ctlog-secret.enc.yaml
shred -u "$stage"
```

Then commit it in a PR, **without** listing it in `kustomization.yaml`:
`createctconfig` rewrites this Secret's `config` and `fulcio-0` keys on every
CA rotation, and a Flux-managed snapshot would revert that until someone
re-exported. The file is a backup, not the source of truth. Re-run the export
after each CA rotation. To restore after a loss:

```bash
SOPS_AGE_KEY_FILE=age.key sops -d infrastructure/gitops/infrastructure/sigstore/ctlog-secret.enc.yaml \
  | KUBECONFIG=/home/al/.kube/config kubectl apply -f -
```

First export: 2026-11-05 (Al, on rig0).

## Distributing the trust roots

Clients need four public values, all published in ConfigMap
`kyverno/private-sigstore` (read by Kyverno Rule 1):

| Key | Source |
|---|---|
| `fulcio-roots.pem` | `curl https://fulcio.almckay.io/api/v2/trustBundle` (the certificates, PEM) |
| `rekor.pub` | `curl https://rekor.almckay.io/api/v1/log/publicKey` |
| `ctlog.pub` | `kubectl get secret -n ctlog-system ctlog-public-key -o jsonpath='{.data.public}' \| base64 -d` |
| `rekor-url` | `https://rekor.almckay.io` |

They are committed as a plain ConfigMap,
`../kyverno/private-sigstore.yaml`, not written by an in-cluster job: only GitOps writes the `kyverno` namespace,
and a CA change should be a reviewed diff. The same values make the
`trusted_root.json` for the Registry Controller's keyless profile and for
`cosign --trusted-root` in release workflows.

## Images

Every image is pulled from `registry.almckay.io/mirror/<host>/<path>` at the
chart's digest. Mirror them (same digest, so trust is unchanged) before the
first reconcile and on every chart bump:

| Upstream | Mirror path |
|---|---|
| `ghcr.io/sigstore/fulcio:v1.9.0@sha256:2de0226c5f82008091a4c9de4f7b84b081f2bff1d13530d7f7357a6ba19d3835` | `mirror/ghcr.io/sigstore/fulcio` |
| `ghcr.io/sigstore/rekor/rekor-server:v1.5.4@sha256:100d793d68d0e1ba9fea7df8503304cef1ca736c891bd074fcae3d450dd64169` | `mirror/ghcr.io/sigstore/rekor/rekor-server` |
| `ghcr.io/sigstore/scaffolding/createctconfig:v0.7.33@sha256:e591f98e3899aa86772a2b033d4a0353ba99db2d17d684970731fb6f829456b6` | `mirror/ghcr.io/sigstore/scaffolding/createctconfig` |
| `ghcr.io/sigstore/scaffolding/createdb@sha256:16673c1099a5a0d3c2f2addc5cd57708681f03c650a39b08d62260655f304637` | `mirror/ghcr.io/sigstore/scaffolding/createdb` |
| `ghcr.io/sigstore/scaffolding/createtree:v0.7.33@sha256:4c845ced03d86217e61652659d0b9718771eb15265d8251173c94c388f0d0aad` | `mirror/ghcr.io/sigstore/scaffolding/createtree` |
| `ghcr.io/sigstore/scaffolding/ct_server:v0.7.33@sha256:24293fa1ed5083412e2a8ad4a97c6c2318b3f414fea64c054d0b5b95e39e3233` | `mirror/ghcr.io/sigstore/scaffolding/ct_server` |
| `ghcr.io/sigstore/scaffolding/trillian_log_server@sha256:32ee491f4d005eac128203e52e5057f9cf6d8901c5df790619a9da24c000bd97` | `mirror/ghcr.io/sigstore/scaffolding/trillian_log_server` |
| `ghcr.io/sigstore/scaffolding/trillian_log_signer@sha256:3d0152303816e88374c62c0faaf5179cb9c3a867fb5e3547e83c6d92f05c33dc` | `mirror/ghcr.io/sigstore/scaffolding/trillian_log_signer` |
| `gcr.io/trillian-opensource-ci/db_server@sha256:2a685a38dd0129cceb646c232d285383f614c7e6fa51ff8f512aef78e4298461` | `mirror/gcr.io/trillian-opensource-ci/db_server` |
| `docker.io/library/redis@sha256:148bb5411c184abd288d9aaed139c98123eeb8824c5d3fce03cf721db58066d8` | `mirror/docker.io/redis` |
| `docker.io/library/busybox@sha256:fd7dc98638c8e305f4dc34e979f1c0fdfdcaeb0fbf8fcff77ae834b6da3d7e6e` | `mirror/docker.io/busybox` |
| `docker.io/curlimages/curl:8.17.0@sha256:935d9100e9ba842cdb060de42472c7ca90cfe9a7c96e4dacb55e79e560b3ff40` | `mirror/docker.io/curlimages/curl` |

The chart names Docker Hub official images without `library/`, so their
mirror paths have none either. Copy with tags where the chart uses one, e.g.
`crane copy <upstream> registry.almckay.io/mirror/ghcr.io/sigstore/fulcio:v1.9.0`;
digest-only refs need any tag (or `crane copy` by digest) so the manifest is
kept.

## Verify

```bash
export KUBECONFIG=/home/al/.kube/config
kubectl get pods -n fulcio-system -n ctlog-system   # repeat per namespace
kubectl get jobs -A | grep -E 'createtree|createctconfig|createdb'
curl -fsS https://fulcio.almckay.io/api/v2/trustBundle | jq '.chains | length'
curl -fsS https://rekor.almckay.io/api/v1/log | jq .treeSize
```
