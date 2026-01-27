"""Tests for the skill publisher."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kubani.framework.registry.models import ResourceInfo, ResourceStatus, VersionInfo
from kubani.framework.registry.skill_publisher import SkillPublisher


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
def skill_publisher(mock_registry_client, mock_oci_client):
    """Create a skill publisher with mocks."""
    with patch("kubani.framework.registry.skill_publisher.get_config") as mock_config:
        mock_config.return_value.registry.url = "http://localhost:8000"
        publisher = SkillPublisher(
            registry_client=mock_registry_client,
            oci_registry_url="localhost:5000",
            agent_name="test-agent",
        )
        publisher._oci_client = mock_oci_client
        return publisher


@pytest.mark.asyncio
async def test_publish_new_skill(skill_publisher, mock_registry_client, mock_oci_client):
    """Test publishing a new skill."""
    # Mock registry responses
    mock_registry_client.get_skill.return_value = None  # Skill doesn't exist

    mock_registry_client.create_skill.return_value = ResourceInfo(
        id="general/general/test-skill",
        name="test-skill",
        resource_type="skill",
        description="A test skill",
        current_version=None,
        oci_repository="localhost:5000/skills/test-skill",
        status=ResourceStatus.DRAFT,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={"domain": "general", "category": "general"},
    )

    mock_registry_client.create_skill_version.return_value = VersionInfo(
        version="0.1.0",
        oci_tag="v0.1.0",
        oci_digest="sha256:abc123",
        status=ResourceStatus.DRAFT,
        created_at=datetime.now(),
        created_by="test-agent",
    )

    # Publish
    skill_info, version_info = await skill_publisher.publish_skill(
        name="test-skill",
        description="A test skill",
        instructions="# Test Instructions\n\nDo the thing.",
        domain="general",
        category="general",
        version="0.1.0",
    )

    # Verify
    assert skill_info.name == "test-skill"
    assert version_info.version == "0.1.0"
    assert version_info.status == ResourceStatus.DRAFT

    # Verify OCI push was called
    mock_oci_client.push.assert_called_once()


@pytest.mark.asyncio
async def test_publish_existing_skill(skill_publisher, mock_registry_client, mock_oci_client):
    """Test publishing a new version of an existing skill."""
    # Mock registry responses - skill exists
    mock_registry_client.get_skill.return_value = ResourceInfo(
        id="general/general/test-skill",
        name="test-skill",
        resource_type="skill",
        description="A test skill",
        current_version="0.1.0",
        oci_repository="localhost:5000/skills/test-skill",
        status=ResourceStatus.PRODUCTION,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={"domain": "general", "category": "general"},
    )

    mock_registry_client.create_skill_version.return_value = VersionInfo(
        version="0.2.0",
        oci_tag="v0.2.0",
        oci_digest="sha256:def456",
        status=ResourceStatus.DRAFT,
        created_at=datetime.now(),
        created_by="test-agent",
    )

    # Publish new version
    skill_info, version_info = await skill_publisher.publish_skill(
        name="test-skill",
        description="Updated test skill",
        instructions="# Updated Instructions",
        version="0.2.0",
    )

    # Verify - should not create new skill
    mock_registry_client.create_skill.assert_not_called()
    assert version_info.version == "0.2.0"


@pytest.mark.asyncio
async def test_publish_skill_with_scripts(skill_publisher, mock_registry_client, mock_oci_client):
    """Test publishing a skill with scripts and references."""
    mock_registry_client.get_skill.return_value = None

    mock_registry_client.create_skill.return_value = ResourceInfo(
        id="k8s/diagnostic/check-pod",
        name="check-pod",
        resource_type="skill",
        description="Check pod health",
        current_version=None,
        oci_repository="localhost:5000/skills/check-pod",
        status=ResourceStatus.DRAFT,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={"domain": "k8s", "category": "diagnostic"},
    )

    mock_registry_client.create_skill_version.return_value = VersionInfo(
        version="1.0.0",
        oci_tag="v1.0.0",
        oci_digest="sha256:xyz789",
        status=ResourceStatus.DRAFT,
        created_at=datetime.now(),
        created_by="test-agent",
    )

    # Publish with scripts
    skill_info, version_info = await skill_publisher.publish_skill(
        name="check-pod",
        description="Check pod health",
        instructions="# Check Pod\n\nRun the check script.",
        domain="k8s",
        category="diagnostic",
        version="1.0.0",
        scripts={
            "check.sh": "#!/bin/bash\nkubectl get pod $1",
        },
        references={
            "example.yaml": "apiVersion: v1\nkind: Pod",
        },
    )

    assert skill_info.name == "check-pod"
    mock_oci_client.push.assert_called_once()


@pytest.mark.asyncio
async def test_publish_skill_with_metadata(skill_publisher, mock_registry_client, mock_oci_client):
    """Test publishing a skill with custom metadata."""
    mock_registry_client.get_skill.return_value = None

    mock_registry_client.create_skill.return_value = ResourceInfo(
        id="general/general/custom-skill",
        name="custom-skill",
        resource_type="skill",
        description="Custom skill",
        current_version=None,
        oci_repository="localhost:5000/skills/custom-skill",
        status=ResourceStatus.DRAFT,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={
            "domain": "general",
            "category": "general",
            "author": "test-agent",
            "tags": ["test", "example"],
        },
    )

    mock_registry_client.create_skill_version.return_value = VersionInfo(
        version="0.1.0",
        oci_tag="v0.1.0",
        oci_digest="sha256:meta123",
        status=ResourceStatus.DRAFT,
        created_at=datetime.now(),
        created_by="test-agent",
    )

    skill_info, version_info = await skill_publisher.publish_skill(
        name="custom-skill",
        description="Custom skill",
        instructions="# Custom\n\nDo custom things.",
        metadata={
            "author": "test-agent",
            "tags": ["test", "example"],
        },
    )

    # Verify create_skill was called with metadata
    call_kwargs = mock_registry_client.create_skill.call_args.kwargs
    assert "author" in call_kwargs.get("metadata", {})


def test_get_skill_publisher():
    """Test the factory function."""
    from kubani.framework.registry.skill_publisher import get_skill_publisher

    with patch("kubani.framework.registry.skill_publisher.get_config") as mock_config:
        mock_config.return_value.registry.url = "http://localhost:8000"
        publisher = get_skill_publisher("my-agent")

    assert publisher.agent_name == "my-agent"
