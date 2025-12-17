"""
Remediation agent for investigating and fixing Kubernetes issues.

Uses the MCP Kubernetes server for safe cluster operations.
Implements a tiered safety model with no delete operations allowed.
"""

import logging
import os
import subprocess
from datetime import UTC, datetime
from typing import Any

from strands import Agent, tool

from k8s_monitor.models import FixAttempt, Investigation, Issue

logger = logging.getLogger(__name__)

# Safety: Operations that are NEVER allowed
BLOCKED_OPERATIONS = frozenset(
    [
        "delete",
        "k8s_delete",
        "drain",
        "k8s_drain",
        "force",
        "--force",
        "taint",  # Can be destructive
    ]
)

# Safe operations for auto-remediation
ALLOWED_WRITE_OPERATIONS = frozenset(
    [
        "k8s_rollout_restart",
        "k8s_scale",
        "k8s_rollout_undo",
        "k8s_annotate",
        "k8s_label",
        "k8s_patch",
        "k8s_set_image",
        "k8s_set_env",
        "k8s_set_resources",
    ]
)


def _is_safe_command(command: str) -> bool:
    """Check if a command is safe to execute (no delete operations)."""
    command_lower = command.lower()
    for blocked in BLOCKED_OPERATIONS:
        if blocked in command_lower:
            logger.warning(f"Blocked unsafe command containing '{blocked}': {command}")
            return False
    return True


def _run_mcp_kubectl(args: list[str], timeout: int = 60) -> dict[str, Any]:
    """
    Run a kubectl command via the MCP server or directly.

    Args:
        args: List of kubectl arguments (without 'kubectl' prefix)
        timeout: Command timeout in seconds

    Returns:
        Dict with 'success', 'output', and optionally 'error'
    """
    # Build the full command
    full_command = ["kubectl"] + args

    # Safety check
    command_str = " ".join(full_command)
    if not _is_safe_command(command_str):
        return {
            "success": False,
            "output": "",
            "error": f"Command blocked by safety policy: {command_str}",
        }

    try:
        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": f"Command timed out after {timeout}s",
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
        }


# Remediation tools for the Strands agent
@tool
def describe_resource(resource_type: str, name: str, namespace: str) -> str:
    """
    Get detailed description of a Kubernetes resource.

    Args:
        resource_type: Type of resource (pod, deployment, service, etc.)
        name: Name of the resource
        namespace: Namespace of the resource

    Returns:
        Detailed description of the resource
    """
    result = _run_mcp_kubectl(["describe", resource_type, name, "-n", namespace])
    if result["success"]:
        return result["output"]
    return f"Error: {result['error']}"


@tool
def get_pod_logs(
    pod_name: str, namespace: str, container: str | None = None, tail: int = 100
) -> str:
    """
    Get logs from a pod.

    Args:
        pod_name: Name of the pod
        namespace: Namespace of the pod
        container: Optional container name (for multi-container pods)
        tail: Number of lines to retrieve (default 100)

    Returns:
        Pod logs
    """
    args = ["logs", pod_name, "-n", namespace, f"--tail={tail}"]
    if container:
        args.extend(["-c", container])

    result = _run_mcp_kubectl(args)
    if result["success"]:
        return result["output"]
    return f"Error: {result['error']}"


@tool
def get_pod_events(pod_name: str, namespace: str) -> str:
    """
    Get events related to a specific pod.

    Args:
        pod_name: Name of the pod
        namespace: Namespace of the pod

    Returns:
        Events related to the pod
    """
    result = _run_mcp_kubectl(
        [
            "get",
            "events",
            "-n",
            namespace,
            f"--field-selector=involvedObject.name={pod_name}",
            "--sort-by=.lastTimestamp",
        ]
    )
    if result["success"]:
        return result["output"]
    return f"Error: {result['error']}"


@tool
def get_resource_yaml(resource_type: str, name: str, namespace: str) -> str:
    """
    Get the YAML definition of a Kubernetes resource.

    Args:
        resource_type: Type of resource
        name: Name of the resource
        namespace: Namespace of the resource

    Returns:
        YAML definition
    """
    result = _run_mcp_kubectl(["get", resource_type, name, "-n", namespace, "-o", "yaml"])
    if result["success"]:
        return result["output"]
    return f"Error: {result['error']}"


