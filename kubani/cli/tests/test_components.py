"""Tests for ComponentRegistry."""


import pytest

from kubani.cli.components import ComponentRegistry


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
    expected = (
        sample_yaml
        / "infrastructure"
        / "gitops"
        / "apps"
        / "ai-agents"
        / "k8s-monitor"
        / "deployment.yaml"
    )
    assert comp.deployment_path(sample_yaml) == expected


def test_component_version_from_pyproject(sample_yaml):
    """Test version extraction from pyproject.toml."""
    source_dir = sample_yaml / "kubani" / "syndicates" / "k8s_monitor"
    source_dir.mkdir(parents=True)
    (source_dir / "pyproject.toml").write_text(
        '[project]\nname = "k8s-monitor"\nversion = "1.0.0"\n'
    )

    registry = ComponentRegistry(sample_yaml)
    comp = registry.get("k8s-monitor")
    assert comp.get_version(sample_yaml) == "1.0.0"


def test_component_image_tag(sample_yaml):
    """Test image tag generation (version-sha)."""
    source_dir = sample_yaml / "kubani" / "syndicates" / "k8s_monitor"
    source_dir.mkdir(parents=True)
    (source_dir / "pyproject.toml").write_text(
        '[project]\nname = "k8s-monitor"\nversion = "1.0.0"\n'
    )

    registry = ComponentRegistry(sample_yaml)
    comp = registry.get("k8s-monitor")
    tag = comp.image_tag(sample_yaml, git_sha="abc1234")
    assert tag == "1.0.0-abc1234"


def test_all_names(sample_yaml):
    registry = ComponentRegistry(sample_yaml)
    names = registry.all_names()
    assert sorted(names) == ["k8s-monitor", "temporal-mcp-server"]
