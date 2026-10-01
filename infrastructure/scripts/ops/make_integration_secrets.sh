#!/usr/bin/env bash
# Runs on rig0 (holds age.key). Writes SOPS-encrypted Secrets into $OUT.
# Plaintext lives only in a mktemp dir that is shredded at the end. Nothing
# is echoed except file names.
set -euo pipefail
REPO=/home/al/git/kubani
OUT=${1:-/home/al/kubani-secrets-out}
export SOPS_AGE_KEY_FILE=$REPO/age.key
cd "$REPO"
mkdir -p "$OUT"
TMP=$(mktemp -d)
cleanup() { find "$TMP" -type f -exec shred -u {} \; 2>/dev/null; rm -rf "$TMP"; }
trap cleanup EXIT

rand() { openssl rand -base64 48 | tr -dc 'a-zA-Z0-9' | head -c "$1"; }
enc() { # enc <plaintext file> <target>
  cp "$1" "$TMP/secret.enc.yaml"; sops --encrypt "$TMP/secret.enc.yaml" > "$2"; rm -f "$TMP/secret.enc.yaml"; echo "wrote $2"
}

# --- Grafana OIDC client: same values as monitoring/grafana-oauth-credentials,
#     copied into namespace auth so the Authentik blueprint can read them via !Env.
GF_ID=$(sops -d --extract '["stringData"]["GF_AUTH_GENERIC_OAUTH_CLIENT_ID"]' infrastructure/gitops/apps/monitoring/oauth-secret.enc.yaml 2>/dev/null || sops -d --extract '["data"]["GF_AUTH_GENERIC_OAUTH_CLIENT_ID"]' infrastructure/gitops/apps/monitoring/oauth-secret.enc.yaml | base64 -d)
GF_SECRET=$(sops -d --extract '["stringData"]["GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET"]' infrastructure/gitops/apps/monitoring/oauth-secret.enc.yaml 2>/dev/null || sops -d --extract '["data"]["GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET"]' infrastructure/gitops/apps/monitoring/oauth-secret.enc.yaml | base64 -d)
cat > "$TMP/grafana-oidc.yaml" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: grafana-oidc-client
  namespace: auth
type: Opaque
stringData:
  GRAFANA_OAUTH_CLIENT_ID: "$GF_ID"
  GRAFANA_OAUTH_CLIENT_SECRET: "$GF_SECRET"
EOF
enc "$TMP/grafana-oidc.yaml" "$OUT/auth-grafana-oidc-client.enc.yaml"

# --- Qdrant read-only API key: new value, for Prometheus /metrics only.
QRO=$(rand 40)
cat > "$TMP/qdrant-ro-db.yaml" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: qdrant-readonly-credentials
  namespace: database
type: Opaque
stringData:
  read-only-api-key: "$QRO"
EOF
enc "$TMP/qdrant-ro-db.yaml" "$OUT/database-qdrant-readonly.enc.yaml"
cat > "$TMP/qdrant-ro-mon.yaml" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: qdrant-metrics-credentials
  namespace: monitoring
type: Opaque
stringData:
  api-key: "$QRO"
EOF
enc "$TMP/qdrant-ro-mon.yaml" "$OUT/monitoring-qdrant-metrics.enc.yaml"

# --- ntfy: declarative users/tokens/ACL. 'al' (admin, phone app) and
#     'alertmanager' (publishes to kubani-* via token from the bridge).
AL_PW=$(rand 24)
AM_PW=$(rand 24)
AL_HASH=$(docker run --rm httpd:2.4-alpine htpasswd -nbB al "$AL_PW" | cut -d: -f2)
AM_HASH=$(docker run --rm httpd:2.4-alpine htpasswd -nbB alertmanager "$AM_PW" | cut -d: -f2)
TOKEN="tk_$(openssl rand -base64 48 | tr -dc 'a-z0-9' | head -c 29)"
cat > "$TMP/ntfy-auth.yaml" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: ntfy-auth
  namespace: monitoring
type: Opaque
stringData:
  NTFY_AUTH_USERS: "al:$AL_HASH:admin,alertmanager:$AM_HASH:user"
  NTFY_AUTH_TOKENS: "alertmanager:$TOKEN:alertmanager-ntfy bridge"
  NTFY_AUTH_ACCESS: "alertmanager:kubani-*:write-only"
  # Read by the operator (sops -d) to sign the phone app in as 'al'.
  al-password: "$AL_PW"
EOF
enc "$TMP/ntfy-auth.yaml" "$OUT/monitoring-ntfy-auth.enc.yaml"

# --- bridge config as a Secret (carries the ntfy token).
cat > "$TMP/bridge.yaml" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: alertmanager-ntfy-config
  namespace: monitoring
type: Opaque
stringData:
  config.yml: |
    http:
      addr: :8000
    ntfy:
      baseurl: http://ntfy.monitoring.svc.cluster.local
      auth:
        token: "$TOKEN"
      notification:
        topic: 'labels.severity == "none" ? "kubani-watchdog" : "kubani-alerts"'
        priority: 'labels.severity == "critical" ? "urgent" : (labels.severity == "warning" ? "default" : "min")'
        tags:
          - tag: rotating_light
            condition: status == "firing" && labels.severity == "critical"
          - tag: warning
            condition: status == "firing" && labels.severity == "warning"
          - tag: white_check_mark
            condition: status == "resolved"
        templates:
          title: '{{ index .Labels "alertname" }} ({{ .Status }}) [{{ index .Labels "severity" }}]'
          description: '{{ index .Annotations "summary" }}'
          headers:
            X-Click: '{{ index .Annotations "runbook_url" }}'
EOF
enc "$TMP/bridge.yaml" "$OUT/monitoring-alertmanager-ntfy-config.enc.yaml"
echo "done"
