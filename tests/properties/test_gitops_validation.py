"""Property-based tests for GitOps manifest validation.

Feature: cluster-stability, Property 8: kustomize build succeeds for all GitOps paths
Validates: Requirements 8.1, 8.2
"""

import subprocess
from pathlib import Path

import yaml

GITOPS_ROOT = Path("infrastructure/gitops")

# Kustomization paths to validate (Property 8)
KUSTOMIZATION_PATHS = [
    GITOPS_ROOT / "infrastructure",
    GITOPS_ROOT / "apps",
    GITOPS_ROOT / "flux-system",
]

# Operational namespaces whose secrets we validate (Property 8 - secrets aspect)
# Maps secret name references to the directory where their .enc.yaml should live
GITOPS_APPS_DIR = GITOPS_ROOT / "apps"
GITOPS_INFRA_DIR = GITOPS_ROOT / "infrastructure"


def _run_kustomize_build(path: Path) -> subprocess.CompletedProcess:
    """Run kustomize build against a path and return the result.

    Uses `kubectl kustomize` (built-in) since standalone `kustomize` may not
    be installed in all environments.
    """
    return subprocess.run(
        ["kubectl", "kustomize", str(path)],
        capture_output=True,
        text=True,
    )


def _collect_yaml_files(root: Path) -> list[Path]:
    """Recursively collect all .yaml files under root, excluding kustomization.yaml."""
    return [
        p for p in root.rglob("*.yaml")
        if p.name != "kustomization.yaml"
    ]


def _extract_secret_names_from_manifest(manifest: dict) -> list[str]:
    """
    Extract secret names referenced via secretKeyRef or secretRef in a manifest.
    Returns a list of (secret_name, manifest_path) tuples.
    """
    secret_names = []

    def _walk(obj):
        if isinstance(obj, dict):
            # secretKeyRef: {name: ..., key: ...}
            if "secretKeyRef" in obj:
                ref = obj["secretKeyRef"]
                if isinstance(ref, dict) and "name" in ref:
                    secret_names.append(ref["name"])
            # secretRef: {name: ...}
            if "secretRef" in obj:
                ref = obj["secretRef"]
                if isinstance(ref, dict) and "name" in ref:
                    secret_names.append(ref["name"])
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(manifest)
    return secret_names


# ---------------------------------------------------------------------------
# Property 8: kustomize build succeeds for all GitOps paths
# ---------------------------------------------------------------------------


