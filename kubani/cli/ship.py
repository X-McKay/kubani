"""Ship orchestrator - full pipeline from test to deploy.

Usage: kubani ship <component>

Pipeline:
  0. Check for clean git state (no staged changes)
  1. Auto-bump patch version in pyproject.toml
  2. Run tests (pytest via uv)
  3. Build and push container (earthly --push +push)
  4. Patch deployment.yaml with new image tag
  5. Commit version bump + manifest change
  6. Push to remote (triggers Flux GitOps)
  7. Wait for rollout + verify health
"""

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from kubani.cli.components import ComponentInfo, ComponentRegistry, get_git_sha

logger = logging.getLogger(__name__)

# kubectl needs explicit KUBECONFIG
KUBECONFIG = os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))


class ShipPhase(Enum):
    PENDING = "pending"
    PREFLIGHT = "preflight"
    BUMPING = "bumping"
    TESTING = "testing"
    BUILDING = "building"
    PUSHING = "pushing"
    PATCHING = "patching"
    COMMITTING = "committing"
    VERIFYING = "verifying"
    DONE = "done"
    FAILED = "failed"


@dataclass
class ShipResult:
    component: str
    phase: ShipPhase
    success: bool = False
    image_tag: str = ""
    message: str = ""
    steps_completed: list[str] = field(default_factory=list)


