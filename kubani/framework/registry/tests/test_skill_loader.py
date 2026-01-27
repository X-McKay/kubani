"""Tests for the skill loader."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kubani.framework.registry.models import ResourceInfo, ResourceStatus, VersionInfo
from kubani.framework.registry.skill_loader import SkillLoader


@pytest.fixture
def mock_registry_client():
    """Create a mock registry client."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_oci_client():
    """Create a mock OCI client."""
    return MagicMock()


@pytest.fixture
def skill_loader(mock_registry_client, mock_oci_client, tmp_path):
    """Create a skill loader with mocks."""
    with patch("kubani.framework.registry.skill_loader.get_config") as mock_config:
        mock_config.return_value.registry.url = "http://localhost:8000"
        loader = SkillLoader(
            registry_client=mock_registry_client,
            cache_dir=tmp_path / "cache",
            oci_registry_url="localhost:5000",
        )
        loader._oci_client = mock_oci_client
        return loader


@pytest.mark.asyncio
async def test_load_skill_from_cache(skill_loader, mock_registry_client, tmp_path):
    """Test loading a skill that's already cached."""
    # Setup cache
    cache_path = tmp_path / "cache" / "abc123def456"
    cache_path.mkdir(parents=True)
    (cache_path / "SKILL.md").write_text(
        """---
name: test-skill
description: A test skill
---

# Test Skill Instructions
"""
    )

    # Setup mock responses
    mock_registry_client.get_skill.return_value = ResourceInfo(
        id="general/general/test-skill",
        name="test-skill",
        resource_type="skill",
        description="A test skill",
        current_version="1.0.0",
        oci_repository="localhost:5000/skills/test-skill",
        status=ResourceStatus.PRODUCTION,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={"domain": "general", "category": "general"},
    )

    mock_registry_client.get_skill_version.return_value = VersionInfo(
        version="1.0.0",
        oci_tag="v1.0.0",
        oci_digest="sha256:abc123def456",
        status=ResourceStatus.PRODUCTION,
        created_at=datetime.now(),
        created_by="human",
        promoted_at=datetime.now(),
        promoted_by="human",
    )

    # Load skill
    skill = await skill_loader.load_skill("test-skill")

    assert skill is not None
    assert skill.name == "test-skill"
    assert skill.description == "A test skill"
    assert "Test Skill Instructions" in skill.instructions


@pytest.mark.asyncio
async def test_load_skill_pulls_from_oci(
    skill_loader, mock_registry_client, mock_oci_client, tmp_path
):
    """Test loading a skill that needs to be pulled."""
    # Setup mock responses
    mock_registry_client.get_skill.return_value = ResourceInfo(
        id="k8s/diagnostic/test-skill",
        name="test-skill",
        resource_type="skill",
        description="A test skill",
        current_version="1.0.0",
        oci_repository="localhost:5000/skills/test-skill",
        status=ResourceStatus.PRODUCTION,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={"domain": "k8s", "category": "diagnostic"},
    )

    mock_registry_client.get_skill_version.return_value = VersionInfo(
        version="1.0.0",
        oci_tag="v1.0.0",
        oci_digest="sha256:newdigest123",
        status=ResourceStatus.PRODUCTION,
        created_at=datetime.now(),
        created_by="human",
        promoted_at=datetime.now(),
        promoted_by="human",
    )

    # Mock OCI pull to create files
    def mock_pull(target, outdir):
        out_path = Path(outdir)
        (out_path / "SKILL.md").write_text(
            """---
name: test-skill
description: Pulled skill
---

# Pulled Instructions
"""
        )

    mock_oci_client.pull.side_effect = mock_pull

    # Load skill
    skill = await skill_loader.load_skill("test-skill")

    assert skill is not None
    assert skill.name == "test-skill"
    mock_oci_client.pull.assert_called_once()


@pytest.mark.asyncio
async def test_load_skill_not_found(skill_loader, mock_registry_client):
    """Test loading a skill that doesn't exist."""
    mock_registry_client.get_skill.return_value = None

    skill = await skill_loader.load_skill("nonexistent-skill")

    assert skill is None


