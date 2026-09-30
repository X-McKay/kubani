#!/usr/bin/env bash
# Generate a new agentgateway virtual-key Secret, encrypted with SOPS, without
# ever writing the plaintext key inside the repo or printing it to the
# terminal. See .claude/rules/auth.md: never a key in a ConfigMap, a
# manifest, or a commit.
#
#   gateway_key.sh <name>
#
# Writes infrastructure/gitops/apps/ai-gateway/keys/<name>.enc.yaml
# (namespace ai-gateway, key api-key). Refuses if age.key is missing.
set -euo pipefail

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[[ $# -eq 1 ]] || usage
NAME=$1
[[ $NAME =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "name must match [a-z0-9-]+" >&2; exit 2; }

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
AGE_KEY="$REPO/age.key"
OUT_DIR="$REPO/infrastructure/gitops/apps/ai-gateway/keys"
OUT="$OUT_DIR/$NAME.enc.yaml"

[[ -f "$AGE_KEY" ]] || { echo "refusing: $AGE_KEY not found (see .claude/rules/secrets.md)" >&2; exit 1; }

STAGE_DIR=$(mktemp -d)
# Name matters: .sops.yaml's creation_rule matches on the input filename
# (path_regex \.enc\.yaml$), so the staged file must literally end in
# secret.enc.yaml, not just live in a randomly-named temp file.
STAGE="$STAGE_DIR/secret.enc.yaml"
cleanup() { shred -u "$STAGE" 2>/dev/null || rm -f "$STAGE"; rmdir "$STAGE_DIR" 2>/dev/null || true; }
trap cleanup EXIT

KEY_VALUE=$(openssl rand -base64 48 | tr -dc 'a-zA-Z0-9' | head -c 40)
[[ ${#KEY_VALUE} -eq 40 ]] || { echo "key generation produced ${#KEY_VALUE} chars, expected 40" >&2; exit 1; }

cat >"$STAGE" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: gateway-key-$NAME
  namespace: ai-gateway
type: Opaque
stringData:
  api-key: "$KEY_VALUE"
EOF

mkdir -p "$OUT_DIR"
SOPS_AGE_KEY_FILE="$AGE_KEY" sops --encrypt "$STAGE" >"$OUT"

echo "wrote $OUT (key value not printed — read it back with:"
echo "  SOPS_AGE_KEY_FILE=age.key sops -d $OUT"
echo ")"
echo
echo "Add to infrastructure/gitops/apps/ai-gateway/kustomization.yaml:"
echo "  - keys/$NAME.enc.yaml"
echo
echo "Fill in the auth inventory row in"
echo "docs/infrastructure/configuration/authentik-app-access.md:"
echo "  | ai.almckay.io (or the relevant hostname) | Agent / service -> LLM API | gateway-key-$NAME | $(date -u +%Y-%m-%d) |"
echo
echo "Then attach a token budget and AgentgatewayPolicy referencing gateway-key-$NAME"
echo "(see .claude/skills/gateway-onboard/SKILL.md)."
