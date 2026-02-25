"""Nexus Orchestrator Temporal Activities.

Activities are the units of work executed by the Temporal worker. They are
designed as pure functions that accept serializable inputs and return
serializable outputs, making them independently testable.

Each activity handles one specific concern:

Agentic loop activities (Strands-based):
- run_agent_turn: Creates a Strands Agent with core tools, runs the full
  think→act→observe loop to completion, and returns the final response.
- run_mission_agent_turn: Like run_agent_turn but for proactive missions.
  Uses a mission-specific system prompt, enforces a max_tool_calls budget,
  uses a policy-scoped MCP client set, and returns a structured result
  indicating whether to notify the user.

Legacy planning activities (kept for backward compatibility):
- plan_response: Uses the LLM to create an execution plan from user input.
- execute_skill: Runs a skill in the execution sandbox.
- generate_response: Uses the LLM to synthesize a final response.

Infrastructure activities:
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
from datetime import UTC
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


# =========================================================================
# Agentic Loop Activity (Strands-based)
# =========================================================================


# System prompt for the Strands agent
AGENT_SYSTEM_PROMPT = """/no_think
You are Nexus, the Kubani platform's personal intelligence assistant. You help
users with coding tasks, research, knowledge management, and skill discovery.

You are a TOOL-USING assistant. You MUST use your tools to gather real
information before answering. Do NOT answer from memory or training data
when a tool can provide accurate, up-to-date information.

CRITICAL RULES FOR TOOL USE:
1. When the user provides a URL: ALWAYS use fetch to read it before responding.
2. When the user asks about a website, project, or external topic: use
   web_search or fetch to get current information.
3. When the user asks about files in the workspace: use read_file first.
4. Prefer tool-sourced facts over your training knowledge.
5. Only respond without tools for simple greetings or conversational messages.

Your tools:

WORKSPACE: read_file, write_file, edit_file, bash, register_skill
  For coding tasks and file operations. Always read before editing.
  Use edit_file for surgical changes, write_file for new files.

MEMORY (via MCP): Store and query knowledge, learnings, and context.
  For remembering information across conversations.

SKILLS (via MCP): Discover and execute registered Kubani skills.
  For finding and running pre-built capabilities.

FETCH (via MCP): fetch — read any URL and get its content as markdown.
  Use this when the user provides a URL or references a web page.

WEB SEARCH: web_search — DuckDuckGo internet search.
  Use this to find current information when no URL is given.

COMPUTER USE (via MCP): screenshot, click, type_text, scroll, navigate, key
  For browser automation. Take a screenshot first, then use analyze_screen
  to understand what's on screen, then issue actions.

VISION: analyze_screen — send a screenshot to the vision model for UI element grounding.
  Always call this after screenshot to understand the page before clicking.

WHEN TOOLS FAIL:
- If a tool call returns an error, DO NOT immediately give up or apologize.
- Analyze the error, then retry with corrected parameters or try an
  alternative tool.
- Retry the same tool up to 2 times with different parameters before giving up.
- If fetch fails on a URL, try web_search for the same topic as a fallback.
- Only report failure to the user after exhausting alternatives.
- When reporting a failure, explain what you tried and what went wrong.

After gathering information with tools, respond with a clear, concise
summary based on what you found.

Notes:
- For cluster operations (pod status, deployments, etc.), let the user
  know that dedicated cluster tools are coming soon. You can still help
  with Kubernetes YAML files, Helm charts, and documentation.
