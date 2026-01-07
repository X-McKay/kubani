"""
Memory system for k8s-monitor remediation learning.

Uses:
- Redis for fast issue signature deduplication (O(1) lookup)
- mem0 with Qdrant + Neo4j for semantic similarity and graph-based relationship tracking

The graph memory enables queries like:
- "What fixes have worked for OOMKilled issues in namespace X?"
- "Which pods are affected by similar resource constraints?"
- "What permanent fixes have been applied to recurring issues?"
"""

import hashlib
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import redis
from mem0 import Memory

from k8s_monitor.memory_config import get_k8s_graph_mem0_config
from k8s_monitor.models import Issue, RemediationRecord

logger = logging.getLogger(__name__)

# Singleton instances
_memory_instance: Memory | None = None
_redis_client: redis.Redis | None = None

# Redis key prefixes and TTL
REDIS_SIGNATURE_SET_KEY = "k8s-monitor:issue-signatures"
REDIS_PERMANENT_FIX_KEY = "k8s-monitor:permanent-fixes"
REDIS_SIGNATURE_TTL_DAYS = 30  # Issue signatures expire after 30 days
REDIS_PERMANENT_FIX_TTL_DAYS = 90  # Permanent fixes remembered longer


def get_redis() -> redis.Redis | None:
    """
    Get or create Redis client (singleton).

    Returns None if Redis is not configured or unavailable.
    """
    global _redis_client
    if _redis_client is None:
        redis_host = os.environ.get("REDIS_HOST", "redis-master.cache.svc.cluster.local")
        redis_port = int(os.environ.get("REDIS_PORT", "6379"))
        redis_password = os.environ.get("REDIS_PASSWORD", "")

        try:
            _redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password if redis_password else None,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            # Test connection
            _redis_client.ping()
            logger.info(f"Connected to Redis at {redis_host}:{redis_port}")
        except redis.ConnectionError as e:
            logger.warning(f"Redis not available, falling back to mem0 only: {e}")
            _redis_client = None

    return _redis_client


def get_memory_config() -> dict[str, Any]:
    """
    Build mem0 configuration with Qdrant + Neo4j graph memory.

    Uses get_k8s_graph_mem0_config() which provides:
    - Qdrant for high-performance vector similarity search
    - Neo4j for graph-based entity/relationship tracking
    - vLLM for embeddings and LLM operations
    - K8s-specific graph prompts for entity extraction

    Environment variables:
        QDRANT_HOST: Qdrant host
        QDRANT_PORT: Qdrant port (default: 6333)
        QDRANT_COLLECTION: Collection name (default: k8s-remediation)
        QDRANT_API_KEY: Qdrant API key
        NEO4J_URL: Neo4j bolt URL
        NEO4J_USERNAME: Neo4j username
        NEO4J_PASSWORD: Neo4j password
        VLLM_API_URL: vLLM API URL for LLM operations
        VLLM_MODEL: vLLM model name
        EMBEDDINGS_API_URL: Embeddings API URL
        EMBEDDINGS_MODEL: Embeddings model name
    """
    return get_k8s_graph_mem0_config(
        collection_name=os.environ.get("QDRANT_COLLECTION", "k8s-remediation"),
    )


def get_memory() -> Memory:
    """
    Get or create the memory instance (singleton).

    Returns:
        Configured mem0 Memory instance with Qdrant + Neo4j
    """
    global _memory_instance
    if _memory_instance is None:
        config = get_memory_config()
        logger.info("Initializing mem0 memory system for k8s-monitor (Qdrant + Neo4j)")
        _memory_instance = Memory.from_config(config)
        logger.info("Memory system initialized successfully")
    return _memory_instance


