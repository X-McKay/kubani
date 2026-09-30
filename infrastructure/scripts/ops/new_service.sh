#!/usr/bin/env bash
# Scaffold a new service from the deployment skeleton, so it starts with
# requests/limits, a PSA-restricted securityContext, a NetworkPolicy pair, a
# topology nodeSelector, and a PDB instead of arriving without them (see
# .claude/rules/gitops.md "Manifest Standards").
#
#   new_service.sh <name> <namespace>
#
# Copies infrastructure/gitops/_templates/service/ to
# infrastructure/gitops/apps/<name>/ and substitutes the SERVICE_NAME and
# SERVICE_NAMESPACE placeholders.
set -euo pipefail

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[[ $# -eq 2 ]] || usage
NAME=$1
NAMESPACE=$2
[[ $NAME =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "name must match [a-z0-9-]+" >&2; exit 2; }
[[ $NAMESPACE =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "namespace must match [a-z0-9-]+" >&2; exit 2; }

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
TEMPLATE_DIR="$REPO/infrastructure/gitops/_templates/service"
TARGET_DIR="$REPO/infrastructure/gitops/apps/$NAME"

[[ -d "$TEMPLATE_DIR" ]] || { echo "template not found: $TEMPLATE_DIR" >&2; exit 1; }
[[ -e "$TARGET_DIR" ]] && { echo "refusing to overwrite existing $TARGET_DIR" >&2; exit 1; }

cp -r "$TEMPLATE_DIR" "$TARGET_DIR"

# Substitute placeholders in every copied file. `-i.bak` with an explicit
# backup suffix is accepted by both BSD/macOS sed and GNU sed (unlike bare
# `-i` with no suffix, whose argument-count differs between the two), so
# this works unmodified on the operator's Mac and on the cluster host.
find "$TARGET_DIR" -type f -print0 | while IFS= read -r -d '' f; do
  sed -i.bak \
    -e "s/SERVICE_NAME/$NAME/g" \
    -e "s/SERVICE_NAMESPACE/$NAMESPACE/g" \
    "$f"
  rm -f "$f.bak"
done

echo "scaffolded $TARGET_DIR"
echo
echo "Checklist before this PR merges (.claude/rules/gitops.md):"
echo "  [ ] Add '- $NAME' to infrastructure/gitops/apps/kustomization.yaml"
echo "  [ ] Add the netpol file's cross-namespace allow rules to infrastructure/networking/ if this service is reached from another namespace"
echo "  [ ] Add a capacity ledger line to docs/infrastructure/cluster/capacity.md"
echo "  [ ] Add an auth inventory row to docs/infrastructure/configuration/authentik-app-access.md (pick the row from .claude/rules/auth.md's decision table; fill in $TARGET_DIR/auth.md)"
echo "  [ ] Set real requests/limits (the template's are placeholders) and land on a topology.kubani.io/* nodeSelector"
echo "  [ ] just validate-local"
