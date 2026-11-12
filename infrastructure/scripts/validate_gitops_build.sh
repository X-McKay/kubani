#!/usr/bin/env bash
# Build every kustomize root that Flux reconciles. Local only: `kubectl kustomize`
# renders manifests and contacts no cluster.
#
# The roots are the `path:` of each Flux Kustomization under flux-system, so a new
# Kustomization is covered without editing a list. The run fails when the roots
# cannot be derived or a root that must exist is missing from them, so a renamed
# file can never turn this into a check that builds nothing. `just
# validate-gitops-build` and the CI workflow both call this script.
#
# A Flux Kustomization whose path the pattern below cannot read (a path outside
# infrastructure/gitops, a folded scalar, a flow mapping) would otherwise be skipped
# without a word, so the number of paths derived (before removing duplicates) must
# equal the number of Flux Kustomization objects in the directory, `*.yaml` and
# `*.yml` alike. FLUX_DIR overrides the directory, for testing this script.
set -euo pipefail
shopt -s nullglob

cd "$(git rev-parse --show-toplevel)"

flux_dir=${FLUX_DIR:-infrastructure/gitops/flux-system}
flux_files=("$flux_dir"/*.yaml "$flux_dir"/*.yml)
# Roots that must be among the derived ones; their absence means derivation broke.
required=(infrastructure/gitops/apps infrastructure/gitops/infrastructure infrastructure/gitops/flux-system)

if (( ${#flux_files[@]} == 0 )); then
    echo "error: no YAML files under $flux_dir; nothing would be built" >&2
    exit 1
fi

# Every path line the pattern reads, duplicates kept, so they can be counted against the objects.
mapfile -t paths < <(
    grep -hE '^[[:space:]]*path:[[:space:]]*["'\'']?(\./)?infrastructure/gitops' "${flux_files[@]}" \
        | sed -E 's/^[[:space:]]*path:[[:space:]]*//; s/["'\'']//g; s/[[:space:]]+$//; s|^\./||; s|/$||' || true
)
mapfile -t roots < <(printf '%s\n' "${paths[@]}" | sort -u | sed '/^$/d')

# Flux Kustomization objects: a top-level apiVersion in the kustomize.toolkit.fluxcd.io group and kind Kustomization.
# flux-system/kustomization.yaml is a kustomize.config.k8s.io file of the same kind; the CRDs in gotk-components.yaml
# name the group only in other fields.
objects=0
for file in "${flux_files[@]}"; do
    count=$(awk '
        /^---/ { if (flux && kind) n++; flux = 0; kind = 0; next }
        /^apiVersion:[[:space:]]*["'\'']?kustomize\.toolkit\.fluxcd\.io\// { flux = 1 }
        /^kind:[[:space:]]*["'\'']?Kustomization["'\'']?[[:space:]]*$/ { kind = 1 }
        END { if (flux && kind) n++; print n + 0 }
    ' "$file")
    objects=$((objects + count))
done
if (( ${#paths[@]} != objects )); then
    echo "error: $objects Flux Kustomization objects under $flux_dir but ${#paths[@]} paths under infrastructure/gitops were read from them;" >&2
    echo "       a path outside infrastructure/gitops, a folded scalar or a flow mapping would be skipped, so the build fails instead" >&2
    exit 1
fi

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
