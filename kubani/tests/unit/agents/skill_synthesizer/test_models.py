"""Tests for Skill Synthesizer agent models."""


from kubani.agents.skill_synthesizer.models import (
    ProposedSkill,
    SkillProposalStatus,
    SynthesisResult,
)


class TestSkillProposalStatus:
    """Tests for SkillProposalStatus enum."""

    def test_all_statuses_exist(self):
        """Test that all expected statuses exist."""
        assert SkillProposalStatus.PENDING.value == "pending"
        assert SkillProposalStatus.APPROVED.value == "approved"
        assert SkillProposalStatus.REJECTED.value == "rejected"
        assert SkillProposalStatus.DEPLOYED.value == "deployed"
        assert SkillProposalStatus.EXPIRED.value == "expired"


class TestProposedSkill:
    """Tests for ProposedSkill dataclass."""

    def test_default_skill(self):
        """Test default skill values."""
        skill = ProposedSkill()
        assert skill.name == ""
        assert skill.domain == ""
        assert skill.category == ""
        assert skill.description == ""
        assert skill.instructions == ""
        assert skill.status == SkillProposalStatus.PENDING
        assert skill.confidence == 0.0
        assert skill.test_cases == []

    def test_custom_skill(self):
        """Test custom skill values."""
        skill = ProposedSkill(
            name="oom-recovery",
            domain="k8s",
            category="remediation",
            description="Handle OOM killed pods",
            instructions="1. Check memory limits\n2. Increase limits",
            confidence=0.85,
            estimated_success_rate=0.9,
        )
        assert skill.name == "oom-recovery"
        assert skill.domain == "k8s"
        assert skill.category == "remediation"
        assert skill.confidence == 0.85

    def test_to_dict(self):
        """Test conversion to dictionary."""
        skill = ProposedSkill(
            name="test-skill",
            domain="test",
            category="diagnostic",
            description="A test skill",
            status=SkillProposalStatus.APPROVED,
            confidence=0.95,
        )
        data = skill.to_dict()
        assert data["name"] == "test-skill"
        assert data["domain"] == "test"
        assert data["status"] == "approved"
        assert data["confidence"] == 0.95

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "skill_id": "skill-123",
            "name": "loaded-skill",
            "domain": "news",
            "category": "analysis",
            "description": "Analyzes news",
            "instructions": "Do analysis",
            "status": "deployed",
            "confidence": 0.88,
            "approvers": ["user1", "user2"],
        }
        skill = ProposedSkill.from_dict(data)
        assert skill.skill_id == "skill-123"
        assert skill.name == "loaded-skill"
        assert skill.status == SkillProposalStatus.DEPLOYED
        assert skill.confidence == 0.88
        assert skill.approvers == ["user1", "user2"]

    def test_to_skill_markdown(self):
        """Test skill markdown generation."""
        skill = ProposedSkill(
            name="example-skill",
            domain="k8s",
            category="diagnostic",
            description="An example diagnostic skill",
            instructions="Step 1: Do this\nStep 2: Do that",
            implementation_notes="Uses kubectl commands",
            source_patterns=["pattern1", "pattern2"],
            source_executions=["exec1", "exec2", "exec3"],
            test_cases=[
                {"description": "Test case 1"},
                {"description": "Test case 2"},
            ],
            confidence=0.85,
            estimated_success_rate=0.9,
        )
        markdown = skill.to_skill_markdown()

        assert "name: example-skill" in markdown
        assert "domain: k8s" in markdown
        assert "category: diagnostic" in markdown
        assert "confidence: 0.85" in markdown
        assert "# example-skill" in markdown
        assert "An example diagnostic skill" in markdown
        assert "Step 1: Do this" in markdown
        assert "Uses kubectl commands" in markdown
        assert "3 successful executions" in markdown
        assert "90%" in markdown
        assert "- pattern1" in markdown
        assert "- Test case 1" in markdown


class TestSynthesisResult:
    """Tests for SynthesisResult dataclass."""

    def test_default_result(self):
        """Test default result values."""
        result = SynthesisResult()
        assert result.proposals == []
        assert result.patterns_analyzed == 0
        assert result.insights_analyzed == 0
        assert result.proposals_created == 0
        assert result.proposals_posted == 0
        assert result.duration_ms == 0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        skill = ProposedSkill(name="test")
        result = SynthesisResult(
            proposals=[skill],
            patterns_analyzed=5,
            insights_analyzed=10,
            proposals_created=1,
            proposals_posted=1,
            duration_ms=2000,
        )
        data = result.to_dict()
        assert len(data["proposals"]) == 1
        assert data["patterns_analyzed"] == 5
        assert data["insights_analyzed"] == 10
        assert data["proposals_created"] == 1
        assert data["duration_ms"] == 2000