def _extract_search_results(results: Any) -> list[dict[str, Any]]:
    """
    Safely extract search results from mem0 response.

    mem0's search() can return different formats depending on version:
    - List of dicts: [{"memory": ..., "metadata": ..., "score": ...}, ...]
    - Wrapped response: {"results": [...]}
    - Other unexpected formats

    Args:
        results: Raw response from memory.search()

    Returns:
        List of result dicts, each with memory/metadata/score keys
    """
    if results is None:
        return []

    # If already a list, process each item
    if isinstance(results, list):
        extracted = []
        for item in results:
            if isinstance(item, dict):
                extracted.append(item)
            elif isinstance(item, str):
                # Some versions return just the memory text
                extracted.append({"memory": item, "metadata": {}, "score": 0})
            else:
                logger.debug(f"Unexpected result item type: {type(item)}")
        return extracted

    # If wrapped in a results key
    if isinstance(results, dict):
        if "results" in results:
            return _extract_search_results(results["results"])
        # Single result dict
        return [results]

    logger.warning(f"Unexpected search results type: {type(results)}")
    return []


def _extract_memory_id(result: Any) -> str | None:
    """
    Extract memory ID from mem0 add() result.

    With infer=False, mem0 returns {"results": [{"id": "...", ...}], "relations": ...}

    Args:
        result: Raw response from memory.add()

    Returns:
        Memory ID if found, None otherwise
    """
    if isinstance(result, dict):
        # Check for id at top level
        if "id" in result:
            return result["id"]
        # Check for results list
        results = result.get("results", [])
        if results and isinstance(results, list) and len(results) > 0:
            return results[0].get("id")
    return None


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


def is_signature_seen(signature: str) -> bool:
    """
    Fast check if an issue signature has been seen before using Redis.

    O(1) lookup in Redis SET. Falls back to mem0 search if Redis unavailable.

    Args:
        signature: The issue signature to check

    Returns:
        True if signature has been seen before
    """
    # Try Redis first (fast O(1) lookup)
    redis_client = get_redis()
    if redis_client:
        try:
            return redis_client.sismember(REDIS_SIGNATURE_SET_KEY, signature)
        except redis.RedisError as e:
            logger.warning(f"Redis error checking signature: {e}")

    # Fallback to mem0 search (slower)
    try:
        memory = get_memory()
        raw_results = memory.search(
            f"issue signature {signature}",
            user_id="k8s-monitor-agent",
            limit=3,
        )

        for result in _extract_search_results(raw_results):
            metadata = result.get("metadata", {})
            if metadata.get("issue_signature") == signature:
                return True

        return False

    except Exception as e:
        logger.warning(f"Failed to check signature in memory: {e}")
        return False


def mark_signature_seen(signature: str) -> None:
    """
    Mark an issue signature as seen in Redis for fast future lookups.

    Args:
        signature: The issue signature to mark as seen
    """
    redis_client = get_redis()
    if redis_client:
        try:
            redis_client.sadd(REDIS_SIGNATURE_SET_KEY, signature)
            redis_client.expire(REDIS_SIGNATURE_SET_KEY, REDIS_SIGNATURE_TTL_DAYS * 86400)
        except redis.RedisError as e:
            logger.warning(f"Redis error marking signature seen: {e}")


def store_remediation_memory(
    record: RemediationRecord,
    permanent_fix: str | None = None,
) -> str | None:
    """
    Store a remediation record in memory for future learning.

    Uses infer=False to skip mem0's built-in fact extraction, which can fail
    with vLLM/Qwen models. The graph store still extracts entities and
    relationships for relationship tracking.

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

        # Build memory content for semantic search and graph extraction
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

        content = f"""
