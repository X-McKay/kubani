# `kubani ship` Command & Justfile Cleanup Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a single `kubani ship <component>` command that orchestrates the full test-build-push-tag-deploy-verify cycle for ANY component (syndicates, MCP servers, Nexus), backed by a component registry; simultaneously clean the justfile from ~1200 lines to ~1000 by removing deprecated commands and collapsing duplicates.

**Architecture:** A `components.yaml` file maps every deployable component to its source path, Earthfile, deployment manifest, image name, and package name. The existing `DeploymentOrchestrator` in `deploy.py` is extended with a `ComponentRegistry` that reads this map. A new `kubani ship` CLI command wraps the pipeline: run tests -> build -> push -> patch manifest -> commit -> git push -> verify. The justfile is cleaned by deleting deprecated wrappers and collapsing MCP test variants.

**Tech Stack:** Python 3.12, Typer, PyYAML, existing Earthly build system, existing GitOps manifests, pytest, uv workspaces

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `components.yaml` | Create | Component registry mapping names to paths, Earthfiles, deployments |
| `kubani/cli/components.py` | Create | `ComponentRegistry` class: load, validate, resolve components |
| `kubani/cli/ship.py` | Create | `ShipOrchestrator`: bump -> test -> build -> push -> patch -> commit -> push -> verify |
| `kubani/cli/cli.py` | Modify | Add `ship` command, wire to `ShipOrchestrator` |
| `kubani/cli/deploy.py` | Modify | Extract `LocalBuilder.target_map` to use `ComponentRegistry`, update `GitOpsUpdater` |
| `kubani/cli/tests/test_components.py` | Create | Tests for `ComponentRegistry` |
| `kubani/cli/tests/test_ship.py` | Create | Tests for `ShipOrchestrator` |
| `justfile` | Modify | Remove deprecated commands, collapse MCP test variants |

---

## Chunk 1: Component Registry

### Task 1: Create `components.yaml`

This is the single source of truth for all deployable components.

**Files:**
- Create: `components.yaml`

- [ ] **Step 1: Create `components.yaml` with all deployable components**

```yaml
# components.yaml - Component registry for kubani ship
#
# Each component maps a short name to its source, build, and deploy locations.
# Used by `kubani ship` to orchestrate the full pipeline.

components:
  # === Syndicates ===
  k8s-monitor:
    type: syndicate
    source: kubani/syndicates/k8s_monitor
    earthfile: kubani/syndicates/k8s_monitor/Earthfile
    package: k8s-monitor-syndicate
    image_name: k8s-monitor        # must match IMAGE_NAME in Earthfile
    deployment: infrastructure/gitops/apps/ai-agents/k8s-monitor/deployment.yaml
    namespace: ai-agents

  news-monitor:
    type: syndicate
    source: kubani/syndicates/news_digest
    earthfile: kubani/syndicates/news_digest/Earthfile
    package: news-digest-syndicate
    image_name: news-monitor
    deployment: infrastructure/gitops/apps/ai-agents/news-monitor/deployment.yaml
    namespace: ai-agents

  # === MCP Servers ===
  temporal-mcp-server:
    type: mcp-server
    source: kubani/mcp/servers/temporal
    earthfile: kubani/mcp/servers/temporal/Earthfile
    package: temporal-mcp-server
    image_name: temporal-mcp-server
    deployment: infrastructure/gitops/apps/ai-agents/temporal-mcp-server/deployment.yaml
    namespace: ai-agents

  discord-mcp-server:
    type: mcp-server
    source: kubani/mcp/servers/discord
    earthfile: kubani/mcp/servers/discord/Earthfile
    package: discord-mcp-server
    image_name: discord-mcp-server
    deployment: infrastructure/gitops/apps/ai-agents/discord-mcp-server/deployment.yaml
    namespace: ai-agents

  memory-mcp-server:
    type: mcp-server
    source: kubani/mcp/servers/memory
    earthfile: kubani/mcp/servers/memory/Earthfile
    package: memory-mcp-server
    image_name: memory-mcp-server
    deployment: infrastructure/gitops/apps/ai-agents/memory-mcp-server/deployment.yaml
    namespace: ai-agents

  qdrant-mcp-server:
    type: mcp-server
    source: kubani/mcp/servers/qdrant
    earthfile: kubani/mcp/servers/qdrant/Earthfile
    package: qdrant-mcp-server
    image_name: qdrant-mcp-server
    deployment: infrastructure/gitops/apps/ai-agents/qdrant-mcp-server/deployment.yaml
    namespace: ai-agents

  skills-mcp-server:
    type: mcp-server
    source: kubani/mcp/servers/skills
    earthfile: kubani/mcp/servers/skills/Earthfile
    package: skills-mcp-server
    image_name: skills-mcp-server
    deployment: infrastructure/gitops/apps/ai-agents/skills-mcp-server/deployment.yaml
    namespace: ai-agents

  # === Nexus ===
  nexus-orchestrator:
    type: nexus
    source: kubani/nexus/orchestrator
    earthfile: kubani/nexus/orchestrator/Earthfile
    package: nexus-orchestrator
    image_name: kubani-nexus-orchestrator  # image name differs from component name
    deployment_name: nexus-orchestrator    # k8s Deployment metadata.name
    pod_selector: "app=nexus-orchestrator" # uses non-standard label (no kubernetes.io prefix)
    deployment: infrastructure/gitops/apps/nexus/orchestrator-deployment.yaml
    namespace: nexus

  nexus-gateway:
    type: nexus
    source: kubani/nexus/gateway
    earthfile: kubani/nexus/gateway/Earthfile
    package: nexus-gateway
    image_name: kubani-nexus-gateway
    deployment_name: nexus-gateway
    pod_selector: "app=nexus-gateway"
    deployment: infrastructure/gitops/apps/nexus/gateway-deployment.yaml
    namespace: nexus

  # === Platform ===
  registry:
    type: platform
    source: platform/registry
    earthfile: platform/registry/Earthfile
    package: registry
    image_name: kubani-registry
    deployment_name: metadata-registry  # k8s name differs from component name
    deployment: infrastructure/gitops/apps/registry/deployment.yaml
    namespace: ai-agents

  kubani-ui:
    type: platform
    source: platform/ui
    earthfile: platform/ui/Earthfile
    package: kubani-ui
    image_name: kubani-ui
    build_target: docker  # no separate push target; uses SAVE IMAGE --push in docker target
    deployment: infrastructure/gitops/apps/kubani-ui/deployment.yaml
    namespace: kubani-ui
```

