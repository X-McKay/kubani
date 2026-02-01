"""
Skill Synthesizer Agent - Proposes new skills from successful patterns.

The Skill Synthesizer is part of the Voyager-inspired continuous learning system.
It analyzes skill opportunities identified by the Reflection Agent and:
- Generates skill proposals with full instructions
- Creates test cases for validation
- Posts proposals to Discord for human approval

Usage:
    from kubani.agents.skill_synthesizer import SkillSynthesizerAgent

    synthesizer = SkillSynthesizerAgent()
    proposals = await synthesizer.synthesize_skills()
"""

import logging
import re
import time
from pathlib import Path
from typing import Any

from kubani.agents._base import KubaniAgent
from kubani.agents.skill_synthesizer.models import (
    ProposedSkill,
    SkillProposalStatus,
    SynthesisResult,
)
from kubani.framework.config import get_config
from kubani.framework.mcp import get_mcp_client

logger = logging.getLogger(__name__)

SYNTHESIZER_PROMPT = """You are a Skill Synthesizer Agent in a continuous learning system.

Your role is to create new skills from successful patterns identified by the Reflection Agent.
When creating skills:

1. **Name**: Create a clear, descriptive kebab-case name
2. **Domain**: Identify the domain (k8s, news, infrastructure, etc.)
3. **Category**: Categorize (diagnostic, remediation, monitoring, etc.)
4. **Instructions**: Write clear, step-by-step instructions
5. **Test Cases**: Define validation test cases

Skills should be:
- Reusable across similar situations
- Well-documented with clear instructions
- Validated with concrete test cases
- Focused on a single responsibility

Format skills as Markdown with YAML frontmatter.
"""


