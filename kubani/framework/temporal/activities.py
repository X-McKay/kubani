"""Base Temporal activities for agent execution.

This module provides the infrastructure to wrap Kubani agents as Temporal activities.
Activities are thin wrappers that handle:
- Agent instantiation and caching
- Temporal serialization requirements (dicts instead of dataclasses)
- Heartbeating for long-running agent calls
- Consistent error handling and logging

Usage:
    from kubani.framework.temporal.activities import agent_activity, run_agent_activity

    # Register activities with worker
    worker = Worker(
        client,
        task_queue="my-task-queue",
        activities=[run_agent_activity],
    )

    # Execute in workflow
    result = await workflow.execute_activity(
        run_agent_activity,
        args=["event-classifier", "Classify this event: OOMKilled"],
        start_to_close_timeout=timedelta(minutes=5),
        heartbeat_timeout=timedelta(minutes=1),
    )
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import activity
from temporalio.common import RetryPolicy

logger = logging.getLogger(__name__)


# =============================================================================
# Type Definitions
# =============================================================================


@dataclass
class AgentInput:
    """Input for running an agent.

    Attributes:
        agent_name: Name of the agent to run (e.g., "event-classifier")
        input_text: The prompt/input to send to the agent
        context: Optional additional context for the agent
        max_tokens: Optional token limit override
    """

    agent_name: str
    input_text: str
    context: dict[str, Any] | None = None
    max_tokens: int | None = None


@dataclass
class AgentOutput:
    """Output from running an agent.

    Attributes:
        agent_name: Name of the agent that ran
        result: The agent's response text
        success: Whether the execution succeeded
        error: Error message if failed
        metadata: Additional metadata (timing, tokens, etc.)
    """

    agent_name: str
    result: str
    success: bool
    error: str | None = None
    metadata: dict[str, Any] | None = None


# =============================================================================
# Default Retry Policy
# =============================================================================


DEFAULT_AGENT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
    non_retryable_error_types=["AgentNotFoundError", "ValidationError"],
)


# =============================================================================
# Agent Registry
# =============================================================================

# Cache of agent instances to avoid re-instantiation
_agent_cache: dict[str, Any] = {}


def _get_agent(agent_name: str) -> Any:
    """Get or create an agent instance by name.

    Args:
        agent_name: Name of the agent (e.g., "event-classifier", "remediator")

    Returns:
        Agent instance

    Raises:
        AgentNotFoundError: If agent is not registered
    """
    if agent_name in _agent_cache:
        return _agent_cache[agent_name]

    # Import agent dynamically based on name
    # Agent names map to kubani/agents/{name}/agent.py
    agent_module_map = {
        "event-classifier": "kubani.agents.event_classifier.agent",
        "remediator": "kubani.agents.remediator.agent",
        "feed-collector": "kubani.agents.feed_collector.agent",
        "content-analyst": "kubani.agents.content_analyst.agent",
        "trend-analyst": "kubani.agents.trend_analyst.agent",
        "digest-publisher": "kubani.agents.digest_publisher.agent",
        "research-collector": "kubani.agents.research_collector.agent",
        "research-analyst": "kubani.agents.research_analyst.agent",
        "skill-learner": "kubani.agents.skill_learner.agent",
    }

    if agent_name not in agent_module_map:
        raise AgentNotFoundError(f"Unknown agent: {agent_name}")

    try:
        import importlib

        module_path = agent_module_map[agent_name]
        module = importlib.import_module(module_path)

        # Convention: Agent class is the module's main export
        # e.g., EventClassifierAgent, RemediatorAgent
        agent_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and attr_name.endswith("Agent")
                and attr_name != "KubaniAgent"
            ):
                agent_class = attr
                break

        if agent_class is None:
            raise AgentNotFoundError(f"No agent class found in {module_path}")

        agent = agent_class()
        _agent_cache[agent_name] = agent
        logger.info(f"Instantiated agent: {agent_name}")
        return agent

    except ImportError as e:
        raise AgentNotFoundError(f"Failed to import agent {agent_name}: {e}") from e


def clear_agent_cache() -> None:
    """Clear the agent cache. Useful for testing."""
    _agent_cache.clear()


# =============================================================================
# Exceptions
# =============================================================================


class AgentNotFoundError(Exception):
    """Raised when an agent is not found in the registry."""

    pass


class AgentExecutionError(Exception):
    """Raised when agent execution fails."""

    pass


# =============================================================================
# Activities
# =============================================================================


@activity.defn
async def run_agent_activity(
    agent_name: str,
    input_text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run an agent with the given input.

    This is the primary activity for executing agents within Temporal workflows.
    It handles agent instantiation, execution, and result serialization.

    Args:
        agent_name: Name of the agent to run (e.g., "event-classifier")
        input_text: The prompt/input to send to the agent
        context: Optional additional context

    Returns:
        Dict with 'result', 'success', 'error', and 'metadata'

    Example:
        # In a workflow
        result = await workflow.execute_activity(
            run_agent_activity,
            args=["event-classifier", "Classify: OOMKilled in pod nginx"],
            start_to_close_timeout=timedelta(minutes=5),
        )

        if result["success"]:
            classification = result["result"]
    """
    logger.info(f"run_agent_activity: Starting {agent_name}")

    try:
        # Get or create agent
        agent = _get_agent(agent_name)

        # Heartbeat to indicate we're still working
        activity.heartbeat(f"Running agent {agent_name}")

        # Build input with context if provided
        full_input = input_text
        if context:
            import json

            context_str = json.dumps(context, indent=2)
            full_input = f"{input_text}\n\nContext:\n{context_str}"

        # Run the agent
        result = await agent.run(full_input)

        logger.info(f"run_agent_activity: {agent_name} completed successfully")

        return {
            "agent_name": agent_name,
            "result": result,
            "success": True,
            "error": None,
            "metadata": {
                "context_provided": context is not None,
            },
        }

    except AgentNotFoundError as e:
        logger.error(f"run_agent_activity: Agent not found: {e}")
        return {
            "agent_name": agent_name,
            "result": "",
            "success": False,
            "error": str(e),
            "metadata": None,
        }

    except Exception as e:
        logger.exception(f"run_agent_activity: {agent_name} failed: {e}")
        return {
            "agent_name": agent_name,
            "result": "",
            "success": False,
            "error": str(e),
            "metadata": None,
        }


