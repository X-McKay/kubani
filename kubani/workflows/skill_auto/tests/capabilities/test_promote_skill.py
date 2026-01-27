"""Tests for promote_skill capability module."""

import json

import pytest

from kubani.workflows.skill_auto.capabilities.promote_skill import (
    await_approval,
    load_existing_skills,
    promote_skill,
    send_notification,
    send_promotion_request,
    sync_registry,
)


class MockFileSystem:
    """In-memory filesystem for testing."""

    def __init__(self, files: dict[str, str] | None = None):
        self.files: dict[str, str] = files or {}
        self.dirs: set[str] = set()

    def read(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def write(self, path: str, content: str) -> None:
        self.files[path] = content

    def exists(self, path: str) -> bool:
        # Check if path is a file
        if path in self.files:
            return True
        # Check if path is an explicit directory
        if path in self.dirs:
            return True
        # Check if path is an implicit directory (parent of any file)
        for file_path in self.files:
            if file_path.startswith(path + "/"):
                return True
        return False

    def mkdir(self, path: str, parents: bool = True) -> None:
        self.dirs.add(path)

    def list_files(self, path: str, pattern: str) -> list[str]:
        """Simple glob simulation."""
        results = []
        for p in self.files.keys():
            if p.startswith(path) and p.endswith("SKILL.md"):
                results.append(p)
        return results

    def move(self, src: str, dst: str) -> None:
        """Move all files from src prefix to dst prefix."""
        to_move = [(k, v) for k, v in self.files.items() if k.startswith(src)]
        for old_path, content in to_move:
            new_path = old_path.replace(src, dst, 1)
            self.files[new_path] = content
            del self.files[old_path]


class MockDiscordClient:
    """Mock Discord client for testing."""

    def __init__(
        self,
        send_response: dict | None = None,
        reaction_response: dict | None = None,
    ):
        self.send_response = send_response or {
            "message_id": "123",
            "channel_id": "456",
        }
        self.reaction_response = reaction_response
        self.sent_embeds: list[dict] = []
        self.reactions_added: list[tuple[str, str, str]] = []

    async def send_embed(self, channel_name: str, embed: dict) -> dict:
        self.sent_embeds.append({"channel": channel_name, "embed": embed})
        return self.send_response

    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        self.reactions_added.append((channel_id, message_id, emoji))

    async def await_reaction(
        self,
        channel_id: str,
        message_id: str,
        valid_emojis: list[str],
        timeout_seconds: int,
    ) -> dict | None:
        return self.reaction_response


class MockRegistryClient:
    """Mock registry client for testing."""

    def __init__(self, response: dict | None = None):
        self.response = response or {"skill_id": "skill-123"}
        self.synced_skills: list[tuple[str, dict]] = []

    async def sync_skill(self, skill_path: str, metadata: dict) -> dict:
        self.synced_skills.append((skill_path, metadata))
        return self.response


class TestLoadExistingSkills:
    """Tests for load_existing_skills function."""

    def test_loads_skills_from_directory(self):
        """Load skills from skills directory."""
        fs = MockFileSystem(
            {
                "skills/general/skill1/SKILL.md": "---\nname: skill1\ndescription: First skill\n---",
                "skills/general/skill2/SKILL.md": "---\nname: skill2\ndescription: Second skill\n---",
            }
        )

        skills = load_existing_skills(fs, "skills")

        assert len(skills) == 2
        assert any(s["name"] == "skill1" for s in skills)
        assert any(s["name"] == "skill2" for s in skills)

    def test_extracts_metadata(self):
        """Extract metadata from frontmatter."""
        fs = MockFileSystem(
            {
                "skills/test/SKILL.md": """---
name: test-skill
description: A test skill
triggers:
  - test_event
---"""
            }
        )

        skills = load_existing_skills(fs, "skills")

        assert len(skills) == 1
        assert skills[0]["name"] == "test-skill"
        assert skills[0]["description"] == "A test skill"
        assert "test_event" in skills[0]["triggers"]

    def test_excludes_development_when_requested(self):
        """Exclude _development skills when include_development=False."""
        fs = MockFileSystem(
            {
                "skills/_development/wip/SKILL.md": "---\nname: wip\n---",
                "skills/general/prod/SKILL.md": "---\nname: prod\n---",
            }
        )

        skills = load_existing_skills(fs, "skills", include_development=False)

        assert len(skills) == 1
        assert skills[0]["name"] == "prod"

    def test_returns_empty_for_nonexistent_path(self):
        """Return empty list for nonexistent path."""
        fs = MockFileSystem()

        skills = load_existing_skills(fs, "nonexistent")

        assert skills == []


class TestPromoteSkill:
    """Tests for promote_skill function."""

    def test_moves_skill_to_target_category(self):
        """Move skill to production location."""
        fs = MockFileSystem(
            {
                "dev/test-skill/SKILL.md": "content",
                "dev/test-skill/metadata.json": '{"status": "development"}',
            }
        )

        result = promote_skill(fs, "dev/test-skill", "general", "skills")

        assert result["success"] is True
        assert result["promoted_path"] == "skills/general/test-skill"
        assert "skills/general/test-skill/SKILL.md" in fs.files

    def test_updates_metadata_status(self):
        """Update metadata status to production."""
        fs = MockFileSystem(
            {
                "dev/test-skill/SKILL.md": "content",
                "dev/test-skill/metadata.json": '{"status": "development"}',
            }
        )

        promote_skill(fs, "dev/test-skill", "general", "skills")

        metadata = json.loads(fs.files["skills/general/test-skill/metadata.json"])
        assert metadata["status"] == "production"
        assert "promoted_at" in metadata
        assert metadata["category"] == "general"

    def test_creates_metadata_if_missing(self):
        """Create metadata file if it doesn't exist."""
        fs = MockFileSystem(
            {
                "dev/test-skill/SKILL.md": "content",
            }
        )

        promote_skill(fs, "dev/test-skill", "general", "skills")

        assert "skills/general/test-skill/metadata.json" in fs.files
        metadata = json.loads(fs.files["skills/general/test-skill/metadata.json"])
        assert metadata["status"] == "production"


class TestSendNotification:
    """Tests for send_notification function."""

    @pytest.mark.asyncio
    async def test_sends_started_notification(self):
        """Send started notification."""
        discord = MockDiscordClient()

        result = await send_notification(
            discord,
            event_type="started",
            channel="test-channel",
            skill_name="test-skill",
        )

        assert result["sent"] is True
        assert len(discord.sent_embeds) == 1
        assert "Started" in discord.sent_embeds[0]["embed"]["title"]

    @pytest.mark.asyncio
    async def test_sends_iteration_notification(self):
        """Send iteration complete notification with metrics."""
        discord = MockDiscordClient()

        result = await send_notification(
            discord,
            event_type="iteration_complete",
            channel="test-channel",
            skill_name="test-skill",
            iteration=2,
            metrics={"accuracy": 0.85, "tests_passed": 4, "tests_total": 5},
        )

        assert result["sent"] is True
        embed = discord.sent_embeds[0]["embed"]
        assert "Iteration 2" in embed["title"]
        assert "85.0%" in str(embed["fields"])

    @pytest.mark.asyncio
    async def test_sends_failed_notification(self):
        """Send failed notification with error."""
        discord = MockDiscordClient()

        result = await send_notification(
            discord,
            event_type="failed",
            channel="test-channel",
            skill_name="test-skill",
            error="Something went wrong",
        )

        assert result["sent"] is True
        embed = discord.sent_embeds[0]["embed"]
        assert "Failed" in embed["title"]
        assert "Something went wrong" in embed["description"]


class TestSendPromotionRequest:
    """Tests for send_promotion_request function."""

    @pytest.mark.asyncio
    async def test_sends_promotion_embed(self):
        """Send promotion request embed."""
        discord = MockDiscordClient()

        result = await send_promotion_request(
            discord,
            skill_name="test-skill",
            skill_path="/path/to/skill",
            metrics={"accuracy": 0.9, "tests_passed": 5, "tests_total": 5},
            iterations=3,
            channel="approvals",
        )

        assert result["sent"] is True
        assert result["message_id"] == "123"
        embed = discord.sent_embeds[0]["embed"]
        assert "Promotion Request" in embed["title"]
        assert "90.0%" in str(embed["fields"])

    @pytest.mark.asyncio
    async def test_handles_missing_metrics(self):
        """Handle None metrics gracefully."""
        discord = MockDiscordClient()

        result = await send_promotion_request(
            discord,
            skill_name="test-skill",
            skill_path="/path/to/skill",
            metrics=None,
            iterations=1,
            channel="approvals",
        )

        assert result["sent"] is True
        embed = discord.sent_embeds[0]["embed"]
        assert "N/A" in str(embed["fields"])


class TestAwaitApproval:
    """Tests for await_approval function."""

    @pytest.mark.asyncio
    async def test_returns_approved_on_checkmark(self):
        """Return approved when checkmark reaction received."""
        discord = MockDiscordClient(reaction_response={"emoji": "\u2705"})

        result = await await_approval(discord, "channel-1", "msg-1")

        assert result["approved"] is True
        assert result["rejected"] is False
        assert result["timeout"] is False

    @pytest.mark.asyncio
    async def test_returns_rejected_on_x_mark(self):
        """Return rejected when X reaction received."""
        discord = MockDiscordClient(reaction_response={"emoji": "\u274c"})

        result = await await_approval(discord, "channel-1", "msg-1")

        assert result["approved"] is False
        assert result["rejected"] is True
        assert result["timeout"] is False

    @pytest.mark.asyncio
    async def test_returns_timeout_on_none(self):
        """Return timeout when no reaction received."""
        discord = MockDiscordClient(reaction_response=None)

        result = await await_approval(discord, "channel-1", "msg-1")

        assert result["approved"] is False
        assert result["rejected"] is False
        assert result["timeout"] is True

    @pytest.mark.asyncio
    async def test_adds_reaction_options(self):
        """Add checkmark and X reactions to message."""
        discord = MockDiscordClient(reaction_response={"emoji": "\u2705"})

        await await_approval(discord, "channel-1", "msg-1")

        assert len(discord.reactions_added) == 2
        emojis = [r[2] for r in discord.reactions_added]
        assert "\u2705" in emojis
        assert "\u274c" in emojis


class TestSyncRegistry:
    """Tests for sync_registry function."""

    @pytest.mark.asyncio
    async def test_syncs_skill_to_registry(self):
        """Sync skill metadata to registry."""
        fs = MockFileSystem(
            {
                "skills/test/SKILL.md": "---\nname: test\ndescription: Test skill\n---",
                "skills/test/metadata.json": '{"status": "production"}',
            }
        )
        registry = MockRegistryClient()

        result = await sync_registry(fs, "skills/test", registry)

        assert result["synced"] is True
        assert result["skill_id"] == "skill-123"
        assert len(registry.synced_skills) == 1

    @pytest.mark.asyncio
    async def test_includes_frontmatter_metadata(self):
        """Include frontmatter metadata in sync."""
        fs = MockFileSystem(
            {
                "skills/test/SKILL.md": "---\nname: test\ndescription: Test skill\n---",
            }
        )
        registry = MockRegistryClient()

        await sync_registry(fs, "skills/test", registry)

        _, metadata = registry.synced_skills[0]
        assert metadata["name"] == "test"
        assert metadata["description"] == "Test skill"

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_skill(self):
        """Return error if SKILL.md not found."""
        fs = MockFileSystem()
        registry = MockRegistryClient()

        result = await sync_registry(fs, "skills/missing", registry)

        assert result["synced"] is False
        assert "not found" in result["error"]
