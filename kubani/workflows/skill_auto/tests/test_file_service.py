"""Tests for file_service.py - File operations with mock filesystem.

These tests use an in-memory mock filesystem for fast, isolated testing.
"""

import json
from pathlib import Path

import pytest

from kubani.workflows.skill_auto.file_service import (
    create_backup,
    load_existing_skills,
    load_iteration_history,
    promote_skill,
    revert_to_version,
    save_iteration_result,
    write_skill_files,
)


class MockFileService:
    """In-memory mock file service for testing."""

    def __init__(self):
        self.files: dict[str, str] = {}
        self.directories: set[str] = set()

    def read(self, path: str) -> str:
        """Read file from mock filesystem."""
        if path not in self.files:
            raise FileNotFoundError(f"File not found: {path}")
        return self.files[path]

    def write(self, path: str, content: str) -> None:
        """Write file to mock filesystem."""
        # Auto-create parent directory
        parent = str(Path(path).parent)
        self.directories.add(parent)
        self.files[path] = content

    def exists(self, path: str) -> bool:
        """Check if path exists in mock filesystem."""
        return path in self.files or path in self.directories

    def mkdir(self, path: str) -> None:
        """Create directory in mock filesystem."""
        self.directories.add(path)
        # Add all parent directories too
        p = Path(path)
        for parent in p.parents:
            self.directories.add(str(parent))

    def list_files(self, path: str, pattern: str) -> list[str]:
        """List files matching pattern in mock filesystem."""
        results = []
        # Simple glob-like matching
        for file_path in self.files:
            # Check if file is under the given path
            if not (file_path.startswith(path + "/") or file_path.startswith(path) and path == "."):
                continue

            # Check pattern matches
            if (
                pattern == "**/SKILL.md"
                and file_path.endswith("/SKILL.md")
                or (
                    pattern.startswith("iteration_")
                    and "iteration_" in file_path
                    and file_path.endswith(".json")
                )
            ):
                results.append(file_path)
        return results

    def copy(self, src: str, dst: str) -> None:
        """Copy file in mock filesystem."""
        self.files[dst] = self.files[src]

    def move(self, src: str, dst: str) -> None:
        """Move file/directory in mock filesystem."""
        # Move all files that start with src path
        to_move = [(k, v) for k, v in self.files.items() if k.startswith(src)]
        for old_path, content in to_move:
            new_path = old_path.replace(src, dst, 1)
            self.files[new_path] = content
            del self.files[old_path]

        # Update directories
        to_update = [d for d in self.directories if d.startswith(src)]
        for old_dir in to_update:
            new_dir = old_dir.replace(src, dst, 1)
            self.directories.add(new_dir)
            self.directories.discard(old_dir)


@pytest.fixture
def mock_fs():
    """Create a fresh mock filesystem."""
    return MockFileService()


@pytest.fixture
def fs_with_skills(mock_fs):
    """Mock filesystem with some existing skills."""
    # Add parent directories
    mock_fs.directories.add("/skills")
    mock_fs.directories.add("/skills/general")
    mock_fs.directories.add("/skills/general/deploy-app")
    mock_fs.directories.add("/skills/_development")
    mock_fs.directories.add("/skills/_development/test-skill")

    # Production skill
    mock_fs.files["/skills/general/deploy-app/SKILL.md"] = """---
name: deploy-app
description: Deploy applications to Kubernetes
triggers:
  - deployment_request
---

# Deploy App

Deploy applications.
"""

    # Development skill
    mock_fs.files["/skills/_development/test-skill/SKILL.md"] = """---
name: test-skill
description: A test skill in development
---

# Test Skill
"""

    return mock_fs


class TestLoadExistingSkills:
    """Tests for load_existing_skills function."""

    def test_loads_skills(self, fs_with_skills):
        """Load skills from filesystem."""
        skills = load_existing_skills(fs_with_skills, "/skills")

        assert len(skills) == 2
        names = [s["name"] for s in skills]
        assert "deploy-app" in names
        assert "test-skill" in names

    def test_excludes_development(self, fs_with_skills):
        """Exclude _development skills when requested."""
        skills = load_existing_skills(fs_with_skills, "/skills", include_development=False)

        assert len(skills) == 1
        assert skills[0]["name"] == "deploy-app"

    def test_empty_directory(self, mock_fs):
        """Return empty list for empty/nonexistent directory."""
        skills = load_existing_skills(mock_fs, "/nonexistent")
        assert skills == []

    def test_extracts_metadata(self, fs_with_skills):
        """Extract all metadata fields from skills."""
        skills = load_existing_skills(fs_with_skills, "/skills")

        deploy = next(s for s in skills if s["name"] == "deploy-app")
        assert deploy["description"] == "Deploy applications to Kubernetes"
        assert deploy["triggers"] == ["deployment_request"]
        assert "/skills/general/deploy-app" in deploy["path"]


