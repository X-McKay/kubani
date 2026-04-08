#!/usr/bin/env bash
#
# rotate_sops_keys.sh — Rotate the SOPS age key used to encrypt secrets.
#
# This script:
#   1. Generates a new age keypair
#   2. Backs up the old key
#   3. Updates .sops.yaml with the new public key
#   4. Re-keys all .enc.yaml files using `sops updatekeys` (decrypts with old, re-encrypts with new)
#   5. Installs the new key locally
#   6. Applies the new SOPS age secret to the cluster via stdin
#
# Usage:
#   ./scripts/rotate_sops_keys.sh                # Normal rotation (requires old key)
#   ./scripts/rotate_sops_keys.sh --from-cluster  # Recovery mode: extract secrets from k8s
#   ./scripts/rotate_sops_keys.sh --dry-run       # Preview what would happen (no changes)
#
# Prerequisites:
#   - age, sops, kubectl, yq installed
#   - KUBECONFIG set or ~/.kube/config available

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGE_KEY_FILE="${REPO_ROOT}/age.key"
SOPS_YAML="${REPO_ROOT}/.sops.yaml"
ENC_PATTERN="*.enc.yaml"
DATE_SUFFIX="$(date +%Y%m%d)"
FROM_CLUSTER=false
DRY_RUN=false

# --- Helpers ---

die() { echo "ERROR: $*" >&2; exit 1; }

check_deps() {
    local missing=()
    for cmd in age-keygen sops kubectl yq; do
        command -v "$cmd" &>/dev/null || missing+=("$cmd")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        die "Missing required tools: ${missing[*]}"
    fi
}

find_enc_files() {
    find "${REPO_ROOT}/infrastructure" -name "${ENC_PATTERN}" -type f | sort
}

# --- Parse args ---

while [[ $# -gt 0 ]]; do
    case "$1" in
        --from-cluster) FROM_CLUSTER=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help)
            sed -n '3,/^$/s/^# \?//p' "$0"
            exit 0
            ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# --- Main ---

check_deps

echo "=== SOPS Age Key Rotation ==="
[[ "$DRY_RUN" == true ]] && echo "[DRY RUN — no changes will be made]"
echo ""

# Discover encrypted files
mapfile -t ENC_FILES < <(find_enc_files)
echo "Found ${#ENC_FILES[@]} encrypted secret files."

