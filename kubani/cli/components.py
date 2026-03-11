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
