#!/usr/bin/env bash
# Fail loudly when kubectl is pointed at anything other than the kubani cluster.
#
# validate_cluster.sh sets KUBECONFIG but not a context. A context switch therefore
# silently redirects every assertion to a different cluster, where they may all pass
# while telling you nothing. Assert node identity rather than context name, because
# contexts get renamed and node names are the actual thing we care about.
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
EXPECTED="asio rig0 sparky strix"

if ! ACTUAL=$(kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null); then
    echo "✗ cannot reach a cluster with the current kubeconfig" >&2
    exit 1
fi

ACTUAL=$(echo "$ACTUAL" | sort | tr '\n' ' ' | sed 's/ $//')
EXPECTED=$(echo "$EXPECTED" | tr ' ' '\n' | sort | tr '\n' ' ' | sed 's/ $//')

if [[ "$ACTUAL" != "$EXPECTED" ]]; then
    echo "✗ kubectl is NOT pointed at the kubani cluster" >&2
    echo "    context:  $(kubectl config current-context 2>/dev/null || echo unknown)" >&2
    echo "    expected: $EXPECTED" >&2
    echo "    actual:   $ACTUAL" >&2
    echo "  Fix with: kubectl config use-context <kubani-context>" >&2
    exit 1
fi

echo "✓ cluster identity confirmed: $ACTUAL"
