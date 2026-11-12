#!/usr/bin/env bash
# Build every kustomize root that Flux reconciles. Local only: `kubectl kustomize`
# renders manifests and contacts no cluster.
#
# The roots are the `path:` of each Flux Kustomization under flux-system, so a new
# Kustomization is covered without editing a list. The run fails when the roots
# cannot be derived or a root that must exist is missing from them, so a renamed
# file can never turn this into a check that builds nothing. `just
# validate-gitops-build` and the CI workflow both call this script.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

flux_dir=infrastructure/gitops/flux-system
# Roots that must be among the derived ones; their absence means derivation broke.
required=(infrastructure/gitops/apps infrastructure/gitops/infrastructure "$flux_dir")

mapfile -t roots < <(
    grep -hE '^[[:space:]]*path:[[:space:]]*["'\'']?(\./)?infrastructure/gitops' "$flux_dir"/*.yaml \
        | sed -E 's/^[[:space:]]*path:[[:space:]]*//; s/["'\'']//g; s/[[:space:]]+$//; s|^\./||; s|/$||' \
        | sort -u
)

if (( ${#roots[@]} == 0 )); then
    echo "error: no Flux Kustomization path found under $flux_dir; nothing would be built" >&2
    exit 1
fi
for need in "${required[@]}"; do
    found=0
    for root in "${roots[@]}"; do
        [[ "$root" == "$need" ]] && found=1
    done
    if (( found == 0 )); then
        echo "error: $need is not among the roots derived from $flux_dir: ${roots[*]}" >&2
        exit 1
    fi
done

for root in "${roots[@]}"; do
    if [[ ! -d "$root" ]]; then
        echo "error: Flux reconciles $root, which is not a directory in this checkout" >&2
        exit 1
    fi
    echo "Validating $root"
    kubectl kustomize "$root" >/dev/null
done
echo "built ${#roots[@]} roots"