@tool
def restart_deployment(deployment_name: str, namespace: str) -> str:
    """
    Restart a deployment by triggering a rolling restart.

    Args:
        deployment_name: Name of the deployment
        namespace: Namespace of the deployment

    Returns:
        Result of the restart command
    """
    result = _run_mcp_kubectl(
        ["rollout", "restart", "deployment", deployment_name, "-n", namespace]
    )
    if result["success"]:
        return f"Successfully initiated restart of deployment {deployment_name}"
    return f"Error restarting deployment: {result['error']}"


@tool
def scale_deployment(deployment_name: str, namespace: str, replicas: int) -> str:
    """
    Scale a deployment to a specific number of replicas.

    Args:
        deployment_name: Name of the deployment
        namespace: Namespace of the deployment
        replicas: Target number of replicas (max 10 for safety)

    Returns:
        Result of the scale command
    """
    # Safety limit
    if replicas > 10:
        return "Error: Cannot scale above 10 replicas for safety. Please scale manually."
    if replicas < 0:
        return "Error: Replicas must be >= 0"

    result = _run_mcp_kubectl(
        ["scale", "deployment", deployment_name, "-n", namespace, f"--replicas={replicas}"]
    )
    if result["success"]:
        return f"Successfully scaled deployment {deployment_name} to {replicas} replicas"
    return f"Error scaling deployment: {result['error']}"


@tool
def rollback_deployment(deployment_name: str, namespace: str) -> str:
    """
    Rollback a deployment to the previous revision.

    Args:
        deployment_name: Name of the deployment
        namespace: Namespace of the deployment

    Returns:
        Result of the rollback command
    """
    result = _run_mcp_kubectl(["rollout", "undo", "deployment", deployment_name, "-n", namespace])
    if result["success"]:
        return f"Successfully rolled back deployment {deployment_name}"
    return f"Error rolling back deployment: {result['error']}"


@tool
def check_rollout_status(deployment_name: str, namespace: str) -> str:
    """
    Check the rollout status of a deployment.

    Args:
        deployment_name: Name of the deployment
        namespace: Namespace of the deployment

    Returns:
        Current rollout status
    """
    result = _run_mcp_kubectl(
        ["rollout", "status", "deployment", deployment_name, "-n", namespace, "--timeout=30s"]
    )
    if result["success"]:
        return result["output"]
    return f"Rollout status: {result['error']}"


@tool
def annotate_resource(resource_type: str, name: str, namespace: str, annotation: str) -> str:
    """
    Add an annotation to a Kubernetes resource.

    Args:
        resource_type: Type of resource
        name: Name of the resource
        namespace: Namespace of the resource
        annotation: Annotation in key=value format

    Returns:
        Result of the annotation command
    """
    result = _run_mcp_kubectl(
        ["annotate", resource_type, name, "-n", namespace, annotation, "--overwrite"]
    )
    if result["success"]:
        return f"Successfully annotated {resource_type}/{name}"
    return f"Error annotating: {result['error']}"


@tool
def get_node_conditions(node_name: str) -> str:
    """
    Get the conditions of a node.

    Args:
        node_name: Name of the node

    Returns:
        Node conditions
    """
    result = _run_mcp_kubectl(["get", "node", node_name, "-o", "jsonpath={.status.conditions}"])
    if result["success"]:
        return result["output"]
    return f"Error: {result['error']}"


@tool
def verify_fix(resource_type: str, name: str, namespace: str) -> str:
    """
    Verify if a resource is now healthy after a fix attempt.

    Args:
        resource_type: Type of resource
        name: Name of the resource
        namespace: Namespace of the resource

    Returns:
        Current status of the resource
    """
    result = _run_mcp_kubectl(["get", resource_type, name, "-n", namespace, "-o", "wide"])
    if result["success"]:
        return result["output"]
    return f"Error checking status: {result['error']}"


# All remediation tools
REMEDIATION_TOOLS = [
    describe_resource,
    get_pod_logs,
    get_pod_events,
    get_resource_yaml,
    restart_deployment,
    scale_deployment,
    rollback_deployment,
    check_rollout_status,
    annotate_resource,
    get_node_conditions,
    verify_fix,
]


