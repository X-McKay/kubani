"""
Critic Agent for Voyager-style Continuous Learning.

The Critic Agent evaluates agent executions and skill proposals:
- Analyzes execution traces for success/failure patterns
- Validates proposed skills against quality criteria
- Provides structured feedback for improvement
- Maintains quality gates for skill library

Inspired by Voyager's self-verification mechanism.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CriticVerdict(Enum):
    """Verdict from the critic agent."""

    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    REJECTED = "rejected"
    NEEDS_MORE_DATA = "needs_more_data"


@dataclass
class ExecutionAnalysis:
    """Analysis of an agent execution."""

    execution_id: str
    agent_name: str
    task_summary: str
    success: bool
    verdict: CriticVerdict
    score: float  # 0.0 to 1.0
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    improvement_suggestions: list[str] = field(default_factory=list)
    skill_opportunities: list[dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "execution_id": self.execution_id,
            "agent_name": self.agent_name,
            "task_summary": self.task_summary,
            "success": self.success,
            "verdict": self.verdict.value,
            "score": self.score,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "improvement_suggestions": self.improvement_suggestions,
            "skill_opportunities": self.skill_opportunities,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SkillProposal:
    """A proposed new skill or skill modification."""

    name: str
    description: str
    trigger_pattern: str
    implementation: str
    examples: list[dict[str, Any]]
    source_executions: list[str]  # Execution IDs that inspired this skill
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillReview:
    """Review of a skill proposal by the critic."""

    proposal: SkillProposal
    verdict: CriticVerdict
    score: float
    feedback: str
    quality_checks: dict[str, bool] = field(default_factory=dict)
    suggested_improvements: list[str] = field(default_factory=list)
    approval_confidence: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "proposal_name": self.proposal.name,
            "verdict": self.verdict.value,
            "score": self.score,
            "feedback": self.feedback,
            "quality_checks": self.quality_checks,
            "suggested_improvements": self.suggested_improvements,
            "approval_confidence": self.approval_confidence,
            "timestamp": self.timestamp.isoformat(),
        }


class CriticAgent:
    """
    Critic Agent that evaluates executions and skill proposals.

    Uses LLM-based analysis to:
    1. Evaluate execution quality and identify patterns
    2. Review skill proposals for quality and usefulness
    3. Suggest improvements and new skill opportunities
    """

    EXECUTION_ANALYSIS_PROMPT = """You are a Critic Agent evaluating an AI agent's execution.

Agent: {agent_name}
Task: {task_summary}

Execution Trace:
{execution_trace}

Outcome:
{outcome}

Analyze this execution and provide:
1. Whether it was successful and why
2. Strengths demonstrated
3. Weaknesses or inefficiencies
4. Specific improvement suggestions
5. Potential skill opportunities (reusable patterns)

Respond as JSON:
{{
    "success": <true/false>,
    "score": <0.0-1.0>,
    "verdict": "<approved|needs_revision|rejected>",
    "strengths": ["<strength 1>", ...],
    "weaknesses": ["<weakness 1>", ...],
    "improvement_suggestions": ["<suggestion 1>", ...],
    "skill_opportunities": [
        {{
            "name": "<skill_name>",
            "description": "<what it does>",
            "trigger": "<when to use it>",
            "confidence": <0.0-1.0>
        }}
    ]
}}"""

    SKILL_REVIEW_PROMPT = """You are a Critic Agent reviewing a proposed skill for the skill library.

Proposed Skill:
Name: {name}
Description: {description}
Trigger Pattern: {trigger_pattern}

Implementation:
{implementation}

Examples from executions:
{examples}

Review this skill proposal against these quality criteria:
1. **Clarity**: Is the skill well-defined and understandable?
2. **Generalizability**: Can it be applied to multiple scenarios?
3. **Correctness**: Is the implementation likely to work correctly?
4. **Usefulness**: Does it provide significant value?
5. **Safety**: Are there any potential risks or edge cases?

