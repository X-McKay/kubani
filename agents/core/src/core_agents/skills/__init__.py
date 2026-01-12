"""
Skill library framework for knowledge-based agent capabilities.

Skills represent KNOWLEDGE about when and how to use MCP tools, not executable code.
Each skill contains:
- Preconditions (when to apply)
- Actions (MCP tool references)
- Success criteria (how to verify)
- Learning metadata (confidence, usage stats)

This module provides:
- Skill schema (Pydantic models)
- SkillLibrary interface and Qdrant implementation
- UnifiedSkillLibrary for markdown-based skills (Agent Skills format)
- LocalRunner for testing skills locally
- Semantic retrieval by preconditions

Example (Python Skill format):
    from core_agents.skills import Skill, SkillLibrary, get_skill_library

    # Create a skill (knowledge, not code)
    skill = Skill(
        id="k8s-restart-crashloop",
        name="Restart CrashLoopBackOff Pod",
        domain="k8s",
        category="remediation",
        description="Restart a pod stuck in CrashLoopBackOff",
        preconditions=["Pod status is CrashLoopBackOff", "Restart count > 3"],
        actions=[
            SkillAction(
                description="Delete pod to trigger recreation",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="pods_delete",
                    params={"name": "$pod_name", "namespace": "$namespace"},
                ),
            )
        ],
        success_criteria=["New pod reaches Running within 2 minutes"],
    )

    # Store and retrieve skills
    library = await get_skill_library()
    await library.add(skill)
    matches = await library.search("pod crashing repeatedly", domain="k8s")

Example (Markdown/Agent Skills format):
    from core_agents.skills import UnifiedSkillLibrary, get_unified_skill_library

    # Load and sync markdown skills
    library = await get_unified_skill_library(skills_dir="skills")
    await library.sync()  # Index all SKILL.md files to Qdrant

    # Search for matching skills
    results = await library.search("pod crashing repeatedly", domain="k8s")
    for result in results:
        print(f"Skill: {result.skill.name} (score: {result.score})")
        print(result.skill.body)  # Full markdown content

Example (Local testing):
    from core_agents.skills import LocalRunner, test_skill

    # Test a single skill
    result = await test_skill("k8s/remediation/restart-crashloop")
    print(f"Passed: {result['passed']}/{result['total']}")

    # Or use the runner directly with custom mocks
    runner = LocalRunner(
        skills_dir="skills",
        mcp_mocks={
            "kubernetes-mcp-server": {
                "pods_delete": lambda p: {"success": True},
            },
        },
    )
    result = await runner.execute_skill(
        "k8s/remediation/restart-crashloop",
        context={"pod_name": "nginx-123", "namespace": "default"},
    )
"""

# Registry integration utilities
import logging as _logging

from core_agents.skills.library import (
    QdrantSkillLibrary,
    SkillLibrary,
    get_skill_library,
)
from core_agents.skills.local_runner import (
    LocalRunner,
    MockMCPClient,
    ScenarioResult,
    SkillExecutionResult,
    SkillExecutor,
    SkillLoader,
    test_all_skills,
    test_skill,
)
from core_agents.skills.schema import (
    MCPToolReference,
    Skill,
    SkillAction,
    SkillCategory,
    SkillDomain,
    SkillOutcome,
    SkillStatus,
)
from core_agents.skills.unified import (
    AgentSkill,
    SkillSearchResult,
    UnifiedSkillLibrary,
    get_unified_skill_library,
)
from core_agents.skills.mcp_server import (
    MCPToolDefinition,
    MCPToolResult,
    SkillsMCPServer,
)
from core_agents.skills.validator import (
    SandboxConfig,
    SkillPromoter,
    SkillValidator,
    ValidationResult,
    VerificationResult,
    select_skill_with_confidence,
)

_logger = _logging.getLogger(__name__)
_registry_client = None


async def record_skill_outcome_to_registry(
    skill_id: str,
    success: bool,
    skill_name: str | None = None,
    domain: str | None = None,
    category: str | None = None,
    confidence: float = 0.5,
    requires_approval: bool = False,
) -> bool:
    """
    Record a skill execution outcome to the centralized registry.

    This function handles registry client initialization and ensures the skill
    exists in the registry before recording the outcome.

    Args:
        skill_id: Unique skill identifier (e.g., 'k8s/remediation/restart-crashloop')
        success: Whether the skill execution was successful
        skill_name: Human-readable name (optional, uses skill_id if not provided)
        domain: Skill domain (k8s, news, general) - extracted from skill_id if not provided
        category: Skill category - extracted from skill_id if not provided
        confidence: Current confidence score for new skills
        requires_approval: Whether skill requires human approval

    Returns:
        True if outcome was recorded, False otherwise
    """
    global _registry_client

    try:
        from core_agents.config_unified import get_config
        from core_agents.registry import get_registry_client

        config = get_config()
        if not config.registry.enabled:
            return False

        # Lazy init registry client
        if _registry_client is None:
            _registry_client = get_registry_client()
            await _registry_client.connect()

        # Try to record outcome
        result = await _registry_client.record_skill_outcome(skill_id, success)

        # If skill doesn't exist, register it first then record outcome
        if result is None:
            # Extract domain/category from skill_id if not provided
            # skill_id format: 'domain/category/skill-name' e.g., 'k8s/remediation/restart-crashloop'
            parts = skill_id.split("/")
            if len(parts) >= 2:
                domain = domain or parts[0]
                category = category or parts[1]
            else:
                domain = domain or "general"
                category = category or "general"

            name = skill_name or skill_id.split("/")[-1].replace("-", " ").title()

            await _registry_client.register_skill(
                skill_id=skill_id,
                name=name,
                domain=domain,
                category=category,
                status="experimental",
                confidence=confidence,
                requires_approval=requires_approval,
            )

            # Now record the outcome
            await _registry_client.record_skill_outcome(skill_id, success)

        _logger.debug(f"Recorded skill outcome: {skill_id} success={success}")
        return True

    except Exception as e:
        _logger.warning(f"Failed to record skill outcome to registry: {e}")
        return False


__all__ = [
    # Schema (Python format)
    "Skill",
    "SkillAction",
    "SkillCategory",
    "SkillDomain",
    "SkillOutcome",
    "SkillStatus",
    "MCPToolReference",
    # Library (Python format)
    "SkillLibrary",
    "QdrantSkillLibrary",
    "get_skill_library",
    # Unified library (Markdown/Agent Skills format)
    "AgentSkill",
    "UnifiedSkillLibrary",
    "get_unified_skill_library",
    "SkillSearchResult",
    # Local testing
    "LocalRunner",
    "SkillLoader",
    "SkillExecutor",
    "SkillExecutionResult",
    "ScenarioResult",
    "MockMCPClient",
    "test_skill",
    "test_all_skills",
    # Validator
    "SkillValidator",
    "SkillPromoter",
    "ValidationResult",
    "VerificationResult",
    "SandboxConfig",
    "select_skill_with_confidence",
    # Registry integration
    "record_skill_outcome_to_registry",
    # MCP Server
    "SkillsMCPServer",
    "MCPToolDefinition",
    "MCPToolResult",
]
