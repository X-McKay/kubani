"""
Memory system for k8s-monitor remediation learning.

Uses mem0 with PostgreSQL + pgvector to store and retrieve past remediation
experiences, enabling the agent to learn from previous issues and fixes.
"""

import hashlib
import logging
import os
from typing import Any

from mem0 import Memory

from k8s_monitor.models import Issue, RemediationRecord

logger = logging.getLogger(__name__)

# Singleton memory instance
_memory_instance: Memory | None = None


def get_memory_config() -> dict[str, Any]:
    """
    Build mem0 configuration from environment variables.

    Environment variables:
        MEMORY_PG_HOST: PostgreSQL host (default: postgresql.database.svc.cluster.local)
        MEMORY_PG_PORT: PostgreSQL port (default: 5432)
        MEMORY_PG_USER: PostgreSQL user (default: k8s_monitor)
        MEMORY_PG_PASSWORD: PostgreSQL password
        MEMORY_PG_DATABASE: Database name (default: k8s_monitor_memory)
        VLLM_API_URL: vLLM API URL for LLM operations
        VLLM_MODEL: vLLM model name
    """
    pg_host = os.environ.get("MEMORY_PG_HOST", "postgresql.database.svc.cluster.local")
    pg_port = int(os.environ.get("MEMORY_PG_PORT", "5432"))
    pg_user = os.environ.get("MEMORY_PG_USER", "k8s_monitor")
    pg_password = os.environ.get("MEMORY_PG_PASSWORD", "k8s-monitor-mem0-2024")
    pg_database = os.environ.get("MEMORY_PG_DATABASE", "k8s_monitor_memory")

    vllm_url = os.environ.get("VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1")
    vllm_model = os.environ.get("VLLM_MODEL", "openai/gpt-oss-20b")

    return {
        "llm": {
            "provider": "openai",
            "config": {
                "model": vllm_model,
                "api_key": "not-needed",
                "openai_base_url": vllm_url,
                "temperature": 0.1,
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                # Small, fast model that runs locally
            },
        },
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "host": pg_host,
                "port": pg_port,
                "user": pg_user,
                "password": pg_password,
                "dbname": pg_database,
            },
        },
        "version": "v1.1",
    }


def get_memory() -> Memory:
    """
    Get or create the memory instance (singleton).

    Returns:
        Configured mem0 Memory instance
    """
    global _memory_instance
    if _memory_instance is None:
        config = get_memory_config()
        logger.info("Initializing mem0 memory system")
        _memory_instance = Memory.from_config(config)
        logger.info("Memory system initialized successfully")
    return _memory_instance


def generate_issue_signature(issue: Issue) -> str:
    """
    Generate a normalized signature for an issue to identify similar issues.

    This helps identify recurring issues even if descriptions vary slightly.

    Args:
        issue: The issue to generate a signature for

    Returns:
        A hash-based signature string
    """
    # Normalize key fields
    normalized = f"{issue.resource_type}:{issue.namespace}:{issue.severity.value}"

    # Add keywords from title (lowercase, sorted)
    title_words = sorted(set(issue.title.lower().split()))
    normalized += ":" + ",".join(title_words[:5])  # Top 5 words

    return hashlib.sha256(normalized.encode()).hexdigest()[:12]


def store_remediation_memory(
    record: RemediationRecord,
    permanent_fix: str | None = None,
) -> str | None:
    """
    Store a remediation record in memory for future learning.

    Args:
        record: The completed remediation record
        permanent_fix: Optional description of a permanent fix if one was applied

    Returns:
        Memory ID if successful, None otherwise
    """
    try:
        memory = get_memory()
        issue = record.issue
        signature = generate_issue_signature(issue)

        # Build memory content
        successful_fixes = [f.action_taken for f in record.fix_attempts if f.success]
        failed_fixes = [
            {"action": f.action_taken, "error": f.error_message}
            for f in record.fix_attempts
            if not f.success
        ]

        # Get root cause from investigations
        root_cause = "Unknown"
        if record.investigations:
            root_cause = record.investigations[-1].root_cause

        memory_content = f"""
Issue: {issue.title}
Resource: {issue.resource_type}/{issue.resource_name} in namespace {issue.namespace}
Severity: {issue.severity.value}
Root Cause: {root_cause}
Final Outcome: {record.final_outcome or record.status.value}
Successful Fixes: {", ".join(successful_fixes) if successful_fixes else "None"}
Failed Approaches: {len(failed_fixes)} attempts failed
{"Permanent Fix Applied: " + permanent_fix if permanent_fix else ""}
"""

        # Store with metadata for filtering
        metadata = {
            "issue_signature": signature,
            "resource_type": issue.resource_type,
            "namespace": issue.namespace,
            "severity": issue.severity.value,
            "status": record.status.value,
            "has_permanent_fix": permanent_fix is not None,
            "successful_fix_count": len(successful_fixes),
            "failed_fix_count": len(failed_fixes),
        }

        result = memory.add(
            memory_content,
            user_id="k8s-monitor-agent",
            metadata=metadata,
        )

        memory_id = result.get("id") if isinstance(result, dict) else None
        logger.info(f"Stored remediation memory: {memory_id} for issue {issue.id}")
        return memory_id

    except Exception as e:
        logger.error(f"Failed to store remediation memory: {e}")
        return None


