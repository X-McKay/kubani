"""
K8s-Monitor Swarm Orchestration.

Multi-agent swarm for Kubernetes cluster monitoring and remediation.
Uses Strands Swarm pattern with dynamic handoffs between specialist agents.
"""

import asyncio
import contextlib
import logging
from typing import Any

from strands.multiagent import Swarm

from k8s_monitor.agents.cluster_remediator import ClusterRemediatorAgent
from k8s_monitor.agents.cluster_scout import ClusterScoutAgent
from k8s_monitor.agents.cluster_triage import ClusterTriageAgent
from k8s_monitor.agents.discord_notifier import DiscordNotifierAgent
from k8s_monitor.agents.pod_diagnostician import PodDiagnosticianAgent
from k8s_monitor.agents.remediation_memory import RemediationMemoryAgent

logger = logging.getLogger(__name__)


def create_k8s_monitor_swarm() -> Swarm:
    """
    Create the K8s monitoring swarm with all specialist agents.

    Returns:
        Configured Swarm instance
    """
    # Initialize all agents
    cluster_triage = ClusterTriageAgent()
    cluster_scout = ClusterScoutAgent()
    pod_diagnostician = PodDiagnosticianAgent()
    cluster_remediator = ClusterRemediatorAgent()
    remediation_memory = RemediationMemoryAgent()
    discord_notifier = DiscordNotifierAgent()

    # Create swarm with agents - entry_point is the triage agent
    swarm = Swarm(
        [
            cluster_triage.agent,
            cluster_scout.agent,
            pod_diagnostician.agent,
            cluster_remediator.agent,
            remediation_memory.agent,
            discord_notifier.agent,
        ],
        entry_point=cluster_triage.agent,
        # Guardrails (tuned for optimized prompts + vLLM inference time)
        max_handoffs=10,  # Prevent excessive agent switching
        max_iterations=20,  # Total execution cap
        execution_timeout=300.0,  # 5 minute total timeout
        node_timeout=120.0,  # 2 minutes per agent turn (buffer for vLLM latency)
        repetitive_handoff_detection_window=8,  # Window for detecting repetitive handoffs
        repetitive_handoff_min_unique_agents=3,  # Minimum unique agents in window
    )

    logger.info("Created K8s monitor swarm with 6 agents")
    return swarm


async def run_health_check() -> dict[str, Any]:
    """
    Run a cluster health check using the swarm.

    Starts with ClusterTriageAgent which routes to specialists as needed.
    Always ends with DiscordNotifierAgent publishing results.

    Returns:
        Health check results including status, summary, and any issues found
    """
    logger.info("Starting swarm health check")

    try:
        swarm = create_k8s_monitor_swarm()

        # Run health check starting with triage agent (entry_point)
        result = swarm(
            "Perform a comprehensive cluster health check. Check all nodes, deployments, "
            "and recent events. Report any issues found and publish a summary to Discord."
        )

        logger.info("Swarm health check completed")
        return parse_swarm_result(result, "health_check")

    except Exception as e:
        logger.exception(f"Swarm health check failed: {e}")
        return {
            "status": "error",
            "summary": f"Health check failed: {e}",
            "issues": [str(e)],
            "recommendations": ["Check agent logs for details"],
        }


async def run_investigation(
    issue_title: str,
    resource_type: str,
    resource_name: str,
    namespace: str,
    description: str = "",
) -> dict[str, Any]:
    """
    Investigate and remediate a specific issue using the swarm.

    Starts with ClusterTriageAgent which routes to specialists for investigation,
    potential remediation, and learning storage.

    Args:
        issue_title: Title/summary of the issue
        resource_type: Kubernetes resource type (Pod, Deployment, etc.)
        resource_name: Name of the affected resource
        namespace: Kubernetes namespace
        description: Additional issue description

    Returns:
        Investigation results including root cause, actions taken, and outcome
    """
    logger.info(f"Starting swarm investigation: {issue_title}")

    try:
        swarm = create_k8s_monitor_swarm()

        prompt = f"""
        Investigate and remediate this issue:

        Issue: {issue_title}
        Resource: {resource_type}/{resource_name}
        Namespace: {namespace}
        Description: {description or "No additional details"}

        Steps:
        1. Check memories for similar past issues
        2. Investigate using Kubernetes tools (logs, events, describe)
        3. Identify the root cause
        4. If a safe fix is available, apply it
        5. Store what you learned for future reference
        6. Publish results to Discord
        """

        result = swarm(prompt)

        logger.info("Swarm investigation completed")
        return parse_swarm_result(result, "investigation")

    except Exception as e:
        logger.exception(f"Swarm investigation failed: {e}")
        return {
            "root_cause": "Investigation failed",
            "summary": str(e),
            "actions": [],
            "outcome": "failed",
            "recommendations": ["Manual investigation required"],
        }