- [ ] **Step 2: Commit**

```bash
git add components.yaml
git commit -m "feat: add components.yaml registry for kubani ship"
```

---

### Task 2: Create `ComponentRegistry` class

**Files:**
- Create: `kubani/cli/tests/test_components.py`
- Create: `kubani/cli/components.py`

- [ ] **Step 1: Write failing tests for ComponentRegistry**

```python
"""Tests for ComponentRegistry."""

import pytest
from pathlib import Path

from kubani.cli.components import ComponentInfo, ComponentRegistry


@pytest.fixture
def sample_yaml(tmp_path):
    """Create a minimal components.yaml for testing."""
    content = """\
components:
  k8s-monitor:
    type: syndicate
    source: kubani/syndicates/k8s_monitor
    earthfile: kubani/syndicates/k8s_monitor/Earthfile
    package: k8s-monitor-syndicate
    image_name: k8s-monitor
    deployment: infrastructure/gitops/apps/ai-agents/k8s-monitor/deployment.yaml
    namespace: ai-agents
  temporal-mcp-server:
    type: mcp-server
    source: kubani/mcp/servers/temporal
    earthfile: kubani/mcp/servers/temporal/Earthfile
    package: temporal-mcp-server
    image_name: temporal-mcp-server
    deployment: infrastructure/gitops/apps/ai-agents/temporal-mcp-server/deployment.yaml
    namespace: ai-agents
"""
    yaml_path = tmp_path / "components.yaml"
    yaml_path.write_text(content)
    return tmp_path


def test_load_components(sample_yaml):
    registry = ComponentRegistry(sample_yaml)
    assert len(registry.components) == 2


def test_get_component(sample_yaml):
    registry = ComponentRegistry(sample_yaml)
    comp = registry.get("k8s-monitor")
    assert comp is not None
    assert comp.name == "k8s-monitor"
    assert comp.type == "syndicate"
    assert comp.package == "k8s-monitor-syndicate"
    assert comp.namespace == "ai-agents"


def test_get_unknown_component(sample_yaml):
    registry = ComponentRegistry(sample_yaml)
    assert registry.get("does-not-exist") is None


def test_list_by_type(sample_yaml):
    registry = ComponentRegistry(sample_yaml)
    syndicates = registry.list_by_type("syndicate")
    assert len(syndicates) == 1
    assert syndicates[0].name == "k8s-monitor"
    mcp = registry.list_by_type("mcp-server")
    assert len(mcp) == 1


def test_component_source_path(sample_yaml):
    registry = ComponentRegistry(sample_yaml)
    comp = registry.get("k8s-monitor")
    assert comp.source_path(sample_yaml) == sample_yaml / "kubani" / "syndicates" / "k8s_monitor"


def test_component_earthfile_path(sample_yaml):
    registry = ComponentRegistry(sample_yaml)
    comp = registry.get("temporal-mcp-server")
    assert comp.earthfile_path(sample_yaml) == (
        sample_yaml / "kubani" / "mcp" / "servers" / "temporal" / "Earthfile"
    )


def test_component_deployment_path(sample_yaml):
    registry = ComponentRegistry(sample_yaml)
    comp = registry.get("k8s-monitor")
    expected = sample_yaml / "infrastructure" / "gitops" / "apps" / "ai-agents" / "k8s-monitor" / "deployment.yaml"
    assert comp.deployment_path(sample_yaml) == expected


def test_component_version_from_pyproject(sample_yaml):
    """Test version extraction from pyproject.toml."""
    # Create a fake pyproject.toml
    source_dir = sample_yaml / "kubani" / "syndicates" / "k8s_monitor"
    source_dir.mkdir(parents=True)
    (source_dir / "pyproject.toml").write_text('[project]\nname = "k8s-monitor"\nversion = "1.0.0"\n')

    registry = ComponentRegistry(sample_yaml)
    comp = registry.get("k8s-monitor")
    assert comp.get_version(sample_yaml) == "1.0.0"


def test_component_image_tag(sample_yaml):
    """Test image tag generation (version-sha)."""
    source_dir = sample_yaml / "kubani" / "syndicates" / "k8s_monitor"
    source_dir.mkdir(parents=True)
    (source_dir / "pyproject.toml").write_text('[project]\nname = "k8s-monitor"\nversion = "1.0.0"\n')

    registry = ComponentRegistry(sample_yaml)
    comp = registry.get("k8s-monitor")
    tag = comp.image_tag(sample_yaml, git_sha="abc1234")
    assert tag == "1.0.0-abc1234"


def test_all_names(sample_yaml):
    registry = ComponentRegistry(sample_yaml)
    names = registry.all_names()
    assert sorted(names) == ["k8s-monitor", "temporal-mcp-server"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/al/git/kubani && uv run pytest kubani/cli/tests/test_components.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kubani.cli.components'`

- [ ] **Step 3: Implement `ComponentRegistry`**

