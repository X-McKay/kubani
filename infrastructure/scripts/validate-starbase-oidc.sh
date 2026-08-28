#!/usr/bin/env bash
# Read-only post-reconcile checks for the mounted Starbase Authentik blueprint.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly ROOT_DIR
readonly DISCOVERY_URL="https://auth.almckay.io/application/o/starbase/.well-known/openid-configuration"
readonly EXPECTED_ISSUER="https://auth.almckay.io/application/o/starbase/"
readonly EXPECTED_JWKS="https://auth.almckay.io/application/o/starbase/jwks/"
OBSERVED_AT="$(date -u +%s)"
readonly OBSERVED_AT

cleanup() {
  rm -f "${DISCOVERY_FILE:-}" "${JWKS_FILE:-}"
}

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

assert_blueprint_scalar() {
  local blueprint="$1"
  local key="$2"
  local expected="$3"
  local label="$4"
  local key_count
  local exact_count

  read -r key_count exact_count < <(
    printf '%s\n' "$blueprint" | awk -v key="$key" -v expected="$expected" '
      {
        line = $0
        sub(/^[[:space:]]*/, "", line)
        if (substr(line, 1, length(key) + 1) == key ":") {
          key_count++
          value = substr(line, length(key) + 2)
          sub(/^[[:space:]]*/, "", value)
          sub(/[[:space:]]*#.*$/, "", value)
          sub(/[[:space:]]*$/, "", value)
          if (value == expected) {
            exact_count++
          }
        }
      }
      END { print key_count + 0, exact_count + 0 }
    '
  )
  assert_equal "$key_count" "1" "$label key count"
  assert_equal "$exact_count" "1" "$label exact value"
}

main() {
  trap cleanup EXIT

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
  [[ "$blueprint" == *"grant_types:"* && "$blueprint" == *"authorization_code"* ]] || fail "Starbase OIDC provider is not authorization-code-only"
  assert_blueprint_scalar "$blueprint" "access_token_validity" "minutes=15" "Starbase OIDC access-token lifetime"
  assert_blueprint_scalar "$blueprint" "refresh_token_validity" "hours=8" "Starbase OIDC refresh-token lifetime"
  [[ "$blueprint" == *"redirect_uri_type: authorization"* ]] || fail "Starbase callback is not an authorization redirect"
  [[ "$blueprint" != *"client_secret"* ]] || fail "Starbase blueprint unexpectedly contains a client secret"

  DISCOVERY_FILE="$(mktemp)"
  JWKS_FILE="$(mktemp)"
  curl --fail --silent --show-error --location \
    --header 'Cache-Control: no-cache' \
    "${DISCOVERY_URL}?observed_at=${OBSERVED_AT}" >"$DISCOVERY_FILE"

  assert_equal "$(jq -er '.issuer' "$DISCOVERY_FILE")" "$EXPECTED_ISSUER" "OIDC issuer"
  assert_equal "$(jq -er '.jwks_uri' "$DISCOVERY_FILE")" "$EXPECTED_JWKS" "OIDC JWKS URI"
  jq -e '.authorization_endpoint | startswith("https://auth.almckay.io/")' "$DISCOVERY_FILE" >/dev/null
  jq -e '.token_endpoint | startswith("https://auth.almckay.io/")' "$DISCOVERY_FILE" >/dev/null
  jq -e '.userinfo_endpoint | startswith("https://auth.almckay.io/")' "$DISCOVERY_FILE" >/dev/null
  jq -e '.grant_types_supported | index("authorization_code") != null' "$DISCOVERY_FILE" >/dev/null
  jq -e '.response_types_supported | index("code") != null' "$DISCOVERY_FILE" >/dev/null
  jq -e '.code_challenge_methods_supported | index("S256") != null' "$DISCOVERY_FILE" >/dev/null

  curl --fail --silent --show-error --location \
    --header 'Cache-Control: no-cache' \
    "${EXPECTED_JWKS}?observed_at=${OBSERVED_AT}" >"$JWKS_FILE"
  jq -e '.keys | length > 0 and any(.[]; .kty == "RSA")' "$JWKS_FILE" >/dev/null

  printf 'PASS: Starbase OIDC discovery, JWKS, and owner blueprint contract verified.\n'
  printf 'MANUAL: after an identity change, exercise both authorized-member success and non-member denial.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