def test_property_8_kustomize_available():
    """kubectl kustomize must be accessible (built-in to kubectl)."""
    result = subprocess.run(
        ["kubectl", "kustomize", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "kubectl kustomize is not available. "
        "Ensure kubectl is installed: https://kubernetes.io/docs/tasks/tools/"
    )


def test_property_8_all_kustomization_paths_exist():
    """
    Feature: cluster-stability, Property 8: kustomize build succeeds for all GitOps paths

    All expected kustomization root paths must exist before we attempt to build them.

    Validates: Requirements 8.1
    """
    for path in KUSTOMIZATION_PATHS:
        assert path.exists(), (
            f"Kustomization path does not exist: {path}"
        )
        kustomization_file = path / "kustomization.yaml"
        assert kustomization_file.exists(), (
            f"No kustomization.yaml found at: {path}"
        )


def test_property_8_kustomize_build_infrastructure():
    """
    Feature: cluster-stability, Property 8: kustomize build succeeds for all GitOps paths

    Running `kustomize build infrastructure/gitops/infrastructure` must exit with code 0.

    Validates: Requirements 8.1
    """
    path = GITOPS_ROOT / "infrastructure"
    result = _run_kustomize_build(path)
    assert result.returncode == 0, (
        f"kustomize build failed for {path}:\n{result.stderr}"
    )


def test_property_8_kustomize_build_apps():
    """
    Feature: cluster-stability, Property 8: kustomize build succeeds for all GitOps paths

    Running `kustomize build infrastructure/gitops/apps` must exit with code 0.

    Validates: Requirements 8.1
    """
    path = GITOPS_ROOT / "apps"
    result = _run_kustomize_build(path)
    assert result.returncode == 0, (
        f"kustomize build failed for {path}:\n{result.stderr}"
    )


def test_property_8_kustomize_build_flux_system():
    """
    Feature: cluster-stability, Property 8: kustomize build succeeds for all GitOps paths

    Running `kustomize build infrastructure/gitops/flux-system` must exit with code 0.

    Validates: Requirements 8.1
    """
    path = GITOPS_ROOT / "flux-system"
    result = _run_kustomize_build(path)
    assert result.returncode == 0, (
        f"kustomize build failed for {path}:\n{result.stderr}"
    )


def test_property_8_kustomize_build_produces_output():
    """
    When kustomize build succeeds, it must produce non-empty YAML output
    (i.e., at least one Kubernetes resource is defined).

    Validates: Requirements 8.3
    """
    failures = []
    for path in KUSTOMIZATION_PATHS:
        result = _run_kustomize_build(path)
        if result.returncode != 0:
            failures.append(f"{path}: build failed — {result.stderr[:200]}")
            continue
        if not result.stdout.strip():
            failures.append(f"{path}: build succeeded but produced no output")

    assert not failures, (
        "The following kustomization paths produced no output:\n"
        + "\n".join(f"  - {f}" for f in failures)
    )


# ---------------------------------------------------------------------------
# Property 8 (secrets aspect): encrypted secret presence
# ---------------------------------------------------------------------------

# Bootstrap/infrastructure secrets that are created out-of-band during cluster
# setup and are intentionally not stored as .enc.yaml files in the repository.
# These are created manually (e.g., flux bootstrap, SOPS key injection).
BOOTSTRAP_SECRETS = frozenset({
    "sops-age",       # SOPS decryption key injected during cluster bootstrap
    "flux-system",    # Flux SSH deploy key created by `flux bootstrap`
    "oci-credentials",  # OCI registry credentials created manually
    "git-deploy-key",   # Git SSH key created manually
})


def _build_enc_yaml_secret_set(root: Path) -> set[str]:
    """
    Build a set of all secret names defined by .enc.yaml files anywhere in the gitops tree.

    Each .enc.yaml file is a SOPS-encrypted Kubernetes Secret resource. The secret name
    is read from metadata.name inside the file, not inferred from the filename.
    """
    all_secrets: set[str] = set()
    for enc_file in root.rglob("*.enc.yaml"):
        try:
            with open(enc_file) as f:
                doc = yaml.safe_load(f)
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        secret_name = doc.get("metadata", {}).get("name")
        if secret_name:
            all_secrets.add(secret_name)
    return all_secrets


def test_property_8_secrets_all_yaml_files_are_parseable():
    """
    All YAML files in the GitOps tree must be parseable without errors.
    This is a prerequisite for the secret reference checks.

    Validates: Requirements 8.2
    """
    failures = []
    for yaml_file in _collect_yaml_files(GITOPS_ROOT):
        try:
            with open(yaml_file) as f:
                list(yaml.safe_load_all(f))
        except yaml.YAMLError as e:
            failures.append(f"{yaml_file}: {e}")

    assert not failures, (
        "The following YAML files could not be parsed:\n"
        + "\n".join(f"  - {f}" for f in failures)
    )


def test_property_8_secrets_referenced_secrets_have_enc_yaml():
    """
    Feature: cluster-stability, Property 8 (secrets aspect): kustomize build succeeds for all GitOps paths

    For any manifest YAML file that references a secret via secretKeyRef or secretRef,
    a corresponding .enc.yaml file must exist somewhere in the GitOps tree that defines
    a Secret with the referenced name in its metadata.name.

    Bootstrap secrets (sops-age, flux-system, oci-credentials, git-deploy-key) are
    excluded because they are created out-of-band during cluster setup and are not
    stored as encrypted files in the repository.

    Directories prefixed with '.' (e.g., .cluster-swarm-disabled) are skipped as
    they contain disabled/archived manifests that are intentionally incomplete.

    Validates: Requirements 8.2
    """
    # Build set of all secret names defined by .enc.yaml files anywhere in the tree
    all_enc_secrets = _build_enc_yaml_secret_set(GITOPS_ROOT)

    missing_enc_files = []

    for yaml_file in _collect_yaml_files(GITOPS_ROOT):
        # Skip .enc.yaml files themselves — they define secrets, not reference them
        if ".enc" in yaml_file.name:
            continue

        # Skip disabled/archived directories (prefixed with '.')
        if any(part.startswith(".") for part in yaml_file.parts):
            continue

        try:
            with open(yaml_file) as f:
                docs = list(yaml.safe_load_all(f))
        except yaml.YAMLError:
            continue  # parse errors caught by the previous test

        for doc in docs:
            if not isinstance(doc, dict):
                continue
            secret_names = _extract_secret_names_from_manifest(doc)
            for secret_name in secret_names:
                # Skip known bootstrap/infrastructure secrets not stored in repo
                if secret_name in BOOTSTRAP_SECRETS:
                    continue

                # Check if any .enc.yaml anywhere in the gitops tree defines this secret
                if secret_name not in all_enc_secrets:
                    missing_enc_files.append(
                        f"{yaml_file.relative_to(GITOPS_ROOT)}: "
                        f"references secret '{secret_name}' but no .enc.yaml in "
                        f"the GitOps tree defines it"
                    )

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_missing = [x for x in missing_enc_files if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]

    assert not unique_missing, (
        "The following secret references are missing their .enc.yaml definitions:\n"
        + "\n".join(f"  - {f}" for f in unique_missing)
    )
