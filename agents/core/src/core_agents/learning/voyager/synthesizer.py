"""
Skill Synthesizer for Automatic Skill Generation.

The Skill Synthesizer:
- Analyzes successful execution patterns
- Generates new skill proposals from patterns
- Refines skills based on Critic feedback
- Manages the skill proposal lifecycle

Inspired by Voyager's automatic curriculum and skill library.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx

try:
    from prometheus_client import Counter, Histogram

    SKILLS_REJECTED = Counter(
        "learning_skills_rejected_total",
        "Total number of skills rejected",
        ["reason"],
    )
    SKILLS_APPROVED = Counter(
        "learning_skills_approved_total",
        "Total number of skills approved",
        ["auto_approved"],
    )
    SYNTHESIS_DURATION = Histogram(
        "learning_synthesis_duration_seconds",
        "Time spent synthesizing skills",
        buckets=[1, 5, 10, 30, 60, 120, 300],
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

from core_agents.learning.voyager.critic import (
    CriticAgent,
    CriticVerdict,
    SkillProposal,
    SkillReview,
)

logger = logging.getLogger(__name__)


class SkillStatus(Enum):
    """Status of a skill in the synthesis pipeline."""

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    NEEDS_REVISION = "needs_revision"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPLOYED = "deployed"


@dataclass
class SkillCandidate:
    """A candidate skill being synthesized."""

    id: str
    name: str
    description: str
    trigger_pattern: str
    implementation: str
    examples: list[dict[str, Any]]
    source_executions: list[str]
    status: SkillStatus = SkillStatus.DRAFT
    confidence: float = 0.0
    reviews: list[SkillReview] = field(default_factory=list)
    revision_count: int = 0
    discord_message_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_proposal(self) -> SkillProposal:
        """Convert to a SkillProposal for review."""
        return SkillProposal(
            name=self.name,
            description=self.description,
            trigger_pattern=self.trigger_pattern,
            implementation=self.implementation,
            examples=self.examples,
            source_executions=self.source_executions,
            confidence=self.confidence,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger_pattern": self.trigger_pattern,
            "implementation": self.implementation,
            "examples": self.examples,
            "source_executions": self.source_executions,
            "status": self.status.value,
            "confidence": self.confidence,
            "revision_count": self.revision_count,
            "discord_message_id": self.discord_message_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def to_discord_message(self) -> str:
        """Format as a Discord message for approval."""
        return f"""🔧 **New Skill Proposal: {self.name}**

**Description**
{self.description}

**When to Use**
{self.trigger_pattern}

**Implementation**
```python
{self.implementation[:500]}{"..." if len(self.implementation) > 500 else ""}
```

**Confidence**: {self.confidence:.1%}
**Based on**: {len(self.source_executions)} execution(s)
**Status**: {self.status.value}

React to vote:
✅ Approve | ❌ Reject | 🔄 Request Revision | 💬 Discuss
"""


class SkillSynthesizer:
    """
    Synthesizes new skills from execution patterns.

    Pipeline:
    1. Identify patterns from successful executions
    2. Generate skill candidates
    3. Submit to Critic for review
    4. Refine based on feedback
    5. Post to Discord for approval
    6. Deploy approved skills
    """

    SKILL_GENERATION_PROMPT = """You are a Skill Synthesizer creating reusable skills from execution patterns.

Successful Execution Patterns:
{patterns}

Source Executions:
{executions}

Generate a reusable skill that captures this pattern:
1. Give it a clear, descriptive name
2. Describe what it does
3. Define when it should be triggered
4. Write the implementation as Python code
5. Include input/output specifications

The skill should be:
- General enough to apply to similar situations
- Specific enough to be useful
- Well-documented
- Safe and idempotent where possible

Respond as JSON:
{{
    "name": "<skill_name_snake_case>",
    "description": "<detailed description>",
    "trigger_pattern": "<when to use this skill>",
    "implementation": "<python code>",
    "inputs": [
        {{"name": "<input_name>", "type": "<type>", "description": "<desc>"}}
    ],
    "outputs": [
        {{"name": "<output_name>", "type": "<type>", "description": "<desc>"}}
    ],
    "confidence": <0.0-1.0>,
    "tags": ["<tag1>", ...]
}}"""

    SKILL_REFINEMENT_PROMPT = """You are refining a skill based on Critic feedback.

Current Skill:
Name: {name}
Description: {description}
Implementation:
{implementation}

Critic Feedback:
{feedback}

Suggested Improvements:
{improvements}

Refine the skill to address the feedback while maintaining its core functionality.

