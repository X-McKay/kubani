#!/usr/bin/env bash
# Adds a login to registry.almckay.io, and optionally a dockerconfigjson pull
# Secret for it, all SOPS-encrypted in place in this checkout.
#
#   add_registry_user.sh <user> [<namespace>/<secret-name> <target .enc.yaml>]
#
# Runs where age.key is (rig0), from a kubani checkout (the repo root is
# derived from this script's path; age.key defaults to /home/al/git/kubani/age.key).
# It edits, without printing any value:
#   - registry/basic-auth-secret.enc.yaml   appends the user's htpasswd line
#   - registry/credentials-secret.enc.yaml  adds <user>-username / <user>-password
#   - <target>                               a kubernetes.io/dockerconfigjson Secret
# Plaintext lives only in a mktemp dir that is shredded on exit. Review the
# diff (file names only change), commit, push. Traefik reloads the middleware
# Secret on its own; a consumer of the pull Secret needs no restart for
# Kyverno, which reads it per verification.
#
# Every registry login can pull AND push (one basicAuth middleware,
# docs/infrastructure/configuration/registry.md); a separate user only buys
# separate revocation.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-/home/al/git/kubani/age.key}"
USER_NAME=${1:?usage: add_registry_user.sh <user> [<ns>/<secret> <target.enc.yaml>]}
PULL_SECRET=${2:-}
TARGET=${3:-}
REGISTRY_HOST=registry.almckay.io
BASIC=infrastructure/gitops/infrastructure/registry/basic-auth-secret.enc.yaml
CREDS=infrastructure/gitops/infrastructure/registry/credentials-secret.enc.yaml
cd "$REPO"
[[ -f $SOPS_AGE_KEY_FILE ]] || { echo "no age key at $SOPS_AGE_KEY_FILE" >&2; exit 1; }
[[ $USER_NAME =~ ^[a-z][a-z0-9-]*$ ]] || { echo "user must be lowercase alphanumeric" >&2; exit 1; }
if [[ -n $PULL_SECRET && -z $TARGET ]]; then echo "a pull Secret needs a target file" >&2; exit 1; fi

TMP=$(mktemp -d)
cleanup() { find "$TMP" -type f -exec shred -u {} \; 2>/dev/null; rm -rf "$TMP"; }
trap cleanup EXIT

sops -d --extract '["stringData"]["users"]' "$BASIC" > "$TMP/users"
if grep -q "^${USER_NAME}:" "$TMP/users"; then
  echo "user $USER_NAME already exists in $BASIC" >&2; exit 1
fi

# Alphanumeric (see .claude/rules/secrets.md, "Rotating a Credential").
PASSWORD=$(openssl rand -base64 64 | tr -dc 'a-zA-Z0-9' | head -c 40)
if command -v htpasswd >/dev/null; then
  htpasswd -nbB "$USER_NAME" "$PASSWORD" | head -n1 > "$TMP/line"
else
  # Traefik accepts apr1 too; with a 40-char random password the hash
  # strength is not the limit.
  printf '%s:%s\n' "$USER_NAME" "$(openssl passwd -apr1 "$PASSWORD")" > "$TMP/line"
fi

json() { python3 -c 'import json,sys; print(json.dumps(open(sys.argv[1]).read()))' "$1"; }
{ sed -e '$a\' "$TMP/users"; cat "$TMP/line"; } | sed '/^$/d' > "$TMP/users.new"
sops set "$BASIC" '["stringData"]["users"]' "$(json "$TMP/users.new")"
printf '%s' "$USER_NAME" > "$TMP/u"; printf '%s' "$PASSWORD" > "$TMP/p"
sops set "$CREDS" "[\"stringData\"][\"${USER_NAME}-username\"]" "$(json "$TMP/u")"
sops set "$CREDS" "[\"stringData\"][\"${USER_NAME}-password\"]" "$(json "$TMP/p")"
echo "updated $BASIC and $CREDS"

if [[ -n $PULL_SECRET ]]; then
  NS=${PULL_SECRET%%/*}; NAME=${PULL_SECRET#*/}
  python3 - "$TMP/secret.enc.yaml" "$NS" "$NAME" "$REGISTRY_HOST" "$USER_NAME" "$TMP/p" <<'EOF'
import base64, json, sys
out, ns, name, host, user, pfile = sys.argv[1:]
pw = open(pfile).read()
auth = base64.b64encode(f"{user}:{pw}".encode()).decode()
cfg = json.dumps({"auths": {host: {"username": user, "password": pw, "auth": auth}}})
with open(out, "w") as f:
    f.write(f"""apiVersion: v1
kind: Secret
metadata:
  name: {name}
  namespace: {ns}
type: kubernetes.io/dockerconfigjson
stringData:
  .dockerconfigjson: {json.dumps(cfg)}
""")
EOF
  # Named secret.enc.yaml so the .sops.yaml creation rule matches.
  sops --config "$REPO/.sops.yaml" --encrypt "$TMP/secret.enc.yaml" > "$TARGET"
  echo "wrote $TARGET"
fi
