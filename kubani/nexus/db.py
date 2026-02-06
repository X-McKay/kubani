"""Nexus database access layer.

Provides async database operations for the Nexus PostgreSQL database.
Uses raw asyncpg for simplicity and performance, avoiding ORM overhead.

All functions are pure and stateless — they accept a connection pool
as a parameter, making them easy to test with mock pools.

Usage:
    from kubani.nexus.db import create_pool, save_message, get_conversation_history

    pool = await create_pool("postgresql://kubani:kubani@localhost:5432/kubani_nexus")
    await save_message(pool, conversation_id, "user", "Hello!")
    history = await get_conversation_history(pool, conversation_id)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class DBPool(Protocol):
    """Protocol for database connection pools.

    This protocol allows us to swap in a mock pool for testing
    without depending on asyncpg directly.
    """

    async def execute(self, query: str, *args: Any) -> str: ...
    async def fetch(self, query: str, *args: Any) -> list[Any]: ...
    async def fetchrow(self, query: str, *args: Any) -> Any: ...
    async def fetchval(self, query: str, *args: Any) -> Any: ...


async def create_pool(database_url: str) -> Any:
    """Create an asyncpg connection pool.

    Args:
        database_url: PostgreSQL connection URL.

    Returns:
        asyncpg.Pool instance.
    """
    import asyncpg

    return await asyncpg.create_pool(database_url, min_size=2, max_size=10)


# =========================================================================
# Conversation Operations
# =========================================================================


async def ensure_conversation(
    pool: DBPool,
    conversation_id: str,
    user_id: str,
    source: str = "kubani-ui",
) -> None:
    """Ensure a conversation record exists, creating it if necessary.

    Args:
        pool: Database connection pool.
        conversation_id: Unique conversation identifier.
        user_id: User who owns this conversation.
        source: Origin of the conversation (discord, kubani-ui, etc.).
    """
    await pool.execute(
        """
        INSERT INTO conversations (id, user_id, source, status)
        VALUES ($1, $2, $3, 'active')
        ON CONFLICT (id) DO UPDATE SET updated_at = NOW()
        """,
        conversation_id,
        user_id,
        source,
    )


async def save_message(
    pool: DBPool,
    conversation_id: str,
    role: str,
    content: str,
    source: str = "kubani-ui",
    metadata: dict[str, Any] | None = None,
) -> int:
    """Save a message to the conversation history.

    Args:
        pool: Database connection pool.
        conversation_id: Conversation this message belongs to.
        role: Message role ('user' or 'assistant').
        content: Message text content.
        source: Origin of the message.
        metadata: Optional additional metadata.

    Returns:
        The database ID of the inserted message.
    """
    row_id = await pool.fetchval(
        """
        INSERT INTO conversation_messages (conversation_id, role, content, source, metadata)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        conversation_id,
        role,
        content,
        source,
        json.dumps(metadata or {}),
    )
    return row_id


