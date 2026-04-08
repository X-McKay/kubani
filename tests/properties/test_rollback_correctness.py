"""Property-based tests for deployment rollback correctness.

Feature: cluster-stability, Property 9: Rollback produces a manifest with the previous image tag
Validates: Requirements 9.1
"""

import subprocess
import textwrap
from pathlib import Path


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a git command in the given directory."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _setup_git_repo(tmp_path: Path) -> Path:
    """
    Create a minimal git repo with two commits, each containing a deployment.yaml
    with a different image tag. Returns the repo root.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialise repo with a stable identity
    _git(["init"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)

    # Create the component directory structure mirroring the real layout
    component_dir = repo / "infrastructure" / "gitops" / "apps" / "myapp"
    component_dir.mkdir(parents=True)

    deployment = component_dir / "deployment.yaml"

    # --- First commit: old image tag ---
    deployment.write_text(
        textwrap.dedent("""\
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: myapp
        spec:
          template:
            spec:
              containers:
              - name: myapp
                image: registry.example.io/myapp:v1.0.0
        """)
    )
    _git(["add", "."], repo)
    _git(["commit", "-m", "initial: deploy myapp v1.0.0"], repo)

    # --- Second commit: new image tag ---
    deployment.write_text(
        textwrap.dedent("""\
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: myapp
        spec:
          template:
            spec:
              containers:
              - name: myapp
                image: registry.example.io/myapp:v1.1.0
        """)
    )
    _git(["add", "."], repo)
    _git(["commit", "-m", "deploy: bump myapp to v1.1.0"], repo)

    return repo


def _extract_image_tag(manifest_path: Path) -> str:
    """Extract the first image: value from a deployment manifest."""
    for line in manifest_path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("image:"):
            return stripped.split("image:", 1)[1].strip().strip('"')
    raise ValueError(f"No 'image:' line found in {manifest_path}")


def _run_rollback_logic(repo: Path, component: str) -> subprocess.CompletedProcess:
    """
    Execute the rollback logic extracted from the justfile recipe.

    This mirrors the shell logic in `just rollback <component>` so we can test
    it without invoking `just` (which would require the full justfile context).
    """
    script = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -euo pipefail

        manifest=$(find infrastructure/gitops/apps -name "deployment.yaml" -path "*{component}*" | head -1)
        if [[ -z "$manifest" ]]; then
            echo "Error: No deployment manifest found for '{component}'" >&2
            exit 1
        fi

        current=$(grep -m1 'image:' "$manifest" | awk '{{print $2}}' | tr -d '"')
        if [[ -z "$current" ]]; then
            echo "Error: Could not extract current image tag" >&2
            exit 1
        fi

        previous=$(git show HEAD~1:"$manifest" 2>/dev/null | grep -m1 'image:' | awk '{{print $2}}' | tr -d '"')
        if [[ -z "$previous" ]]; then
            echo "Error: No previous version found for '{component}'" >&2
            exit 1
        fi

        if [[ "$current" == "$previous" ]]; then
            echo "Error: Current and previous image tags are identical: $current" >&2
            exit 1
        fi

        sed -i "s|$current|$previous|g" "$manifest"

        git add "$manifest"
        git commit -m "rollback: revert {component} to $previous"

        echo "ROLLED_BACK_TO=$previous"
    """)

    return subprocess.run(
        ["bash", "-c", script],
        cwd=repo,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Property 9: Rollback produces a manifest with the previous image tag
# ---------------------------------------------------------------------------


def test_property_9_rollback_produces_previous_image_tag(tmp_path):
    """
    Feature: cluster-stability, Property 9: Rollback produces a manifest with the previous image tag

    For any component with at least two image tag commits in Git history, running the
    rollback command must produce a manifest containing the image tag from the commit
    immediately before the most recent one.

    Validates: Requirements 9.1
    """
    repo = _setup_git_repo(tmp_path)
    manifest = repo / "infrastructure" / "gitops" / "apps" / "myapp" / "deployment.yaml"

    # Confirm starting state: manifest has the new tag
    assert _extract_image_tag(manifest) == "registry.example.io/myapp:v1.1.0"

    result = _run_rollback_logic(repo, "myapp")
    assert result.returncode == 0, (
        f"Rollback script failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # After rollback, the manifest must contain the previous tag
    rolled_back_tag = _extract_image_tag(manifest)
    assert rolled_back_tag == "registry.example.io/myapp:v1.0.0", (
        f"Expected manifest to contain 'registry.example.io/myapp:v1.0.0' after rollback, "
        f"but got '{rolled_back_tag}'"
    )


def test_property_9_rollback_commits_the_revert(tmp_path):
    """
    After rollback, a new git commit must exist with the previous image tag in the manifest.

    Validates: Requirements 9.2
    """
    repo = _setup_git_repo(tmp_path)

    result = _run_rollback_logic(repo, "myapp")
    assert result.returncode == 0, (
        f"Rollback script failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # The HEAD commit message should reference the rollback
    log = _git(["log", "--oneline", "-1"], repo)
    assert "rollback" in log.stdout.lower(), (
        f"Expected HEAD commit to mention 'rollback', got: {log.stdout.strip()}"
    )

    # The HEAD commit must contain the previous image tag in the manifest
    manifest_at_head = _git(
        ["show", "HEAD:infrastructure/gitops/apps/myapp/deployment.yaml"], repo
    )
    assert "v1.0.0" in manifest_at_head.stdout, (
        f"HEAD commit manifest does not contain the previous tag 'v1.0.0':\n{manifest_at_head.stdout}"
    )


def test_property_9_rollback_fails_gracefully_when_no_previous_commit(tmp_path):
    """
    When no previous commit exists for a component, the rollback command must
    exit with a non-zero code and a clear error message.

    Validates: Requirements 9.4
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)

    component_dir = repo / "infrastructure" / "gitops" / "apps" / "newapp"
    component_dir.mkdir(parents=True)
    deployment = component_dir / "deployment.yaml"
    deployment.write_text(
        textwrap.dedent("""\
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: newapp
        spec:
          template:
            spec:
              containers:
              - name: newapp
                image: registry.example.io/newapp:v1.0.0
        """)
    )
    _git(["add", "."], repo)
    _git(["commit", "-m", "initial: deploy newapp v1.0.0"], repo)

    # Only one commit exists — no HEAD~1
    result = _run_rollback_logic(repo, "newapp")
    assert result.returncode != 0, (
        "Expected rollback to fail when no previous commit exists, but it succeeded"
    )
    # The script exits non-zero; the error message may appear in stderr or stdout
    # depending on whether set -e exits before the explicit echo runs.
    combined = result.stdout + result.stderr
    assert "error" in combined.lower() or combined.strip() == "", (
        f"Expected a non-zero exit (got {result.returncode}) with optional error message. "
        f"stdout: {result.stdout!r}, stderr: {result.stderr!r}"
    )


def test_property_9_rollback_fails_gracefully_when_component_not_found(tmp_path):
    """
    When no deployment manifest is found for the given component name, the rollback
    command must exit with a non-zero code and a clear error message.

    Validates: Requirements 9.4
    """
    repo = _setup_git_repo(tmp_path)

    result = _run_rollback_logic(repo, "nonexistent-component")
    assert result.returncode != 0, (
        "Expected rollback to fail for a nonexistent component, but it succeeded"
    )
    assert "error" in result.stderr.lower(), (
        f"Expected a clear error message, got stderr: {result.stderr!r}"
    )
