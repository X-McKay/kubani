"""Tests for registry commands."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from kubani.cli.cli import app

runner = CliRunner()


class TestRegistryPush:
    """Tests for registry push command."""

    def test_push_help(self):
        """Test push command shows help."""
        result = runner.invoke(app, ["registry", "push", "--help"])

        assert result.exit_code == 0
        assert "Push a resource to the OCI registry" in result.output
        assert "--source" in result.output
        assert "--changelog" in result.output
        assert "--dry-run" in result.output

    def test_push_invalid_resource_type(self):
        """Test push rejects invalid resource types."""
        result = runner.invoke(app, ["registry", "push", "invalid", "test", "v1.0.0"])

        assert result.exit_code == 1
        assert "Invalid resource type" in result.output

    def test_push_dry_run(self, tmp_path):
        """Test push dry run doesn't make changes."""
        # Create a temp source directory
        source_dir = tmp_path / "test-skill"
        source_dir.mkdir()
        (source_dir / "skill.md").write_text("# Test Skill")

        result = runner.invoke(
            app,
            [
                "registry",
                "push",
                "skill",
                "test-skill",
                "v1.0.0",
                "--source",
                str(source_dir),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Dry run" in result.output

    @patch("kubani.cli.oci.KubaniOCIClient")
    @patch("kubani.cli.registry_client.RegistryClient")
    def test_push_success(self, mock_registry_client_class, mock_oci_client_class, tmp_path):
        """Test successful push operation."""
        # Create a temp source directory
        source_dir = tmp_path / "test-skill"
        source_dir.mkdir()
        (source_dir / "skill.md").write_text("# Test Skill")

        # Mock OCI client
        mock_oci_client = MagicMock()
        mock_oci_client.push.return_value = MagicMock(
            repository="registry.almckay.io/skills/test-skill",
            tag="v1.0.0",
            digest="sha256:abc123",
            size_bytes=1024,
        )
        mock_oci_client_class.return_value = mock_oci_client

        # Mock registry client
        mock_registry_client = AsyncMock()
        mock_registry_client.get_skill.side_effect = Exception("Not found")
        mock_registry_client.create_skill.return_value = MagicMock()
        mock_registry_client.create_skill_version.return_value = MagicMock(
            version="v1.0.0",
            status="draft",
        )
        mock_registry_client.__aenter__.return_value = mock_registry_client
        mock_registry_client.__aexit__.return_value = None
        mock_registry_client_class.return_value = mock_registry_client

        result = runner.invoke(
            app,
            [
                "registry",
                "push",
                "skill",
                "test-skill",
                "v1.0.0",
                "--source",
                str(source_dir),
            ],
        )

        assert result.exit_code == 0
        assert "Successfully pushed" in result.output


class TestRegistryPull:
    """Tests for registry pull command."""

    def test_pull_help(self):
        """Test pull command shows help."""
        result = runner.invoke(app, ["registry", "pull", "--help"])

        assert result.exit_code == 0
        assert "Pull a resource from the OCI registry" in result.output
        assert "--dest" in result.output
        assert "--force" in result.output

    def test_pull_invalid_resource_type(self):
        """Test pull rejects invalid resource types."""
        result = runner.invoke(app, ["registry", "pull", "invalid", "test"])

        assert result.exit_code == 1
        assert "Invalid resource type" in result.output

    @patch("kubani.cli.oci.KubaniOCIClient")
    @patch("kubani.cli.registry_client.RegistryClient")
    def test_pull_success(self, mock_registry_client_class, mock_oci_client_class, tmp_path):
        """Test successful pull operation."""
        dest_dir = tmp_path / "pulled-skill"

        # Mock registry client for latest version lookup
        mock_registry_client = AsyncMock()
        mock_registry_client.get_skill_version.return_value = MagicMock(version="v1.0.0")
        mock_registry_client.__aenter__.return_value = mock_registry_client
        mock_registry_client.__aexit__.return_value = None
        mock_registry_client_class.return_value = mock_registry_client

        # Mock OCI client
        mock_oci_client = MagicMock()
        mock_oci_client.pull.return_value = MagicMock(
            extracted_path=dest_dir,
            digest="sha256:abc123",
        )
        mock_oci_client_class.return_value = mock_oci_client

        result = runner.invoke(
            app,
            [
                "registry",
                "pull",
                "skill",
                "test-skill",
                "v1.0.0",
                "--dest",
                str(dest_dir),
            ],
        )

        assert result.exit_code == 0
        assert "Successfully pulled" in result.output

    def test_pull_destination_exists_without_force(self, tmp_path):
        """Test pull fails if destination exists without --force."""
        dest_dir = tmp_path / "existing-skill"
        dest_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "registry",
                "pull",
                "skill",
                "test-skill",
                "v1.0.0",
                "--dest",
                str(dest_dir),
            ],
        )

        assert result.exit_code == 1
        assert "already exists" in result.output