Remediation Record for Kubernetes Issue
Issue: {issue.title}
Resource: {issue.resource_type}/{issue.resource_name} in namespace {issue.namespace}
Severity: {issue.severity.value}
Root Cause: {root_cause}
Final Outcome: {record.final_outcome or record.status.value}
Successful Fixes: {", ".join(successful_fixes) if successful_fixes else "None"}
Failed Approaches: {len(failed_fixes)} attempts failed
{"Permanent Fix Applied: " + permanent_fix if permanent_fix else ""}
Timestamp: {datetime.now(UTC).isoformat()}
"""

        # Store with metadata for filtering
        metadata = {
            "issue_signature": signature,
            "resource_type": issue.resource_type,
            "resource_name": issue.resource_name,
            "namespace": issue.namespace,
            "severity": issue.severity.value,
            "status": record.status.value,
            "root_cause": root_cause,
            "has_permanent_fix": permanent_fix is not None,
            "permanent_fix": permanent_fix,
            "successful_fix_count": len(successful_fixes),
            "successful_fixes": successful_fixes,
            "failed_fix_count": len(failed_fixes),
            "stored_at": datetime.now(UTC).isoformat(),
            "type": "remediation",
        }

        # Use infer=False with messages format (required by mem0)
        messages = [{"role": "user", "content": content}]
        result = memory.add(
            messages,
            user_id="k8s-monitor-agent",
            metadata=metadata,
            infer=False,
        )

        # Mark signature in Redis for fast future lookups
        mark_signature_seen(signature)

        # If permanent fix was applied, also cache in Redis
        if permanent_fix:
            _cache_permanent_fix(signature, permanent_fix)

        memory_id = _extract_memory_id(result)
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
Kubernetes issue similar to: {issue.title}
Resource type: {issue.resource_type}
Namespace: {issue.namespace}
Description: {issue.description[:500]}
"""

        raw_results = memory.search(
            query,
            user_id="k8s-monitor-agent",
            limit=limit,
        )

        # Process results
        memories = []
        for result in _extract_search_results(raw_results):
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
        permanent_fix = metadata.get("permanent_fix")
        status = metadata.get("status", "unknown")
        successful_fixes = metadata.get("successful_fixes", [])

        context_parts.append(f"### Similar Issue #{i} (relevance: {score:.2f})")
        context_parts.append(content.strip())

        if successful_fixes:
            context_parts.append(f"**Fixes that worked:** {', '.join(successful_fixes)}")

        if has_permanent_fix and permanent_fix:
            context_parts.append(f"**Permanent fix applied:** {permanent_fix}")

        if status == "escalated":
            context_parts.append("**Warning: This issue required human intervention.**")

        context_parts.append("")  # Empty line separator

    return "\n".join(context_parts)


def _cache_permanent_fix(signature: str, fix_description: str) -> None:
    """Cache a permanent fix in Redis for fast lookups."""
    redis_client = get_redis()
    if redis_client:
        try:
            redis_client.hset(REDIS_PERMANENT_FIX_KEY, signature, fix_description)
            redis_client.expire(REDIS_PERMANENT_FIX_KEY, REDIS_PERMANENT_FIX_TTL_DAYS * 86400)
        except redis.RedisError as e:
            logger.warning(f"Redis error caching permanent fix: {e}")


def _get_cached_permanent_fix(signature: str) -> str | None:
    """Get a cached permanent fix from Redis."""
    redis_client = get_redis()
    if redis_client:
        try:
            return redis_client.hget(REDIS_PERMANENT_FIX_KEY, signature)
        except redis.RedisError as e:
            logger.warning(f"Redis error getting cached permanent fix: {e}")
    return None


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

        content = f"""
PERMANENT FIX RECORD for Kubernetes Issue
Issue Type: {issue.title}
Resource Pattern: {issue.resource_type} in {issue.namespace}
Root Cause Pattern: {issue.description[:200]}
Permanent Fix: {fix_description}
Recommendation: When this issue recurs, suggest this permanent fix to the operator.
Applied At: {datetime.now(UTC).isoformat()}
"""

        metadata = {
            "issue_signature": signature,
            "type": "permanent_fix",
            "resource_type": issue.resource_type,
            "namespace": issue.namespace,
            "fix_description": fix_description,
            "applied_at": datetime.now(UTC).isoformat(),
        }

        # Use infer=False with messages format
        messages = [{"role": "user", "content": content}]
        memory.add(
            messages,
            user_id="k8s-monitor-agent",
            metadata=metadata,
            infer=False,
        )

        # Also cache in Redis for fast lookups
        _cache_permanent_fix(signature, fix_description)

        logger.info(f"Recorded permanent fix for issue signature {signature}")
        return True

    except Exception as e:
        logger.error(f"Failed to record permanent fix: {e}")
        return False


