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
| `rekor-signer.enc.yaml` | Rekor's ECDSA P-256 log key (SOPS) |
| `trillian-mysql-auth.enc.yaml` | MySQL root and `mysql` user passwords (SOPS) |
| `trillian-mysql-pvc.yaml` | 10 GiB Longhorn volume for both logs' Merkle trees |
| `ingress.yaml` | Traefik ingresses for Fulcio and Rekor (Let's Encrypt) |
| `netpol.yaml` | default-deny ingress plus the component paths |

## Key material

| Key | Where it lives | If lost |
|---|---|---|
| Rekor log key | SOPS, `rekor-signer.enc.yaml` | new log identity; old inclusion proofs no longer verify |
| Trillian MySQL data | `trillian-mysql-data` PVC | empty logs; every entry and SCT unprovable |
| Fulcio CA | `fulcio-system/fulcio-server-secret`, made by the `fulcio-createcerts` job | new root; images signed under the old one fail Rule 1 until re-released or the old root is kept in the bundle |
| CT log key | `ctlog-system/ctlog-secret`, made by `createctconfig` | old SCTs fail verification |

The two generated keys exist only in the cluster until they are exported.
The jobs skip when the Secret already exists, so a restored Secret is kept.

### Backing up the trust roots

After first boot, export both Secrets into SOPS from a node (never into a
file in the repo before encryption):

```bash
export KUBECONFIG=/home/al/.kube/config
for s in fulcio-system/fulcio-server-secret ctlog-system/ctlog-secret; do
  ns=${s%/*}; name=${s#*/}
  stage=$(mktemp -d)/secret.enc.yaml   # name matches the .sops.yaml rule
  kubectl get secret -n "$ns" "$name" -o yaml \
    | yq 'del(.metadata.uid, .metadata.resourceVersion, .metadata.creationTimestamp, .metadata.managedFields, .metadata.ownerReferences)' > "$stage"
  SOPS_AGE_KEY_FILE=age.key sops --encrypt "$stage" \
    > "infrastructure/gitops/infrastructure/sigstore/$name.enc.yaml"
  shred -u "$stage"
done
```

Then add both files to `kustomization.yaml` in a PR.

## Distributing the trust roots

Clients need four public values, all published in ConfigMap
`kyverno/private-sigstore` (read by Kyverno Rule 1):

| Key | Source |
|---|---|
| `fulcio-roots.pem` | `curl https://fulcio.almckay.io/api/v2/trustBundle` (the certificates, PEM) |
| `rekor.pub` | `curl https://rekor.almckay.io/api/v1/log/publicKey` |
| `ctlog.pub` | `kubectl get secret -n ctlog-system ctlog-public-key -o jsonpath='{.data.public}' \| base64 -d` |
| `rekor-url` | `https://rekor.almckay.io` |

They are committed as a plain ConfigMap after first boot, in their own PR,
not written by an in-cluster job: only GitOps writes the `kyverno` namespace,
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
| `ghcr.io/sigstore/scaffolding/createcerts@sha256:4d64dac937e26251327f91a26e188131fc8e9f75ee49bd698d662a3c1bf0d19c` | `mirror/ghcr.io/sigstore/scaffolding/createcerts` |
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
kubectl get jobs -A | grep -E 'createcerts|createtree|createctconfig|createdb'
curl -fsS https://fulcio.almckay.io/api/v2/trustBundle | jq '.chains | length'
curl -fsS https://rekor.almckay.io/api/v1/log | jq .treeSize
```