```python
"""Component registry for kubani ship.

Reads components.yaml and provides lookup/resolution for all deployable components.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml


def get_git_sha(project_root: Path) -> str:
    """Get short git SHA. Shared utility for ship and deploy."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


@dataclass
class ComponentInfo:
    """A deployable component."""

    name: str
    type: str  # syndicate, mcp-server, nexus, platform
    source: str  # relative path to source directory
    earthfile: str  # relative path to Earthfile
    package: str  # uv/pip package name
    image_name: str  # Docker image name (may differ from component name)
    deployment: str  # relative path to deployment.yaml
    namespace: str  # kubernetes namespace
    build_target: str = "push"  # Earthly target name (default: push)
    deployment_name: str = ""  # k8s Deployment metadata.name (defaults to component name)
    pod_selector: str = ""  # pod label selector override (e.g. "app=nexus-orchestrator")

    def __post_init__(self):
        if not self.deployment_name:
            self.deployment_name = self.name
        if not self.pod_selector:
            self.pod_selector = f"app.kubernetes.io/name={self.name}"

    def source_path(self, project_root: Path) -> Path:
        return project_root / self.source

    def earthfile_path(self, project_root: Path) -> Path:
        return project_root / self.earthfile

    def deployment_path(self, project_root: Path) -> Path:
        return project_root / self.deployment

    def get_version(self, project_root: Path) -> str:
        """Read version from the component's pyproject.toml."""
        pyproject = self.source_path(project_root) / "pyproject.toml"
        if not pyproject.exists():
            return "0.0.0"
        content = pyproject.read_text()
        match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        return match.group(1) if match else "0.0.0"

    def image_tag(self, project_root: Path, git_sha: str) -> str:
        """Generate image tag: version-sha."""
        version = self.get_version(project_root)
        return f"{version}-{git_sha}"


class ComponentRegistry:
    """Registry of all deployable components, loaded from components.yaml."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.components: dict[str, ComponentInfo] = {}
        self._load()

    def _load(self):
        yaml_path = self.project_root / "components.yaml"
        if not yaml_path.exists():
            return
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        for name, info in (data.get("components") or {}).items():
            self.components[name] = ComponentInfo(
                name=name,
                type=info["type"],
                source=info["source"],
                earthfile=info["earthfile"],
                package=info["package"],
                image_name=info.get("image_name", name),
                deployment=info["deployment"],
                namespace=info["namespace"],
                build_target=info.get("build_target", "push"),
                deployment_name=info.get("deployment_name", ""),
                pod_selector=info.get("pod_selector", ""),
            )

    def get(self, name: str) -> ComponentInfo | None:
        return self.components.get(name)

    def list_by_type(self, component_type: str) -> list[ComponentInfo]:
        return [c for c in self.components.values() if c.type == component_type]

    def all_names(self) -> list[str]:
        return list(self.components.keys())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/al/git/kubani && uv run pytest kubani/cli/tests/test_components.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add kubani/cli/components.py kubani/cli/tests/test_components.py
git commit -m "feat: add ComponentRegistry for unified component resolution"
```

---

## Chunk 2: Ship Orchestrator

### Task 3: Create `ShipOrchestrator`

The ship orchestrator runs the full pipeline: test -> build -> push -> patch deployment.yaml -> commit -> verify.

**Files:**
- Create: `kubani/cli/tests/test_ship.py`
- Create: `kubani/cli/ship.py`

- [ ] **Step 1: Write failing tests for ShipOrchestrator**

