"""
Critic Agent - Evaluates agent execution quality.

The Critic Agent is part of the Voyager-inspired continuous learning system.
It evaluates every agent execution and provides structured feedback including:
- Success/failure analysis
- Improvement identification
- Pattern recognition

Usage:
    from kubani.agents.critic import CriticAgent

    critic = CriticAgent()
    evaluation = await critic.evaluate_execution(execution_record)
"""

import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from kubani.agents._base import KubaniAgent
from kubani.agents.critic.models import (
    CriticEvaluation,
    ExecutionRecord,
)
from kubani.framework.config import get_config
from kubani.framework.llm import get_llm
from kubani.framework.mcp import get_mcp_client

logger = logging.getLogger(__name__)


class ExecutionAnalysis(BaseModel):
    """Structured output from LLM execution analysis."""

    task_completion: float = Field(
        ge=0.0, le=1.0, description="Score for task completion (0.0-1.0)"
    )
    efficiency: float = Field(
        ge=0.0, le=1.0, description="Score for execution efficiency (0.0-1.0)"
    )
    safety: float = Field(
        ge=0.0, le=1.0, description="Score for safety guideline adherence (0.0-1.0)"
    )
    quality: float = Field(
        ge=0.0, le=1.0, description="Score for output quality (0.0-1.0)"
    )
    success: bool = Field(description="Whether the execution was successful overall")
    failure_reason: str | None = Field(
        default=None, description="Reason for failure if not successful"
    )
    improvement_suggestions: list[str] = Field(
        default_factory=list, description="Specific suggestions for improvement"
    )
    identified_patterns: list[str] = Field(
        default_factory=list, description="Reusable patterns identified"
    )
    strengths: list[str] = Field(default_factory=list, description="What went well")
    weaknesses: list[str] = Field(
        default_factory=list, description="What could be better"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in this evaluation (0.0-1.0)"
    )

CRITIC_PROMPT = """You are a Critic Agent in a continuous learning system.

Your role is to evaluate agent executions and provide structured feedback.
You analyze task completions to identify:
1. Whether the task was successfully completed
2. How efficiently it was executed
3. Whether safety guidelines were followed
4. The quality of the output

For each execution, provide scores (0.0-1.0) for:
- task_completion: Did the agent complete the requested task?
- efficiency: Was the execution efficient (minimal steps, good resource usage)?
- safety: Were safety guidelines followed (no dangerous operations)?
- quality: Was the output high quality and useful?

Also identify:
- improvement_suggestions: Specific ways to improve
- identified_patterns: Reusable patterns that could become skills
- strengths: What went well
- weaknesses: What could be better

Be objective and constructive. Focus on actionable feedback.
"""


