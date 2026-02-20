"""Nexus Orchestrator Temporal Activities.

Activities are the units of work executed by the Temporal worker. They are
designed as pure functions that accept serializable inputs and return
serializable outputs, making them independently testable.

Each activity handles one specific concern:
- plan_response: Uses the LLM to create an execution plan from user input.
- execute_skill: Runs a skill in the execution sandbox.
- generate_response: Uses the LLM to synthesize a final response.
- persist_message: Saves a message to the PostgreSQL database.
- publish_response: Publishes an agent response via Redis pub/sub.
- recall_memories: Queries the memory system for relevant context.
- store_memory: Stores a new memory from the conversation.
- notify_discord: Sends a notification to Discord.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import timedelta
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


# =========================================================================
# Planning Activity
# =========================================================================


@activity.defn
async def plan_response(input_data: dict[str, Any]) -> dict[str, Any]:
    """Use the LLM to analyze user input and create an execution plan.

    This is the 'brain' of the agent. It receives the user's message along
    with conversation history and available skills, and produces a structured
    plan of steps to execute.

    Args:
        input_data: Dict containing:
            - user_message: str - The user's message text.
            - conversation_history: list[dict] - Recent conversation messages.
            - available_skills: list[str] - Names of available skills.
            - memories: list[str] - Relevant memories from the memory system.

    Returns:
        Dict containing:
            - goal: str - The high-level goal derived from the user's message.
            - steps: list[dict] - Ordered steps to execute.
            - direct_response: str | None - If the message needs no plan,
              a direct conversational response.
            - needs_plan: bool - Whether a multi-step plan is needed.
    """
    user_message = input_data.get("user_message", "")
    conversation_history = input_data.get("conversation_history", [])
    available_skills = input_data.get("available_skills", [])
    memories = input_data.get("memories", [])

    activity.heartbeat("Starting planning")

    # Build the planning prompt
    skills_list = "\n".join(f"  - {s}" for s in available_skills) if available_skills else "  (none)"
    memories_context = "\n".join(f"  - {m}" for m in memories) if memories else "  (none)"

    history_text = ""
    for msg in conversation_history[-10:]:  # Last 10 messages for context
        role = msg.get("role", "user")
        content = msg.get("content", "")
        history_text += f"  {role}: {content}\n"

    system_prompt = f"""/no_think
You are the Kubani Nexus planning agent. Your job is to analyze the user's
message and decide whether to respond directly or create a multi-step execution plan.

AVAILABLE SKILLS:
{skills_list}

RELEVANT MEMORIES:
{memories_context}

RECENT CONVERSATION:
{history_text}

RULES:
1. For simple conversational messages (greetings, questions about yourself, etc.),
   respond directly without creating a plan.
2. For tasks that require action (research, monitoring, code generation, etc.),
   create a structured plan with specific steps.
3. Each step should reference a specific skill if one is available.
4. Keep plans concise — prefer fewer, well-defined steps over many small ones.

Respond with a JSON object:
{{
  "needs_plan": true/false,
  "direct_response": "response text if needs_plan is false",
  "goal": "high-level goal if needs_plan is true",
  "steps": [
    {{"id": 1, "description": "what to do", "skill_name": "skill-name or null"}}
  ]
}}

