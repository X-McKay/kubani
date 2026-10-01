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
if [[ "$COMMAND" =~ git[[:space:]]+push([[:space:]]|$) ]] && \
   [[ "$COMMAND" =~ [[:space:]](-f|--force|--force-with-lease)([[:space:]]|=|$) ]]; then
    # Extract the remote and branch if specified
    for branch in "${PROTECTED_BRANCHES[@]}"; do
        # Check if pushing to a protected branch
        if [[ "$COMMAND" =~ (origin[[:space:]]+$branch|$branch:|/$branch) ]]; then
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
# scale/edit against real operational namespaces is blocked unless it matches
# the documented recovery/bench/preflight allowlist.
# ============================================================================
OPERATIONAL_NAMESPACES="vllm database cache auth ai-gateway monitoring temporal registry flux-system kube-system longhorn-system"

if [[ "$COMMAND" =~ kubectl[[:space:]]+.*(apply|create|delete|patch|replace|scale|edit) ]]; then
    # Extract a namespace token from -n/--namespace in any of: "-n vllm",
    # "-nvllm", "--namespace vllm", "--namespace=vllm".
    NS=""
    if [[ "$COMMAND" =~ --namespace=([a-zA-Z0-9_-]+) ]]; then
        NS="${BASH_REMATCH[1]}"
    elif [[ "$COMMAND" =~ --namespace[[:space:]]+([a-zA-Z0-9_-]+) ]]; then
        NS="${BASH_REMATCH[1]}"
    elif [[ "$COMMAND" =~ -n=([a-zA-Z0-9_-]+) ]]; then
        NS="${BASH_REMATCH[1]}"
    elif [[ "$COMMAND" =~ -n[[:space:]]+([a-zA-Z0-9_-]+) ]]; then
        NS="${BASH_REMATCH[1]}"
    elif [[ "$COMMAND" =~ -n([a-zA-Z0-9_-]+) ]]; then
        NS="${BASH_REMATCH[1]}"
    fi

    if [ -n "$NS" ] && [[ " $OPERATIONAL_NAMESPACES " == *" $NS "* ]]; then
        ALLOWED=0

        # kubectl delete pod -n vllm (any selector or name) — the documented
        # engine-stall recovery.
        if [[ "$NS" == "vllm" ]] && [[ "$COMMAND" =~ kubectl[[:space:]]+delete[[:space:]]+pod ]]; then
            ALLOWED=1
        fi

        # kubectl delete pod|job|configmap -n vllm for the transient bench
        # and preflight resources, by name (inference-bench-<ts>) or by the
        # label selector both scripts set (-l kubani.io/role=inference-bench).
        if [[ "$NS" == "vllm" ]] && \
           [[ "$COMMAND" =~ kubectl[[:space:]]+delete[[:space:]]+(pod|job|configmap) ]] && \
           [[ "$COMMAND" =~ (inference-bench|inference-preflight) ]]; then
            ALLOWED=1
        fi

        # kubectl apply -f - / kubectl create configmap in vllm for the same
        # transient bench/preflight resources.
        if [[ "$NS" == "vllm" ]] && \
           [[ "$COMMAND" =~ kubectl[[:space:]]+apply[[:space:]]+-f[[:space:]]+- ]] && \
           [[ "$COMMAND" =~ (inference-bench|inference-preflight) ]]; then
            ALLOWED=1
        fi
        if [[ "$NS" == "vllm" ]] && \
           [[ "$COMMAND" =~ kubectl[[:space:]]+create[[:space:]]+configmap ]] && \
           [[ "$COMMAND" =~ (inference-bench|inference-preflight) ]]; then
            ALLOWED=1
        fi

        if [[ "$ALLOWED" -ne 1 ]]; then
            echo "{\"decision\": \"block\", \"reason\": \"kubectl $COMMAND targets operational namespace '$NS' directly. Prefer GitOps (edit infrastructure/gitops/ and let Flux reconcile). Allowed exceptions: kubectl delete pod -n vllm (engine restart recovery), inference-bench-*/inference-preflight-* transient pod/job/configmap lifecycle in vllm, and flux reconcile.\"}"
            exit 2
        fi
    fi
fi

# flux reconcile is always allowed (it is the documented rollback mechanism
# and does not bypass GitOps — it just tells Flux to reconcile now).

# Log commands to system journal (non-blocking)
# Query with: journalctl -t kubani-claude-bash -f
logger -t kubani-claude-bash -p user.info "$COMMAND" 2>/dev/null || true

exit 0