@activity.defn
async def classify_event_activity(
    event_data: dict[str, Any],
) -> dict[str, Any]:
    """Classify a Kubernetes event using the EventClassifier agent.

    This is a specialized activity for event classification that uses
    the EventClassifier's classify_event method directly rather than
    the generic agent.run() interface.

    Args:
        event_data: Dictionary representation of K8sEvent

    Returns:
        Dict with classification result or error

    Example:
        result = await workflow.execute_activity(
            classify_event_activity,
            args=[{"type": "Warning", "reason": "OOMKilled", ...}],
            start_to_close_timeout=timedelta(minutes=2),
        )
    """
    logger.info(f"classify_event_activity: Processing event {event_data.get('reason')}")

    try:
        from kubani.agents.event_classifier.agent import K8sEvent

        agent = _get_agent("event-classifier")

        # Heartbeat
        activity.heartbeat("Classifying event")

        # Create K8sEvent from dict
        event = K8sEvent.from_dict(event_data)

        # Check if event should be ignored
        if agent.should_ignore_event(event):
            return {
                "success": True,
                "ignored": True,
                "reason": "Event matches ignore patterns",
                "classification": None,
            }

        # Classify the event
        classification = await agent.classify_event(event)

        return {
            "success": True,
            "ignored": False,
            "classification": {
                "severity": classification.severity,
                "is_actionable": classification.is_actionable,
                "category": classification.category,
                "reason": classification.reason,
                "method": classification.method.value,
                "confidence": classification.confidence,
                "suggested_action": classification.suggested_action,
            },
        }

    except Exception as e:
        logger.exception(f"classify_event_activity: Failed: {e}")
        return {
            "success": False,
            "ignored": False,
            "classification": None,
            "error": str(e),
        }