- Be concise in your responses."""


@activity.defn
async def run_agent_turn(input_data: dict[str, Any]) -> dict[str, Any]:
    """Run a full agentic turn using the Strands Agent SDK.

    Creates a Strands Agent with OpenAIModel pointing to vLLM and the
    core workspace tools. The agent handles the full LLM↔Tool loop
    internally and returns when the LLM produces a text response
    without tool calls.

    Args:
        input_data: Dict containing:
            - user_message: str — the user's message
            - conversation_history: list[dict] — recent conversation
            - memories: list[str] — relevant memories
            - user_id: str — for workspace resolution

    Returns:
        Dict with response_text and tool_calls_made.
    """
    user_message = input_data.get("user_message", "")
    conversation_history = input_data.get("conversation_history", [])
    memories = input_data.get("memories", [])
    user_id = input_data.get("user_id", "default")

    activity.heartbeat("Creating Strands agent")
    logger.info(f"run_agent_turn: user={user_id}, msg={user_message[:100]}")

    from strands import Agent
    from strands.models.openai import OpenAIModel

    from kubani.framework.config import get_llm_config
    from kubani.nexus.tools.core import get_workspace
    from kubani.nexus.tools.mcp_clients import create_mcp_clients
    from kubani.nexus.tools.strands_tools import create_tools
    from kubani.nexus.tools.vision import analyze_screen

    llm_config = get_llm_config()
    workspace = get_workspace(user_id)
    workspace_tools = create_tools(workspace)
    workspace_tools.append(analyze_screen)

    # Create MCP clients. Strands Agent() will call start() on each
    # MCPClient during tool registration. If any fail, Agent() raises
    # ValueError so we wrap in a try/except below.
    mcp_clients = create_mcp_clients()
    logger.info(f"Created {len(mcp_clients)} MCP client(s)")

    model = OpenAIModel(
        client_args={
            "api_key": llm_config.api_key or "not-needed",
            "base_url": llm_config.api_url,
        },
        model_id=llm_config.model,
        params={
            "temperature": llm_config.temperature,
            "max_tokens": llm_config.max_tokens,
        },
    )

    # Build the prompt with context
    prompt_parts = []

    # Add memories if available
    if memories:
        mem_text = "Relevant context from memory:\n" + "\n".join(f"- {m}" for m in memories)
        prompt_parts.append(mem_text)

    # Add conversation history summary (last 10 messages)
    if conversation_history:
        history_lines = []
        for msg in conversation_history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:500]
            history_lines.append(f"{role}: {content}")
        if history_lines:
            prompt_parts.append("Recent conversation:\n" + "\n".join(history_lines))

    prompt_parts.append(user_message)
    full_prompt = "\n\n".join(prompt_parts)

    # Try creating agent with MCP clients. If any MCP server is
    # unreachable, Agent() raises ValueError — fall back to workspace only.
    system_prompt = AGENT_SYSTEM_PROMPT
    try:
        all_tools = [*workspace_tools, *mcp_clients]
        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=all_tools,
            callback_handler=None,
        )
        logger.info(f"Agent created with {len(all_tools)} tools (inc. MCP)")
    except ValueError as e:
        logger.warning(f"MCP client failed during Agent init, falling back: {e}")
        mcp_clients = []
        system_prompt += (
            "\n\nNote: MCP servers could not be reached. "
            "Memory, Skills, and Fetch tools are unavailable this session."
        )
        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=workspace_tools,
            callback_handler=None,
        )

    activity.heartbeat("Running Strands agent loop")

    try:
        result = await agent.invoke_async(full_prompt)
        response_text = str(result)

        # Strip Qwen3 empty thinking tags (appear even with /no_think prefix)
        import re

        response_text = re.sub(r"<think>\s*</think>\s*", "", response_text).strip()

        activity.heartbeat("Agent loop complete")
        logger.info(
            f"run_agent_turn complete: stop_reason={result.stop_reason}, response={response_text[:200]}"
        )

        return {
            "response_text": response_text,
            "stop_reason": str(result.stop_reason),
        }
    except Exception as e:
        logger.error(f"Strands agent error: {e}", exc_info=True)
        return {
            "response_text": f"I encountered an error while processing your request: {e}",
            "stop_reason": "error",
        }
    finally:
        # Clean up MCP client connections to prevent SSE leaks
        # on activity timeout or cancellation.
        # Strands MCPClient uses stop() (context manager pattern), not close().
        for client in mcp_clients:
            try:
                client.stop(None, None, None)
            except Exception:
                pass


# =========================================================================
# Mission Agent Turn Activity (proactive loop)
# =========================================================================


# System prompt for autonomous mission turns.
# The agent is instructed to work on the goal, use tools efficiently,
# and return a structured JSON response indicating whether to notify the user.
MISSION_SYSTEM_PROMPT = """/no_think
You are Nexus, running in autonomous mission mode. You are executing a
scheduled background mission on behalf of the user — they are NOT actively
watching this session.

Your mission goal:
{mission_goal}

You have a budget of {max_tool_calls} tool calls to complete this mission.
Use your tools efficiently. Prioritise gathering real, current data over
reasoning from training knowledge.

CRITICAL RULES:
1. Work autonomously — do not ask the user clarifying questions.
2. Use your tool budget wisely. Stop early if you have a clear answer.
3. Only flag something as an anomaly if it is genuinely unusual or actionable.
4. Do NOT notify the user for routine, expected, or unchanged results.
5. Be concise in your notification text — the user wants a summary, not a log.

When you have finished gathering information, you MUST respond with a JSON
object in EXACTLY this format (no markdown fences, no extra text):
{{
  "should_notify": true,
  "found_anomaly": false,
  "notification_text": "A concise summary of findings for the user."
}}

