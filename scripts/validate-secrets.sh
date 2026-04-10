#!/usr/bin/env bash
set -euo pipefail
echo "=== Validating encrypted secret presence ==="
errors=0
while IFS= read -r -d '' yaml_file; do
    # Skip kustomization.yaml files
    [[ "$(basename "$yaml_file")" == "kustomization.yaml" ]] && continue
    dir="$(dirname "$yaml_file")"
    # Extract secret names from secretKeyRef and secretRef fields
    secret_names=$(python3 -c "
import sys, yaml
try:
    docs = list(yaml.safe_load_all(open('$yaml_file')))
except Exception:
    sys.exit(0)
names = set()
def walk(obj):
    if isinstance(obj, dict):
        for k in ('secretKeyRef', 'secretRef'):
            if k in obj and isinstance(obj[k], dict) and 'name' in obj[k]:
                names.add(obj[k]['name'])
        for v in obj.values():
            walk(v)
    elif isinstance(obj, list):
        for i in obj:
            walk(i)
for doc in docs:
    if isinstance(doc, dict):
        walk(doc)
for n in sorted(names):
    print(n)
" 2>/dev/null)
    for secret_name in $secret_names; do
        enc_file="$dir/$secret_name.enc.yaml"
        if [[ ! -f "$enc_file" ]]; then
            rel_yaml="${yaml_file#infrastructure/gitops/}"
            rel_enc="${enc_file#infrastructure/gitops/}"
            echo "  ✗ $rel_yaml references '$secret_name' but $rel_enc not found"
            errors=$((errors + 1))
        fi
    done
done < <(find infrastructure/gitops -name "*.yaml" -print0)
echo ""
if [[ $errors -gt 0 ]]; then
    echo "✗ $errors missing encrypted secret file(s)"
    exit 1
fi
echo "✓ All secret references have corresponding .enc.yaml files"