@activity.defn
async def remediate_issue_activity(
    issue_summary: str,
    resource_info: dict[str, Any],
    suggested_action: str | None = None,
) -> dict[str, Any]:
    """Remediate a Kubernetes issue using the Remediator agent.

    Args:
        issue_summary: Description of the issue
        resource_info: Dict with namespace, name, kind
        suggested_action: Optional suggested remediation

    Returns:
        Dict with remediation result

    Example:
        result = await workflow.execute_activity(
            remediate_issue_activity,
            args=[
                "Pod crash loop due to OOMKilled",
                {"namespace": "default", "name": "nginx", "kind": "Pod"},
                "Increase memory limit",
            ],
            start_to_close_timeout=timedelta(minutes=10),
        )
    """
    logger.info(f"remediate_issue_activity: Remediating {resource_info.get('name')}")

    try:
        agent = _get_agent("remediator")

        activity.heartbeat("Starting remediation")

        # Build remediation prompt
        prompt = f"""Remediate the following Kubernetes issue:

Issue: {issue_summary}

Resource:
- Namespace: {resource_info.get("namespace", "default")}
- Name: {resource_info.get("name", "unknown")}
- Kind: {resource_info.get("kind", "Pod")}
"""
        if suggested_action:
            prompt += f"\nSuggested Action: {suggested_action}"

        result = await agent.run(prompt)

        return {
            "success": True,
            "result": result,
            "resource": resource_info,
        }

    except Exception as e:
        logger.exception(f"remediate_issue_activity: Failed: {e}")
        return {
            "success": False,
            "result": "",
            "resource": resource_info,
            "error": str(e),
        }


# =============================================================================
# Swarm Support Activities
# =============================================================================


@activity.defn
async def run_agent_for_swarm_activity(
    agent_name: str,
    task_message: str,
    task_context: dict[str, Any],
    capability: str,
) -> dict[str, Any]:
    """Run an agent for a swarm task.

    This activity is designed for the swarm pattern where agents pull tasks
    from a shared pool. It includes additional context about the swarm task
    and the capability being exercised.

    Args:
        agent_name: Name of the agent to run
        task_message: The task message
        task_context: Context from the swarm task (includes memory, prior work)
        capability: The capability this agent is exercising

    Returns:
        Dict with result, handoff information if any, and metadata
    """
    logger.info(f"run_agent_for_swarm_activity: {agent_name} executing capability '{capability}'")

    try:
        agent = _get_agent(agent_name)

        activity.heartbeat(f"Running {agent_name} for capability {capability}")

        # Build context-rich prompt
        import json

        prompt = f"""You are executing the "{capability}" capability.

Task: {task_message}

Context:
{json.dumps(task_context, indent=2)}

After completing your work, indicate if you need to hand off to another agent.
"""

        result = await agent.run(prompt)

        # Parse result for handoff requests
        handoff = None
        if "HANDOFF:" in result:
            # Simple convention: agent includes HANDOFF: <capability> in response
            import re

            match = re.search(r"HANDOFF:\s*(\w+)", result)
            if match:
                handoff = {
                    "requested_capability": match.group(1),
                    "reason": "Agent requested handoff",
                }

        return {
            "success": True,
            "agent_name": agent_name,
            "capability": capability,
            "result": result,
            "handoff": handoff,
            "metadata": {
                "task_context_keys": list(task_context.keys()),
            },
        }

    except Exception as e:
        logger.exception(f"run_agent_for_swarm_activity: {agent_name} failed: {e}")
        return {
            "success": False,
            "agent_name": agent_name,
            "capability": capability,
            "result": "",
            "handoff": None,
            "error": str(e),
        }


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Types
    "AgentInput",
    "AgentOutput",
    "AgentNotFoundError",
    "AgentExecutionError",
    # Activities
    "run_agent_activity",
    "classify_event_activity",
    "remediate_issue_activity",
    "run_agent_for_swarm_activity",
    # Utilities
    "clear_agent_cache",
    "DEFAULT_AGENT_RETRY_POLICY",
]