def _extract_swarm_output(result: Any) -> str:
    """
    Extract meaningful text output from a SwarmResult object.

    Handles the Strands SwarmResult structure:
    - result.status: Status enum (COMPLETED, FAILED)
    - result.results: dict mapping agent names to NodeResult objects
    - Each NodeResult has a .result attribute with the agent's output

    Args:
        result: SwarmResult or any result object

    Returns:
        Extracted text content suitable for parsing
    """
    # If it's already a string, return it
    if isinstance(result, str):
        return result

    # Try to extract from SwarmResult structure
    try:
        # Check if result has the expected SwarmResult attributes
        if hasattr(result, "results") and isinstance(result.results, dict):
            # Get status for logging
            status = getattr(result, "status", None)
            logger.debug(f"SwarmResult status: {status}")

            # Try to get the discord_notifier result first (final agent)
            if "discord_notifier" in result.results:
                node_result = result.results["discord_notifier"]
                if hasattr(node_result, "result"):
                    output = node_result.result
                    if output and not isinstance(output, Exception):
                        return str(output)

            # Fall back to collecting output from all agents
            outputs = []
            for agent_name, node_result in result.results.items():
                if hasattr(node_result, "result"):
                    agent_output = node_result.result
                    # Skip exceptions and empty results
                    if agent_output and not isinstance(agent_output, Exception):
                        outputs.append(f"[{agent_name}]: {agent_output}")

            if outputs:
                return "\n\n".join(outputs)

            # If all results were errors, report the failure
            if status and hasattr(status, "value") and status.value == "failed":
                # Try to extract error information
                for agent_name, node_result in result.results.items():
                    if hasattr(node_result, "result"):
                        agent_output = node_result.result
                        if isinstance(agent_output, Exception):
                            return f"Swarm execution failed in {agent_name}: {agent_output}"
                return "Swarm execution failed - no successful agent outputs"

        # Try get_agent_results() method if available
        if hasattr(result, "get_agent_results"):
            agent_results = result.get_agent_results()
            if agent_results:
                outputs = [str(ar) for ar in agent_results if ar]
                if outputs:
                    return "\n\n".join(outputs)

    except Exception as e:
        logger.warning(f"Error extracting swarm output: {e}")

    # Last resort: use str() but log a warning
    logger.warning(
        "Could not extract structured output from SwarmResult, "
        "falling back to str() representation"
    )
    return str(result)


def parse_swarm_result(result: Any, result_type: str) -> dict[str, Any]:
    """
    Parse swarm result into structured format.

    Args:
        result: Raw swarm result (SwarmResult object or string)
        result_type: Type of result ("health_check" or "investigation")

    Returns:
        Structured result dictionary
    """
    # Extract text content from SwarmResult object
    text = _extract_swarm_output(result)

    if result_type == "health_check":
        return parse_health_check_result(text)
    else:
        return parse_investigation_result(text)


def parse_health_check_result(text: str) -> dict[str, Any]:
    """Parse health check result text into structured format."""
    import re

    # Extract status
    status = "healthy"
    if "critical" in text.lower() or "🚨" in text:
        status = "critical"
    elif "warning" in text.lower() or "⚠️" in text:
        status = "warning"
    elif "healthy" in text.lower() or "✅" in text:
        status = "healthy"

    # Extract summary (first paragraph or sentence)
    lines = text.strip().split("\n")
    summary = lines[0] if lines else "Health check completed"

    # Try to extract issues count
    issues = []
    issues_match = re.search(r"(\d+)\s+issue", text, re.IGNORECASE)
    if issues_match:
        issues = [f"{issues_match.group(1)} issues detected"]

    return {
        "status": status,
        "summary": summary[:500],  # Truncate if too long
        "issues": issues,
        "recommendations": [],
        "raw_response": text,
    }