```python
"""Tests for ShipOrchestrator."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from kubani.cli.components import ComponentInfo, ComponentRegistry, get_git_sha
from kubani.cli.ship import ShipOrchestrator, ShipResult, ShipPhase


@pytest.fixture
def mock_component():
    return ComponentInfo(
        name="temporal-mcp-server",
        type="mcp-server",
        source="kubani/mcp/servers/temporal",
        earthfile="kubani/mcp/servers/temporal/Earthfile",
        package="temporal-mcp-server",
        image_name="temporal-mcp-server",
        deployment="infrastructure/gitops/apps/ai-agents/temporal-mcp-server/deployment.yaml",
        namespace="ai-agents",
    )


@pytest.fixture
def mock_registry(mock_component):
    reg = MagicMock(spec=ComponentRegistry)
    reg.get.return_value = mock_component
    reg.all_names.return_value = ["temporal-mcp-server"]
    reg.project_root = Path("/fake")
    return reg


def test_ship_result_defaults():
    result = ShipResult(component="test", phase=ShipPhase.PENDING)
    assert result.success is False
    assert result.image_tag == ""


def test_ship_phases_ordering():
    """Verify ship phases are in the expected order."""
    phases = list(ShipPhase)
    assert phases[0] == ShipPhase.PENDING
    assert phases[1] == ShipPhase.PREFLIGHT
    assert phases[2] == ShipPhase.BUMPING
    assert phases[3] == ShipPhase.TESTING
    assert phases[4] == ShipPhase.BUILDING
    assert phases[5] == ShipPhase.PUSHING
    assert phases[6] == ShipPhase.PATCHING
    assert phases[7] == ShipPhase.COMMITTING
    assert phases[8] == ShipPhase.VERIFYING
    assert phases[9] == ShipPhase.DONE
    assert phases[10] == ShipPhase.FAILED


@pytest.mark.asyncio
async def test_ship_unknown_component():
    reg = MagicMock(spec=ComponentRegistry)
    reg.get.return_value = None
    reg.all_names.return_value = []
    reg.project_root = Path("/fake")

    ship = ShipOrchestrator(reg)
    result = await ship.ship("nonexistent")
    assert result.phase == ShipPhase.FAILED
    assert "not found" in result.message.lower()


@pytest.mark.asyncio
async def test_ship_staged_changes_rejected(mock_registry):
    """Ship should fail if there are staged git changes."""
    ship = ShipOrchestrator(mock_registry)
    with patch.object(ship, "_check_clean_staging", return_value=False):
        result = await ship.ship("temporal-mcp-server")
    assert result.phase == ShipPhase.FAILED
    assert "staged" in result.message.lower()


@pytest.mark.asyncio
async def test_ship_test_failure(mock_registry):
    ship = ShipOrchestrator(mock_registry)
    with patch.object(ship, "_check_clean_staging", return_value=True), \
         patch.object(ship, "_bump_version", return_value=True), \
         patch.object(ship, "_run_tests", return_value=False):
        result = await ship.ship("temporal-mcp-server")
    assert result.phase == ShipPhase.FAILED
    assert "test" in result.message.lower()


@pytest.mark.asyncio
async def test_ship_build_failure(mock_registry):
    ship = ShipOrchestrator(mock_registry)
    with patch.object(ship, "_check_clean_staging", return_value=True), \
         patch.object(ship, "_bump_version", return_value=True), \
         patch.object(ship, "_run_tests", return_value=True), \
         patch.object(ship, "_build_and_push", return_value=(False, "")):
        result = await ship.ship("temporal-mcp-server")
    assert result.phase == ShipPhase.FAILED
    assert "build" in result.message.lower()


@pytest.mark.asyncio
async def test_ship_skip_test(mock_registry):
    """When skip_test=True, tests should not run."""
    ship = ShipOrchestrator(mock_registry)
    with patch.object(ship, "_check_clean_staging", return_value=True), \
         patch.object(ship, "_bump_version", return_value=True), \
         patch.object(ship, "_run_tests") as mock_test, \
         patch.object(ship, "_build_and_push", return_value=(True, "1.0.0-abc")), \
         patch.object(ship, "_patch_manifest", return_value=True), \
         patch.object(ship, "_commit_manifest", return_value=True), \
         patch.object(ship, "_git_push", return_value=True), \
         patch.object(ship, "_verify_deployment", return_value=True):
        result = await ship.ship("temporal-mcp-server", skip_test=True)
    mock_test.assert_not_called()
    assert result.phase == ShipPhase.DONE


@pytest.mark.asyncio
async def test_ship_skip_verify(mock_registry):
    """When skip_verify=True, verification should not run."""
    ship = ShipOrchestrator(mock_registry)
    with patch.object(ship, "_check_clean_staging", return_value=True), \
         patch.object(ship, "_bump_version", return_value=True), \
         patch.object(ship, "_run_tests", return_value=True), \
         patch.object(ship, "_build_and_push", return_value=(True, "1.0.0-abc")), \
         patch.object(ship, "_patch_manifest", return_value=True), \
         patch.object(ship, "_commit_manifest", return_value=True), \
         patch.object(ship, "_git_push", return_value=True), \
         patch.object(ship, "_verify_deployment") as mock_verify:
        result = await ship.ship("temporal-mcp-server", skip_verify=True)
    mock_verify.assert_not_called()
    assert result.phase == ShipPhase.DONE


@pytest.mark.asyncio
async def test_ship_dry_run(mock_registry):
    """Dry run should run preflight + tests only, no build/push/deploy."""
    ship = ShipOrchestrator(mock_registry)
    with patch.object(ship, "_check_clean_staging", return_value=True), \
         patch.object(ship, "_run_tests", return_value=True), \
         patch.object(ship, "_build_and_push") as mock_build:
        result = await ship.ship("temporal-mcp-server", dry_run=True)
    mock_build.assert_not_called()
    assert result.phase == ShipPhase.DONE
    assert "dry" in result.message.lower()


@pytest.mark.asyncio
async def test_ship_happy_path(mock_registry):
    """Full ship pipeline succeeds."""
    ship = ShipOrchestrator(mock_registry)
    with patch.object(ship, "_check_clean_staging", return_value=True), \
         patch.object(ship, "_bump_version", return_value=True), \
         patch.object(ship, "_run_tests", return_value=True), \
         patch.object(ship, "_build_and_push", return_value=(True, "1.0.1-abc1234")), \
         patch.object(ship, "_patch_manifest", return_value=True), \
         patch.object(ship, "_commit_manifest", return_value=True), \
         patch.object(ship, "_git_push", return_value=True), \
         patch.object(ship, "_verify_deployment", return_value=True):
        result = await ship.ship("temporal-mcp-server")
    assert result.phase == ShipPhase.DONE
    assert result.success is True
    assert result.image_tag == "1.0.1-abc1234"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/al/git/kubani && uv run pytest kubani/cli/tests/test_ship.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kubani.cli.ship'`

- [ ] **Step 3: Implement `ShipOrchestrator`**

```python
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

        # Step 0: Preflight — reject if there are staged changes that would
        # contaminate the manifest commit. Unstaged changes are OK (common with
        # multiple Claude Code sessions on desktop, CLI, VSCode).
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

        # Step 2+3: Build and push
        result.phase = ShipPhase.BUILDING
        print(f"  Building and pushing {component_name}...")
        success, image_tag = self._build_and_push(comp, version)
        if not success:
            result.phase = ShipPhase.FAILED
            result.message = f"Build/push failed for {component_name}"
            return result
        result.image_tag = image_tag
        result.steps_completed.append("build")

        # Step 4: Patch manifest (reuse existing GitOpsUpdater)
        result.phase = ShipPhase.PATCHING
        print(f"  Patching deployment manifest ({image_tag})...")
        if not self._patch_manifest(comp, image_tag):
            result.phase = ShipPhase.FAILED
            result.message = f"Failed to patch manifest for {component_name}"
            return result
        result.steps_completed.append("patch")

        # Step 5: Commit and push
        result.phase = ShipPhase.COMMITTING
        print(f"  Committing manifest change...")
        if not self._commit_manifest(comp, image_tag):
            result.phase = ShipPhase.FAILED
            result.message = f"Failed to commit manifest for {component_name}"
            return result
        result.steps_completed.append("commit")

        print(f"  Pushing to remote...")
        if not self._git_push():
            result.phase = ShipPhase.FAILED
            result.message = f"Failed to push manifest commit for {component_name}"
            return result
        result.steps_completed.append("push")

        # Step 6: Verify
        if not skip_verify:
            result.phase = ShipPhase.VERIFYING
            print(f"  Verifying deployment...")
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
        """Auto-bump patch version in pyproject.toml before building.

        Ensures every ship produces a unique version for clean rollback.
        Uses existing version_utils.bump_version().
        """
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
        new_content = content[:match.start(2)] + new_version + content[match.end(2):]
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
            result = subprocess.run(
                cmd, cwd=self.project_root, capture_output=False, timeout=300
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error(f"Tests timed out for {comp.name}")
            return False
        except Exception as e:
            logger.error(f"Error running tests for {comp.name}: {e}")
            return False

    def _build_and_push(
        self, comp: ComponentInfo, version: str | None = None
    ) -> tuple[bool, str]:
        """Build and push container image via Earthly."""
        git_sha = get_git_sha(self.project_root)
        image_tag = version or comp.image_tag(self.project_root, git_sha)

        # Use ./ prefix for Earthly local targets (required to avoid remote interpretation)
        earthfile_rel = Path(comp.earthfile).parent

        # Build and push in one step
        cmd = [
            "earthly",
            "--push",
            f"./{earthfile_rel}+{comp.build_target}",
            f"--VERSION={image_tag}",
        ]

        try:
            result = subprocess.run(
                cmd, cwd=self.project_root, capture_output=False, timeout=600
            )
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
        """Update deployment.yaml with new image tag.

        Uses comp.deployment_path() directly (not GitOpsUpdater, which hardcodes
        the ai-agents path). Matches image by comp.image_name to handle cases
        where image name differs from component name (e.g. kubani-nexus-orchestrator).
        """
        import re

        manifest_path = comp.deployment_path(self.project_root)
        if not manifest_path.exists():
            logger.error(f"Manifest not found: {manifest_path}")
            return False

        content = manifest_path.read_text()

        # Match image line using the component's actual image name
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
        """Commit the version bump and deployment.yaml change.

        Stages only the specific files we changed (manifest + pyproject.toml).
        Pre-commit hooks run with visible output — if they fail, the pipeline
        stops and shows the hook output so the developer can fix the issue.
        """
        manifest = comp.deployment_path(self.project_root)
        pyproject = comp.source_path(self.project_root) / "pyproject.toml"

        try:
            # Stage only the files we changed
            files_to_add = [str(manifest)]
            if pyproject.exists():
                files_to_add.append(str(pyproject))
            subprocess.run(
                ["git", "add"] + files_to_add,
                cwd=self.project_root,
                check=True,
            )
            # Do NOT use capture_output — let pre-commit hooks print to terminal
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
        """Wait for rollout and verify pod health.

        Uses comp.deployment_name for kubectl rollout (handles cases like
        registry -> metadata-registry). Uses comp.pod_selector for pod
        queries (handles nexus's non-standard `app:` labels).
        """
        kubectl_env = {**os.environ, "KUBECONFIG": KUBECONFIG}
        try:
            # Wait for rollout using the actual k8s deployment name
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

            # Check pod phases using the component's pod selector
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/al/git/kubani && uv run pytest kubani/cli/tests/test_ship.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add kubani/cli/ship.py kubani/cli/tests/test_ship.py
git commit -m "feat: add ShipOrchestrator for full test-build-deploy pipeline"
```