def check_for_permanent_fix(issue: Issue) -> str | None:
    """
    Check if a permanent fix exists for this type of issue.

    Uses Redis for fast lookup, falls back to mem0 search.

    Args:
        issue: The issue to check

    Returns:
        Description of permanent fix if one exists, None otherwise
    """
    signature = generate_issue_signature(issue)

    # Try Redis first (fast)
    cached_fix = _get_cached_permanent_fix(signature)
    if cached_fix:
        return cached_fix

    # Fallback to mem0 search
    try:
        memory = get_memory()

        # Search specifically for permanent fix records
        query = f"PERMANENT FIX for {issue.resource_type} {issue.title}"

        raw_results = memory.search(
            query,
            user_id="k8s-monitor-agent",
            limit=5,
        )

        for result in _extract_search_results(raw_results):
            metadata = result.get("metadata", {})
            if (
                metadata.get("type") == "permanent_fix"
                and metadata.get("issue_signature") == signature
            ):
                fix = metadata.get("fix_description")
                if fix:
                    # Cache for next time
                    _cache_permanent_fix(signature, fix)
                    return fix

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


def query_recent_remediations(
    days: int = 7,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Query recent remediation records from Qdrant.

    Uses direct Qdrant client for fast retrieval without LLM calls.

    Args:
        days: Number of days to look back
        limit: Maximum records to return

    Returns:
        List of remediation records with metadata
    """
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models

        qdrant_host = os.environ.get("QDRANT_HOST", "qdrant.database.svc.cluster.local")
        qdrant_port = int(os.environ.get("QDRANT_PORT", "6333"))
        qdrant_api_key = os.environ.get("QDRANT_API_KEY")
        collection = os.environ.get("QDRANT_COLLECTION", "k8s-remediation")

        # Connect to Qdrant directly (bypass mem0 for speed)
        client = QdrantClient(
            url=f"http://{qdrant_host}:{qdrant_port}",
            api_key=qdrant_api_key if qdrant_api_key else None,
        )

        cutoff = datetime.now(UTC) - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()

        results = client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="remediation"),
                    ),
                ]
            ),
            limit=limit * 2,  # Fetch extra since we filter by date
            with_payload=True,
            with_vectors=False,
        )

        records = []
        for point in results[0]:  # scroll returns (points, next_offset)
            payload = point.payload or {}

            # Filter by stored_at >= cutoff
            stored_at_str = payload.get("stored_at", "")
            if stored_at_str:
                try:
                    stored_at_dt = datetime.fromisoformat(stored_at_str.replace("Z", "+00:00"))
                    if stored_at_dt < cutoff:
                        continue
                except ValueError:
                    continue

            records.append(payload)

        # Sort by stored_at descending
        records.sort(
            key=lambda r: r.get("stored_at", ""),
            reverse=True,
        )

        logger.info(f"Queried {len(records[:limit])} remediations since {cutoff_iso}")
        return records[:limit]

    except Exception as e:
        logger.error(f"Failed to query recent remediations: {e}")
        return []


def get_fix_success_rate(resource_type: str, fix_action: str) -> float:
    """
    Calculate the success rate of a specific fix action for a resource type.

    Uses graph relationships to find all instances where this fix was applied.

    Args:
        resource_type: The Kubernetes resource type (e.g., "Pod", "Deployment")
        fix_action: The fix action to check (e.g., "restart", "scale up")

    Returns:
        Success rate as a float between 0.0 and 1.0, or -1.0 if no data
    """
    try:
        memory = get_memory()

        query = f"remediation {resource_type} fix {fix_action} outcome"
        raw_results = memory.search(
            query,
            user_id="k8s-monitor-agent",
            limit=20,
        )

        total = 0
        successes = 0

        for result in _extract_search_results(raw_results):
            metadata = result.get("metadata", {})
            if (
                metadata.get("resource_type") == resource_type
                and fix_action.lower() in str(metadata.get("successful_fixes", [])).lower()
            ):
                total += 1
                if metadata.get("status") in ["resolved", "mitigated"]:
                    successes += 1

        if total == 0:
            return -1.0  # No data

        return successes / total

    except Exception as e:
        logger.error(f"Failed to calculate fix success rate: {e}")
        return -1.0
