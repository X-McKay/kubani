"""Tests for migration and export commands."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_registry_client():
    """Create a mock registry client."""
    client = MagicMock()
    client.get_skill = AsyncMock(return_value=None)
    client.create_skill = AsyncMock()
    client.create_skill_version = AsyncMock()
    client.promote_skill_version = AsyncMock()
    client.get_agent = AsyncMock(return_value=None)
    client.create_agent_version = AsyncMock()
    client.get_syndicate = AsyncMock(return_value=None)
    client.create_syndicate = AsyncMock()
    client.create_syndicate_version = AsyncMock()
    client.list_skills = AsyncMock(return_value=[])
    client._request = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_oci_client():
    """Create a mock OCI client."""
    client = MagicMock()
    client.push = MagicMock(
        return_value=MagicMock(
            repository="registry.almckay.io/skills/test-skill",
            tag="v1.0.0",
            digest="sha256:abc123",
            size_bytes=1024,
        )
    )
    client.pull = MagicMock()
    return client


@pytest.fixture
def kubani_project(tmp_path):
    """Create a temporary Kubani project structure."""
    # Create kubani directory structure
    kubani_dir = tmp_path / "kubani"
    kubani_dir.mkdir()

    # Create skills directory with a test skill
    skills_dir = kubani_dir / "skills" / "test" / "diagnostic"
    skills_dir.mkdir(parents=True)

    skill_dir = skills_dir / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: test-skill
description: A test skill for migration
version: "1.0.0"
metadata:
  domain: test
  category: diagnostic
---

# Test Skill

This is a test skill for verifying migration functionality.
"""
    )

    # Create agents directory with a test agent
    agents_dir = kubani_dir / "agents" / "test-agent"
    agents_dir.mkdir(parents=True)
    (agents_dir / "config.yaml").write_text(
        """name: test-agent
description: A test agent
version: "1.0.0"
"""
    )

    # Create syndicates directory with a test syndicate
    syndicates_dir = kubani_dir / "syndicates" / "test-syndicate"
    syndicates_dir.mkdir(parents=True)
    (syndicates_dir / "config.yaml").write_text(
        """name: test-syndicate
description: A test syndicate
version: "1.0.0"
agents:
  - test-agent
"""
    )

    return tmp_path


class TestMigrateCommand:
    """Tests for the migrate command."""

    @pytest.mark.asyncio
    async def test_migrate_skills_dry_run(
        self, kubani_project, mock_registry_client, mock_oci_client
    ):
        """Test migration dry run shows what would be migrated."""
        from kubani.cli.commands.migrate import _migrate_to_registry

        with (
            patch(
                "kubani.cli.commands.migrate.get_registry_client", return_value=mock_registry_client
            ),
            patch("kubani.cli.commands.migrate.get_oci_client", return_value=mock_oci_client),
        ):
            await _migrate_to_registry(
                project_root=kubani_project,
                dry_run=True,
                migrate_skills=True,
                migrate_agents=False,
                migrate_syndicates=False,
            )

        # In dry run mode, OCI push should not be called
        mock_oci_client.push.assert_not_called()

    @pytest.mark.asyncio
    async def test_migrate_skills_actual(
        self, kubani_project, mock_registry_client, mock_oci_client
    ):
        """Test actual skill migration."""
        from kubani.cli.commands.migrate import _migrate_to_registry

        with (
            patch(
                "kubani.cli.commands.migrate.get_registry_client", return_value=mock_registry_client
            ),
            patch("kubani.cli.commands.migrate.get_oci_client", return_value=mock_oci_client),
        ):
            await _migrate_to_registry(
                project_root=kubani_project,
                dry_run=False,
                migrate_skills=True,
                migrate_agents=False,
                migrate_syndicates=False,
            )

        # OCI push should be called
        mock_oci_client.push.assert_called_once()
        # Registry create should be called
        mock_registry_client.create_skill.assert_called_once()
        mock_registry_client.create_skill_version.assert_called_once()

    @pytest.mark.asyncio
    async def test_migrate_skips_existing(
        self, kubani_project, mock_registry_client, mock_oci_client
    ):
        """Test migration skips already migrated skills."""
        # Mock skill as already existing with a version
        mock_registry_client.get_skill = AsyncMock(
            return_value={"id": "test/diagnostic/test-skill", "current_version": "1.0.0"}
        )

        from kubani.cli.commands.migrate import _migrate_to_registry

        with (
            patch(
                "kubani.cli.commands.migrate.get_registry_client", return_value=mock_registry_client
            ),
            patch("kubani.cli.commands.migrate.get_oci_client", return_value=mock_oci_client),
        ):
            await _migrate_to_registry(
                project_root=kubani_project,
                dry_run=False,
                migrate_skills=True,
                migrate_agents=False,
                migrate_syndicates=False,
            )

        # Should not push or create since skill exists
        mock_oci_client.push.assert_not_called()
        mock_registry_client.create_skill.assert_not_called()

    @pytest.mark.asyncio
    async def test_migrate_agents(self, kubani_project, mock_registry_client, mock_oci_client):
        """Test agent migration."""
        from kubani.cli.commands.migrate import _migrate_to_registry

        with (
            patch(
                "kubani.cli.commands.migrate.get_registry_client", return_value=mock_registry_client
            ),
            patch("kubani.cli.commands.migrate.get_oci_client", return_value=mock_oci_client),
        ):
            await _migrate_to_registry(
                project_root=kubani_project,
                dry_run=False,
                migrate_skills=False,
                migrate_agents=True,
                migrate_syndicates=False,
            )

        # OCI push should be called for agent
        mock_oci_client.push.assert_called_once()
        call_args = mock_oci_client.push.call_args
        assert call_args.kwargs["resource_type"] == "agent"

    @pytest.mark.asyncio
    async def test_migrate_syndicates(self, kubani_project, mock_registry_client, mock_oci_client):
        """Test syndicate migration."""
        from kubani.cli.commands.migrate import _migrate_to_registry

        with (
            patch(
                "kubani.cli.commands.migrate.get_registry_client", return_value=mock_registry_client
            ),
            patch("kubani.cli.commands.migrate.get_oci_client", return_value=mock_oci_client),
        ):
            await _migrate_to_registry(
                project_root=kubani_project,
                dry_run=False,
                migrate_skills=False,
                migrate_agents=False,
                migrate_syndicates=True,
            )

        # OCI push should be called for syndicate
        mock_oci_client.push.assert_called_once()
        call_args = mock_oci_client.push.call_args
        assert call_args.kwargs["resource_type"] == "syndicate"