---

### Task 4: Wire `kubani ship` CLI command

**Files:**
- Modify: `kubani/cli/cli.py`

- [ ] **Step 1: Add `ship` command to cli.py**

Add between the `deploy` command and the "Skill and Agent Command Groups" section (after line ~529):

```python
# -----------------------------------------------------------------------------
# Ship Command
# -----------------------------------------------------------------------------


@app.command()
def ship(
    component: Annotated[str | None, typer.Argument(help="Component to ship (e.g. temporal-mcp-server)")] = None,
    version: Annotated[
        str | None,
        typer.Option("--version", help="Override version tag"),
    ] = None,
    skip_test: Annotated[
        bool, typer.Option("--skip-test", help="Skip running tests")
    ] = False,
    skip_verify: Annotated[
        bool, typer.Option("--skip-verify", help="Skip post-deploy verification")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Run tests only, don't build or deploy")
    ] = False,
    list_components: Annotated[
        bool, typer.Option("--list", "-l", help="List all shippable components")
    ] = False,
):
    """
    Ship a component: test -> build -> push -> deploy -> verify.

    This is the primary command for getting code changes into production.
    It runs the full pipeline for any component defined in components.yaml.

    Examples:
        kubani ship temporal-mcp-server
        kubani ship k8s-monitor --skip-test
        kubani ship nexus-orchestrator --dry-run
        kubani ship --list
    """
    from kubani.cli.components import ComponentRegistry
    from kubani.cli.ship import ShipOrchestrator

    project_root = find_project_root()
    registry = ComponentRegistry(project_root)

    if list_components:
        typer.echo("Shippable components:")
        for name in sorted(registry.all_names()):
            comp = registry.get(name)
            typer.echo(f"  {name:30s} ({comp.type})")
        raise typer.Exit()

    if component is None:
        typer.echo("Error: component name required (or use --list)")
        raise typer.Exit(1)

    typer.echo(f"Shipping {component}...")
    orchestrator = ShipOrchestrator(registry)
    result = asyncio.run(
        orchestrator.ship(
            component,
            skip_test=skip_test,
            skip_verify=skip_verify,
            dry_run=dry_run,
            version=version,
        )
    )

    if result.success:
        typer.echo(f"\n{result.message}")
    else:
        typer.echo(f"\nFailed: {result.message}", err=True)
        sys.exit(1)
```

- [ ] **Step 2: Verify `kubani ship --list` works**

Run: `cd /home/al/git/kubani && uv run kubani ship --list`
Expected: Lists all components from components.yaml with their types

- [ ] **Step 3: Verify `kubani ship temporal-mcp-server --dry-run` works**

Run: `cd /home/al/git/kubani && uv run kubani ship temporal-mcp-server --dry-run`
Expected: Runs tests for temporal-mcp-server, then prints "Dry run complete"

- [ ] **Step 4: Commit**

```bash
git add kubani/cli/cli.py
git commit -m "feat: add kubani ship command for full test-build-deploy pipeline"
```

---

## Chunk 3: Integrate ComponentRegistry into existing deploy.py

### Task 5: Update `DeploymentOrchestrator` to use `ComponentRegistry`

The existing `kubani deploy` command hardcodes component mappings. Wire it to use `ComponentRegistry` so both `deploy` and `ship` share the same source of truth.

**Files:**
- Modify: `kubani/cli/deploy.py`

- [ ] **Step 1: Update `LocalBuilder` to use ComponentRegistry**

Replace the hardcoded `target_map` dict (lines 600-606) and `_get_version` method (lines 608-660):