class TestWriteSkillFiles:
    """Tests for write_skill_files function."""

    def test_creates_all_files(self, mock_fs):
        """Create SKILL.md, test_cases.yaml, and metadata.json."""
        spec = {
            "name": "my-skill",
            "description": "Test skill",
            "inputs": {"param": {"type": "string"}},
            "outputs": {"result": {"type": "string"}},
            "steps": ["Do something"],
            "error_handling": ["Handle errors"],
        }

        result = write_skill_files(mock_fs, spec, "test_cases:\n  - name: test1", "/output")

        assert result["path"] == "/output/my-skill"
        assert "/output/my-skill/SKILL.md" in mock_fs.files
        assert "/output/my-skill/test_cases.yaml" in mock_fs.files
        assert "/output/my-skill/metadata.json" in mock_fs.files

    def test_skill_md_content(self, mock_fs):
        """Verify SKILL.md has correct content."""
        spec = {
            "name": "test-skill",
            "description": "A test skill",
            "steps": ["Step 1", "Step 2"],
        }

        write_skill_files(mock_fs, spec, "test_cases: []", "/output")

        content = mock_fs.files["/output/test-skill/SKILL.md"]
        assert "name: test-skill" in content
        assert "A test skill" in content
        assert "Step 1" in content

    def test_metadata_json_content(self, mock_fs):
        """Verify metadata.json has correct content."""
        spec = {"name": "my-skill", "description": "Test"}

        write_skill_files(mock_fs, spec, "test_cases: []", "/output")

        metadata = json.loads(mock_fs.files["/output/my-skill/metadata.json"])
        assert metadata["name"] == "my-skill"
        assert metadata["status"] == "development"
        assert metadata["created_by"] == "auto-mode"

    def test_returns_content_for_state(self, mock_fs):
        """Return content for workflow state tracking."""
        spec = {"name": "my-skill", "description": "Test"}
        test_yaml = "test_cases:\n  - name: test1"

        result = write_skill_files(mock_fs, spec, test_yaml, "/output")

        assert "content" in result
        assert "test_cases" in result
        assert result["test_cases"] == test_yaml

    def test_infers_name_from_description(self, mock_fs):
        """Infer skill name from description when name is missing."""
        spec = {
            "description": "Analyze JSON log entries",
            "inputs": {"log": {"type": "string"}},
            "outputs": {"result": {"type": "object"}},
            "steps": ["Parse log"],
        }

        result = write_skill_files(mock_fs, spec, "test_cases: []", "/output")

        # Name should be inferred from description
        assert "analyze-json-log-entries" in result["path"]
        assert spec["name"] == "analyze-json-log-entries"  # spec should be updated


class TestSaveIterationResult:
    """Tests for save_iteration_result function."""

    def test_saves_to_json(self, mock_fs):
        """Save iteration result to JSON file."""
        mock_fs.mkdir("/skill")

        result = save_iteration_result(
            mock_fs,
            skill_path="/skill",
            iteration=1,
            score=0.75,
            improved=True,
            action="continue",
        )

        assert result["saved"] is True
        assert "/skill/iteration_1.json" in mock_fs.files

        data = json.loads(mock_fs.files["/skill/iteration_1.json"])
        assert data["iteration"] == 1
        assert data["score"] == 0.75
        assert data["improved"] is True
        assert data["action"] == "continue"

    def test_includes_metrics(self, mock_fs):
        """Include metrics in saved data."""
        mock_fs.mkdir("/skill")

        save_iteration_result(
            mock_fs,
            skill_path="/skill",
            iteration=2,
            score=0.8,
            improved=True,
            action="stop_success",
            metrics={"accuracy": 0.85, "latency_ms": 1500},
        )

        data = json.loads(mock_fs.files["/skill/iteration_2.json"])
        assert data["metrics"]["accuracy"] == 0.85

    def test_includes_error(self, mock_fs):
        """Include error message when present."""
        mock_fs.mkdir("/skill")

        save_iteration_result(
            mock_fs,
            skill_path="/skill",
            iteration=3,
            score=0.0,
            improved=False,
            action="stop_regression",
            error="Evaluation failed",
        )

        data = json.loads(mock_fs.files["/skill/iteration_3.json"])
        assert data["error"] == "Evaluation failed"


