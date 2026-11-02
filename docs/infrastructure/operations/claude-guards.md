# Claude guards on rig0

What Claude Code may do on its own when it works in this repo, and where each
boundary is enforced. Boundary last changed 2026-11-02.

## Three layers

| Layer | File | Decides |
|---|---|---|
| Pre-bash hook | `.claude/hooks/pre-bash.sh` (tests: `bash .claude/hooks/test-pre-bash.sh`) | Hard blocks. Runs in every permission mode, ignores allow rules. |
| Permission rules | `.claude/settings.json` (`permissions.allow` / `deny`) | Which commands run without a prompt; deny rules block before anything else. |
| Auto-mode classifier | `~/.claude/settings.json` on rig0 (`autoMode`) | Judgement calls in auto mode for anything the rules above don't settle. |

Remote Control sessions load the hook and settings from the **main checkout**
(`/home/al/git/kubani`), so a change takes effect in the next rig0 session after
it is merged and pulled there.

## Hook boundary

Allowed (no block): kubectl writes in `tenant-*`, `agent-platform`, `auth`,
`temporal` and any namespace not listed below; `flux reconcile` / `flux get`;
pushing release tags such as `investigator/v0.1.4`; SOPS encryption of a freshly
generated value (the rotation workflow in `.claude/rules/secrets.md`).

Blocked:

- kubectl `apply|create|delete|patch|replace|scale|edit` in `vllm`, `database`,
  `cache`, `ai-gateway`, `monitoring`, `registry`, `flux-system`, `kube-system`,
  `longhorn-system`, `kyverno` (vllm keeps its pod-delete and bench/preflight
  exceptions).
- The same verbs on ClusterPolicies, webhook configurations, CRDs, ClusterRoles
  and ClusterRoleBindings.
- `kubectl create secret|token`, `add_registry_user`, `htpasswd`, `age-keygen`,
  `cosign generate-key-pair` (credential minting).
- `systemctl daemon-reexec`, `gh variable|secret set|delete`,
  `flux uninstall|delete`, `kubectl rollout restart`, `kubectl delete namespace`,
  force push to protected branches.

The hook parses each kubectl call in a command line separately, so a read in a
guarded namespace next to the word "create" elsewhere no longer trips it.
A namespace set only inside a `-f` manifest is not seen by the hook; do not rely
on that gap.

## Auto-mode classifier

The classifier does not read `autoMode` from repo settings, so the rig0 entries
live in [`.claude/automode.rig0.json`](../../../.claude/automode.rig0.json) and
must be merged into `~/.claude/settings.json` by hand:

```bash
cd ~/git/kubani
cp ~/.claude/settings.json ~/.claude/settings.json.bak
jq -s '.[0] * .[1]' ~/.claude/settings.json.bak .claude/automode.rig0.json > ~/.claude/settings.json
claude auto-mode config | jq '.allow[-5:]'   # confirm the entries are live
```

The merge replaces any existing `autoMode` block. Both lists keep `$defaults`, so
the built-in protections (force push, data exfiltration, production deploys)
stay in force.