Old code (`LocalBuilder.__init__` around line 592-606):
```python
    def __init__(
        self,
        project_root: Path = None,
        registry: str = DEFAULT_REGISTRY,
    ):
        """Initialize the local builder."""
        self.project_root = project_root or Path.cwd()
        self.registry = registry
        # Map deployment targets to Earthly targets
        self.target_map = {
            "k8s-monitor": "k8s-monitor",
            "news-monitor": "news-monitor",
            "registry": "registry",
            "ui": "ui",
        }
```

New code:
```python
    def __init__(
        self,
        project_root: Path = None,
        registry: str = DEFAULT_REGISTRY,
    ):
        """Initialize the local builder."""
        self.project_root = project_root or Path.cwd()
        self.registry = registry
        # Load component registry for path resolution
        from kubani.cli.components import ComponentRegistry
        self._component_registry = ComponentRegistry(self.project_root)
```

- [ ] **Step 2: Update `_get_version` to use ComponentRegistry**

Replace the `_get_version` method body to try ComponentRegistry first:

```python
    def _get_version(self, target: str) -> str:
        """Get the current version from pyproject.toml or generate one."""
        comp = self._component_registry.get(target)
        if comp:
            version = comp.get_version(self.project_root)
            if version != "0.0.0":
                return version

        # Fallback: date-based version
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d.%H%M%S")
```

- [ ] **Step 3: Update `_get_earthly_target` to use ComponentRegistry**

Find the method that resolves Earthly targets and update it. The existing method (around line 660-700) uses hardcoded paths. Replace the target resolution:

```python
    def _get_earthly_target(self, target: str) -> str:
        """Get the Earthly build target for a component."""
        comp = self._component_registry.get(target)
        if comp:
            earthfile_dir = comp.earthfile_path(self.project_root).parent
            rel_path = earthfile_dir.relative_to(self.project_root)
            return f"./{rel_path}+docker"

        # Fallback for agents/ directory convention
        agent_earthfile = self.project_root / "agents" / target / "Earthfile"
        if agent_earthfile.exists():
            return f"./agents/{target}+docker"

        raise FileNotFoundError(f"No Earthfile found for {target}")
```

- [ ] **Step 4: Update `DeploymentTarget` enum to be dynamic**

Add an `OTHER` variant to the enum and update the target parsing in `deploy()`:

```python
class DeploymentTarget(Enum):
    """Deployment targets."""
    K8S_MONITOR = "k8s-monitor"
    NEWS_MONITOR = "news-monitor"
    REGISTRY = "registry"
    UI = "ui"
    ALL = "all"
    OTHER = "other"  # Any component from components.yaml
```

Update the target parsing in `DeploymentOrchestrator.deploy()` (around line 1132-1147):

```python
        # Parse target
        try:
            deploy_target = DeploymentTarget(target)
        except ValueError:
            deploy_target = DeploymentTarget.OTHER

        # ...

        # Determine targets to build/deploy
        if deploy_target == DeploymentTarget.ALL:
            targets = ["k8s-monitor", "news-monitor"]
        else:
            targets = [target]
```

- [ ] **Step 5: Run existing deploy tests to check for regressions**

Run: `cd /home/al/git/kubani && uv run pytest kubani/cli/tests/ -v -k "deploy or build" --tb=short`
Expected: Existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add kubani/cli/deploy.py
git commit -m "refactor: use ComponentRegistry in deploy.py for path resolution"
```

---

## Chunk 4: Justfile Cleanup

### Task 6: Remove deprecated `kdev-*` commands

These 10 commands (lines ~449-497) just print deprecation warnings and delegate. They've been deprecated long enough.

**Files:**
- Modify: `justfile`

- [ ] **Step 1: Delete all `kdev-*` recipes**

Remove these lines from the justfile (approximately lines 449-497):

```
# [DEPRECATED] Use 'kubani run' directly
kdev-run agent *args:
    ...
kdev-test agent *args:
    ...
kdev-eval agent *args:
    ...
kdev-dashboard:
    ...
kdev-trace agent *args:
    ...
kdev-metrics agent *args:
    ...
kdev-build agent *args:
    ...
kdev-deploy agent *args:
    ...
kdev-new name *args:
    ...
kdev-skills-validate:
    ...
```

- [ ] **Step 2: Verify justfile still parses**

Run: `cd /home/al/git/kubani && just --list | head -20`
Expected: Lists commands without any `kdev-*` entries

- [ ] **Step 3: Commit**

```bash
git add justfile
git commit -m "chore: remove 10 deprecated kdev-* commands from justfile"
```

---

### Task 7: Collapse MCP test variants

Replace 12 MCP test recipes with 2 using arguments.

**Files:**
- Modify: `justfile`

- [ ] **Step 1: Replace MCP test section**

Delete the entire MCP Server Testing section (lines ~1086-1201, from `# MCP Server Testing` to the `mcp-test-list` recipe). Replace with:

```just
# =============================================================================
# MCP Server Testing
# =============================================================================

# Run MCP server tests (optionally filter by server and/or test type)
# Examples: just mcp-test, just mcp-test temporal, just mcp-test temporal unit
mcp-test server="" type="":
    #!/usr/bin/env bash
    set -euo pipefail
    args=""
    if [[ -n "{{server}}" ]]; then
        args="--server {{server}}"
    else
        args="--all"
    fi
    if [[ -n "{{type}}" ]]; then
        args="$args --{{type}}"
    fi
    echo "=== Running MCP tests ($args) ==="
    cd kubani/mcp/servers && uv run python test_runner.py $args

# Run post-deployment tests for MCP servers
mcp-test-deployed:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Running post-deployment tests for MCP servers ==="
    cd kubani/mcp/servers && uv run python test_runner.py --deployed
```

- [ ] **Step 2: Verify the new recipes work**

Run: `cd /home/al/git/kubani && just mcp-test --dry-run 2>&1 | head -5`
Expected: Shows the bash script that would run

- [ ] **Step 3: Commit**

```bash
git add justfile
git commit -m "chore: collapse 12 MCP test recipes into 2 with arguments"
```

---

### Task 8: Remove dead version management recipes

