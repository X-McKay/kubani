# Starbase Phase 3 inactive-bundle evidence

Date: 2026-08-24

Scope: repository-only implementation of accepted Starbase ADR 0008

Result: ready for pull-request review as inactive desired-state evidence; not
ready or authorized for Flux activation

## Authority and boundaries

Al McKay accepted Starbase ADR 0008 on 2026-08-24 and authorized continuation
of its repository implementation. This change does not provision the dedicated
GitHub App, add Starbase to a Flux Kustomization, merge the branch, reconcile
Flux, create Kubernetes objects, execute migrations, deliver secrets, or mutate
Kubani.

The work used an isolated worktree based on Kubani
`90f5725d37a4afd839a0b210c62ae449af82e661`. The existing main checkout's
uncommitted Temporal NetworkPolicy change was not modified.

## Content-bound inputs

- Manifest evidence repository: `X-McKay/Starbase`
- Manifest evidence revision: `c966518b8c82e755664faa9c37bfd5854089f8a2`
- Manifest path:
  `docs/evidence/releases/0.1.0-rc.2/release-manifest.json`
- Manifest SHA-256:
  `8c2fbdeab2d6b853fbeee57cf027f5169e44481647e93b79eb089ff717bac738`
- Manifest-derived source revision:
  `ab25087ec856be89d2e00f69f7d230d71cf5301a`
- Product-owned base: `deploy/kubani-base`
- Target platform: `linux/amd64`

The renderer accepts distinct clean Git checkouts for evidence and source,
rejects revision or repository substitution, rejects dirty source, and derives
the source revision and all six images only from the verified manifest.

## Generated result

The deterministic result contains 28 objects and has rendered SHA-256
`1898db68c632f0df0ac336c62e54ea5b517c0b6d04dc4d151d9b3fc5eb3c6f82`.
It:

- pins the six accepted `0.1.0-rc.2` images by digest;
- removes every all-zero image placeholder;
- renders the GitHub connector at zero replicas;
- includes no GitHub HTTPS or catch-all egress;
- includes no Ingress or Secret object;
- preserves dedicated ServiceAccounts and disabled automatic token mounting;
- bounds inventory to at most 48 objects and the three Starbase namespaces;
- gives each migration Job a migration-content-derived name; and
- retains one-day Job cleanup, active deadlines, and rendered-not-authorized
  annotations.

The Kubani apps aggregate does not reference the Starbase directory. The lock
records that expected inactive state, the exact object inventory, input and
output digests, renderer digest, and the supported `darwin-arm64` toolchain:
Python 3.12.13, PyYAML 6.0.3, kubectl v1.31.14, and Kustomize v5.4.2 with
binary or module SHA-256 identities.

## Test and validation evidence

The behavioral test began red because the promotion module did not exist. The
implemented suite now has 15 passing tests covering deterministic transformation,
source and digest substitution, dirty source, hand edits, object growth,
unexpected or mutable images, Secret objects, automatic token mounting,
restricted workload security, GitHub HTTPS and broad-selector egress, unknown
input keys, migration-name fencing, and Job retention.

Executed successfully:

- Python compilation and `unittest` discovery: 15 tests passed.
- Exact generate followed by verify against the two clean Starbase checkouts.
- `just validate-local` with the locked disposable Python environment and CI
  hook mode: inventory, SOPS ciphertext checks, full-tree plaintext-Secret
  check, all four existing Kustomize builds, promotion tests, and hook policy
  passed.
- The configured changed-file pre-commit suite passed after adding the public
  revision hashes to `.secrets.baseline`: YAML, large-file, merge-conflict,
  private-key, yamllint, Gitleaks, detect-secrets, and plaintext-Secret checks.
- Actionlint passed for the changed `validate.yml` workflow.
- Trivy v0.74.0 reported zero HIGH or CRITICAL Kubernetes
  misconfigurations in the generated bundle and zero repository secret
  findings.
- `git diff --check` passed.
- Exact verification completed locally in 0.27 seconds real time.

The repository's unchanged `audit.yml` produces an existing standalone
Actionlint warning for its custom `sparky` self-hosted runner label when no
Actionlint runner-label configuration is supplied. The changed workflow passes.
A client-only `kubectl create --dry-run` attempt was not accepted as evidence
because kubectl still attempted API discovery against an intentionally empty
kubeconfig. No server-side dry run was performed.

## Kubani pre/post observation

Both read-only checkpoints used context `default` with the existing protected
administrative recovery identity. No credential value was read or retained.

Before implementation, API and etcd readiness passed; all four nodes were Ready
and schedulable; active pods were Running and ready; and all Flux resources were
Ready at `main@sha1:90f5725d37a4afd839a0b210c62ae449af82e661`.
`asio` used 5% CPU and 29% memory, while `strix` used 5% CPU and 21% memory.

At `2026-08-24T20:40:37Z`, the same API, node, workload, and Flux checks passed
at the unchanged revision. `asio` used 3% CPU and 29% memory; `strix` used 4%
CPU and 21% memory. No non-Running active pod was observed. This is a fresh
point-in-time health check, not representative load or rollout evidence.

## Remaining gates

- Record and checksum-verify the supported Linux CI rendering toolchain.
- Separately authorize and provision the read-only Starbase GitHub App.
- Implement the trusted default-branch acquisition job and prove token
  isolation, revocation, fork failure, and credential-free render comparison.
- Review and merge this inactive bundle without adding it to Flux.
- Close Authentik, PostgreSQL roles and backup/restore, secret delivery,
  Kubernetes/API/issuer/network reachability, external observation,
  representative capacity, and recovery gates.
- Exercise migration Job replacement behavior in a disposable Kubernetes
  target before either Job is applied to Kubani.
- Obtain a separate exact-revision activation decision before any Flux change.

Before activation, rollback is deletion or revert of these inactive repository
files. There is no cluster rollback because this change creates no live state.
