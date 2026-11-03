# Claude guards on rig0

What Claude Code may do on its own when it works in this repo, and where each
boundary is enforced. Boundary last changed 2026-11-02.

## Three layers

| Layer | File | Decides |
|---|---|---|
| Pre-bash hook | `.claude/hooks/pre-bash.sh` (tests: `bash .claude/hooks/test-pre-bash.sh`) | Hard blocks. Runs in every permission mode, ignores allow rules. |
| Permission rules | `.claude/settings.json` (`permissions.allow` / `deny`) | Which commands run without a prompt; deny rules block before anything else. |
| Auto-mode classifier | `/etc/claude-code/managed-settings.d/50-kubani-automode.json` on rig0 (`autoMode`) | Judgement calls in auto mode for anything the rules above don't settle. |

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

The classifier reads `autoMode` only from user settings, managed settings or
`--settings`, never from repo settings. On rig0 the entries live in a
root-owned managed-settings drop-in, because the Claude desktop app rewrote
`~/.claude/settings.json` on 2026-11-02 and dropped a hand-merged `autoMode`
block. A file under `/etc/claude-code/` is not touched by the app.

[`.claude/automode.rig0.json`](../../../.claude/automode.rig0.json) is the drop-in. It also sets
`parentSettingsBehavior: "merge"`: without it, the presence of any managed file
makes Claude Code ignore the settings the desktop app passes to the sessions it
launches.

Install or update it on rig0 (and after any change to that file) with
`bash infrastructure/scripts/ops/install_claude_guards.sh`, which runs these
steps with their checks and refuses a checkout with uncommitted changes:

```bash
cd ~/git/kubani
git status --short && git checkout main && git pull --ff-only
jq -e . .claude/automode.rig0.json >/dev/null \
  && sudo install -D -m 0644 .claude/automode.rig0.json \
       /etc/claude-code/managed-settings.d/50-kubani-automode.json
claude auto-mode config | jq '.allow[-5:]'   # the homelab entries are listed
```

Validate before installing: a managed file that is not valid JSON stops
Claude Code from starting. In a session, `/status` shows the source as
`Managed settings (drop-ins)`. Remove any copy of the block from
`~/.claude/settings.json` so the rules have one home.

Both lists keep `$defaults`, so the built-in protections (force push, data
exfiltration, production deploys) stay in force.

## The main checkout must be on main

Remote Control sessions run the hook and settings from whatever branch
`/home/al/git/kubani` has checked out. If it sits on a feature branch, merged
guard changes do not apply. The `git checkout main && git pull` above covers it.
