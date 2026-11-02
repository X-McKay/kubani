#!/bin/bash
# Pre-bash hook - validates commands before execution
# Warns about potentially dangerous operations

# Get command from stdin with timeout to prevent hanging
# Claude Code sends JSON via stdin with tool_input.command
# GNU `timeout` is absent on macOS; without this guard the stdin read collapsed
# to '{}' and the hook exited before checking anything. Fall back to running
# the command directly: the harness enforces its own hook timeout anyway.
with_timeout() {
    if command -v timeout >/dev/null 2>&1; then timeout "$@"; else shift; "$@"; fi
}
INPUT=$(with_timeout 1s cat 2>/dev/null || echo '{}')

# Parse command from JSON - read input once, no seeking
COMMAND=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    print(data.get('tool_input', {}).get('command', ''))
except:
    print('')
" 2>/dev/null)

# If no command from JSON, exit
if [ -z "$COMMAND" ]; then
    exit 0
fi

# Define dangerous patterns
DANGEROUS_PATTERNS=(
    "rm -rf /"
    "rm -rf /*"
    "rm -rf ~"
    "> /dev/sda"
    "mkfs."
    "dd if="
    ":(){:|:&};:"
    "chmod -R 777 /"
    "kubectl delete namespace"
    "kubectl delete --all"
    "DROP DATABASE"
    "DROP TABLE"
)

# Check for dangerous patterns
for pattern in "${DANGEROUS_PATTERNS[@]}"; do
    if [[ "$COMMAND" == *"$pattern"* ]]; then
        echo "⚠️  Potentially dangerous command detected: $pattern"
        echo "Command: $COMMAND"
        # Return exit code 2 to block the command
        exit 2
    fi
done

# ============================================================================
# PROTECTED BRANCH CHECKS - Block force push to main/master
# ============================================================================
PROTECTED_BRANCHES=("main" "master" "production" "release")

# Check for git push --force variants
# Require the force flag to appear as a standalone token (leading whitespace,
# trailing whitespace/=/end-of-string) so branch names containing "-f" (e.g.
# "feature/infra-repo-focus") don't trigger a false positive.
# Only the `git push ...` segment is inspected (up to the next ; && || |):
# a `helm template --values x -f y` or `rm -f` earlier in the same command
# line is not a force push, and "origin/main" in an unrelated `git fetch`
# is not a protected-branch target (false positive seen 2026-10-01).
PUSH_SEG=$(printf '%s' "$COMMAND" | grep -oE 'git[[:space:]]+push([^;&|]*)' | head -1 || true)
if [[ -n "$PUSH_SEG" ]] && \
   [[ "$PUSH_SEG" =~ [[:space:]](-f|--force|--force-with-lease)([[:space:]]|=|$) ]]; then
    # Extract the remote and branch if specified
    for branch in "${PROTECTED_BRANCHES[@]}"; do
        # Check if pushing to a protected branch
        if [[ "$PUSH_SEG" =~ (origin[[:space:]]+$branch|$branch:|/$branch) ]]; then
            echo "{\"decision\": \"block\", \"reason\": \"Force push to protected branch '$branch' is blocked. This requires manual intervention outside of Claude Code.\"}"
            exit 2
        fi
    done

    # If pushing to current branch, check what branch we're on
    CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
    for branch in "${PROTECTED_BRANCHES[@]}"; do
        if [ "$CURRENT_BRANCH" = "$branch" ]; then
            echo "{\"decision\": \"block\", \"reason\": \"Force push from protected branch '$branch' is blocked. Switch to a feature branch or use regular push.\"}"
            exit 2
        fi
    done

    # Warn about force push but allow on non-protected branches
    echo "⚠️  Force push detected on non-protected branch - proceeding with caution" >&2
fi

# ============================================================================
# ROLLOUT RESTART - never on Flux-managed workloads
# ============================================================================
# Flux reverts the restartedAt annotation within its reconcile interval
# (<=10 min). On 2026-09-25 that killed a replacement vllm pod mid-weight-load
# and doubled a 5-minute outage. Recovery is `kubectl delete pod`, which
# leaves the spec Flux owns untouched. See
# docs/troubleshooting/vllm-main-engine-hang-gb10.md and
# .claude/rules/kubernetes.md.
if [[ "$COMMAND" =~ kubectl[[:space:]]+.*rollout[[:space:]]+restart ]]; then
    echo '{"decision": "block", "reason": "kubectl rollout restart is never safe on a Flux-managed workload: Flux reverts the restartedAt annotation within its reconcile interval, which doubled the 2026-09-25 vllm outage. Use `kubectl delete pod -n <ns> -l <selector>` instead (see docs/troubleshooting/vllm-main-engine-hang-gb10.md), or `just inference-restart main|fast`."}'
    exit 2