The `bump*` and `changelog*` recipes (lines ~1042-1083) reference `scripts/bump-version.py` and `scripts/generate-changelog.py` which do not exist. These are ~40 lines of dead code. Version bumping is now handled automatically by `kubani ship`.

**Files:**
- Modify: `justfile`

- [ ] **Step 1: Delete all `bump*`, `agent-versions`, and `changelog*` recipes**

Remove these recipes (approximately lines 1042-1083):

```
agent-versions:
    ...
bump agent bump_type="patch":
    ...
bump-auto agent:
    ...
bump-all:
    ...
bump-preview agent:
    ...
changelog *args:
    ...
changelog-preview:
    ...
```

- [ ] **Step 2: Verify justfile still parses**

Run: `cd /home/al/git/kubani && just --list | head -20`
Expected: No `bump*`, `agent-versions`, or `changelog*` entries

- [ ] **Step 3: Commit**

```bash
git add justfile
git commit -m "chore: remove 7 dead version management recipes from justfile"
```

---

### Task 9: Remove deprecated cluster/status commands

These delegate to `kubani cluster` commands.

**Files:**
- Modify: `justfile`

- [ ] **Step 1: Delete deprecated cluster recipes**

Remove these recipes (approximately lines 688-710):

```
# Provision the cluster ...
provision *args:
    ...
# Show cluster status ...
status:
    ...
# Discover Tailscale nodes ...
discover *args:
    ...
# Add a node to inventory ...
add-node hostname ip *args:
    ...
# Remove a node from inventory ...
remove-node hostname *args:
    ...
```

- [ ] **Step 2: Verify justfile still parses**

Run: `cd /home/al/git/kubani && just --list | wc -l`
Expected: Fewer lines than before

- [ ] **Step 3: Commit**

```bash
git add justfile
git commit -m "chore: remove 5 deprecated cluster commands from justfile"
```

---

### Task 10: Add `ship` recipe to justfile

A thin wrapper around `kubani ship` for discoverability.

**Files:**
- Modify: `justfile`

- [ ] **Step 1: Add ship recipe after the Agent Development section**

Add after the `sync-agent` recipe:

```just
# Ship a component (test -> build -> push -> deploy -> verify)
ship component *args:
    kubani ship {{component}} {{args}}

# List all shippable components
ship-list:
    kubani ship --list
```

- [ ] **Step 2: Verify it works**

Run: `cd /home/al/git/kubani && just ship --list`
Expected: Shows component list from components.yaml

- [ ] **Step 3: Commit**

```bash
git add justfile
git commit -m "feat: add just ship recipe wrapping kubani ship"
```

---

### Task 11: Final justfile audit and line count

**Files:**
- Review: `justfile`

- [ ] **Step 1: Count lines before and after**

Run: `cd /home/al/git/kubani && wc -l justfile`
Expected: Approximately 990 lines (down from ~1200). The reduction is ~210 lines:
- kdev-* removal: ~48 lines
- MCP test collapse: ~100 lines
- Cluster command removal: ~22 lines
- Dead bump/changelog removal: ~40 lines

Note: The remaining ~990 lines include actively-used sections that should stay:
- `model-*` section (~150 lines) — actively used for model management
- `flux-*` section (~60 lines) — kubectl shortcuts for GitOps
- `secrets-*` section (~45 lines) — SOPS workflow helpers
- `dev-*` section (~100 lines) — local development

- [ ] **Step 2: Run `just --list` and verify all remaining commands work**

Run: `cd /home/al/git/kubani && just --list`
Expected: Clean list with no deprecated entries

- [ ] **Step 3: Final commit if any cleanup needed**

```bash
git add justfile
git commit -m "chore: finalize justfile cleanup"
```

---

## Chunk 5: Update Claude Code Instructions

### Task 12: Update CLAUDE.md, rules, commands, and skills to use `kubani ship`

Claude Code reads these files at conversation start and when touching matching paths. If they still reference the old manual workflow (`just build`, `kubani deploy`, manual manifest editing), Claude will keep using it. All 6 files must be updated so `kubani ship` is the primary path.

**Files:**
- Modify: `.claude/CLAUDE.md`
- Modify: `.claude/rules/development-workflow.md`
- Modify: `.claude/rules/agents.md`
- Modify: `.claude/rules/gitops.md`
- Modify: `.claude/commands/deploy.md`
- Modify: `.claude/skills/local-development/SKILL.md`

- [ ] **Step 1: Update `.claude/CLAUDE.md` Quick Reference**

Replace the build/deploy section in the Quick Reference block:

Old:
```bash
# Building & deploying
just build <agent>
kubani deploy --agent <agent> --wait
```

New:
```bash
# Ship (test -> build -> push -> deploy -> verify)
kubani ship <component>           # Full pipeline
kubani ship <component> --dry-run # Tests only
kubani ship --list                # List components
```

Also update the 4-stage workflow reference:
Old:
```
3. **Container Build** — `just build <agent>`, smoke test the image
4. **Deploy & Validate** — Push, Flux deploys, check pods/logs, smoke test
```

New:
```
3. **Ship** — `kubani ship <component>` (builds, pushes, patches manifest, commits, pushes, verifies)
```

- [ ] **Step 2: Rewrite `.claude/rules/development-workflow.md`**

Replace the entire file with:

```markdown
# Development Workflow Rule

When making code changes that will be deployed:

1. **Test locally first** before shipping
   - Use egress config (`config/local.yaml` or `.env`) to test against cluster services
   - Run `just test-unit` and `just lint` before proceeding
   - For prompt/behavior changes: run the agent locally and verify the change works

2. **Ship via `kubani ship`** — this is the primary deployment command
   - `kubani ship <component>` runs the full pipeline: bump version -> test -> build -> push -> patch manifest -> commit -> git push -> verify
   - `kubani ship <component> --dry-run` to validate tests without deploying
   - `kubani ship <component> --skip-test` if you already tested locally
   - `kubani ship --list` to see all shippable components

3. **Never manually edit deployment manifests** to update image tags
   - `kubani ship` handles manifest patching, version bumping, and git commit/push
   - Manual edits bypass version tracking and pre-commit hooks

4. **If ship fails**, read the output — it stops at the failing step with a clear message
   - Test failure: fix the test, ship again
   - Pre-commit hook failure: fix the issue, ship again
   - Verify failure: check pod logs, fix forward with another ship
```