Respond as JSON:
{{
    "verdict": "<approved|needs_revision|rejected|needs_more_data>",
    "score": <0.0-1.0>,
    "feedback": "<detailed feedback>",
    "quality_checks": {{
        "clarity": <true/false>,
        "generalizability": <true/false>,
        "correctness": <true/false>,
        "usefulness": <true/false>,
        "safety": <true/false>
    }},
    "suggested_improvements": ["<improvement 1>", ...],
    "approval_confidence": <0.0-1.0>
}}"""

    def __init__(
        self,
        llm_api_url: str,
        llm_model: str,
        auto_approve_threshold: float = 0.95,
    ):
        self.llm_api_url = llm_api_url
        self.llm_model = llm_model
        self.auto_approve_threshold = auto_approve_threshold

    async def analyze_execution(
        self,
        execution_id: str,
        agent_name: str,
        task_summary: str,
        execution_trace: list[dict[str, Any]],
        outcome: dict[str, Any],
    ) -> ExecutionAnalysis:
        """Analyze an agent execution and provide feedback."""
        prompt = self.EXECUTION_ANALYSIS_PROMPT.format(
            agent_name=agent_name,
            task_summary=task_summary,
            execution_trace=json.dumps(execution_trace, indent=2),
            outcome=json.dumps(outcome, indent=2),
        )

        try:
            response = await self._call_llm(prompt)
            data = self._parse_json_response(response)

            return ExecutionAnalysis(
                execution_id=execution_id,
                agent_name=agent_name,
                task_summary=task_summary,
                success=data.get("success", False),
                verdict=CriticVerdict(data.get("verdict", "needs_revision")),
                score=data.get("score", 0.5),
                strengths=data.get("strengths", []),
                weaknesses=data.get("weaknesses", []),
                improvement_suggestions=data.get("improvement_suggestions", []),
                skill_opportunities=data.get("skill_opportunities", []),
            )

        except Exception as e:
            logger.error(f"Execution analysis failed: {type(e).__name__}: {e}")
            return ExecutionAnalysis(
                execution_id=execution_id,
                agent_name=agent_name,
                task_summary=task_summary,
                success=False,
                verdict=CriticVerdict.NEEDS_REVISION,
                score=0.0,
                weaknesses=[f"Analysis failed: {type(e).__name__}: {e}"],
            )

    async def review_skill_proposal(self, proposal: SkillProposal) -> SkillReview:
        """Review a skill proposal and provide feedback."""
        prompt = self.SKILL_REVIEW_PROMPT.format(
            name=proposal.name,
            description=proposal.description,
            trigger_pattern=proposal.trigger_pattern,
            implementation=proposal.implementation,
            examples=json.dumps(proposal.examples, indent=2),
        )

        try:
            response = await self._call_llm(prompt)
            data = self._parse_json_response(response)

            return SkillReview(
                proposal=proposal,
                verdict=CriticVerdict(data.get("verdict", "needs_revision")),
                score=data.get("score", 0.5),
                feedback=data.get("feedback", ""),
                quality_checks=data.get("quality_checks", {}),
                suggested_improvements=data.get("suggested_improvements", []),
                approval_confidence=data.get("approval_confidence", 0.0),
            )

        except Exception as e:
            logger.error(f"Skill review failed: {type(e).__name__}: {e}")
            return SkillReview(
                proposal=proposal,
                verdict=CriticVerdict.NEEDS_REVISION,
                score=0.0,
                feedback=f"Review failed: {type(e).__name__}: {e}",
            )

    def should_auto_approve(self, review: SkillReview) -> bool:
        """Determine if a skill should be auto-approved."""
        return (
            review.verdict == CriticVerdict.APPROVED
            and review.approval_confidence >= self.auto_approve_threshold
            and all(review.quality_checks.values())
        )

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM API."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.llm_api_url}/chat/completions",
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 2048,
                },
                timeout=60.0,
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