def search_similar_issues(
    issue: Issue,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Search for similar past issues and their resolutions.

    Args:
        issue: The current issue to find similar cases for
        limit: Maximum number of results to return

    Returns:
        List of relevant memories with their content and metadata
    """
    try:
        memory = get_memory()

        # Build search query
        query = f"""
Issue similar to: {issue.title}
Resource type: {issue.resource_type}
Namespace: {issue.namespace}
Description: {issue.description[:500]}
"""

        results = memory.search(
            query,
            user_id="k8s-monitor-agent",
            limit=limit,
        )

        # Process results
        memories = []
        for result in results:
            memories.append(
                {
                    "content": result.get("memory", ""),
                    "metadata": result.get("metadata", {}),
                    "score": result.get("score", 0),
                }
            )

        logger.info(f"Found {len(memories)} similar past issues for {issue.id}")
        return memories

    except Exception as e:
        logger.error(f"Failed to search similar issues: {e}")
        return []


def get_remediation_context(issue: Issue) -> str:
    """
    Get formatted context from past remediations for a similar issue.

    This is the main function to call before investigating a new issue.
    It provides the agent with relevant past experience.

    Args:
        issue: The current issue to get context for

    Returns:
        Formatted string with past remediation experiences
    """
    memories = search_similar_issues(issue)

    if not memories:
        return "No similar past issues found in memory."

    context_parts = ["## Past Remediation Experience\n"]

    for i, mem in enumerate(memories, 1):
        metadata = mem.get("metadata", {})
        content = mem.get("content", "")
        score = mem.get("score", 0)

        # Extract key info
        has_permanent_fix = metadata.get("has_permanent_fix", False)
        status = metadata.get("status", "unknown")

        context_parts.append(f"### Similar Issue #{i} (relevance: {score:.2f})")
        context_parts.append(content.strip())

        if has_permanent_fix:
            context_parts.append("**Note: A permanent fix was applied for this issue.**")

        if status == "escalated":
            context_parts.append("**Warning: This issue required human intervention.**")

        context_parts.append("")  # Empty line separator

    return "\n".join(context_parts)


def mark_permanent_fix_applied(
    issue: Issue,
    fix_description: str,
) -> bool:
    """
    Record that a permanent fix was applied for an issue type.

    This helps the agent learn that certain recurring issues have
    permanent solutions that should be suggested to humans.

    Args:
        issue: The issue that was permanently fixed
        fix_description: Description of the permanent fix

    Returns:
        True if successfully recorded
    """
    try:
        memory = get_memory()
        signature = generate_issue_signature(issue)

        memory_content = f"""
PERMANENT FIX RECORD
Issue Type: {issue.title}
Resource Pattern: {issue.resource_type} in {issue.namespace}
Root Cause Pattern: {issue.description[:200]}
Permanent Fix: {fix_description}
Recommendation: When this issue recurs, suggest this permanent fix to the operator.
"""

        memory.add(
            memory_content,
            user_id="k8s-monitor-agent",
            metadata={
                "issue_signature": signature,
                "type": "permanent_fix",
                "resource_type": issue.resource_type,
            },
        )

        logger.info(f"Recorded permanent fix for issue signature {signature}")
        return True

    except Exception as e:
        logger.error(f"Failed to record permanent fix: {e}")
        return False


def check_for_permanent_fix(issue: Issue) -> str | None:
    """
    Check if a permanent fix exists for this type of issue.

    Args:
        issue: The issue to check

    Returns:
        Description of permanent fix if one exists, None otherwise
    """
    try:
        memory = get_memory()
        signature = generate_issue_signature(issue)

        # Search specifically for permanent fix records
        query = f"PERMANENT FIX for {issue.resource_type} {issue.title}"

        results = memory.search(
            query,
            user_id="k8s-monitor-agent",
            limit=3,
        )

        for result in results:
            metadata = result.get("metadata", {})
            if (
                metadata.get("type") == "permanent_fix"
                and metadata.get("issue_signature") == signature
            ):
                content = result.get("memory", "")
                # Extract permanent fix description
                if "Permanent Fix:" in content:
                    fix_start = content.find("Permanent Fix:") + len("Permanent Fix:")
                    fix_end = content.find("\n", fix_start)
                    if fix_end == -1:
                        fix_end = len(content)
                    return content[fix_start:fix_end].strip()

        return None

    except Exception as e:
        logger.error(f"Failed to check for permanent fix: {e}")
        return None


def get_recurrence_count(issue: Issue) -> int:
    """
    Count how many times this type of issue has occurred.

    Args:
        issue: The issue to count recurrences for

    Returns:
        Number of times this issue type has been seen
    """
    try:
        signature = generate_issue_signature(issue)
        memories = search_similar_issues(issue, limit=20)

        count = sum(
            1 for m in memories if m.get("metadata", {}).get("issue_signature") == signature
        )

        return count

    except Exception as e:
        logger.error(f"Failed to count recurrences: {e}")
        return 0