@pytest.mark.asyncio
async def test_load_skill_no_version(skill_loader, mock_registry_client):
    """Test loading a skill with no version available."""
    mock_registry_client.get_skill.return_value = ResourceInfo(
        id="general/general/test-skill",
        name="test-skill",
        resource_type="skill",
        description="A test skill",
        current_version=None,
        oci_repository=None,
        status=ResourceStatus.DRAFT,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={},
    )
    mock_registry_client.get_skill_version.return_value = None

    skill = await skill_loader.load_skill("test-skill")

    assert skill is None


@pytest.mark.asyncio
async def test_list_available_skills(skill_loader, mock_registry_client):
    """Test listing available skills."""
    mock_registry_client.list_skills.return_value = [
        ResourceInfo(
            id="k8s/diagnostic/skill1",
            name="skill1",
            resource_type="skill",
            description="First skill",
            current_version="1.0.0",
            oci_repository="localhost:5000/skills/skill1",
            status=ResourceStatus.PRODUCTION,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"domain": "k8s", "category": "diagnostic"},
        ),
        ResourceInfo(
            id="general/general/skill2",
            name="skill2",
            resource_type="skill",
            description="Second skill",
            current_version="2.0.0",
            oci_repository="localhost:5000/skills/skill2",
            status=ResourceStatus.PRODUCTION,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"domain": "general", "category": "general"},
        ),
    ]

    skills = await skill_loader.list_available_skills()

    assert len(skills) == 2
    assert skills[0]["name"] == "skill1"
    assert skills[1]["name"] == "skill2"


def test_clear_cache_all(skill_loader, tmp_path):
    """Test clearing the entire cache."""
    # Create some cache entries
    cache_dir = tmp_path / "cache"
    (cache_dir / "abc123").mkdir(parents=True)
    (cache_dir / "def456").mkdir(parents=True)
    (cache_dir / "abc123" / "SKILL.md").write_text("test")
    (cache_dir / "def456" / "SKILL.md").write_text("test")

    skill_loader.clear_cache()

    # Cache dir should be empty but exist
    assert cache_dir.exists()
    assert len(list(cache_dir.iterdir())) == 0


def test_is_cached(skill_loader, tmp_path):
    """Test cache checking."""
    _ = tmp_path / "cache"  # Used by fixture indirectly
    digest = "sha256:abc123def456789"

    # Not cached initially
    assert not skill_loader._is_cached(digest)

    # Create cache entry
    cache_path = skill_loader._get_cache_path(digest)
    cache_path.mkdir(parents=True)
    (cache_path / "SKILL.md").write_text("test")

    # Now cached
    assert skill_loader._is_cached(digest)


def test_parse_skill_directory_with_scripts(skill_loader, tmp_path):
    """Test parsing a skill directory with scripts and references."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()

    # Create SKILL.md
    (skill_dir / "SKILL.md").write_text(
        """---
name: test-skill
description: A test skill
metadata:
  domain: k8s
  category: diagnostic
---

# Test Instructions

This is the skill body.
"""
    )

    # Create scripts directory
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "check.sh").write_text("#!/bin/bash\necho test")

    # Create references directory
    refs_dir = skill_dir / "references"
    refs_dir.mkdir()
    (refs_dir / "example.yaml").write_text("key: value")

    # Create mock info objects
    skill_info = ResourceInfo(
        id="k8s/diagnostic/test-skill",
        name="test-skill",
        resource_type="skill",
        description="A test skill",
        current_version="1.0.0",
        oci_repository="localhost:5000/skills/test-skill",
        status=ResourceStatus.PRODUCTION,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={},
    )
    version_info = VersionInfo(
        version="1.0.0",
        oci_tag="v1.0.0",
        oci_digest="sha256:test",
        status=ResourceStatus.PRODUCTION,
        created_at=datetime.now(),
        created_by="human",
    )

    # Parse
    content = skill_loader._parse_skill_directory(skill_dir, skill_info, version_info)

    assert content.name == "test-skill"
    assert content.description == "A test skill"
    assert content.domain == "k8s"
    assert content.category == "diagnostic"
    assert "Test Instructions" in content.instructions
    assert "check.sh" in content.scripts
    assert "example.yaml" in content.references