INVESTIGATION_PROMPT = """You are a Kubernetes expert investigating cluster issues.

SAFETY RULES (CRITICAL):
- You CANNOT delete any resources
- You CANNOT drain nodes
- You CANNOT modify RBAC
- You can only use the provided tools

Your task is to investigate the following issue and determine the root cause.

ISSUE:
{issue_description}

Resource: {resource_type}/{resource_name} in namespace {namespace}

{memory_context}

Use the available tools to:
1. Describe the resource to understand its current state
2. Check logs if it's a pod
3. Review events for any errors
4. Examine the resource configuration

IMPORTANT: Review the past remediation experience above. If similar issues have been fixed before:
- Consider what worked and what didn't
- If a permanent fix exists, mention it in your findings
- Avoid repeating approaches that failed for similar issues

After investigation, provide:
1. Your findings
2. The identified root cause
3. A specific proposed fix using ONLY these safe operations:
   - restart_deployment: Restart a deployment
   - scale_deployment: Scale replicas (max 10)
   - rollback_deployment: Rollback to previous version
   - annotate_resource: Add annotations

Format your final response as:
FINDINGS: <detailed findings>
ROOT_CAUSE: <identified root cause>
PROPOSED_FIX: <description of the fix>
FIX_COMMAND: <specific tool and parameters to use>
CONFIDENCE: <0.0 to 1.0>
RECURRING_ISSUE: <true/false - is this a recurring issue based on memory?>
PERMANENT_FIX_NEEDED: <if recurring, describe what permanent fix would prevent recurrence>
"""


FIX_PROMPT = """You are a Kubernetes expert applying a fix to resolve a cluster issue.

SAFETY RULES (CRITICAL):
- You CANNOT delete any resources
- You CANNOT drain nodes
- You can only use the provided safe tools

Issue: {issue_description}
Root Cause: {root_cause}
Proposed Fix: {proposed_fix}

Execute the fix using the appropriate tool, then verify the fix worked.

After attempting the fix:
1. Execute the remediation action
2. Wait briefly for the action to take effect
3. Use verify_fix to check if the resource is now healthy

Format your final response as:
ACTION_TAKEN: <what you did>
COMMAND_EXECUTED: <the exact tool call>
RESULT: <outcome of the action>
VERIFICATION: <status after fix>
SUCCESS: <true or false>
ERROR_MESSAGE: <if failed, why>
"""


def create_investigation_agent() -> Agent:
    """Create an agent configured for issue investigation."""
    try:
        from agent_platform.llm_client import create_vllm_model_provider

        model = create_vllm_model_provider()
    except ImportError:
        from strands.models.openai import OpenAIModel

        model = OpenAIModel(
            client_args={
                "base_url": os.environ.get(
                    "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
                ),
                "api_key": "not-needed",
            },
            model_id=os.environ.get("VLLM_MODEL", "openai/gpt-oss-20b"),
        )

    return Agent(
        model=model,
        tools=REMEDIATION_TOOLS,
        system_prompt="You are a Kubernetes cluster expert. Investigate issues thoroughly using the available tools.",
    )


def create_fix_agent() -> Agent:
    """Create an agent configured for applying fixes."""
    try:
        from agent_platform.llm_client import create_vllm_model_provider

        model = create_vllm_model_provider()
    except ImportError:
        from strands.models.openai import OpenAIModel

        model = OpenAIModel(
            client_args={
                "base_url": os.environ.get(
                    "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
                ),
                "api_key": "not-needed",
            },
            model_id=os.environ.get("VLLM_MODEL", "openai/gpt-oss-20b"),
        )

    return Agent(
        model=model,
        tools=REMEDIATION_TOOLS,
        system_prompt="You are a Kubernetes expert applying safe remediation actions. Never delete resources.",
    )