class TestRegistryPromote:
    """Tests for registry promote command."""

    def test_promote_help(self):
        """Test promote command shows help."""
        result = runner.invoke(app, ["registry", "promote", "--help"])

        assert result.exit_code == 0
        assert "Promote a resource version" in result.output
        assert "draft -> testing -> staging -> production" in result.output

    def test_promote_invalid_resource_type(self):
        """Test promote rejects invalid resource types."""
        result = runner.invoke(app, ["registry", "promote", "invalid", "test", "v1.0.0"])

        assert result.exit_code == 1
        assert "Invalid resource type" in result.output

    @patch("kubani.cli.registry_client.RegistryClient")
    def test_promote_success(self, mock_registry_client_class):
        """Test successful promote operation."""
        mock_registry_client = AsyncMock()
        mock_registry_client.get_skill_version.return_value = MagicMock(status="draft")
        mock_registry_client.promote_skill_version.return_value = MagicMock(
            status="testing",
            promoted_at=datetime.now(),
        )
        mock_registry_client.__aenter__.return_value = mock_registry_client
        mock_registry_client.__aexit__.return_value = None
        mock_registry_client_class.return_value = mock_registry_client

        result = runner.invoke(
            app,
            ["registry", "promote", "skill", "test-skill", "v1.0.0"],
        )

        assert result.exit_code == 0
        assert "Promoted" in result.output
        assert "draft" in result.output and "testing" in result.output


class TestRegistryList:
    """Tests for registry list command."""

    def test_list_help(self):
        """Test list command shows help."""
        result = runner.invoke(app, ["registry", "list", "--help"])

        assert result.exit_code == 0
        assert "List resources in the registry" in result.output

    def test_list_invalid_resource_type(self):
        """Test list rejects invalid resource types."""
        result = runner.invoke(app, ["registry", "list", "invalid"])

        assert result.exit_code == 1
        assert "Invalid resource type" in result.output

    @patch("kubani.cli.registry_client.RegistryClient")
    def test_list_skills(self, mock_registry_client_class):
        """Test listing skills."""
        from kubani.cli.registry_client import ResourceInfo

        mock_registry_client = AsyncMock()
        mock_registry_client.list_skills.return_value = [
            ResourceInfo(
                id="1",
                name="skill1",
                description="Test skill 1",
                current_version="v1.0.0",
                status="production",
                oci_repository="registry.almckay.io/skills/skill1",
                created_at=datetime(2024, 1, 1),
                updated_at=datetime(2024, 1, 1),
                metadata={},
            ),
            ResourceInfo(
                id="2",
                name="skill2",
                description="Test skill 2",
                current_version="v0.1.0",
                status="testing",
                oci_repository="registry.almckay.io/skills/skill2",
                created_at=datetime(2024, 1, 1),
                updated_at=datetime(2024, 1, 1),
                metadata={},
            ),
        ]
        mock_registry_client.__aenter__.return_value = mock_registry_client
        mock_registry_client.__aexit__.return_value = None
        mock_registry_client_class.return_value = mock_registry_client

        result = runner.invoke(app, ["registry", "list", "skill"])

        assert result.exit_code == 0
        assert "skill1" in result.output
        assert "skill2" in result.output

    @patch("kubani.cli.registry_client.RegistryClient")
    def test_list_empty(self, mock_registry_client_class):
        """Test listing when no resources exist."""
        mock_registry_client = AsyncMock()
        mock_registry_client.list_skills.return_value = []
        mock_registry_client.__aenter__.return_value = mock_registry_client
        mock_registry_client.__aexit__.return_value = None
        mock_registry_client_class.return_value = mock_registry_client

        result = runner.invoke(app, ["registry", "list", "skill"])

        assert result.exit_code == 0
        assert "No skills found" in result.output


class TestRegistryVersions:
    """Tests for registry versions command."""

    def test_versions_help(self):
        """Test versions command shows help."""
        result = runner.invoke(app, ["registry", "versions", "--help"])

        assert result.exit_code == 0
        assert "List versions of a resource" in result.output

    def test_versions_invalid_resource_type(self):
        """Test versions rejects invalid resource types."""
        result = runner.invoke(app, ["registry", "versions", "invalid", "test"])

        assert result.exit_code == 1
        assert "Invalid resource type" in result.output

    @patch("kubani.cli.registry_client.RegistryClient")
    def test_versions_list(self, mock_registry_client_class):
        """Test listing versions."""
        mock_registry_client = AsyncMock()
        mock_registry_client.list_skill_versions.return_value = [
            MagicMock(
                version="v1.0.0",
                status="production",
                oci_tag="v1.0.0",
                created_at=datetime(2024, 1, 1),
                created_by="cli:kubani",
            ),
            MagicMock(
                version="v0.1.0",
                status="deprecated",
                oci_tag="v0.1.0",
                created_at=datetime(2023, 12, 1),
                created_by="ci:pipeline",
            ),
        ]
        mock_registry_client.__aenter__.return_value = mock_registry_client
        mock_registry_client.__aexit__.return_value = None
        mock_registry_client_class.return_value = mock_registry_client

        result = runner.invoke(app, ["registry", "versions", "skill", "test-skill"])

        assert result.exit_code == 0
        assert "v1.0.0" in result.output
        assert "v0.1.0" in result.output
        assert "production" in result.output