class TestExportCommand:
    """Tests for the export command."""

    @pytest.mark.asyncio
    async def test_export_no_changes(self, kubani_project, mock_registry_client, mock_oci_client):
        """Test export when registry has no resources."""
        from kubani.cli.commands.export import _export_to_git

        with (
            patch(
                "kubani.cli.commands.export.get_registry_client", return_value=mock_registry_client
            ),
            patch("kubani.cli.commands.export.get_oci_client", return_value=mock_oci_client),
        ):
            await _export_to_git(
                project_root=kubani_project,
                do_commit=False,
                do_push=False,
                export_skills=True,
                export_agents=True,
                export_syndicates=True,
            )

        # No OCI pull should occur when no resources in registry
        mock_oci_client.pull.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_skills(self, kubani_project, mock_registry_client, mock_oci_client):
        """Test exporting skills from registry."""
        # Mock registry returning a skill
        mock_registry_client.list_skills = AsyncMock(
            return_value=[
                {
                    "id": "test/diagnostic/test-skill",
                    "name": "test-skill",
                    "current_version": "1.0.0",
                    "metadata": {"domain": "test", "category": "diagnostic"},
                }
            ]
        )
        mock_registry_client.get_skill_version = AsyncMock(
            return_value={"version": "1.0.0", "oci_tag": "v1.0.0"}
        )

        from kubani.cli.commands.export import _export_to_git

        with (
            patch(
                "kubani.cli.commands.export.get_registry_client", return_value=mock_registry_client
            ),
            patch("kubani.cli.commands.export.get_oci_client", return_value=mock_oci_client),
        ):
            await _export_to_git(
                project_root=kubani_project,
                do_commit=False,
                do_push=False,
                export_skills=True,
                export_agents=False,
                export_syndicates=False,
            )

        # OCI pull should be called for the skill
        mock_oci_client.pull.assert_called_once()


class TestSyncDeprecation:
    """Tests for the deprecated sync command."""

    def test_sync_shows_deprecation_warning(self, capsys):
        """Test that sync command shows deprecation warning."""
        from kubani.cli.commands.sync import _show_deprecation_warning

        _show_deprecation_warning()

        # Can't easily capture Rich output, but the function should not raise


def test_parse_skill_md(tmp_path):
    """Test parsing SKILL.md frontmatter."""
    from kubani.cli.commands.migrate import _parse_skill_md

    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text(
        """---
name: my-skill
description: Test description
version: "2.0.0"
metadata:
  author: test
---

# My Skill

Content here.
"""
    )

    result = _parse_skill_md(skill_file)

    assert result["name"] == "my-skill"
    assert result["description"] == "Test description"
    assert result["version"] == "2.0.0"
    assert result["metadata"]["author"] == "test"


def test_parse_skill_md_no_frontmatter(tmp_path):
    """Test parsing SKILL.md without frontmatter."""
    from kubani.cli.commands.migrate import _parse_skill_md

    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("# Just a skill\n\nNo frontmatter here.")

    result = _parse_skill_md(skill_file)

    assert result == {}