fi

# ============================================================================
# OPERATIONAL NAMESPACE GUARD - kubectl apply/create/delete/patch/replace/
# scale/edit against core operational namespaces is blocked unless it matches
# the documented recovery/bench/preflight allowlist.
#
# Boundary (2026-11-02, see docs/infrastructure/operations/claude-guards.md):
#   guarded   core shared services and the GitOps/admission control plane below
#   allowed   tenant-*, agent-platform, auth, temporal and every other
#             namespace: platform workloads Claude deploys and tests directly
# ============================================================================
OPERATIONAL_NAMESPACES="vllm database cache ai-gateway monitoring registry flux-system kube-system longhorn-system kyverno"
MUTATING_VERBS="apply create delete patch replace scale edit"
# Cluster-scoped kinds that change admission, CRDs or RBAC for everyone.
GUARDED_CLUSTER_KINDS="clusterpolicy clusterpolicies cpol validatingwebhookconfiguration validatingwebhookconfigurations mutatingwebhookconfiguration mutatingwebhookconfigurations crd crds customresourcedefinition customresourcedefinitions clusterrole clusterroles clusterrolebinding clusterrolebindings"

# Parse every kubectl invocation separately (split on ; && || | and newlines)
# into "verb|namespace|kind". Matching the verb and the namespace
# against the whole command line used to block e.g.
# `kubectl get secret -n flux-system ... && echo created`, because "create"
# appeared anywhere after "kubectl" (false positive seen 2026-11-01).
KUBECTL_CALLS=$(printf '%s' "$COMMAND" | python3 -c '
import re, sys
VALUE_FLAGS = {"-n", "--namespace", "--context", "--kubeconfig", "--cluster",
               "--user", "-s", "--server", "--as", "--token", "-l",
               "--selector", "-f", "--filename", "-o", "--output", "-p",
               "--patch", "--type", "-c", "--container"}
for seg in re.split(r"\n|;|&&|\|\||\|", sys.stdin.read()):
    m = re.search(r"(?:^|[\s/(])kubectl\s+(.*)", seg)
    if not m:
        continue
    toks = [t.strip("\"'\''") for t in m.group(1).split()]
    ns, pos, i = "", [], 0
    while i < len(toks):
        t = toks[i]
        if t in ("-n", "--namespace"):
            ns = toks[i + 1] if i + 1 < len(toks) else ""
            i += 2
            continue
        mm = re.match(r"^(?:--namespace=|-n=?)([A-Za-z0-9_-]+)$", t)
        if mm:
            ns = mm.group(1)
        elif t in VALUE_FLAGS:
            i += 2
            continue
        elif not t.startswith("-"):
            pos.append(t)
        i += 1
    verb = pos[0].lower() if pos else ""
    kind = pos[1].lower().split("/")[0] if len(pos) > 1 else ""
    print("%s|%s|%s" % (verb, ns, kind))
' 2>/dev/null)

while IFS="|" read -r VERB NS KIND; do
    [[ -z "$VERB" ]] && continue
    [[ " $MUTATING_VERBS " == *" $VERB "* ]] || continue

    # Credential minting outside SOPS/GitOps: plaintext Secrets and tokens.
    if [[ "$VERB" == "create" ]] && [[ "$KIND" == "secret" || "$KIND" == "token" ]]; then
        echo "{\"decision\": \"block\", \"reason\": \"kubectl create $KIND mints a credential outside SOPS/GitOps. Commit a SOPS-encrypted Secret instead (.claude/rules/secrets.md), or hand Al the command.\"}"
        exit 2
    fi

    # Admission, CRD and RBAC objects are cluster-wide: GitOps only.
    for k in $GUARDED_CLUSTER_KINDS; do
        if [[ "$KIND" == "$k" ]]; then
            echo "{\"decision\": \"block\", \"reason\": \"kubectl $VERB $KIND changes cluster-wide admission/CRD/RBAC state. Change it in infrastructure/gitops/ and let Flux reconcile.\"}"
            exit 2
        fi
    done

    if [ -n "$NS" ] && [[ " $OPERATIONAL_NAMESPACES " == *" $NS "* ]]; then
        ALLOWED=0

        # kubectl delete pod -n vllm (any selector or name) — the documented
        # engine-stall recovery.
        if [[ "$NS" == "vllm" ]] && [[ "$VERB" == "delete" ]] && [[ "$KIND" =~ ^pods?$ ]]; then
            ALLOWED=1
        fi

        # kubectl delete pod|job|configmap -n vllm for the transient bench
        # and preflight resources, by name (inference-bench-<ts>) or by the
        # label selector both scripts set (-l kubani.io/role=inference-bench).
        if [[ "$NS" == "vllm" ]] && [[ "$VERB" == "delete" ]] && \
           [[ "$KIND" =~ ^(pods?|jobs?|configmaps?)$ ]] && \
           [[ "$COMMAND" =~ (inference-bench|inference-preflight) ]]; then
            ALLOWED=1
        fi

        # kubectl apply -f - / kubectl create configmap in vllm for the same
        # transient bench/preflight resources.
        if [[ "$NS" == "vllm" ]] && \
           [[ "$VERB" == "apply" || ( "$VERB" == "create" && "$KIND" == "configmap" ) ]] && \
           [[ "$COMMAND" =~ (inference-bench|inference-preflight) ]]; then
            ALLOWED=1
        fi

        if [[ "$ALLOWED" -ne 1 ]]; then
            echo "{\"decision\": \"block\", \"reason\": \"kubectl $VERB targets guarded namespace '$NS' directly. Prefer GitOps (edit infrastructure/gitops/ and let Flux reconcile). Guarded: $OPERATIONAL_NAMESPACES. Allowed exceptions: kubectl delete pod -n vllm (engine restart recovery), inference-bench-*/inference-preflight-* transient pod/job/configmap lifecycle in vllm. tenant-*, agent-platform, auth and temporal are not guarded.\"}"
            exit 2
        fi
    fi
done <<< "$KUBECTL_CALLS"

# ============================================================================
# HOST, CREDENTIAL AND GITOPS-CONTROL GUARDS
# ============================================================================
# These used to be enforced only by the auto-mode classifier, so whether they
# were blocked depended on its judgement call. They are fixed rules now, which
# is what lets the classifier be relaxed for everything else.
block() {
    echo "{\"decision\": \"block\", \"reason\": \"$1\"}"
    exit 2
}

# rig0 is Al's workstation; re-executing systemd there is his call.
if [[ "$COMMAND" =~ systemctl[[:space:]]+daemon-reexec ]]; then
    block "systemctl daemon-reexec restarts PID 1 on a cluster node (rig0 is also Al's workstation). Hand Al the command."
fi

# Repository variables and secrets drive CI signing and publishing.
if [[ "$COMMAND" =~ gh[[:space:]]+(variable|secret)[[:space:]]+(set|delete|remove) ]]; then
    block "gh variable/secret changes alter CI signing and publishing for every release. Hand Al the command."
fi

# Removing Flux or its objects disables GitOps itself.
if [[ "$COMMAND" =~ (^|[[:space:];&|])flux[[:space:]]+(uninstall|delete)([[:space:]]|$) ]]; then
    block "flux uninstall/delete removes GitOps control. Change infrastructure/gitops/ instead."
fi

# Credential minting: registry users, htpasswd entries and signing keys.
# (SOPS encryption of a freshly generated value stays allowed: that is the
# documented rotation workflow in .claude/rules/secrets.md.)
if [[ "$COMMAND" =~ (add_registry_user|htpasswd|age-keygen|cosign[[:space:]]+generate-key-pair) ]]; then
    block "This mints a credential or signing key (registry user, htpasswd, age key, cosign key). Hand Al the command; cosign keys are never used here (keyless only)."
fi

# Allowed on purpose (no rule needed): flux reconcile (the documented
# rollback mechanism; it only tells Flux to reconcile now), flux get, and
# pushing release tags such as investigator/v0.1.4 (the release-tags ruleset
# on GitHub is the gate for those).

# Log commands to system journal (non-blocking)
# Query with: journalctl -t kubani-claude-bash -f
logger -t kubani-claude-bash -p user.info "$COMMAND" 2>/dev/null || true

exit 0