class TestLoadIterationHistory:
    """Tests for load_iteration_history function."""

    def test_loads_history(self, mock_fs):
        """Load iteration history from files."""
        mock_fs.mkdir("/skill")
        mock_fs.files["/skill/iteration_1.json"] = json.dumps({"iteration": 1, "score": 0.6})
        mock_fs.files["/skill/iteration_2.json"] = json.dumps({"iteration": 2, "score": 0.7})

        history = load_iteration_history(mock_fs, "/skill")

        assert len(history) == 2
        assert history[0]["iteration"] == 1
        assert history[1]["iteration"] == 2

    def test_sorts_by_iteration(self, mock_fs):
        """Sort history by iteration number."""
        mock_fs.mkdir("/skill")
        mock_fs.files["/skill/iteration_3.json"] = json.dumps({"iteration": 3})
        mock_fs.files["/skill/iteration_1.json"] = json.dumps({"iteration": 1})
        mock_fs.files["/skill/iteration_2.json"] = json.dumps({"iteration": 2})

        history = load_iteration_history(mock_fs, "/skill")

        assert [h["iteration"] for h in history] == [1, 2, 3]

    def test_empty_directory(self, mock_fs):
        """Return empty list for empty directory."""
        history = load_iteration_history(mock_fs, "/nonexistent")
        assert history == []


class TestCreateBackup:
    """Tests for create_backup function."""

    def test_creates_backup(self, mock_fs):
        """Create timestamped backup of file."""
        mock_fs.files["/skill/SKILL.md"] = "original content"

        backup_path = create_backup(mock_fs, "/skill/SKILL.md", "20260125_120000")

        assert backup_path == "/skill/SKILL.md.backup.20260125_120000"
        assert mock_fs.files[backup_path] == "original content"

    def test_handles_nonexistent_file(self, mock_fs):
        """Handle backup request for nonexistent file."""
        backup_path = create_backup(mock_fs, "/nonexistent", "20260125_120000")

        assert backup_path == "/nonexistent.backup.20260125_120000"
        assert backup_path not in mock_fs.files


class TestRevertToVersion:
    """Tests for revert_to_version function."""

    def test_reverts_files(self, mock_fs):
        """Revert SKILL.md and test_cases.yaml to previous version."""
        mock_fs.mkdir("/skill")
        mock_fs.files["/skill/SKILL.md"] = "current content"
        mock_fs.files["/skill/test_cases.yaml"] = "current tests"

        result = revert_to_version(
            mock_fs,
            skill_path="/skill",
            content="old content",
            test_cases="old tests",
        )

        assert result["reverted"] is True
        assert mock_fs.files["/skill/SKILL.md"] == "old content"
        assert mock_fs.files["/skill/test_cases.yaml"] == "old tests"

    def test_creates_backups(self, mock_fs):
        """Create backups before reverting."""
        mock_fs.mkdir("/skill")
        mock_fs.files["/skill/SKILL.md"] = "current content"

        revert_to_version(mock_fs, "/skill", "old", "old tests")

        # Check that a backup was created
        backup_files = [f for f in mock_fs.files if ".backup." in f]
        assert len(backup_files) >= 1


class TestPromoteSkill:
    """Tests for promote_skill function."""

    def test_promotes_skill(self, mock_fs):
        """Promote skill from _development to production."""
        mock_fs.mkdir("/skills/_development/my-skill")
        mock_fs.files["/skills/_development/my-skill/SKILL.md"] = "skill content"
        mock_fs.files["/skills/_development/my-skill/metadata.json"] = json.dumps(
            {"name": "my-skill", "status": "development"}
        )

        result = promote_skill(
            mock_fs,
            skill_path="/skills/_development/my-skill",
            target_category="general",
            skills_root="/skills",
        )

        assert result["success"] is True
        assert result["promoted_path"] == "/skills/general/my-skill"
        assert "/skills/general/my-skill/SKILL.md" in mock_fs.files

    def test_updates_metadata(self, mock_fs):
        """Update metadata status on promotion."""
        mock_fs.mkdir("/skills/_development/my-skill")
        mock_fs.files["/skills/_development/my-skill/SKILL.md"] = "content"
        mock_fs.files["/skills/_development/my-skill/metadata.json"] = json.dumps(
            {"name": "my-skill", "status": "development"}
        )

        promote_skill(
            mock_fs,
            skill_path="/skills/_development/my-skill",
            target_category="k8s",
            skills_root="/skills",
        )

        metadata = json.loads(mock_fs.files["/skills/k8s/my-skill/metadata.json"])
        assert metadata["status"] == "production"
        assert metadata["category"] == "k8s"
        assert "promoted_at" in metadata