class CriticAgent(KubaniAgent):
    """
    Evaluates agent executions and provides structured feedback.

    Part of the continuous learning system, the Critic Agent:
    - Evaluates task completion, efficiency, safety, and quality
    - Identifies improvement opportunities
    - Recognizes patterns that could become skills
    - Stores evaluations in shared memory for reflection
    """

    name = "critic"
    description = "Evaluates agent executions and provides learning feedback"
    version = "1.0.0"

    PROMPT_FILE = Path(__file__).parent / "prompt.md"

    def __init__(self):
        """Initialize the Critic Agent."""
        super().__init__()
        self._evaluation_interval_minutes = 60
        self._min_executions = 5

    @property
    def system_prompt(self) -> str:
        """Get the system prompt for the critic agent."""
        if self.PROMPT_FILE.exists():
            return self.PROMPT_FILE.read_text()
        return CRITIC_PROMPT

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("success", False)
        await self.record_outcome(skill_name, result, success=success)

    async def evaluate_execution(
        self,
        execution: ExecutionRecord,
        context: dict[str, Any] | None = None,
    ) -> CriticEvaluation:
        """
        Evaluate a single agent execution.

        Args:
            execution: The execution record to evaluate
            context: Additional context for evaluation

        Returns:
            CriticEvaluation with scores and feedback
        """
        start_time = time.time()

        evaluation = CriticEvaluation(
            execution_id=execution.execution_id,
            agent_id=execution.agent_id,
            task_description=execution.task_description,
            context=context or {},
        )

        try:
            # Use LLM to analyze the execution
            scores = await self._analyze_execution(execution)

            evaluation.task_completion_score = scores.get("task_completion", 0.0)
            evaluation.efficiency_score = scores.get("efficiency", 0.0)
            evaluation.safety_score = scores.get("safety", 0.0)
            evaluation.quality_score = scores.get("quality", 0.0)

            evaluation.success = scores.get("success", False)
            evaluation.failure_reason = scores.get("failure_reason")
            evaluation.improvement_suggestions = scores.get("improvement_suggestions", [])
            evaluation.identified_patterns = scores.get("identified_patterns", [])
            evaluation.strengths = scores.get("strengths", [])
            evaluation.weaknesses = scores.get("weaknesses", [])
            evaluation.confidence = scores.get("confidence", 0.8)

            evaluation.compute_overall_score()

        except Exception as e:
            logger.error(f"Failed to evaluate execution {execution.execution_id}: {e}")
            evaluation.success = False
            evaluation.failure_reason = f"Evaluation failed: {e}"
            evaluation.confidence = 0.0

        evaluation.evaluation_duration_ms = int((time.time() - start_time) * 1000)

        # Store the evaluation
        await self._store_evaluation(evaluation)

        return evaluation

    async def _analyze_execution(self, execution: ExecutionRecord) -> dict[str, Any]:
        """Use LLM to analyze an execution and return scores."""
        llm = get_llm()

        # Build detailed analysis prompt with execution context
        tool_calls_summary = ""
        if execution.tool_calls:
            tool_calls_summary = "\n".join(
                f"  - {tc.get('name', 'unknown')}: {tc.get('result', 'no result')[:100]}"
                for tc in execution.tool_calls[:10]  # Limit to first 10
            )
            if len(execution.tool_calls) > 10:
                tool_calls_summary += f"\n  ... and {len(execution.tool_calls) - 10} more"

        errors_summary = ""
        if execution.errors:
            errors_summary = "\n".join(f"  - {err}" for err in execution.errors[:5])
            if len(execution.errors) > 5:
                errors_summary += f"\n  ... and {len(execution.errors) - 5} more"

        prompt = f"""Analyze this agent execution and provide evaluation scores.

## Execution Details

**Agent:** {execution.agent_id}
**Task:** {execution.task_description}
**Duration:** {execution.duration_ms}ms
**Reported Success:** {execution.success}
**Result Summary:** {execution.result_summary or 'No summary provided'}

**Tool Calls ({len(execution.tool_calls)} total):**
{tool_calls_summary if tool_calls_summary else '  None'}

**Errors ({len(execution.errors)} total):**
{errors_summary if errors_summary else '  None'}

## Evaluation Guidelines

Score each criterion from 0.0 to 1.0:

1. **task_completion**: Did the agent fully complete the requested task?
   - 1.0 = Fully completed, all objectives met
   - 0.7-0.9 = Mostly complete, minor gaps
   - 0.4-0.6 = Partially complete
   - 0.0-0.3 = Failed or barely started

2. **efficiency**: Was the execution efficient?
   - Consider: execution time, number of tool calls, resource usage
   - Fewer unnecessary steps = higher score
   - Duration benchmark: <30s excellent, <60s good, >120s needs improvement

3. **safety**: Were safety guidelines followed?
   - No dangerous operations, proper error handling
   - Sensitive data handled appropriately
   - 1.0 if no safety concerns, lower if risky operations detected

4. **quality**: Was the output high quality?
   - Accuracy, completeness, usefulness of results
   - Clean, well-structured output

Be objective and base your evaluation on the evidence provided. If the execution clearly succeeded with good results, reflect that in your scores. If there were failures or issues, identify specific improvements."""

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            # Use structured output for reliable parsing
            analysis = await llm.chat_structured(messages, ExecutionAnalysis)
            return analysis.model_dump()
        except Exception as e:
            logger.warning(f"LLM analysis failed, falling back to heuristics: {e}")
            return self._heuristic_analysis(execution)

    def _heuristic_analysis(self, execution: ExecutionRecord) -> dict[str, Any]:
        """Provide heuristic-based analysis when LLM is not available."""
        # Base scores on execution outcome
        task_completion = 0.9 if execution.success else 0.3
        efficiency = min(1.0, 30000 / max(execution.duration_ms, 1000))  # Faster is better
        safety = 1.0 if not execution.errors else 0.7
        quality = 0.8 if execution.success else 0.4

        improvement_suggestions = []
        patterns = []
        strengths = []
        weaknesses = []

        if not execution.success:
            improvement_suggestions.append("Investigate failure cause and add error handling")
            weaknesses.append("Task did not complete successfully")
        else:
            strengths.append("Task completed successfully")

        if execution.duration_ms > 60000:
            improvement_suggestions.append("Consider optimizing for faster execution")
            weaknesses.append("Execution took longer than expected")
        else:
            strengths.append("Execution completed in reasonable time")

        if execution.errors:
            improvement_suggestions.append(f"Address {len(execution.errors)} errors encountered")
            weaknesses.append("Errors occurred during execution")

        if len(execution.tool_calls) > 10:
            improvement_suggestions.append("Consider consolidating tool calls")
        elif execution.tool_calls:
            patterns.append(f"Used {len(execution.tool_calls)} tool calls effectively")

        return {
            "task_completion": task_completion,
            "efficiency": efficiency,
            "safety": safety,
            "quality": quality,
            "success": execution.success,
            "failure_reason": execution.errors[0] if execution.errors else None,
            "improvement_suggestions": improvement_suggestions,
            "identified_patterns": patterns,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "confidence": 0.7,  # Lower confidence for heuristic analysis
        }

    async def _store_evaluation(self, evaluation: CriticEvaluation) -> None:
        """Store evaluation in shared memory."""
        try:
            client = get_mcp_client()
            config = get_config()

            if not config.mcp.memory_enabled:
                logger.debug("Memory MCP not enabled, skipping evaluation storage")
                return

            await client.memory.store_learning(
                agent_id=self.name,
                learning_type="evaluation",
                content=f"Evaluated {evaluation.agent_id}: score={evaluation.overall_score:.2f}",
                confidence=evaluation.confidence,
                context=evaluation.to_dict(),
            )

            logger.info(
                f"Stored evaluation for {evaluation.agent_id}: "
                f"score={evaluation.overall_score:.2f}, success={evaluation.success}"
            )

        except Exception as e:
            logger.warning(f"Failed to store evaluation: {e}")

    async def evaluate_recent_executions(
        self,
        hours: int = 1,
        agent_id: str | None = None,
    ) -> list[CriticEvaluation]:
        """
        Evaluate recent agent executions.

        Args:
            hours: Number of hours to look back
            agent_id: Optional filter for specific agent

        Returns:
            List of evaluations
        """
        try:
            client = get_mcp_client()
            config = get_config()

            if not config.mcp.memory_enabled:
                logger.debug("Memory MCP not enabled")
                return []

            # Query recent executions from memory
            executions = await client.memory.query_learnings(
                query="agent execution",
                agent_id=agent_id,
                learning_type="execution",
                min_confidence=0.0,
                limit=100,
            )

            # Filter by time
            cutoff = datetime.now(UTC) - timedelta(hours=hours)
            recent = [e for e in executions if e.get("timestamp", datetime.min) > cutoff]

            # Evaluate each
            evaluations = []
            for exec_data in recent:
                record = ExecutionRecord(
                    execution_id=exec_data.get("execution_id", "unknown"),
                    agent_id=exec_data.get("agent_id", "unknown"),
                    task_description=exec_data.get("task_description", ""),
                    start_time=exec_data.get("start_time", datetime.now(UTC)),
                    success=exec_data.get("success", False),
                    result_summary=exec_data.get("result_summary", ""),
                )
                evaluation = await self.evaluate_execution(record)
                evaluations.append(evaluation)

                # Trigger learning if there's an improvement opportunity
                if evaluation.has_improvement_opportunity:
                    await self._trigger_learning(evaluation)

            return evaluations

        except Exception as e:
            logger.error(f"Failed to evaluate recent executions: {e}")
            return []

    async def _trigger_learning(self, evaluation: CriticEvaluation) -> None:
        """Trigger learning cycle for evaluations with improvement opportunities."""
        try:
            client = get_mcp_client()
            config = get_config()

            if not config.mcp.memory_enabled:
                return

            # Store as a learning opportunity
            await client.memory.store_learning(
                agent_id=self.name,
                learning_type="improvement_opportunity",
                content=f"Improvement opportunity for {evaluation.agent_id}",
                confidence=evaluation.confidence,
                context={
                    "evaluation_id": evaluation.evaluation_id,
                    "suggestions": evaluation.improvement_suggestions,
                    "patterns": evaluation.identified_patterns,
                    "weaknesses": evaluation.weaknesses,
                },
            )

            logger.info(f"Triggered learning for evaluation {evaluation.evaluation_id}")

        except Exception as e:
            logger.warning(f"Failed to trigger learning: {e}")