if [[ ${#ENC_FILES[@]} -eq 0 ]]; then
    die "No .enc.yaml files found under infrastructure/"
fi

# Step 1: Generate new age keypair
echo ""
echo "--- Step 1: Generate new age keypair ---"
NEW_KEY_FILE=$(mktemp)
rm -f "$NEW_KEY_FILE"
trap 'rm -f "$NEW_KEY_FILE"' EXIT

AGE_OUTPUT=$(age-keygen -o "$NEW_KEY_FILE" 2>&1)
NEW_PUBLIC_KEY=$(echo "$AGE_OUTPUT" | grep -oP 'Public key: \K.*')
echo "New public key: ${NEW_PUBLIC_KEY}"

# Step 2: Back up old key
echo ""
echo "--- Step 2: Back up old key ---"
if [[ -f "$AGE_KEY_FILE" ]]; then
    OLD_KEY_FILE="$AGE_KEY_FILE"
    if [[ "$DRY_RUN" == true ]]; then
        echo "Would back up age.key to age.key.old.${DATE_SUFFIX}"
    else
        BACKUP="${AGE_KEY_FILE}.old.${DATE_SUFFIX}"
        cp "$AGE_KEY_FILE" "$BACKUP"
        echo "Old key backed up to: ${BACKUP}"
    fi
else
    echo "WARNING: No existing age.key found."
    if [[ "$FROM_CLUSTER" != true ]]; then
        die "Cannot decrypt existing secrets without old key. Use --from-cluster to recover from live cluster."
    fi
    OLD_KEY_FILE=""
fi

# Step 3: Update .sops.yaml with new public key (must happen before updatekeys)
echo ""
echo "--- Step 3: Update .sops.yaml ---"
OLD_PUBLIC_KEY=$(yq '.creation_rules[0].age' "$SOPS_YAML")
if [[ "$DRY_RUN" == true ]]; then
    echo "Would update .sops.yaml: ${OLD_PUBLIC_KEY} -> ${NEW_PUBLIC_KEY}"
else
    yq -i ".creation_rules[0].age = \"${NEW_PUBLIC_KEY}\"" "$SOPS_YAML"
    echo "Updated .sops.yaml: ${OLD_PUBLIC_KEY} -> ${NEW_PUBLIC_KEY}"
fi

# Step 4: Re-encrypt all secrets
echo ""
echo "--- Step 4: Re-encrypt secrets ---"

FAILED=()
SUCCESS=0

for enc_file in "${ENC_FILES[@]}"; do
    rel_path="${enc_file#"${REPO_ROOT}/"}"
    echo -n "  ${rel_path} ... "

    if [[ "$FROM_CLUSTER" == true ]]; then
        # Recovery mode: extract secret values from live cluster
        secret_name=$(yq '.metadata.name' "$enc_file")
        secret_ns=$(yq '.metadata.namespace' "$enc_file")

        if [[ -z "$secret_name" || "$secret_name" == "null" ]]; then
            echo "SKIP (no metadata.name)"
            FAILED+=("$rel_path (no metadata.name)")
            continue
        fi

        if [[ "$DRY_RUN" == true ]]; then
            # Just check if the secret exists in the cluster
            if kubectl get secret "$secret_name" -n "$secret_ns" &>/dev/null; then
                echo "OK (would extract from cluster: ${secret_ns}/${secret_name})"
                ((SUCCESS++))
            else
                echo "SKIP (not found in cluster: ${secret_ns}/${secret_name})"
                FAILED+=("$rel_path (not in cluster)")
            fi
            continue
        fi

        PLAIN_DATA=$(kubectl get secret "$secret_name" -n "$secret_ns" -o yaml 2>/dev/null) || {
            echo "SKIP (not found in cluster: ${secret_ns}/${secret_name})"
            FAILED+=("$rel_path (not in cluster)")
            continue
        }

        # Build clean plaintext manifest from original structure + live data
        TEMP_PLAIN=$(mktemp)
        yq eval 'del(.sops)' "$enc_file" > "$TEMP_PLAIN"

        HAS_STRING_DATA=$(yq '.stringData // empty' "$enc_file")
        HAS_DATA=$(yq '.data // empty' "$enc_file")

        if [[ -n "$HAS_STRING_DATA" ]]; then
            # Original used stringData — decode base64 from cluster
            while IFS= read -r key; do
                B64_VAL=$(echo "$PLAIN_DATA" | yq ".data.\"${key}\"")
                if [[ -n "$B64_VAL" && "$B64_VAL" != "null" ]]; then
                    DECODED=$(echo "$B64_VAL" | base64 -d)
                    yq -i ".stringData.\"${key}\" = \"${DECODED}\"" "$TEMP_PLAIN"
                fi
            done < <(yq '.stringData | keys | .[]' "$enc_file")
        elif [[ -n "$HAS_DATA" ]]; then
            # Original used data (base64) — copy directly
            while IFS= read -r key; do
                VAL=$(echo "$PLAIN_DATA" | yq ".data.\"${key}\"")
                if [[ -n "$VAL" && "$VAL" != "null" ]]; then
                    yq -i ".data.\"${key}\" = \"${VAL}\"" "$TEMP_PLAIN"
                fi
            done < <(yq '.data | keys | .[]' "$enc_file")
        fi

        SOPS_AGE_KEY_FILE="$NEW_KEY_FILE" sops --encrypt \
            --age "$NEW_PUBLIC_KEY" \
            --encrypted-regex '^(data|stringData)$' \
            "$TEMP_PLAIN" > "$enc_file"

        rm -f "$TEMP_PLAIN"
        echo "OK (from cluster)"
        ((SUCCESS++))
    else
        # Normal rotation: use sops updatekeys (decrypts with old key, re-encrypts with new)
        if [[ "$DRY_RUN" == true ]]; then
            # Verify the file has the expected age recipient
            FILE_RECIPIENT=$(yq '.sops.age[0].recipient' "$enc_file" 2>/dev/null)
            if [[ "$FILE_RECIPIENT" == "$OLD_PUBLIC_KEY" ]]; then
                echo "OK (would re-key)"
                ((SUCCESS++))
            else
                echo "WARN (recipient mismatch: ${FILE_RECIPIENT})"
                FAILED+=("$rel_path (recipient mismatch)")
            fi
            continue
        fi

        if SOPS_AGE_KEY_FILE="$OLD_KEY_FILE" sops updatekeys -y "$enc_file" 2>/dev/null; then
            echo "OK"
            ((SUCCESS++))
        else
            echo "FAIL (updatekeys failed)"
            FAILED+=("$rel_path (updatekeys failed)")
        fi
    fi
done

# Step 5: Install new key
echo ""
echo "--- Step 5: Install new age key ---"
if [[ "$DRY_RUN" == true ]]; then
    echo "Would install new key to: ${AGE_KEY_FILE}"
else
    cp "$NEW_KEY_FILE" "$AGE_KEY_FILE"
    chmod 600 "$AGE_KEY_FILE"
    echo "New key installed at: ${AGE_KEY_FILE}"
fi

# Step 6: Apply SOPS age secret to cluster
echo ""
echo "--- Step 6: Apply SOPS age secret to cluster ---"
if [[ "$DRY_RUN" == true ]]; then
    echo "Would apply new age key to flux-system/sops-age secret"
else
    echo "Applying new age key as Kubernetes secret via stdin..."
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Secret
metadata:
    name: sops-age
    namespace: flux-system
type: Opaque
stringData:
    age.agekey: |
$(sed 's/^/        /' "$NEW_KEY_FILE")
EOF
    echo "Cluster secret updated."
fi

# Summary
echo ""
echo "=== Rotation Complete ==="
[[ "$DRY_RUN" == true ]] && echo "[DRY RUN — no changes were made]"
echo "  New public key: ${NEW_PUBLIC_KEY}"
echo "  Re-encrypted:   ${SUCCESS}/${#ENC_FILES[@]} files"

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo ""
    echo "  FAILED (${#FAILED[@]}):"
    for f in "${FAILED[@]}"; do
        echo "    - $f"
    done
    echo ""
    echo "  Review failed files manually."
    exit 1
fi

if [[ "$DRY_RUN" != true ]]; then
    echo ""
    echo "Next steps:"
    echo "  1. Verify: SOPS_AGE_KEY_FILE=age.key sops --decrypt <any .enc.yaml>"
    echo "  2. Commit the re-encrypted files and updated .sops.yaml"
    echo "  3. Flux will reconcile with the new cluster secret automatically"
fi