async def get_conversation_history(
    pool: DBPool,
    conversation_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Retrieve recent conversation history.

    Args:
        pool: Database connection pool.
        conversation_id: Conversation to retrieve.
        limit: Maximum number of messages to return.

    Returns:
        List of message dicts ordered by creation time (oldest first).
    """
    rows = await pool.fetch(
        """
        SELECT role, content, source, metadata, created_at
        FROM conversation_messages
        WHERE conversation_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        conversation_id,
        limit,
    )
    # Reverse to get chronological order
    return [
        {
            "role": row["role"],
            "content": row["content"],
            "source": row["source"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "timestamp": row["created_at"].isoformat(),
        }
        for row in reversed(rows)
    ]


# =========================================================================
# Agent Actions Log
# =========================================================================


async def log_action_start(
    pool: DBPool,
    conversation_id: str,
    action_type: str,
    description: str,
    input_summary: str = "",
) -> int:
    """Log the start of an agent action.

    Args:
        pool: Database connection pool.
        conversation_id: Associated conversation.
        action_type: Type of action (e.g., 'skill_execution', 'planning').
        description: Human-readable description.
        input_summary: Brief summary of the input.

    Returns:
        The database ID of the action record.
    """
    action_id = await pool.fetchval(
        """
        INSERT INTO agent_actions (conversation_id, action_type, description, status, input_summary)
        VALUES ($1, $2, $3, 'started', $4)
        RETURNING id
        """,
        conversation_id,
        action_type,
        description,
        input_summary,
    )
    return action_id


async def log_action_complete(
    pool: DBPool,
    action_id: int,
    output_summary: str = "",
    error_message: str | None = None,
    duration_ms: int = 0,
) -> None:
    """Log the completion of an agent action.

    Args:
        pool: Database connection pool.
        action_id: ID of the action to update.
        output_summary: Brief summary of the output.
        error_message: Error message if the action failed.
        duration_ms: How long the action took in milliseconds.
    """
    status = "failed" if error_message else "completed"
    await pool.execute(
        """
        UPDATE agent_actions
        SET status = $1, output_summary = $2, error_message = $3,
            duration_ms = $4, completed_at = NOW()
        WHERE id = $5
        """,
        status,
        output_summary,
        error_message,
        duration_ms,
        action_id,
    )


async def get_recent_actions(
    pool: DBPool,
    limit: int = 20,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve recent agent actions for the UI.

    Args:
        pool: Database connection pool.
        limit: Maximum number of actions to return.
        conversation_id: Optional filter by conversation.

    Returns:
        List of action dicts ordered by start time (newest first).
    """
    if conversation_id:
        rows = await pool.fetch(
            """
            SELECT id, conversation_id, action_type, description, status,
                   input_summary, output_summary, error_message, duration_ms,
                   started_at, completed_at
            FROM agent_actions
            WHERE conversation_id = $1
            ORDER BY started_at DESC
            LIMIT $2
            """,
            conversation_id,
            limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, conversation_id, action_type, description, status,
                   input_summary, output_summary, error_message, duration_ms,
                   started_at, completed_at
            FROM agent_actions
            ORDER BY started_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(row) for row in rows]


# =========================================================================
# Skill Registry Operations
# =========================================================================


async def register_skill(
    pool: DBPool,
    name: str,
    version: str,
    oci_url: str,
    description: str = "",
    category: str = "general",
    author: str = "nexus-synthesizer",
    requires_network: bool = False,
    requires_filesystem: bool = False,
) -> int:
    """Register a new skill in the registry.

    Args:
        pool: Database connection pool.
        name: Skill name.
        version: Semantic version.
        oci_url: OCI artifact URL.
        description: Skill description.
        category: Skill category.
        author: Who created this skill.
        requires_network: Whether the skill needs network access.
        requires_filesystem: Whether the skill needs filesystem access.

    Returns:
        The database ID of the registered skill.
    """
    skill_id = await pool.fetchval(
        """
        INSERT INTO skills (name, version, oci_url, description, category, author,
                           requires_network, requires_filesystem, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending')
        ON CONFLICT (name, version) DO UPDATE
        SET oci_url = EXCLUDED.oci_url, description = EXCLUDED.description,
            updated_at = NOW()
        RETURNING id
        """,
        name,
        version,
        oci_url,
        description,
        category,
        author,
        requires_network,
        requires_filesystem,
    )
    return skill_id


async def update_skill_status(
    pool: DBPool,
    skill_id: int,
    status: str,
    risk_score: float | None = None,
    approved_by: str | None = None,
    rejection_reason: str | None = None,
) -> None:
    """Update the status of a skill in the registry.

    Args:
        pool: Database connection pool.
        skill_id: ID of the skill to update.
        status: New status value.
        risk_score: Computed risk score (if available).
        approved_by: Who approved (if applicable).
        rejection_reason: Why rejected (if applicable).
    """
    if risk_score is not None:
        await pool.execute(
            """
            UPDATE skills SET status = $1, risk_score = $2, updated_at = NOW()
            WHERE id = $3
            """,
            status,
            risk_score,
            skill_id,
        )
    if approved_by:
        await pool.execute(
            """
            UPDATE skills SET status = $1, approved_by = $2, approved_at = NOW(), updated_at = NOW()
            WHERE id = $3
            """,
            status,
            approved_by,
            skill_id,
        )
    if rejection_reason:
        await pool.execute(
            """
            UPDATE skills SET status = $1, rejection_reason = $2, updated_at = NOW()
            WHERE id = $3
            """,
            status,
            rejection_reason,
            skill_id,
        )
    if risk_score is None and approved_by is None and rejection_reason is None:
        await pool.execute(
            "UPDATE skills SET status = $1, updated_at = NOW() WHERE id = $2",
            status,
            skill_id,
        )


async def get_skill(
    pool: DBPool,
    name: str,
    version: str = "latest",
) -> dict[str, Any] | None:
    """Retrieve a skill from the registry.

    Args:
        pool: Database connection pool.
        name: Skill name.
        version: Specific version or 'latest'.

    Returns:
        Skill record as a dict, or None if not found.
    """
    if version == "latest":
        row = await pool.fetchrow(
            """
            SELECT * FROM skills
            WHERE name = $1 AND status = 'approved'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            name,
        )
    else:
        row = await pool.fetchrow(
            "SELECT * FROM skills WHERE name = $1 AND version = $2",
            name,
            version,
        )
    return dict(row) if row else None


async def list_skills(
    pool: DBPool,
    status: str | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List skills in the registry with optional filters.

    Args:
        pool: Database connection pool.
        status: Optional status filter.
        category: Optional category filter.
        limit: Maximum number of skills to return.

    Returns:
        List of skill records.
    """
    conditions = []
    params: list[Any] = []
    param_idx = 1

    if status:
        conditions.append(f"status = ${param_idx}")
        params.append(status)
        param_idx += 1

    if category:
        conditions.append(f"category = ${param_idx}")
        params.append(category)
        param_idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    params.append(limit)
    query = f"""
        SELECT * FROM skills
        {where_clause}
        ORDER BY updated_at DESC
        LIMIT ${param_idx}
    """

    rows = await pool.fetch(query, *params)
    return [dict(row) for row in rows]


# =========================================================================
# Approval Queue Operations
# =========================================================================


async def create_approval_request(
    pool: DBPool,
    request_type: str,
    reference_id: int,
    title: str,
    description: str = "",
    risk_score: float = 0.0,
) -> int:
    """Create a new approval request.

    Args:
        pool: Database connection pool.
        request_type: Type of approval (e.g., 'skill_approval').
        reference_id: ID of the referenced entity.
        title: Human-readable title.
        description: Detailed description.
        risk_score: Risk score for context.

    Returns:
        The database ID of the approval request.
    """
    request_id = await pool.fetchval(
        """
        INSERT INTO approval_requests (request_type, reference_id, title, description, risk_score)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        request_type,
        reference_id,
        title,
        description,
        risk_score,
    )
    return request_id


async def get_pending_approvals(pool: DBPool) -> list[dict[str, Any]]:
    """Get all pending approval requests.

    Returns:
        List of pending approval request dicts.
    """
    rows = await pool.fetch(
        """
        SELECT * FROM approval_requests
        WHERE status = 'pending'
        ORDER BY created_at DESC
        """
    )
    return [dict(row) for row in rows]


async def resolve_approval(
    pool: DBPool,
    approval_id: int,
    approved: bool,
    decided_by: str,
    reason: str = "",
) -> None:
    """Resolve an approval request.

    Args:
        pool: Database connection pool.
        approval_id: ID of the approval request.
        approved: Whether the request was approved.
        decided_by: Who made the decision.
        reason: Optional reason for the decision.
    """
    status = "approved" if approved else "rejected"
    await pool.execute(
        """
        UPDATE approval_requests
        SET status = $1, decided_by = $2, decided_at = NOW(), decision_reason = $3
        WHERE id = $4
        """,
        status,
        decided_by,
        reason,
        approval_id,
    )