def parse_investigation_result(text: str) -> dict[str, Any]:
    """Parse investigation result text into structured format."""
    # Determine outcome
    outcome = "unknown"
    if "success" in text.lower() or "resolved" in text.lower() or "fixed" in text.lower():
        outcome = "success"
    elif "failed" in text.lower() or "error" in text.lower():
        outcome = "failed"
    elif "escalat" in text.lower():
        outcome = "escalated"

    # Extract first meaningful content as summary
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    summary = lines[0] if lines else "Investigation completed"

    return {
        "root_cause": "See raw response",
        "summary": summary[:500],
        "actions": [],
        "outcome": outcome,
        "recommendations": [],
        "raw_response": text,
    }


# Granular functions for Temporal activities


def investigate_issue(
    issue_title: str,
    resource_type: str,
    resource_name: str,
    namespace: str,
    description: str = "",
) -> dict[str, Any]:
    """
    Investigate an issue without attempting remediation.

    Uses PodDiagnosticianAgent for deep analysis.

    Args:
        issue_title: Title/summary of the issue
        resource_type: Kubernetes resource type
        resource_name: Name of the affected resource
        namespace: Kubernetes namespace
        description: Additional issue description

    Returns:
        Investigation results compatible with Investigation model
    """
    logger.info(f"Starting investigation-only: {issue_title}")

    try:
        # Use pod diagnostician directly for investigation
        pod_diagnostician = PodDiagnosticianAgent()

        prompt = f"""
        Investigate this issue and identify the root cause. DO NOT attempt any fixes.

        Issue: {issue_title}
        Resource: {resource_type}/{resource_name}
        Namespace: {namespace}
        Description: {description or "No additional details"}

        Analyze:
        1. Get the resource status and events
        2. Check logs for errors
        3. Identify the root cause
        4. Propose a fix (but don't apply it)

        Respond with your findings in this format:
        ROOT_CAUSE: <one line description>
        FINDINGS: <detailed analysis>
        PROPOSED_FIX: <what should be done>
        CONFIDENCE: <0.0-1.0>
        """

        result = str(pod_diagnostician(prompt))
        return _parse_investigation_result(result)

    except Exception as e:
        logger.exception(f"Investigation failed: {e}")
        return {
            "findings": str(e),
            "root_cause": "Investigation failed",
            "proposed_fix": "Manual investigation required",
            "confidence": 0.0,
        }