class ShipOrchestrator:
    """Orchestrates the full ship pipeline for a component."""

    def __init__(self, registry: ComponentRegistry):
        self.registry = registry
        self.project_root = registry.project_root

    async def ship(
        self,
        component_name: str,
        skip_test: bool = False,
        skip_verify: bool = False,
        dry_run: bool = False,
        version: str | None = None,
    ) -> ShipResult:
        """Run the full ship pipeline."""
        result = ShipResult(component=component_name, phase=ShipPhase.PENDING)

        # Resolve component
        comp = self.registry.get(component_name)
        if comp is None:
            result.phase = ShipPhase.FAILED
            result.message = f"Component '{component_name}' not found in components.yaml"
            return result

        # Step 0: Preflight
        result.phase = ShipPhase.PREFLIGHT
        if not self._check_clean_staging():
            result.phase = ShipPhase.FAILED
            result.message = "Staged changes detected — commit or unstage them before shipping"
            return result

        # Step 1: Auto-bump patch version
        if not dry_run:
            result.phase = ShipPhase.BUMPING
            print(f"  Bumping patch version for {component_name}...")
            if not self._bump_version(comp):
                result.phase = ShipPhase.FAILED
                result.message = f"Version bump failed for {component_name}"
                return result
            result.steps_completed.append("bump")

        # Step 2: Test
        if not skip_test:
            result.phase = ShipPhase.TESTING
            print(f"  Testing {component_name}...")
            if not self._run_tests(comp):
                result.phase = ShipPhase.FAILED
                result.message = f"Tests failed for {component_name}"
                return result
            result.steps_completed.append("test")

        # Dry run stops here
        if dry_run:
            result.phase = ShipPhase.DONE
            result.success = True
            result.message = f"Dry run complete for {component_name} (tests passed)"
            return result

        # Step 3: Build and push
        result.phase = ShipPhase.BUILDING
        print(f"  Building and pushing {component_name}...")
        success, image_tag = self._build_and_push(comp, version)
        if not success:
            result.phase = ShipPhase.FAILED
            result.message = f"Build/push failed for {component_name}"
            return result
        result.image_tag = image_tag
        result.steps_completed.append("build")

        # Step 4: Patch manifest
        result.phase = ShipPhase.PATCHING
        print(f"  Patching deployment manifest ({image_tag})...")
        if not self._patch_manifest(comp, image_tag):
            result.phase = ShipPhase.FAILED
            result.message = f"Failed to patch manifest for {component_name}"
            return result
        result.steps_completed.append("patch")

        # Step 5: Commit and push
        result.phase = ShipPhase.COMMITTING
        print("  Committing manifest change...")
        if not self._commit_manifest(comp, image_tag):
            result.phase = ShipPhase.FAILED
            result.message = f"Failed to commit manifest for {component_name}"
            return result
        result.steps_completed.append("commit")

        print("  Pushing to remote...")
        if not self._git_push():
            result.phase = ShipPhase.FAILED
            result.message = f"Failed to push manifest commit for {component_name}"
            return result
        result.steps_completed.append("push")

        # Step 6: Verify
        if not skip_verify:
            result.phase = ShipPhase.VERIFYING
            print("  Verifying deployment...")
            if not self._verify_deployment(comp):
                result.phase = ShipPhase.FAILED
                result.message = f"Deployment verification failed for {component_name}"
                return result
            result.steps_completed.append("verify")

        result.phase = ShipPhase.DONE
        result.success = True
        result.message = f"Shipped {component_name} ({image_tag})"
        return result

    def _check_clean_staging(self) -> bool:
        """Reject if there are staged changes that would contaminate the commit."""
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=self.project_root,
        )
        return result.returncode == 0

    def _bump_version(self, comp: ComponentInfo) -> bool:
        """Auto-bump patch version in pyproject.toml before building."""
        from kubani.cli.version_utils import bump_version

        pyproject = comp.source_path(self.project_root) / "pyproject.toml"
        if not pyproject.exists():
            logger.warning(f"No pyproject.toml for {comp.name}, skipping version bump")
            return True

        content = pyproject.read_text()
        match = re.search(r'(version\s*=\s*["\'])([^"\']+)(["\'])', content)
        if not match:
            return True

        old_version = match.group(2)
        new_version = bump_version(old_version, "patch")
        new_content = content[: match.start(2)] + new_version + content[match.end(2) :]
        pyproject.write_text(new_content)
        print(f"    {old_version} -> {new_version}")
        return True

    def _run_tests(self, comp: ComponentInfo) -> bool:
        """Run pytest for the component using uv."""
        source = comp.source_path(self.project_root)
        tests_dir = source / "tests"

        if not tests_dir.exists():
            print(f"    No tests directory at {tests_dir}, skipping")
            return True

        cmd = ["uv", "run", "--package", comp.package, "pytest", str(tests_dir), "-v", "--tb=short"]
        try:
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=False, timeout=300)
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error(f"Tests timed out for {comp.name}")
            return False
        except Exception as e:
            logger.error(f"Error running tests for {comp.name}: {e}")
            return False

    def _build_and_push(self, comp: ComponentInfo, version: str | None = None) -> tuple[bool, str]:
        """Build and push container image via Earthly."""
        git_sha = get_git_sha(self.project_root)
        image_tag = version or comp.image_tag(self.project_root, git_sha)

        # Use ./ prefix for Earthly local targets
        earthfile_rel = Path(comp.earthfile).parent

        cmd = [
            "earthly",
            "--push",
            f"./{earthfile_rel}+{comp.build_target}",
            f"--VERSION={image_tag}",
        ]

        try:
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=False, timeout=600)
            if result.returncode != 0:
                return False, ""
            return True, image_tag
        except subprocess.TimeoutExpired:
            logger.error(f"Build timed out for {comp.name}")
            return False, ""
        except Exception as e:
            logger.error(f"Build error for {comp.name}: {e}")
            return False, ""

    def _patch_manifest(self, comp: ComponentInfo, image_tag: str) -> bool:
        """Update deployment.yaml with new image tag."""
        manifest_path = comp.deployment_path(self.project_root)
        if not manifest_path.exists():
            logger.error(f"Manifest not found: {manifest_path}")
            return False

        content = manifest_path.read_text()

        registry = "registry.almckay.io"
        pattern = rf"(image:\s*{re.escape(registry)}/{re.escape(comp.image_name)}:)[^\s]+"
        new_content = re.sub(pattern, rf"\g<1>{image_tag}", content)

        if content == new_content:
            logger.warning(f"No image match for {comp.image_name} in {manifest_path}")
            return False

        manifest_path.write_text(new_content)
        print(f"    Updated {manifest_path.relative_to(self.project_root)}")
        return True

    def _commit_manifest(self, comp: ComponentInfo, image_tag: str) -> bool:
        """Commit the version bump and deployment.yaml change."""
        manifest = comp.deployment_path(self.project_root)
        pyproject = comp.source_path(self.project_root) / "pyproject.toml"

        try:
            files_to_add = [str(manifest)]
            if pyproject.exists():
                files_to_add.append(str(pyproject))
            subprocess.run(
                ["git", "add", *files_to_add],
                cwd=self.project_root,
                check=True,
            )
            msg = f"chore(gitops): ship {comp.name} {image_tag}"
            result = subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=self.project_root,
            )
            if result.returncode != 0:
                logger.error("Commit failed (pre-commit hooks may have blocked it)")
                return False
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e}")
            return False

    def _git_push(self) -> bool:
        """Push to remote so Flux can pick up the change."""
        try:
            subprocess.run(
                ["git", "push"],
                cwd=self.project_root,
                capture_output=True,
                check=True,
                timeout=60,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Git push failed: {e.stderr}")
            return False

    def _verify_deployment(self, comp: ComponentInfo) -> bool:
        """Wait for rollout and verify pod health."""
        kubectl_env = {**os.environ, "KUBECONFIG": KUBECONFIG}
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "rollout",
                    "status",
                    f"deployment/{comp.deployment_name}",
                    "-n",
                    comp.namespace,
                    "--timeout=120s",
                ],
                capture_output=True,
                text=True,
                timeout=150,
                env=kubectl_env,
            )
            if result.returncode != 0:
                logger.error(f"Rollout failed: {result.stderr}")
                return False

            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "pods",
                    "-n",
                    comp.namespace,
                    "-l",
                    comp.pod_selector,
                    "-o",
                    "jsonpath={.items[*].status.phase}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env=kubectl_env,
            )
            phases = result.stdout.split()
            if phases and all(p == "Running" for p in phases):
                print(f"    {comp.name} is healthy")
                return True

            logger.warning(f"Pod phases: {phases}")
            return False

        except (subprocess.TimeoutExpired, Exception) as e:
            logger.error(f"Verification error: {e}")
            return False