class SkillSynthesizerAgent(KubaniAgent):
    """
    Synthesizes new skills from successful patterns.

    Part of the continuous learning system, the Skill Synthesizer:
    - Analyzes skill opportunities from reflection
    - Generates complete skill definitions
    - Creates validation test cases
    - Posts proposals to Discord for approval
    """

    name = "skill-synthesizer"
    description = "Creates new skills from successful patterns"
    version = "1.0.0"

    PROMPT_FILE = Path(__file__).parent / "prompt.md"

    def __init__(self):
        """Initialize the Skill Synthesizer Agent."""
        super().__init__()
        self._min_pattern_occurrences = 5
        self._min_success_rate = 0.8

    @property
    def system_prompt(self) -> str:
        """Get the system prompt."""
        if self.PROMPT_FILE.exists():
            return self.PROMPT_FILE.read_text()
        return SYNTHESIZER_PROMPT

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("success", False)
        await self.record_outcome(skill_name, result, success=success)

    async def synthesize_skills(self) -> SynthesisResult:
        """
        Run a skill synthesis cycle.

        Fetches skill opportunities and creates proposals for approval.

        Returns:
            SynthesisResult with proposals created
        """
        start_time = time.time()
        result = SynthesisResult()

        try:
            # Fetch skill opportunities from reflection
            opportunities = await self._fetch_skill_opportunities()
            result.insights_analyzed = len(opportunities)

            if not opportunities:
                logger.info("No skill opportunities found")
                return result

            # Analyze patterns for each opportunity
            for opportunity in opportunities:
                if await self._should_create_skill(opportunity):
                    proposal = await self._synthesize_skill(opportunity)

                    if proposal:
                        result.proposals.append(proposal)
                        result.proposals_created += 1

                        # Post for approval if above threshold
                        if await self._should_post_for_approval(proposal):
                            await self._post_for_approval(proposal)
                            result.proposals_posted += 1

        except Exception as e:
            logger.error(f"Skill synthesis failed: {e}")

        result.duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"Synthesis complete: {result.proposals_created} proposals, "
            f"{result.proposals_posted} posted for approval"
        )

        return result

    async def _fetch_skill_opportunities(self) -> list[dict[str, Any]]:
        """Fetch skill opportunities from memory."""
        try:
            client = get_mcp_client()
            config = get_config()

            if not config.mcp.memory_enabled:
                logger.debug("Memory MCP not enabled")
                return []

            opportunities = await client.memory.query_learnings(
                query="skill opportunity",
                learning_type="insight_skill_opportunity",
                min_confidence=0.7,
                limit=50,
            )

            return opportunities

        except Exception as e:
            logger.error(f"Failed to fetch skill opportunities: {e}")
            return []

    async def _should_create_skill(self, opportunity: dict[str, Any]) -> bool:
        """Check if a skill should be created from this opportunity."""
        context = opportunity.get("context", {})

        # Check minimum occurrences
        occurrences = context.get("occurrence_count", 0)
        if occurrences < self._min_pattern_occurrences:
            return False

        # Check success rate
        success_rate = context.get("success_rate", context.get("confidence", 0))
        if success_rate < self._min_success_rate:
            return False

        # Check if skill already exists
        skill_name = self._generate_skill_name(opportunity)
        return not await self._skill_exists(skill_name)

    async def _skill_exists(self, skill_name: str) -> bool:
        """Check if a skill with this name already exists."""
        try:
            client = get_mcp_client()
            config = get_config()

            if not config.mcp.memory_enabled:
                return False

            existing = await client.memory.query_learnings(
                query=f"skill {skill_name}",
                learning_type="skill_proposal",
                min_confidence=0.0,
                limit=1,
            )

            return len(existing) > 0

        except Exception:
            return False

    def _generate_skill_name(self, opportunity: dict[str, Any]) -> str:
        """Generate a kebab-case skill name from an opportunity."""
        context = opportunity.get("context", {})
        title = context.get("title", opportunity.get("content", ""))

        # Extract meaningful words
        title = title.replace("Skill Opportunity:", "").strip()
        title = title.replace("Pattern:", "").strip()

        # Convert to kebab-case
        words = re.findall(r"[a-zA-Z]+", title.lower())
        name = "-".join(words[:5])  # Max 5 words

        return name or "unnamed-skill"

    def _infer_domain(self, opportunity: dict[str, Any]) -> str:
        """Infer the domain from opportunity context."""
        context = opportunity.get("context", {})
        content = str(context).lower()

        if "kubernetes" in content or "k8s" in content or "pod" in content:
            return "k8s"
        if "news" in content or "article" in content:
            return "news"
        if "discord" in content:
            return "discord"
        if "memory" in content or "learning" in content:
            return "learning"

        agents = context.get("applicable_agents", [])
        if agents:
            if any("k8s" in a or "monitor" in a for a in agents):
                return "k8s"
            if any("news" in a for a in agents):
                return "news"

        return "general"

    def _infer_category(self, opportunity: dict[str, Any]) -> str:
        """Infer the category from opportunity context."""
        context = opportunity.get("context", {})
        content = str(context).lower()

        if "diagnose" in content or "investigate" in content:
            return "diagnostic"
        if "fix" in content or "remediat" in content or "resolve" in content:
            return "remediation"
        if "monitor" in content or "watch" in content:
            return "monitoring"
        if "alert" in content or "notify" in content:
            return "alerting"
        if "report" in content or "summarize" in content:
            return "reporting"

        return "general"

    async def _synthesize_skill(self, opportunity: dict[str, Any]) -> ProposedSkill | None:
        """Synthesize a skill from an opportunity."""
        try:
            context = opportunity.get("context", {})

            skill = ProposedSkill(
                name=self._generate_skill_name(opportunity),
                domain=self._infer_domain(opportunity),
                category=self._infer_category(opportunity),
                description=context.get("description", opportunity.get("content", "")),
                source_insights=[context.get("insight_id", "")],
                source_executions=context.get("evidence", []),
                source_patterns=[context.get("title", "")],
                estimated_success_rate=context.get("success_rate", context.get("confidence", 0)),
                confidence=context.get("confidence", 0.7),
            )

            # Generate instructions
            skill.instructions = self._generate_instructions(opportunity)

            # Generate test cases
            skill.test_cases = self._generate_test_cases(opportunity)

            # Store the proposal
            await self._store_proposal(skill)

            logger.info(f"Synthesized skill: {skill.name}")
            return skill

        except Exception as e:
            logger.error(f"Failed to synthesize skill: {e}")
            return None

    def _generate_instructions(self, opportunity: dict[str, Any]) -> str:
        """Generate skill instructions from opportunity."""
        context = opportunity.get("context", {})
        description = context.get("description", opportunity.get("content", ""))

        return f"""## Steps

1. Analyze the situation to confirm this skill applies
2. Gather necessary context and information
3. Execute the pattern that has proven successful:
   - {description}
4. Verify the outcome matches expectations
5. Report results

## When to Use

Use this skill when encountering similar situations to those that led to its creation.
This skill was synthesized from {context.get("occurrence_count", "multiple")} successful executions.

## Notes

- Confidence: {context.get("confidence", 0.7):.0%}
- Success Rate: {context.get("success_rate", 0.8):.0%}
"""

    def _generate_test_cases(self, opportunity: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate test cases for the skill."""
        context = opportunity.get("context", {})

        # Create basic test cases
        test_cases = [
            {
                "description": "Verify skill executes successfully",
                "input": {"trigger": "standard_case"},
                "expected_output": {"success": True},
            },
            {
                "description": "Verify skill handles edge cases",
                "input": {"trigger": "edge_case"},
                "expected_output": {"success": True},
            },
        ]

        # Add test case based on evidence
        if context.get("evidence"):
            test_cases.append(
                {
                    "description": "Verify skill matches original pattern",
                    "input": {"execution_id": context["evidence"][0]},
                    "expected_output": {"success": True},
                }
            )

        return test_cases

    async def _store_proposal(self, skill: ProposedSkill) -> None:
        """Store a skill proposal in memory."""
        try:
            client = get_mcp_client()
            config = get_config()

            if not config.mcp.memory_enabled:
                return

            await client.memory.store_learning(
                agent_id=self.name,
                learning_type="skill_proposal",
                content=f"Proposed skill: {skill.name}",
                confidence=skill.confidence,
                context=skill.to_dict(),
            )

        except Exception as e:
            logger.warning(f"Failed to store proposal: {e}")

    async def _should_post_for_approval(self, skill: ProposedSkill) -> bool:
        """Check if a skill should be posted for approval."""
        config = get_config()

        # Check if auto-approve threshold is met
        if skill.confidence >= config.learning.auto_approve_threshold:
            logger.info(
                f"Skill {skill.name} meets auto-approve threshold "
                f"({skill.confidence:.2f} >= {config.learning.auto_approve_threshold})"
            )
            skill.status = SkillProposalStatus.APPROVED
            return False  # Don't post, auto-approved

        # Check if Discord approval is required
        return config.learning.require_discord_approval

    async def _post_for_approval(self, skill: ProposedSkill) -> None:
        """Post a skill proposal to Discord for approval."""
        try:
            client = get_mcp_client()
            config = get_config()

            if not config.mcp.discord_enabled:
                logger.debug("Discord MCP not enabled, skipping approval post")
                return

            channel = config.discord.approvals_channel or config.discord.learning_channel
            if not channel:
                logger.warning("No approval channel configured")
                return

            # Build the approval message
            message = f"""🆕 **New Skill Proposal: {skill.domain}/{skill.name}**

📋 **Description:**
{skill.description[:500]}

📊 **Confidence:** {skill.confidence:.0%}
📈 **Based on:** {len(skill.source_executions)} successful executions
🎯 **Estimated Success Rate:** {skill.estimated_success_rate:.0%}

**Test Cases:**
{chr(10).join(f"✓ {tc.get('description', 'Test')}" for tc in skill.test_cases[:3])}

React to approve:
✅ Approve and deploy
❌ Reject
🔄 Request modifications
"""

            result = await client.discord.send_message_to_channel_name(
                channel_name=channel,
                content=message,
            )

            if result.success and result.data:
                skill.approval_message_id = result.data.get("message_id")
                skill.approval_channel = channel
                logger.info(f"Posted skill proposal for {skill.name} to #{channel}")

                # Update stored proposal with message ID
                await self._store_proposal(skill)
            else:
                logger.warning(f"Failed to post approval: {result.error}")

        except Exception as e:
            logger.error(f"Failed to post for approval: {e}")

    async def check_approval_status(self, skill_id: str) -> SkillProposalStatus:
        """Check the approval status of a skill proposal."""
        try:
            client = get_mcp_client()
            config = get_config()

            if not config.mcp.memory_enabled:
                return SkillProposalStatus.PENDING

            # Fetch the proposal
            proposals = await client.memory.query_learnings(
                query=f"skill proposal {skill_id}",
                learning_type="skill_proposal",
                min_confidence=0.0,
                limit=1,
            )

            if not proposals:
                return SkillProposalStatus.PENDING

            proposal_data = proposals[0].get("context", {})
            return SkillProposalStatus(proposal_data.get("status", "pending"))

        except Exception as e:
            logger.error(f"Failed to check approval status: {e}")
            return SkillProposalStatus.PENDING