- [ ] **Step 3: Update `.claude/rules/agents.md` versioning and building sections**

Replace the Versioning section (lines 83-93):

Old:
```markdown
## Versioning

- Version is in `pyproject.toml`: `version = "0.1.0"`
- Image tags use `{version}-{git-sha}` format
- Bump version before deploying changes: `just bump <agent> patch|minor|major`

## Building

- Use kubani: `kubani build <agent>`
- Or Earthly: `earthly ./agents/<agent>+docker`
- Core changes trigger rebuild of ALL agents
```

New:
```markdown
## Versioning & Shipping

- Version is in `pyproject.toml`: `version = "0.1.0"`
- Image tags use `{version}-{git-sha}` format
- `kubani ship` auto-bumps patch version before each build
- Ship a component: `kubani ship <component-name>`
- Core framework changes require shipping ALL dependent agents
```

Also update the Development Tool section (lines 12-20) to include ship:

```bash
kubani run <agent> --hot-reload   # Run locally
kubani test <agent>               # Run tests
kubani eval <agent>               # Run evaluation
kubani ship <agent>               # Ship: test -> build -> deploy (preferred)
```

- [ ] **Step 4: Update `.claude/rules/gitops.md` Image Updates section**

Replace the Image Updates section:

Old:
```markdown
## Image Updates

When updating deployment images:
1. Update ALL image references in the deployment
2. Use consistent tag format: `{version}-{sha}`
3. Commit with message: `chore(gitops): deploy <agent>:<version>`
```

New:
```markdown
## Image Updates

Use `kubani ship <component>` to update deployment images — it handles manifest patching, version bumping, commit, and push automatically. Do NOT manually edit image tags in deployment manifests.

Manual manifest edits are only appropriate for non-image changes (env vars, resources, probes, etc.).
```

- [ ] **Step 5: Update `.claude/commands/deploy.md`**

Add a deprecation notice at the top and redirect to ship:

```markdown
# Deploy Agent

> **Prefer `kubani ship <component>`** — it handles the full pipeline (version bump, test, build, push, manifest patch, commit, push, verify). Use `/deploy` only for rollbacks or deploying a specific pre-built version.
```

- [ ] **Step 6: Update `.claude/skills/local-development/SKILL.md`**

Find references to `kubani deploy --agent` and add a note that `kubani ship` is preferred for the full pipeline. Keep `kubani deploy` references for context but mark as legacy.

- [ ] **Step 7: Commit**

```bash
git add .claude/CLAUDE.md .claude/rules/development-workflow.md .claude/rules/agents.md .claude/rules/gitops.md .claude/commands/deploy.md .claude/skills/local-development/SKILL.md
git commit -m "docs: update Claude Code instructions to use kubani ship workflow"
```

---

## Deferred Items

These were identified during review but deferred from this plan's scope:

- **Flux reconciliation trigger.** After push, Flux polls on an interval (~5min). Could add `flux reconcile kustomization apps` after push. Deferred: the wait is acceptable for v1; can add as a `--reconcile` flag later.
- **Rollback on failed verify.** If `_verify_deployment` fails, the manifest commit is already pushed. Could add `git revert` + push. Deferred: manual rollback is sufficient for now; auto-bump ensures a unique version to roll forward to.
- **Ship vs deploy UX.** Both commands overlap. Intent: `ship` is the primary command; `deploy` continues to work but should get a deprecation notice in a follow-up. Deferred: don't want to change existing workflows in the same PR.
- **Nexus label standardization.** Nexus deployments use `app: name` instead of `app.kubernetes.io/name: name`. Handled via `pod_selector` field for now, but should standardize the labels in a follow-up GitOps PR.
- **components.yaml validation in CI.** Stale paths will rot silently. Deferred: add `kubani ship --validate` in a follow-up PR with CI integration.
- **Ship multiple components.** `kubani ship --type syndicate` or multi-arg support. Deferred: get single-component shipping working first.
- **Dependency-aware shipping.** `kubani ship --changed` via git diff. Deferred: requires dependency graph analysis, out of scope for v1.
- **Branch strategy.** Plan assumes shipping from main. Deferred: document the expected workflow (commit to main) rather than adding branch detection logic.
- **test_command override.** Some components may need custom test commands. Deferred: all current components use pytest; add the field when a concrete need arises.
- **Pre-ship hooks.** Linting/type-checking before ship. Deferred: pre-commit hooks already run during the commit step; don't duplicate.
- **Rich progress output.** Replace print() with Rich spinners. Deferred: cosmetic improvement, not blocking.
- **Drop async for sync.** Ship pipeline is fully synchronous subprocess calls. Deferred: works correctly as-is; refactor if we ever need true async (e.g., parallel builds).

---

## Summary

| Task | What | Files Changed | Tests |
|------|------|---------------|-------|
| 1 | Create `components.yaml` | 1 new | - |
| 2 | `ComponentRegistry` class | 2 new | 10 tests |
| 3 | `ShipOrchestrator` class | 2 new | 11 tests |
| 4 | Wire `kubani ship` CLI command | 1 modified | Manual verification |
| 5 | Integrate ComponentRegistry into deploy.py | 1 modified | Regression check |
| 6 | Remove deprecated `kdev-*` commands | justfile | - |
| 7 | Collapse MCP test recipes (12→2) | justfile | - |
| 8 | Remove dead bump/changelog recipes | justfile | - |
| 9 | Remove deprecated cluster commands | justfile | - |
| 10 | Add `ship` recipe | justfile | Manual verification |
| 11 | Final audit | justfile | Line count check |
| 12 | Update Claude Code instructions | 6 modified | Manual verification |

**Justfile reduction:** ~1200 lines → ~990 lines (~18% reduction, removing ~210 lines of dead/deprecated recipes)
**New capability:** `kubani ship <any-component>` — one command for the full pipeline with auto version bump
**Test coverage:** 21 new unit tests across 2 test files
