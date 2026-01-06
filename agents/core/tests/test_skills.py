"""Tests for the skill library module."""

from core_agents.skills import (
    MCPToolReference,
    Skill,
    SkillAction,
    SkillCategory,
    SkillDomain,
    SkillOutcome,
)


class TestSkillSchema:
    """Tests for Skill and related schemas."""

    def test_create_simple_skill(self):
        """Test creating a basic skill."""
        skill = Skill(
            id="test-skill",
            name="Test Skill",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="A test skill for unit testing",
            preconditions=["Resource exists"],
            actions=[
                SkillAction(
                    description="Get resource",
                    mcp_tool=MCPToolReference(
                        server="kubernetes-mcp-server",
                        tool="pods_get",
                        params={"name": "$pod_name", "namespace": "$namespace"},
                    ),
                )
            ],
            success_criteria=["Resource retrieved"],
            failure_handling="Escalate to human",
        )

        assert skill.id == "test-skill"
        assert skill.domain == SkillDomain.K8S
        assert skill.category == SkillCategory.DIAGNOSTIC
        assert len(skill.actions) == 1
        assert skill.actions[0].mcp_tool.server == "kubernetes-mcp-server"
        assert skill.confidence == 0.5  # Default

    def test_skill_searchable_text(self):
        """Test that searchable text includes relevant fields."""
        skill = Skill(
            id="k8s-restart-crashloop",
            name="Restart CrashLoopBackOff Pod",
            domain=SkillDomain.K8S,
            category=SkillCategory.REMEDIATION,
            description="Restart a pod stuck in CrashLoopBackOff",
            preconditions=["Pod status is CrashLoopBackOff", "Restart count > 3"],
            actions=[],
            success_criteria=["Pod becomes Running"],
            failure_handling="Escalate",
            tags=["pod", "restart", "crashloop"],
        )

        searchable = skill.get_searchable_text()
        assert "CrashLoopBackOff" in searchable
        assert "restart" in searchable.lower()
        assert "pod" in searchable.lower()

    def test_skill_record_outcome(self):
        """Test that recording outcomes updates confidence."""
        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            failure_handling="",
            confidence=0.5,
        )

        # Record success
        skill.record_outcome(success=True)
        assert skill.success_count == 1
        assert skill.failure_count == 0
        assert skill.confidence > 0.5

        # Record failure
        skill.record_outcome(success=False)
        assert skill.success_count == 1
        assert skill.failure_count == 1

    def test_mcp_tool_reference(self):
        """Test MCP tool reference with parameters."""
        tool_ref = MCPToolReference(
            server="kubernetes-mcp-server",
            tool="pods_delete",
            params={
                "name": "$pod_name",
                "namespace": "$namespace",
            },
        )

        assert tool_ref.server == "kubernetes-mcp-server"
        assert tool_ref.tool == "pods_delete"
        assert "$pod_name" in tool_ref.params.values()

    def test_skill_action_timeout(self):
        """Test skill action with custom timeout."""
        action = SkillAction(
            description="Long running operation",
            mcp_tool=MCPToolReference(
                server="test-server",
                tool="test_tool",
                params={},
            ),
            timeout_seconds=300,
        )

        assert action.timeout_seconds == 300

    def test_skill_outcome(self):
        """Test skill outcome recording."""
        outcome = SkillOutcome(
            skill_id="test-skill",
            success=True,
            error_message=None,
        )

        assert outcome.skill_id == "test-skill"
        assert outcome.success is True
        assert outcome.timestamp is not None

    def test_skill_requires_approval(self):
        """Test skill with approval requirement."""
        skill = Skill(
            id="dangerous-skill",
            name="Dangerous Operation",
            domain=SkillDomain.K8S,
            category=SkillCategory.REMEDIATION,
            description="A dangerous operation",
            preconditions=[],
            actions=[],
            success_criteria=[],
            failure_handling="",
            requires_approval=True,
        )

        assert skill.requires_approval is True


class TestSkillDomains:
    """Test skill domain and category enums."""

    def test_all_domains_exist(self):
        """Test that expected domains exist."""
        assert SkillDomain.K8S
        assert SkillDomain.NEWS
        assert SkillDomain.GENERAL

    def test_all_categories_exist(self):
        """Test that expected categories exist."""
        assert SkillCategory.DIAGNOSTIC
        assert SkillCategory.REMEDIATION
        assert SkillCategory.COLLECTION
        assert SkillCategory.ANALYSIS
