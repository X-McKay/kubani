#!/usr/bin/env bash
# Read-only post-reconcile checks for the mounted Starbase Authentik blueprint.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly ROOT_DIR
readonly DISCOVERY_URL="https://auth.almckay.io/application/o/starbase/.well-known/openid-configuration"
readonly EXPECTED_ISSUER="https://auth.almckay.io/application/o/starbase/"
readonly EXPECTED_JWKS="https://auth.almckay.io/application/o/starbase/jwks/"

cleanup() {
  rm -f "${DISCOVERY_FILE:-}" "${JWKS_FILE:-}"
}
trap cleanup EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_equal() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  [[ "$actual" == "$expected" ]] || fail "$label: expected '$expected', got '$actual'"
}

"$ROOT_DIR/infrastructure/scripts/check-cluster-identity.sh"
kubectl get --raw=/readyz >/dev/null

for resource in \
  kustomization/apps \
  kustomization/starbase-foundation \
  helmrelease/authentik; do
  namespace=flux-system
  [[ "$resource" == helmrelease/* ]] && namespace=auth
  ready="$(kubectl get "$resource" -n "$namespace" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')"
  assert_equal "$ready" "True" "$namespace/$resource readiness"
done

blueprint="$(kubectl get configmap/authentik-blueprints -n auth -o jsonpath='{.data.starbase\.yaml}')"
[[ "$blueprint" == *"name: Starbase OIDC"* ]] || fail "mounted ConfigMap lacks starbase.yaml"
[[ "$blueprint" == *"name: starbase-operators"* ]] || fail "blueprint lacks starbase-operators"
[[ "$blueprint" == *"client_type: public"* ]] || fail "Starbase OIDC client is not public"
[[ "$blueprint" != *"client_secret"* ]] || fail "Starbase blueprint unexpectedly contains a client secret"

DISCOVERY_FILE="$(mktemp)"
JWKS_FILE="$(mktemp)"
curl --fail --silent --show-error --location "$DISCOVERY_URL" >"$DISCOVERY_FILE"

assert_equal "$(jq -er '.issuer' "$DISCOVERY_FILE")" "$EXPECTED_ISSUER" "OIDC issuer"
assert_equal "$(jq -er '.jwks_uri' "$DISCOVERY_FILE")" "$EXPECTED_JWKS" "OIDC JWKS URI"
jq -e '.authorization_endpoint | startswith("https://auth.almckay.io/")' "$DISCOVERY_FILE" >/dev/null
jq -e '.token_endpoint | startswith("https://auth.almckay.io/")' "$DISCOVERY_FILE" >/dev/null
jq -e '.userinfo_endpoint | startswith("https://auth.almckay.io/")' "$DISCOVERY_FILE" >/dev/null
jq -e '.code_challenge_methods_supported | index("S256") != null' "$DISCOVERY_FILE" >/dev/null

curl --fail --silent --show-error --location "$EXPECTED_JWKS" >"$JWKS_FILE"
jq -e '.keys | length > 0 and any(.[]; .kty == "RSA")' "$JWKS_FILE" >/dev/null

for workload in \
  starbase-system/starbase-core \
  starbase-connectors/starbase-github-connector \
  starbase-connectors/starbase-kubernetes-connector; do
  namespace="${workload%%/*}"
  name="${workload#*/}"
  replicas="$(kubectl get deployment "$name" -n "$namespace" -o jsonpath='{.spec.replicas}')"
  assert_equal "$replicas" "0" "$workload spec.replicas"
done

while IFS=/ read -r namespace name; do
  suspended="$(kubectl get job "$name" -n "$namespace" -o jsonpath='{.spec.suspend}')"
  assert_equal "$suspended" "true" "$namespace/$name spec.suspend"
done <<'JOBS'
database/starbase-database-bootstrap-v1-e42143ae98e4
starbase-system/starbase-core-migrate-22bfaa3b1e8f
starbase-system/starbase-gateway-migrate-38db19887578
JOBS

printf 'PASS: Starbase OIDC discovery, JWKS, owner blueprint, and inactive workload gates verified.\n'
printf 'MANUAL: verify blueprint success, add only the intended operator to starbase-operators, and exercise member/non-member denial before core activation.\n'