Respond ONLY with the JSON object, no other text."""

    from kubani.framework.llm import get_llm

    llm = get_llm()
    response = await llm.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
    )

    activity.heartbeat("Planning complete")

    # Parse the LLM response (handles code fences, thinking tags, etc.)
    try:
        plan = llm._extract_json(response)
        return {
            "needs_plan": plan.get("needs_plan", False),
            "direct_response": plan.get("direct_response"),
            "goal": plan.get("goal", ""),
            "steps": plan.get("steps", []),
        }
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Failed to parse plan from LLM: {e}. Falling back to direct response.")
        return {
            "needs_plan": False,
            "direct_response": response,
            "goal": "",
            "steps": [],
        }


# =========================================================================
# Skill Execution Activity
# =========================================================================


@activity.defn
async def execute_skill_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """Execute a skill in the sandbox environment.

    This activity delegates to the sandbox module, which handles
    the actual execution in an isolated environment.

    Args:
        input_data: Dict containing:
            - skill_name: str - Name of the skill to execute.
            - skill_version: str - Version to execute.
            - inputs: dict - Input data for the skill.
            - timeout_seconds: int - Maximum execution time.
            - conversation_id: str - For logging purposes.

    Returns:
        Dict containing:
            - success: bool
            - output: str
            - error: str | None
            - duration_ms: int
    """
    skill_name = input_data.get("skill_name", "")
    inputs = input_data.get("inputs", {})
    timeout_seconds = input_data.get("timeout_seconds", 60)

    activity.heartbeat(f"Executing skill: {skill_name}")

    start_time = time.monotonic()

    try:
        from kubani.nexus.sandbox.executor import execute_skill_in_sandbox

        result = await execute_skill_in_sandbox(
            skill_name=skill_name,
            inputs=inputs,
            timeout_seconds=timeout_seconds,
        )

        duration_ms = int((time.monotonic() - start_time) * 1000)

        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "duration_ms": duration_ms,
            "exit_code": result.exit_code,
            "logs": result.logs,
        }
    except Exception as e:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(f"Skill execution failed: {e}")
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "duration_ms": duration_ms,
            "exit_code": -1,
            "logs": "",
        }


# =========================================================================
# Response Generation Activity
# =========================================================================


@activity.defn
async def generate_response(input_data: dict[str, Any]) -> dict[str, Any]:
    """Use the LLM to synthesize a final response from execution results.

    After the plan has been executed, this activity takes the results
    and produces a human-readable response for the user.

    Args:
        input_data: Dict containing:
            - user_message: str - The original user message.
            - goal: str - The plan's goal.
            - step_results: list[dict] - Results from each executed step.
            - conversation_history: list[dict] - Recent conversation.

    Returns:
        Dict containing:
            - response_text: str - The synthesized response.
    """
    user_message = input_data.get("user_message", "")
    goal = input_data.get("goal", "")
    step_results = input_data.get("step_results", [])

    activity.heartbeat("Generating response")

    results_text = ""
    for i, result in enumerate(step_results, 1):
        status = "succeeded" if result.get("success") else "failed"
        output = result.get("output", "")[:500]  # Truncate long outputs
        error = result.get("error", "")
        results_text += f"Step {i} ({status}): {output}\n"
        if error:
            results_text += f"  Error: {error}\n"

    system_prompt = """/no_think
You are the Kubani Nexus assistant. Synthesize the execution results
into a clear, helpful response for the user. Be concise but informative.
If steps failed, explain what went wrong and suggest next steps.
Use Markdown formatting where appropriate."""

    user_prompt = f"""Original request: {user_message}
Goal: {goal}

Execution results:
{results_text}