def _parse_investigation_result(text: str) -> dict[str, Any]:
    """Parse investigation output into structured format."""
    import re

    result = {
        "findings": text,
        "root_cause": "See findings",
        "proposed_fix": "Unknown",
        "confidence": 0.5,
    }

    # Extract structured fields if present
    root_cause_match = re.search(r"ROOT_CAUSE:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if root_cause_match:
        result["root_cause"] = root_cause_match.group(1).strip()

    findings_match = re.search(
        r"FINDINGS:\s*(.+?)(?:PROPOSED_FIX|CONFIDENCE|$)", text, re.IGNORECASE | re.DOTALL
    )
    if findings_match:
        result["findings"] = findings_match.group(1).strip()

    fix_match = re.search(r"PROPOSED_FIX:\s*(.+?)(?:CONFIDENCE|$)", text, re.IGNORECASE | re.DOTALL)
    if fix_match:
        result["proposed_fix"] = fix_match.group(1).strip()

    confidence_match = re.search(r"CONFIDENCE:\s*([\d.]+)", text, re.IGNORECASE)
    if confidence_match:
        with contextlib.suppress(ValueError):
            result["confidence"] = float(confidence_match.group(1))

    return result


def attempt_fix(
    issue_title: str,
    resource_type: str,
    resource_name: str,
    namespace: str,
    proposed_fix: str,
    attempt_number: int,
) -> dict[str, Any]:
    """
    Attempt to fix an issue using the ClusterRemediatorAgent.

    Args:
        issue_title: Title/summary of the issue
        resource_type: Kubernetes resource type
        resource_name: Name of the affected resource
        namespace: Kubernetes namespace
        proposed_fix: The fix to attempt
        attempt_number: Which attempt this is (1-3)

    Returns:
        Fix attempt results compatible with FixAttempt model
    """
    logger.info(f"Starting fix attempt #{attempt_number}: {issue_title}")

    try:
        cluster_remediator = ClusterRemediatorAgent()

        prompt = f"""
        Apply this fix for the issue. This is attempt #{attempt_number}.

        Issue: {issue_title}
        Resource: {resource_type}/{resource_name}
        Namespace: {namespace}
        Proposed Fix: {proposed_fix}

        Apply the fix and report the result in this format:
        ACTION_TAKEN: <what you did>
        SUCCESS: <true or false>
        RESULT: <outcome description>
        ERROR: <error message if failed, otherwise "none">
        """

        result = str(cluster_remediator(prompt))
        return _parse_fix_result(result, attempt_number)

    except Exception as e:
        logger.exception(f"Fix attempt failed: {e}")
        return {
            "attempt_number": attempt_number,
            "action_taken": "Fix attempt failed to execute",
            "success": False,
            "result": "",
            "error_message": str(e),
        }


def _parse_fix_result(text: str, attempt_number: int) -> dict[str, Any]:
    """Parse fix attempt output into structured format."""
    import re

    result = {
        "attempt_number": attempt_number,
        "action_taken": "Unknown",
        "success": False,
        "result": text,
        "error_message": None,
    }

    # Extract structured fields if present
    action_match = re.search(r"ACTION_TAKEN:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if action_match:
        result["action_taken"] = action_match.group(1).strip()

    success_match = re.search(r"SUCCESS:\s*(true|false)", text, re.IGNORECASE)
    if success_match:
        result["success"] = success_match.group(1).lower() == "true"

    result_match = re.search(r"RESULT:\s*(.+?)(?:ERROR|$)", text, re.IGNORECASE | re.DOTALL)
    if result_match:
        result["result"] = result_match.group(1).strip()

    error_match = re.search(r"ERROR:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if error_match:
        error_text = error_match.group(1).strip()
        if error_text.lower() != "none":
            result["error_message"] = error_text

    return result


def verify_fix(resource_type: str, resource_name: str, namespace: str) -> bool:
    """
    Verify if a resource is healthy after a fix attempt.

    Uses kubectl to check resource status directly.

    Args:
        resource_type: Kubernetes resource type
        resource_name: Name of the resource
        namespace: Kubernetes namespace

    Returns:
        True if the resource appears healthy
    """
    logger.info(f"Verifying fix for {resource_type}/{resource_name} in {namespace}")

    try:
        from k8s_monitor.tools import get_pod_status

        # For pods, check status directly
        if resource_type.lower() == "pod":
            status = get_pod_status(resource_name, namespace)
            status_lower = status.lower()

            is_healthy = ("running" in status_lower or "completed" in status_lower) and not (
                "pending" in status_lower
                or "error" in status_lower
                or "failed" in status_lower
                or "crashloop" in status_lower
                or "imagepull" in status_lower
            )
            logger.info(f"Pod health check: {is_healthy}")
            return is_healthy

        # For deployments, check replica status
        elif resource_type.lower() == "deployment":
            from k8s_monitor.tools import get_deployment_status

            status = get_deployment_status(namespace)
            # Check if deployment has ready replicas
            if resource_name in status:
                return "0/" not in status.split(resource_name)[1].split("\n")[0]
            return True

        # Default: assume healthy if no errors
        return True

    except Exception as e:
        logger.warning(f"Verification failed: {e}")
        return False


# Synchronous wrappers for Temporal activities
def sync_health_check() -> dict[str, Any]:
    """Synchronous wrapper for health check."""
    return asyncio.run(run_health_check())


def sync_investigation(
    issue_title: str,
    resource_type: str,
    resource_name: str,
    namespace: str,
    description: str = "",
) -> dict[str, Any]:
    """Synchronous wrapper for investigation."""
    return asyncio.run(
        run_investigation(
            issue_title=issue_title,
            resource_type=resource_type,
            resource_name=resource_name,
            namespace=namespace,
            description=description,
        )
    )
