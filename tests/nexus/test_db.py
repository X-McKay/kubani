"""Tests for the Nexus database access layer.

These tests run against a real PostgreSQL instance (Docker).
They validate all CRUD operations for conversations, messages,
actions, skills, and approval requests.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio

from kubani.nexus.db import (
    create_approval_request,
    create_pool,
    ensure_conversation,
    get_conversation_history,
    get_pending_approvals,
    get_recent_actions,
    get_skill,
    list_skills,
    log_action_complete,
    log_action_start,
    register_skill,
    resolve_approval,
    save_message,
    update_skill_status,
)

DATABASE_URL = "postgresql://kubani:kubani@localhost:5432/kubani_nexus"


@pytest_asyncio.fixture
async def pool():
    """Create a database pool for testing."""
    p = await create_pool(DATABASE_URL)
    yield p
    await p.close()


@pytest.fixture
def conversation_id():
    """Generate a unique conversation ID for each test."""
    return f"test-conv-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def user_id():
    return "test-user-1"


# =========================================================================
# Conversation Tests
# =========================================================================


class TestConversations:
    """Test conversation and message operations."""

    @pytest.mark.asyncio
    async def test_ensure_conversation_creates_new(self, pool, conversation_id, user_id):
        """Test that ensure_conversation creates a new conversation."""
        await ensure_conversation(pool, conversation_id, user_id, "test")

        # Verify it was created
        row = await pool.fetchrow(
            "SELECT * FROM conversations WHERE id = $1", conversation_id
        )
        assert row is not None
        assert row["user_id"] == user_id
        assert row["source"] == "test"
        assert row["status"] == "active"

    @pytest.mark.asyncio
    async def test_ensure_conversation_idempotent(self, pool, conversation_id, user_id):
        """Test that ensure_conversation is idempotent (no error on duplicate)."""
        await ensure_conversation(pool, conversation_id, user_id, "test")
        await ensure_conversation(pool, conversation_id, user_id, "test")

        # Should still be one record
        count = await pool.fetchval(
            "SELECT COUNT(*) FROM conversations WHERE id = $1", conversation_id
        )
        assert count == 1

    @pytest.mark.asyncio
    async def test_save_and_retrieve_messages(self, pool, conversation_id, user_id):
        """Test saving messages and retrieving conversation history."""
        await ensure_conversation(pool, conversation_id, user_id, "test")

        # Save messages
        msg1_id = await save_message(pool, conversation_id, "user", "Hello!", "test")
        msg2_id = await save_message(pool, conversation_id, "assistant", "Hi there!", "system")

        assert msg1_id is not None
        assert msg2_id is not None
        assert msg1_id != msg2_id

        # Retrieve history
        history = await get_conversation_history(pool, conversation_id)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello!"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Hi there!"

    @pytest.mark.asyncio
    async def test_conversation_history_limit(self, pool, conversation_id, user_id):
        """Test that the history limit is respected."""
        await ensure_conversation(pool, conversation_id, user_id, "test")

        # Save 10 messages
        for i in range(10):
            await save_message(pool, conversation_id, "user", f"Message {i}", "test")

        # Retrieve with limit
        history = await get_conversation_history(pool, conversation_id, limit=5)
        assert len(history) == 5

    @pytest.mark.asyncio
    async def test_conversation_history_order(self, pool, conversation_id, user_id):
        """Test that history is returned in chronological order."""
        await ensure_conversation(pool, conversation_id, user_id, "test")

        await save_message(pool, conversation_id, "user", "First", "test")
        await asyncio.sleep(0.01)  # Ensure different timestamps
        await save_message(pool, conversation_id, "user", "Second", "test")
        await asyncio.sleep(0.01)
        await save_message(pool, conversation_id, "user", "Third", "test")

        history = await get_conversation_history(pool, conversation_id)
        assert history[0]["content"] == "First"
        assert history[1]["content"] == "Second"
        assert history[2]["content"] == "Third"


# =========================================================================
# Agent Actions Tests
# =========================================================================


class TestAgentActions:
    """Test agent action logging operations."""

    @pytest.mark.asyncio
    async def test_log_action_lifecycle(self, pool, conversation_id, user_id):
        """Test the full action lifecycle: start → complete."""
        await ensure_conversation(pool, conversation_id, user_id, "test")

        # Start an action
        action_id = await log_action_start(
            pool, conversation_id, "skill_execution", "Fetching URL", "web/fetch-url"
        )
        assert action_id is not None

        # Verify it's in 'started' state
        actions = await get_recent_actions(pool, limit=1, conversation_id=conversation_id)
        assert len(actions) == 1
        assert actions[0]["status"] == "started"
        assert actions[0]["action_type"] == "skill_execution"

        # Complete the action
        await log_action_complete(
            pool, action_id, output_summary="Fetched 1024 bytes", duration_ms=150
        )

        # Verify it's in 'completed' state
        actions = await get_recent_actions(pool, limit=1, conversation_id=conversation_id)
        assert actions[0]["status"] == "completed"
        assert actions[0]["duration_ms"] == 150

    @pytest.mark.asyncio
    async def test_log_action_failure(self, pool, conversation_id, user_id):
        """Test logging a failed action."""
        await ensure_conversation(pool, conversation_id, user_id, "test")

        action_id = await log_action_start(
            pool, conversation_id, "skill_execution", "Fetching URL", "web/fetch-url"
        )

        await log_action_complete(
            pool, action_id, error_message="Connection timeout", duration_ms=5000
        )

        actions = await get_recent_actions(pool, limit=1, conversation_id=conversation_id)
        assert actions[0]["status"] == "failed"
        assert actions[0]["error_message"] == "Connection timeout"

    @pytest.mark.asyncio
    async def test_recent_actions_ordering(self, pool, conversation_id, user_id):
        """Test that recent actions are returned newest first."""
        await ensure_conversation(pool, conversation_id, user_id, "test")

        id1 = await log_action_start(pool, conversation_id, "planning", "Plan A", "")
        await asyncio.sleep(0.01)
        id2 = await log_action_start(pool, conversation_id, "execution", "Plan B", "")

        actions = await get_recent_actions(pool, limit=10, conversation_id=conversation_id)
        assert len(actions) == 2
        # Newest first
        assert actions[0]["description"] == "Plan B"
        assert actions[1]["description"] == "Plan A"


# =========================================================================
# Skill Registry Tests
# =========================================================================


class TestSkillRegistry:
    """Test skill registry operations."""

    @pytest.mark.asyncio
    async def test_register_and_retrieve_skill(self, pool):
        """Test registering a skill and retrieving it."""
        skill_name = f"test/skill-{uuid.uuid4().hex[:6]}"

        skill_id = await register_skill(
            pool,
            name=skill_name,
            version="0.1.0",
            oci_url="oci://registry/test:0.1.0",
            description="A test skill",
            category="test",
            author="test-author",
        )
        assert skill_id is not None

        # Retrieve by name and version
        skill = await get_skill(pool, skill_name, "0.1.0")
        assert skill is not None
        assert skill["name"] == skill_name
        assert skill["version"] == "0.1.0"
        assert skill["status"] == "pending"

    @pytest.mark.asyncio
    async def test_skill_approval_workflow(self, pool):
        """Test the skill approval workflow."""
        skill_name = f"test/approval-{uuid.uuid4().hex[:6]}"

        skill_id = await register_skill(
            pool,
            name=skill_name,
            version="0.1.0",
            oci_url="oci://registry/test:0.1.0",
            description="Needs approval",
        )

        # Initially pending
        skill = await get_skill(pool, skill_name, "0.1.0")
        assert skill["status"] == "pending"

        # Approve it
        await update_skill_status(pool, skill_id, "approved", approved_by="admin")

        # Now it should be approved
        skill = await get_skill(pool, skill_name, "0.1.0")
        assert skill["status"] == "approved"

    @pytest.mark.asyncio
    async def test_get_latest_approved_skill(self, pool):
        """Test getting the latest approved version of a skill."""
        skill_name = f"test/latest-{uuid.uuid4().hex[:6]}"

        # Register v0.1.0 and approve it
        id1 = await register_skill(pool, name=skill_name, version="0.1.0", oci_url="oci://v1")
        await update_skill_status(pool, id1, "approved", approved_by="admin")

        # Register v0.2.0 and approve it
        await asyncio.sleep(0.01)
        id2 = await register_skill(pool, name=skill_name, version="0.2.0", oci_url="oci://v2")
        await update_skill_status(pool, id2, "approved", approved_by="admin")

        # Get latest should return v0.2.0
        skill = await get_skill(pool, skill_name, "latest")
        assert skill is not None
        assert skill["version"] == "0.2.0"

    @pytest.mark.asyncio
    async def test_list_skills_with_filters(self, pool):
        """Test listing skills with status and category filters."""
        prefix = uuid.uuid4().hex[:6]

        id1 = await register_skill(pool, name=f"test/{prefix}-a", version="0.1.0", oci_url="oci://a", category="web")
        await update_skill_status(pool, id1, "approved", approved_by="admin")

        await register_skill(pool, name=f"test/{prefix}-b", version="0.1.0", oci_url="oci://b", category="k8s")

        # Filter by status
        approved = await list_skills(pool, status="approved")
        pending = await list_skills(pool, status="pending")

        approved_names = [s["name"] for s in approved]
        pending_names = [s["name"] for s in pending]

        assert f"test/{prefix}-a" in approved_names
        assert f"test/{prefix}-b" in pending_names

    @pytest.mark.asyncio
    async def test_skill_upsert_on_conflict(self, pool):
        """Test that re-registering the same skill version updates it."""
        skill_name = f"test/upsert-{uuid.uuid4().hex[:6]}"

        id1 = await register_skill(pool, name=skill_name, version="0.1.0", oci_url="oci://v1", description="Original")
        id2 = await register_skill(pool, name=skill_name, version="0.1.0", oci_url="oci://v1-updated", description="Updated")

        assert id1 == id2  # Same ID due to upsert

        skill = await get_skill(pool, skill_name, "0.1.0")
        assert skill["oci_url"] == "oci://v1-updated"


# =========================================================================
# Approval Queue Tests
# =========================================================================


class TestApprovalQueue:
    """Test approval queue operations."""

    @pytest.mark.asyncio
    async def test_create_and_list_approvals(self, pool):
        """Test creating approval requests and listing pending ones."""
        req_id = await create_approval_request(
            pool,
            request_type="skill_approval",
            reference_id=999,
            title="Test Skill Approval",
            description="Please review this skill",
            risk_score=5.5,
        )
        assert req_id is not None

        pending = await get_pending_approvals(pool)
        ids = [r["id"] for r in pending]
        assert req_id in ids

    @pytest.mark.asyncio
    async def test_resolve_approval_approve(self, pool):
        """Test approving a pending request."""
        req_id = await create_approval_request(
            pool,
            request_type="skill_approval",
            reference_id=998,
            title="Approve Me",
        )

        await resolve_approval(pool, req_id, approved=True, decided_by="admin", reason="Looks good")

        # Should no longer be in pending
        pending = await get_pending_approvals(pool)
        ids = [r["id"] for r in pending]
        assert req_id not in ids

    @pytest.mark.asyncio
    async def test_resolve_approval_reject(self, pool):
        """Test rejecting a pending request."""
        req_id = await create_approval_request(
            pool,
            request_type="skill_approval",
            reference_id=997,
            title="Reject Me",
        )

        await resolve_approval(pool, req_id, approved=False, decided_by="admin", reason="Too risky")

        pending = await get_pending_approvals(pool)
        ids = [r["id"] for r in pending]
        assert req_id not in ids