Please provide a clear summary response."""

    from kubani.framework.llm import get_llm

    llm = get_llm()
    response = await llm.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )

    return {"response_text": response}


# =========================================================================
# Persistence Activities
# =========================================================================


@activity.defn
async def persist_message(input_data: dict[str, Any]) -> dict[str, Any]:
    """Save a message to the PostgreSQL database.

    Args:
        input_data: Dict containing:
            - conversation_id: str
            - user_id: str
            - role: str ('user' or 'assistant')
            - content: str
            - source: str

    Returns:
        Dict with message_id.
    """
    from kubani.nexus.db import create_pool, ensure_conversation, save_message

    conversation_id = input_data["conversation_id"]
    user_id = input_data.get("user_id", "system")
    role = input_data["role"]
    content = input_data["content"]
    source = input_data.get("source", "kubani-ui")

    import os

    db_url = os.environ.get(
        "NEXUS_DATABASE_URL",
        "postgresql://kubani:kubani@localhost:5432/kubani_nexus",
    )
    pool = await create_pool(db_url)
    try:
        await ensure_conversation(pool, conversation_id, user_id, source)
        msg_id = await save_message(pool, conversation_id, role, content, source)
        return {"message_id": msg_id}
    finally:
        await pool.close()


@activity.defn
async def log_action_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """Log an agent action to the database for UI observability.

    Args:
        input_data: Dict containing:
            - conversation_id: str
            - action_type: str
            - description: str
            - input_summary: str
            - status: str ('started', 'completed', 'failed')
            - output_summary: str (for completion)
            - error_message: str (for failure)
            - duration_ms: int (for completion)
            - action_id: int (for updates, omit for new actions)

    Returns:
        Dict with action_id.
    """
    from kubani.nexus.db import (
        create_pool,
        log_action_complete,
        log_action_start,
    )

    import os

    db_url = os.environ.get(
        "NEXUS_DATABASE_URL",
        "postgresql://kubani:kubani@localhost:5432/kubani_nexus",
    )
    pool = await create_pool(db_url)
    try:
        action_id = input_data.get("action_id")
        if action_id is None:
            # New action
            action_id = await log_action_start(
                pool,
                input_data["conversation_id"],
                input_data["action_type"],
                input_data["description"],
                input_data.get("input_summary", ""),
            )
        else:
            # Update existing action
            await log_action_complete(
                pool,
                action_id,
                input_data.get("output_summary", ""),
                input_data.get("error_message"),
                input_data.get("duration_ms", 0),
            )
        return {"action_id": action_id}
    finally:
        await pool.close()


# =========================================================================
# Pub/Sub Activity
# =========================================================================


@activity.defn
async def publish_response_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """Publish an agent response via Redis pub/sub.

    This is how the Orchestrator sends responses back to the Gateway,
    which then routes them to the correct client (WebSocket, Discord).

    Args:
        input_data: Dict containing:
            - conversation_id: str
            - text: str
            - metadata: dict (optional)

    Returns:
        Dict with published: bool.
    """
    import os

    from kubani.nexus.pubsub import NexusPubSub

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    pubsub = NexusPubSub(redis_url=redis_url)
    await pubsub.connect()

    try:
        from kubani.nexus.models.messages import AgentMessage

        message = AgentMessage(
            conversation_id=input_data["conversation_id"],
            text=input_data["text"],
            metadata=input_data.get("metadata", {}),
        )
        await pubsub.publish_response(
            input_data["conversation_id"], message.to_dict()
        )
        return {"published": True}
    except Exception as e:
        logger.error(f"Failed to publish response: {e}")
        return {"published": False, "error": str(e)}
    finally:
        await pubsub.close()


# =========================================================================
# Memory Activities
# =========================================================================


@activity.defn
async def recall_memories_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """Query the memory system for relevant context.

    Args:
        input_data: Dict containing:
            - query: str - The text to search for relevant memories.
            - user_id: str - The user to search memories for.
            - limit: int - Maximum number of memories to return.

    Returns:
        Dict with memories: list[str].
    """
    query = input_data.get("query", "")
    user_id = input_data.get("user_id", "default")
    limit = input_data.get("limit", 5)

    activity.heartbeat("Recalling memories")

    try:
        from kubani.nexus.memory.client import MemoryClient

        client = MemoryClient()
        await client.initialize()
        memories = await client.search(query=query, user_id=user_id, limit=limit)
        return {"memories": memories}
    except Exception as e:
        logger.warning(f"Memory recall failed (non-fatal): {e}")
        return {"memories": []}


@activity.defn
async def store_memory_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """Store a new memory from the conversation.

    Args:
        input_data: Dict containing:
            - content: str - The memory content to store.
            - user_id: str - The user this memory belongs to.
            - metadata: dict - Additional metadata.

    Returns:
        Dict with stored: bool.
    """
    content = input_data.get("content", "")
    user_id = input_data.get("user_id", "default")
    metadata = input_data.get("metadata", {})

    try:
        from kubani.nexus.memory.client import MemoryClient

        client = MemoryClient()
        await client.initialize()
        await client.add(content=content, user_id=user_id, metadata=metadata)
        return {"stored": True}
    except Exception as e:
        logger.warning(f"Memory storage failed (non-fatal): {e}")
        return {"stored": False, "error": str(e)}


# =========================================================================
# Discord Notification Activity
# =========================================================================


@activity.defn
async def notify_discord_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """Send a notification to Discord.

    Args:
        input_data: Dict containing:
            - channel: str - Discord channel name or ID.
            - message: str - Message text to send.
            - embed: dict | None - Optional Discord embed.

    Returns:
        Dict with sent: bool.
    """
    channel = input_data.get("channel", "general")
    message = input_data.get("message", "")

    activity.heartbeat("Sending Discord notification")

    try:
        # Use the Discord MCP server to send messages
        import httpx

        import os

        discord_mcp_url = os.environ.get(
            "MCP_DISCORD_URL", "http://localhost:8084"
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{discord_mcp_url}/tools/send_message",
                json={"channel": channel, "content": message},
                timeout=10.0,
            )
            response.raise_for_status()
            return {"sent": True}
    except Exception as e:
        logger.warning(f"Discord notification failed (non-fatal): {e}")
        return {"sent": False, "error": str(e)}
