#!/usr/bin/env python3
"""Fail on Kubernetes Secrets committed without SOPS encryption.

This is the inverse of check-sops-encryption.sh. That hook takes files already
named *.enc.yaml and proves they are encrypted, so it can only ever police
files someone already intended to encrypt. A Secret committed as a plain
`secret.yaml` is invisible to it — which is exactly how a real Qdrant API key
and a Neo4j password reached this repository.

This hook starts from the manifest instead of the filename: every YAML document
with `kind: Secret` must either carry SOPS metadata or hold no secret values at
all. Filenames are irrelevant.

Usage:
    check-plaintext-secrets.py [--all] [paths...]

    (no args)  scan the default roots
    --all      scan the default roots regardless of any paths given
    paths      scan just these files (how pre-commit invokes it)

Exit codes: 0 clean, 1 findings, 2 usage/parse error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print(
        "ERROR: PyYAML is required (uv run pre-commit, or `uv sync`)", file=sys.stderr
    )
    raise SystemExit(2) from None

# Directories scanned when the hook runs without explicit file arguments.
DEFAULT_ROOTS = (Path("infrastructure/gitops"),)

# Fields holding secret material on a v1 Secret.
SECRET_FIELDS = ("data", "stringData")

# Templates are committed on purpose and carry placeholders, not credentials.
# They are checked for placeholder markers rather than skipped outright.
TEMPLATE_SUFFIXES = (".template",)

# Words that, when they make up the WHOLE value, mark it as a deliberate
# stand-in. Matched against the value with separators stripped, never as a
# substring: the Qdrant key that prompted this hook was a real credential that
# merely contained "changeme", and substring matching waved it straight through.
PLACEHOLDER_WORDS = frozenset(
    {
        "changeme",
        "changethis",
        "placeholder",
        "replaceme",
        "example",
        "todo",
        "tbd",
        "secret",
        "password",
        "redacted",
    }
)

# Substitution syntax means the real value is injected at deploy time.
SUBSTITUTION_MARKERS = ("${", "$(")


def is_sops_encrypted(doc: dict) -> bool:
    """True when the document carries SOPS metadata."""
    sops = doc.get("sops")
    return isinstance(sops, dict) and bool(sops)


def is_encrypted_value(value: object) -> bool:
    """True when a value is SOPS ciphertext."""
    return isinstance(value, str) and value.startswith("ENC[AES256_GCM")


def is_placeholder(value: object) -> bool:
    """True when a value is clearly a stand-in rather than a credential.

    Deliberately strict. A false negative here is a leaked credential, so
    anything that is not unmistakably a placeholder is treated as real.
    """
    if not isinstance(value, str):
        return False

    stripped = value.strip()
    if not stripped:
        return True

    lowered = stripped.lower()

    # ${VAR} / $(VAR) — substituted at deploy time.
    if any(marker in lowered for marker in SUBSTITUTION_MARKERS):
        return True

    # <angle-bracket-template>
    if lowered.startswith("<") and lowered.endswith(">"):
        return True

    # Repeated masking characters, e.g. "xxxxxxxx" or "********".
    if len(set(lowered)) == 1 and lowered[0] in "x*.-_0":
        return True

    # The whole value is a placeholder word once separators are removed:
    # "changeme" and "change-me" match, "qdrant-changeme-a1b2c3" does not.
    collapsed = "".join(ch for ch in lowered if ch.isalnum())
    return collapsed in PLACEHOLDER_WORDS


def scan_document(doc: object, path: Path) -> list[str]:
    """Return findings for one YAML document."""
    if not isinstance(doc, dict) or doc.get("kind") != "Secret":
        return []

    # A SOPS-encrypted Secret is fine by definition.
    if is_sops_encrypted(doc):
        return []

    name = (doc.get("metadata") or {}).get("name", "<unnamed>")
    is_template = any(str(path).endswith(s) for s in TEMPLATE_SUFFIXES)
    findings: list[str] = []

    for field in SECRET_FIELDS:
        block = doc.get(field)
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if is_encrypted_value(value) or is_placeholder(value):
                continue
            if is_template:
                findings.append(
                    f"{path}: Secret/{name} template field {field}.{key} holds a "
                    f"literal value; templates must use a placeholder"
                )
            else:
                findings.append(
                    f"{path}: Secret/{name} field {field}.{key} is not encrypted"
                )
    return findings


def scan_file(path: Path) -> list[str]:
    try:
        documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        # Kustomize/Helm templating is not valid YAML; those files cannot
        # declare a literal Secret value, so skip rather than fail the commit.
        if "helm" in str(path).lower() or "template" in str(path).lower():
            return []
        return [f"{path}: could not parse YAML ({exc.__class__.__name__})"]

    findings: list[str] = []
    for doc in documents:
        findings.extend(scan_document(doc, path))
    return findings


def collect_paths(args: argparse.Namespace) -> list[Path]:
    if args.paths and not args.all:
        return [Path(p) for p in args.paths if Path(p).suffix in (".yaml", ".yml")]
    paths: list[Path] = []
    for root in DEFAULT_ROOTS:
        if root.is_dir():
            paths.extend(sorted(root.rglob("*.yaml")))
            paths.extend(sorted(root.rglob("*.yml")))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="files to scan")
    parser.add_argument(
        "--all",
        action="store_true",
        help="scan the default roots even when paths are supplied",
    )
    args = parser.parse_args()

    findings: list[str] = []
    for path in collect_paths(args):
        if path.is_file():
            findings.extend(scan_file(path))

    if findings:
        print("Unencrypted Kubernetes Secret values found:\n")
        for finding in findings:
            print(f"  {finding}")
        print(
            "\nEvery Secret under infrastructure/gitops/ must be SOPS-encrypted.\n"
            "  1. write the plaintext OUTSIDE the repo, named secret.enc.yaml so\n"
            "     the .sops.yaml creation rule matches\n"
            "  2. SOPS_AGE_KEY_FILE=age.key sops --encrypt <staged> > <target>.enc.yaml\n"
            "  3. shred the plaintext and reference the .enc.yaml from kustomization.yaml\n"
            "\nSee .claude/rules/secrets.md."
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