def investigate_issue(issue: Issue) -> Investigation:
    """
    Investigate a detected issue to determine root cause and propose a fix.

    Uses memory system to retrieve past remediation experience for similar issues.

    Args:
        issue: The issue to investigate

    Returns:
        Investigation results with proposed fix
    """
    logger.info(f"Investigating issue: {issue.id} - {issue.title}")

    # Get memory context for similar past issues
    memory_context = ""
    try:
        from k8s_monitor.memory import check_for_permanent_fix, get_remediation_context

        # Check if there's a known permanent fix
        permanent_fix = check_for_permanent_fix(issue)
        if permanent_fix:
            memory_context = f"""## KNOWN PERMANENT FIX
A permanent fix exists for this type of issue: {permanent_fix}
Consider recommending this to the operator instead of temporary fixes.

"""
        # Get similar past issues
        memory_context += get_remediation_context(issue)
        logger.info("Retrieved memory context for investigation")
    except Exception as e:
        logger.warning(f"Failed to retrieve memory context: {e}")
        memory_context = "No memory context available."

    agent = create_investigation_agent()
    prompt = INVESTIGATION_PROMPT.format(
        issue_description=issue.description,
        resource_type=issue.resource_type,
        resource_name=issue.resource_name,
        namespace=issue.namespace,
        memory_context=memory_context,
    )

    result = agent(prompt)
    response = str(result)

    # Parse the response
    findings = _extract_field(response, "FINDINGS")
    root_cause = _extract_field(response, "ROOT_CAUSE")
    proposed_fix = _extract_field(response, "PROPOSED_FIX")
    fix_command = _extract_field(response, "FIX_COMMAND")
    confidence_str = _extract_field(response, "CONFIDENCE")

    try:
        confidence = float(confidence_str.strip())
    except (ValueError, AttributeError):
        confidence = 0.5

    return Investigation(
        issue_id=issue.id,
        findings=findings or response,
        root_cause=root_cause or "Unable to determine",
        proposed_fix=proposed_fix or "Manual investigation required",
        fix_command=fix_command or "",
        confidence=min(max(confidence, 0.0), 1.0),
        investigated_at=datetime.now(UTC).isoformat(),
    )


def attempt_fix(issue: Issue, investigation: Investigation, attempt_number: int) -> FixAttempt:
    """
    Attempt to fix an issue based on investigation results.

    Args:
        issue: The issue to fix
        investigation: Results of the investigation
        attempt_number: Which attempt this is (1-3)

    Returns:
        Record of the fix attempt
    """
    logger.info(f"Attempting fix #{attempt_number} for issue: {issue.id}")

    agent = create_fix_agent()
    prompt = FIX_PROMPT.format(
        issue_description=issue.description,
        root_cause=investigation.root_cause,
        proposed_fix=investigation.proposed_fix,
    )

    result = agent(prompt)
    response = str(result)

    # Parse the response
    action_taken = _extract_field(response, "ACTION_TAKEN")
    command_executed = _extract_field(response, "COMMAND_EXECUTED")
    result_text = _extract_field(response, "RESULT")
    success_str = _extract_field(response, "SUCCESS")
    error_message = _extract_field(response, "ERROR_MESSAGE")

    success = success_str.lower().strip() == "true" if success_str else False

    return FixAttempt(
        attempt_number=attempt_number,
        action_taken=action_taken or response,
        command_executed=command_executed or "Unknown",
        result=result_text or "See action taken",
        success=success,
        error_message=error_message if not success else None,
        attempted_at=datetime.now(UTC).isoformat(),
    )


def _extract_field(text: str, field_name: str) -> str:
    """Extract a field value from the agent response."""
    try:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line.startswith(f"{field_name}:"):
                value = line[len(field_name) + 1 :].strip()
                # Check if value continues on next lines
                j = i + 1
                while j < len(lines) and not any(
                    lines[j].startswith(f"{f}:")
                    for f in [
                        "FINDINGS",
                        "ROOT_CAUSE",
                        "PROPOSED_FIX",
                        "FIX_COMMAND",
                        "CONFIDENCE",
                        "ACTION_TAKEN",
                        "COMMAND_EXECUTED",
                        "RESULT",
                        "VERIFICATION",
                        "SUCCESS",
                        "ERROR_MESSAGE",
                    ]
                ):
                    value += "\n" + lines[j]
                    j += 1
                return value.strip()
        return ""
    except Exception:
        return ""