Or if nothing noteworthy was found:
{{
  "should_notify": false,
  "found_anomaly": false,
  "notification_text": ""
}}
"""


@activity.defn
async def run_mission_agent_turn(input_data: dict[str, Any]) -> dict[str, Any]:
    """Run a proactive mission turn using the Strands Agent SDK.

    Key differences from run_agent_turn:
    - Uses MISSION_SYSTEM_PROMPT (autonomous, no user interaction).
    - Enforces a hard max_tool_calls budget via a callback counter.
    - Uses a policy-scoped MCP client set (default: ``nexus``).
    - Returns a structured result with should_notify / notification_text
      rather than always publishing a response.
    - Records the run outcome in the nexus_mission_runs table.

    Args:
        input_data: Dict containing:
            - mission_id: str
            - mission_title: str
            - mission_goal: str — natural language goal
            - user_id: str
            - mcp_policy: str — MCP policy name (default: ``nexus``)
            - max_tool_calls: int — hard cap (default: 20, max: 50)
            - notify_on: list[str] — conditions for user notification
            - recent_history: list[dict] — last 5 conversation messages

    Returns:
        Dict with:
            - should_notify: bool
            - found_anomaly: bool
            - notification_text: str
            - tool_calls_made: int
            - run_id: str
            - status: str (completed / failed / timed_out)
    """
    import os
    import re
    import time
    import uuid
    from datetime import datetime

    mission_id = input_data.get("mission_id", "unknown")
    mission_title = input_data.get("mission_title", "Untitled Mission")
    mission_goal = input_data.get("mission_goal", "")
    user_id = input_data.get("user_id", "default")
    mcp_policy = input_data.get("mcp_policy", "nexus")
    max_tool_calls = min(int(input_data.get("max_tool_calls", 20)), 50)
    recent_history = input_data.get("recent_history", [])

    run_id = f"run-{uuid.uuid4().hex[:12]}"
    started_at = time.monotonic()
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

    activity.heartbeat(f"Mission {mission_id}: starting run {run_id}")
    logger.info(
        f"run_mission_agent_turn: mission={mission_id}, "
        f"policy={mcp_policy}, max_tool_calls={max_tool_calls}"
    )

    # ------------------------------------------------------------------
    # Record the run start in the database
    # ------------------------------------------------------------------
    db_url = os.environ.get(
        "NEXUS_DATABASE_URL",
        "postgresql://kubani:kubani@localhost:5432/kubani_nexus",
    )
    try:
        from kubani.nexus.db import create_pool
        from kubani.nexus.missions.db import complete_mission_run, create_mission_run

        pool = await create_pool(db_url)
        await create_mission_run(
            pool,
            {
                "id": run_id,
                "mission_id": mission_id,
                "user_id": user_id,
                "status": "running",
                "started_at": datetime.now(UTC).isoformat(),
            },
        )
    except Exception as db_exc:
        logger.warning(f"Could not record mission run start: {db_exc}")
        pool = None

    # ------------------------------------------------------------------
    # Publish "mission started" to the UI activity feed
    # ------------------------------------------------------------------
    try:
        from kubani.framework.ui_events import publish_activity

        await publish_activity(
            source="nexus",
            event_type="agent_activity",
            title=f"Mission started: {mission_title}",
            content=(
                f"**Goal:** {mission_goal}\n\n"
                f"*Budget: {max_tool_calls} tool calls, Policy: {mcp_policy}*"
            ),
            severity="info",
            metadata={
                "mission_id": mission_id,
                "run_id": run_id,
                "user_id": user_id,
                "mcp_policy": mcp_policy,
                "max_tool_calls": max_tool_calls,
            },
            redis_url=redis_url,
        )
    except Exception:
        logger.debug(f"Mission {mission_id}: could not publish start event to UI")

    # ------------------------------------------------------------------
    # Build the agent
    # ------------------------------------------------------------------
    from strands import Agent
    from strands.models.openai import OpenAIModel

    from kubani.framework.config import get_llm_config
    from kubani.nexus.tools.mcp_clients import create_mcp_clients, load_tools_resilient

    llm_config = get_llm_config()
    mcp_clients = create_mcp_clients(policy_name=mcp_policy)

    # Pre-load tools from each client individually so one bad client
    # (e.g. kubernetes npx) doesn't kill all MCP tools.
    mcp_tools, started_clients = await load_tools_resilient(mcp_clients)
    logger.info(f"Mission {mission_id}: loaded {len(mcp_tools)} MCP tools")

    model = OpenAIModel(
        client_args={
            "api_key": llm_config.api_key or "not-needed",
            "base_url": llm_config.api_url,
        },
        model_id=llm_config.model,
        params={
            "temperature": llm_config.temperature,
            "max_tokens": llm_config.max_tokens,
        },
    )

    # ------------------------------------------------------------------
    # Tool call budget enforcer (Strands HookProvider)
    # ------------------------------------------------------------------
    from strands.hooks.events import BeforeToolCallEvent
    from strands.hooks.registry import HookProvider, HookRegistry

    class _ToolBudgetHook(HookProvider):
        """Enforces a hard cap on tool calls per mission run.

        Uses Strands' BeforeToolCallEvent to cancel tool calls once the
        budget is exceeded, preventing runaway agentic loops.
        """

        def __init__(self, budget: int, mid: str) -> None:
            self.budget = budget
            self.mission_id = mid
            self.tool_calls_made = 0

        def register_hooks(self, registry: HookRegistry, **_kwargs: Any) -> None:
            registry.add_callback(BeforeToolCallEvent, self._on_before_tool_call)

        def _on_before_tool_call(self, event: BeforeToolCallEvent) -> None:
            self.tool_calls_made += 1
            tool_name = event.tool_use.get("name", "unknown")
            activity.heartbeat(
                f"Mission {self.mission_id}: tool call "
                f"{self.tool_calls_made}/{self.budget} ({tool_name})"
            )
            if self.tool_calls_made > self.budget:
                event.cancel_tool = (
                    f"Tool call budget exceeded ({self.tool_calls_made}/{self.budget}). "
                    "Stopping mission. Return your JSON result now."
                )

    budget_hook = _ToolBudgetHook(budget=max_tool_calls, mid=mission_id)

    # ------------------------------------------------------------------
    # Build the prompt
    # ------------------------------------------------------------------
    system_prompt = MISSION_SYSTEM_PROMPT.format(
        mission_goal=mission_goal,
        max_tool_calls=max_tool_calls,
    )

    prompt_parts: list[str] = []
    if recent_history:
        history_lines = []
        for msg in recent_history[-5:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:300]
            history_lines.append(f"{role}: {content}")
        prompt_parts.append(
            "Recent conversation context (for reference only):\n" + "\n".join(history_lines)
        )
    prompt_parts.append(
        f"Execute your mission now. Goal: {mission_goal}\n\n"
        "When done, respond ONLY with the JSON result object."
    )
    full_prompt = "\n\n".join(prompt_parts)

    # ------------------------------------------------------------------
    # Run the agent
    # ------------------------------------------------------------------
    result_dict: dict[str, Any] = {
        "should_notify": False,
        "found_anomaly": False,
        "notification_text": "",
        "tool_calls_made": 0,
        "run_id": run_id,
        "status": "completed",
    }

    try:
        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=mcp_tools,
            callback_handler=None,
            hooks=[budget_hook],
        )

        activity.heartbeat(f"Mission {mission_id}: agent created, running loop")
        raw_result = await agent.invoke_async(full_prompt)
        raw_text = str(raw_result)

        # Strip Qwen3 empty thinking tags
        raw_text = re.sub(r"<think>\s*</think>\s*", "", raw_text).strip()

        logger.info(f"run_mission_agent_turn: mission={mission_id}, raw_response={raw_text[:300]}")

        # ------------------------------------------------------------------
        # Parse the structured JSON response from the agent
        # ------------------------------------------------------------------
        import json as _json

        # Try to extract a JSON object from the response
        json_match = re.search(r"\{[\s\S]*\}", raw_text)
        if json_match:
            try:
                parsed = _json.loads(json_match.group())
                result_dict["should_notify"] = bool(parsed.get("should_notify", False))
                result_dict["found_anomaly"] = bool(parsed.get("found_anomaly", False))
                result_dict["notification_text"] = str(parsed.get("notification_text", ""))
            except _json.JSONDecodeError:
                # If the agent didn't return valid JSON, treat the whole
                # response as a notification (conservative fallback)
                logger.warning(
                    f"Mission {mission_id}: could not parse JSON from agent response; "
                    "treating as notification"
                )
                result_dict["should_notify"] = True
                result_dict["notification_text"] = raw_text[:1000]
        else:
            # No JSON found — treat as notification if non-empty
            if raw_text.strip():
                result_dict["should_notify"] = True
                result_dict["notification_text"] = raw_text[:1000]

        result_dict["tool_calls_made"] = budget_hook.tool_calls_made
        result_dict["status"] = "completed"

    except RuntimeError as budget_exc:
        # Tool budget exceeded — still try to parse whatever the agent said
        logger.warning(f"Mission {mission_id}: tool budget exceeded: {budget_exc}")
        result_dict["tool_calls_made"] = budget_hook.tool_calls_made
        result_dict["status"] = "timed_out"
        result_dict["should_notify"] = True
        result_dict["notification_text"] = (
            f"Mission '{mission_title}' reached its tool call budget "
            f"({max_tool_calls} calls) before completing. "
            "Consider increasing the budget or narrowing the goal."
        )

    except Exception as exc:
        logger.error(f"Mission {mission_id}: agent error: {exc}", exc_info=True)
        result_dict["tool_calls_made"] = budget_hook.tool_calls_made
        result_dict["status"] = "failed"
        result_dict["should_notify"] = True
        result_dict["notification_text"] = f"Mission '{mission_title}' encountered an error: {exc}"

    finally:
        # Clean up MCP connections
        for client in started_clients:
            try:
                client.stop(None, None, None)
            except Exception:
                pass

        # Record the run outcome in the database
        duration_ms = int((time.monotonic() - started_at) * 1000)
        if pool is not None:
            try:
                await complete_mission_run(
                    pool,
                    run_id=run_id,
                    status=result_dict["status"],
                    tool_calls_made=result_dict["tool_calls_made"],
                    found_anomaly=result_dict["found_anomaly"],
                    notification_text=result_dict["notification_text"],
                    error_message=""
                    if result_dict["status"] == "completed"
                    else result_dict["notification_text"],
                    duration_ms=duration_ms,
                )
            except Exception as db_exc:
                logger.warning(f"Could not record mission run completion: {db_exc}")
            finally:
                await pool.close()

        # Publish mission result to the UI activity feed
        try:
            from kubani.framework.ui_events import publish_activity

            status = result_dict["status"]
            if status == "completed" and result_dict["should_notify"]:
                await publish_activity(
                    source="nexus",
                    event_type="agent_activity",
                    title=f"Mission finding: {mission_title}",
                    content=result_dict["notification_text"],
                    severity="success",
                    metadata={
                        "mission_id": mission_id,
                        "run_id": run_id,
                        "status": status,
                        "tool_calls_made": result_dict["tool_calls_made"],
                        "found_anomaly": result_dict["found_anomaly"],
                        "duration_ms": duration_ms,
                    },
                    redis_url=redis_url,
                )
            elif status == "completed":
                await publish_activity(
                    source="nexus",
                    event_type="agent_activity",
                    title=f"Mission completed: {mission_title}",
                    content=(
                        f"Completed normally. Used {result_dict['tool_calls_made']}"
                        f"/{max_tool_calls} tool calls in {duration_ms}ms."
                    ),
                    severity="info",
                    metadata={
                        "mission_id": mission_id,
                        "run_id": run_id,
                        "status": status,
                        "tool_calls_made": result_dict["tool_calls_made"],
                        "duration_ms": duration_ms,
                    },
                    redis_url=redis_url,
                )
            elif status == "failed":
                await publish_activity(
                    source="nexus",
                    event_type="alert",
                    title=f"Mission failed: {mission_title}",
                    content=result_dict["notification_text"],
                    severity="error",
                    metadata={
                        "mission_id": mission_id,
                        "run_id": run_id,
                        "status": status,
                        "tool_calls_made": result_dict["tool_calls_made"],
                        "duration_ms": duration_ms,
                    },
                    redis_url=redis_url,
                )
            elif status == "timed_out":
                await publish_activity(
                    source="nexus",
                    event_type="alert",
                    title=f"Mission timed out: {mission_title}",
                    content=result_dict["notification_text"],
                    severity="warning",
                    metadata={
                        "mission_id": mission_id,
                        "run_id": run_id,
                        "status": status,
                        "tool_calls_made": result_dict["tool_calls_made"],
                        "duration_ms": duration_ms,
                    },
                    redis_url=redis_url,
                )
        except Exception:
            logger.debug(f"Mission {mission_id}: could not publish result event to UI")

    activity.heartbeat(f"Mission {mission_id}: run {run_id} complete")
    return result_dict


# =========================================================================
# Planning Activity (legacy — kept for backward compatibility)
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
    skills_list = (
        "\n".join(f"  - {s}" for s in available_skills) if available_skills else "  (none)"
    )
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
    import os

    from kubani.nexus.db import (
        create_pool,
        log_action_complete,
        log_action_start,
    )

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
        await pubsub.publish_response(input_data["conversation_id"], message.to_dict())
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
        import os

        import httpx

        discord_mcp_url = os.environ.get("MCP_DISCORD_URL", "http://localhost:8084")

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