Respond as JSON:
{{
    "name": "<refined_name>",
    "description": "<refined_description>",
    "trigger_pattern": "<refined_trigger>",
    "implementation": "<refined_implementation>",
    "changes_made": ["<change 1>", ...]
}}"""

    # Redis keys for tracking rejected skills and patterns (TTL: 7 days)
    REJECTED_SKILLS_KEY = "learning:rejected_skills"
    REJECTED_PATTERNS_KEY = "learning:rejected_patterns"
    REJECTED_SKILLS_TTL = 60 * 60 * 24 * 7  # 7 days

    def __init__(
        self,
        llm_api_url: str,
        llm_model: str,
        critic: CriticAgent,
        discord_mcp_url: str | None = None,
        registry_url: str | None = None,
        max_revisions: int = 3,
        redis_url: str | None = None,
    ):
        self.llm_api_url = llm_api_url
        self.llm_model = llm_model
        self.critic = critic
        self.discord_mcp_url = discord_mcp_url
        self.registry_url = registry_url
        self.max_revisions = max_revisions
        self.redis_url = redis_url
        self.candidates: dict[str, SkillCandidate] = {}
        self._redis_client: Any | None = None

    async def _get_redis(self) -> Any | None:
        """Get or create Redis client."""
        if self._redis_client is None and self.redis_url:
            try:
                import redis.asyncio as redis

                self._redis_client = redis.from_url(self.redis_url)
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
        return self._redis_client

    async def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        if self._redis_client:
            try:
                await self._redis_client.close()
                self._redis_client = None
                logger.debug("Closed Redis connection")
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")

    @staticmethod
    def _hash_patterns(patterns: list[dict[str, Any]]) -> str:
        """Generate a hash for a set of patterns to detect duplicates."""
        import hashlib

        pattern_str = json.dumps(patterns, sort_keys=True)
        return hashlib.md5(pattern_str.encode()).hexdigest()

    async def _is_pattern_rejected(self, pattern_hash: str) -> bool:
        """Check if a pattern has been previously rejected."""
        redis_client = await self._get_redis()
        if redis_client:
            try:
                return await redis_client.sismember(self.REJECTED_PATTERNS_KEY, pattern_hash)
            except Exception as e:
                logger.debug(f"Failed to check rejected patterns: {e}")
        return False

    async def _mark_pattern_rejected(self, pattern_hash: str) -> None:
        """Mark a pattern as rejected to prevent re-synthesis."""
        redis_client = await self._get_redis()
        if redis_client:
            try:
                await redis_client.sadd(self.REJECTED_PATTERNS_KEY, pattern_hash)
                await redis_client.expire(self.REJECTED_PATTERNS_KEY, self.REJECTED_SKILLS_TTL)
                logger.debug(f"Marked pattern as rejected: {pattern_hash[:8]}...")
            except Exception as e:
                logger.warning(f"Failed to mark pattern as rejected: {e}")

    async def _is_skill_rejected(self, skill_name: str) -> bool:
        """Check if a skill has been previously rejected."""
        redis_client = await self._get_redis()
        if redis_client:
            try:
                return await redis_client.sismember(self.REJECTED_SKILLS_KEY, skill_name)
            except Exception as e:
                logger.debug(f"Failed to check rejected skills: {e}")
        return False

    async def _mark_skill_rejected(self, skill_name: str, reason: str = "max_revisions") -> None:
        """Mark a skill as rejected to prevent re-synthesis."""
        redis_client = await self._get_redis()
        if redis_client:
            try:
                await redis_client.sadd(self.REJECTED_SKILLS_KEY, skill_name)
                await redis_client.expire(self.REJECTED_SKILLS_KEY, self.REJECTED_SKILLS_TTL)
                logger.info(f"Marked skill as rejected: {skill_name}")
                # Record metric
                if METRICS_AVAILABLE:
                    SKILLS_REJECTED.labels(reason=reason).inc()
            except Exception as e:
                logger.warning(f"Failed to mark skill as rejected: {e}")

    async def clear_rejected_skill(self, skill_name: str) -> bool:
        """Clear a rejected skill from Redis (admin operation)."""
        redis_client = await self._get_redis()
        if redis_client:
            try:
                removed = await redis_client.srem(self.REJECTED_SKILLS_KEY, skill_name)
                if removed:
                    logger.info(f"Cleared rejected skill: {skill_name}")
                    return True
            except Exception as e:
                logger.warning(f"Failed to clear rejected skill: {e}")
        return False

    async def clear_rejected_pattern(self, pattern_hash: str) -> bool:
        """Clear a rejected pattern from Redis (admin operation)."""
        redis_client = await self._get_redis()
        if redis_client:
            try:
                removed = await redis_client.srem(self.REJECTED_PATTERNS_KEY, pattern_hash)
                if removed:
                    logger.info(f"Cleared rejected pattern: {pattern_hash[:8]}...")
                    return True
            except Exception as e:
                logger.warning(f"Failed to clear rejected pattern: {e}")
        return False

    async def list_rejected_skills(self) -> list[str]:
        """List all rejected skills (admin operation)."""
        redis_client = await self._get_redis()
        if redis_client:
            try:
                members = await redis_client.smembers(self.REJECTED_SKILLS_KEY)
                return [m.decode() if isinstance(m, bytes) else m for m in members]
            except Exception as e:
                logger.warning(f"Failed to list rejected skills: {e}")
        return []

    async def synthesize_from_patterns(
        self,
        patterns: list[dict[str, Any]],
        executions: list[dict[str, Any]],
    ) -> SkillCandidate | None:
        """Synthesize a skill from execution patterns."""
        prompt = self.SKILL_GENERATION_PROMPT.format(
            patterns=json.dumps(patterns, indent=2),
            executions=json.dumps(executions[:5], indent=2),
        )

        try:
            response = await self._call_llm(prompt)
            data = self._parse_json_response(response)

            candidate = SkillCandidate(
                id=f"skill_{datetime.now(UTC).timestamp()}",
                name=data["name"],
                description=data["description"],
                trigger_pattern=data["trigger_pattern"],
                implementation=data["implementation"],
                examples=[{"pattern": p} for p in patterns],
                source_executions=[e.get("id", "") for e in executions],
                confidence=data.get("confidence", 0.5),
            )

            self.candidates[candidate.id] = candidate
            logger.info(f"Synthesized skill candidate: {candidate.name}")

            return candidate

        except Exception as e:
            logger.error(f"Skill synthesis failed: {type(e).__name__}: {e}")
            return None

    async def submit_for_review(self, candidate: SkillCandidate) -> SkillReview:
        """Submit a skill candidate for Critic review."""
        candidate.status = SkillStatus.UNDER_REVIEW
        candidate.updated_at = datetime.now(UTC)

        review = await self.critic.review_skill_proposal(candidate.to_proposal())
        candidate.reviews.append(review)

        # Update status based on review
        if review.verdict == CriticVerdict.APPROVED:
            if self.critic.should_auto_approve(review):
                candidate.status = SkillStatus.APPROVED
                logger.info(f"Skill auto-approved: {candidate.name}")
                if METRICS_AVAILABLE:
                    SKILLS_APPROVED.labels(auto_approved="true").inc()
            else:
                candidate.status = SkillStatus.PENDING_APPROVAL
        elif review.verdict == CriticVerdict.NEEDS_REVISION:
            candidate.status = SkillStatus.NEEDS_REVISION
        elif review.verdict == CriticVerdict.REJECTED:
            candidate.status = SkillStatus.REJECTED
            await self._mark_skill_rejected(candidate.name, reason="critic_rejected")
        else:
            candidate.status = SkillStatus.NEEDS_REVISION

        return review

    async def refine_skill(
        self,
        candidate: SkillCandidate,
        review: SkillReview,
    ) -> SkillCandidate:
        """Refine a skill based on Critic feedback."""
        if candidate.revision_count >= self.max_revisions:
            logger.warning(f"Max revisions reached for {candidate.name}")
            candidate.status = SkillStatus.REJECTED
            # Mark as rejected to prevent re-synthesis
            await self._mark_skill_rejected(candidate.name, reason="max_revisions")
            return candidate

        prompt = self.SKILL_REFINEMENT_PROMPT.format(
            name=candidate.name,
            description=candidate.description,
            implementation=candidate.implementation,
            feedback=review.feedback,
            improvements=json.dumps(review.suggested_improvements),
        )

        try:
            response = await self._call_llm(prompt)
            data = self._parse_json_response(response)

            # Update candidate with refinements
            candidate.name = data.get("name", candidate.name)
            candidate.description = data.get("description", candidate.description)
            candidate.trigger_pattern = data.get("trigger_pattern", candidate.trigger_pattern)
            candidate.implementation = data.get("implementation", candidate.implementation)
            candidate.revision_count += 1
            candidate.updated_at = datetime.now(UTC)
            candidate.status = SkillStatus.DRAFT

            logger.info(f"Refined skill: {candidate.name} (revision {candidate.revision_count})")

            return candidate

        except Exception as e:
            logger.error(f"Skill refinement failed: {type(e).__name__}: {e}")
            return candidate

    async def post_for_approval(
        self, candidate: SkillCandidate, channel_name: str = "kubani-learning"
    ) -> str | None:
        """Post skill to Discord for human approval."""
        try:
            from core_agents.integrations.discord_mcp import send_discord_message

            message_id = await send_discord_message(
                content=candidate.to_discord_message(),
                channel_name=channel_name,
                agent_name="learning-agent",
            )

            if message_id:
                candidate.discord_message_id = message_id
                candidate.status = SkillStatus.PENDING_APPROVAL
                logger.info(f"Posted skill for approval: {candidate.name} (message: {message_id})")
                return message_id
            else:
                logger.warning(f"Failed to post skill for approval: {candidate.name}")

        except Exception as e:
            logger.error(f"Failed to post for approval: {type(e).__name__}: {e}")

        return None

    async def deploy_skill(self, candidate: SkillCandidate) -> bool:
        """Deploy an approved skill to the registry."""
        if candidate.status != SkillStatus.APPROVED:
            logger.warning(f"Cannot deploy unapproved skill: {candidate.name}")
            return False

        if not self.registry_url:
            logger.warning("Registry URL not configured")
            return False

        try:
            skill_data = {
                "name": candidate.name,
                "description": candidate.description,
                "trigger_pattern": candidate.trigger_pattern,
                "implementation": candidate.implementation,
                "examples": candidate.examples,
                "metadata": {
                    "source": "synthesizer",
                    "confidence": candidate.confidence,
                    "source_executions": candidate.source_executions,
                },
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.registry_url}/api/v1/skills",
                    json=skill_data,
                    timeout=30.0,
                )

                if response.status_code in (200, 201):
                    candidate.status = SkillStatus.DEPLOYED
                    logger.info(f"Deployed skill: {candidate.name}")
                    return True
                else:
                    logger.error(f"Failed to deploy skill: {response.status_code}")

        except Exception as e:
            logger.error(f"Skill deployment failed: {e}")

        return False

    async def process_approval_reaction(
        self,
        candidate_id: str,
        reaction: str,
        user: str,
    ) -> None:
        """Process a Discord reaction for skill approval."""
        candidate = self.candidates.get(candidate_id)
        if not candidate:
            return

        if reaction == "✅":
            candidate.status = SkillStatus.APPROVED
            await self.deploy_skill(candidate)
            if METRICS_AVAILABLE:
                SKILLS_APPROVED.labels(auto_approved="false").inc()
        elif reaction == "❌":
            candidate.status = SkillStatus.REJECTED
            await self._mark_skill_rejected(candidate.name, reason="user_rejected")
        elif reaction == "🔄":
            # Request revision - get latest review and refine
            if candidate.reviews:
                await self.refine_skill(candidate, candidate.reviews[-1])
                await self.submit_for_review(candidate)

    async def run_synthesis_pipeline(
        self,
        patterns: list[dict[str, Any]],
        executions: list[dict[str, Any]],
    ) -> SkillCandidate | None:
        """Run the full synthesis pipeline."""
        import time

        start_time = time.monotonic()
        pattern_hash = self._hash_patterns(patterns)

        try:
            # 0. Check if this pattern was previously rejected
            if await self._is_pattern_rejected(pattern_hash):
                logger.info(f"Skipping previously rejected pattern: {pattern_hash[:8]}...")
                return None

            # 1. Synthesize skill
            candidate = await self.synthesize_from_patterns(patterns, executions)
            if not candidate:
                return None

            # 1b. Check if this skill was previously rejected
            if await self._is_skill_rejected(candidate.name):
                logger.info(f"Skipping previously rejected skill: {candidate.name}")
                candidate.status = SkillStatus.REJECTED
                return candidate

            # 2. Submit for review
            review = await self.submit_for_review(candidate)

            # 3. Refine if needed (up to max_revisions)
            while candidate.status == SkillStatus.NEEDS_REVISION:
                candidate = await self.refine_skill(candidate, review)
                if candidate.status == SkillStatus.REJECTED:
                    # Max revisions reached, skill was marked as rejected
                    # Also mark the pattern to prevent re-synthesis from same patterns
                    await self._mark_pattern_rejected(pattern_hash)
                    break
                review = await self.submit_for_review(candidate)

            # 4. Post for approval if not auto-approved or rejected
            if candidate.status == SkillStatus.PENDING_APPROVAL:
                await self.post_for_approval(candidate)
            elif candidate.status == SkillStatus.APPROVED:
                await self.deploy_skill(candidate)
                # Record approval metric
                if METRICS_AVAILABLE:
                    auto_approved = "true" if not candidate.discord_message_id else "false"
                    SKILLS_APPROVED.labels(auto_approved=auto_approved).inc()

            return candidate

        finally:
            # Record synthesis duration
            if METRICS_AVAILABLE:
                duration = time.monotonic() - start_time
                SYNTHESIS_DURATION.observe(duration)

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM API."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.llm_api_url}/chat/completions",
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                    "max_tokens": 4096,
                },
                timeout=300.0,
            )

            if response.status_code != 200:
                raise RuntimeError(f"LLM API error: {response.status_code}")

            data = response.json()
            return data["choices"][0]["message"]["content"]

    def _parse_json_response(self, response: str) -> dict[str, Any]:
        """Parse JSON from LLM response."""
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(response[json_start:json_end])
        raise ValueError("No valid JSON found in response")
