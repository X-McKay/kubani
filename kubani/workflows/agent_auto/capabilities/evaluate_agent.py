"""Capability for evaluating agents against test cases."""

from ..models import AgentEvaluationResult, AgentTestCase
from ..protocols import AgentRunner
from .metrics import calculate_skill_precision, calculate_skill_recall


class EvaluationService:
    """Service responsible for evaluating an agent against test cases.

    Runs an agent, captures its outputs and invoked skills, and scores
    its performance using the pure metrics functions.
    """

    def __init__(self, agent_runner: AgentRunner):
        self._runner = agent_runner

    async def evaluate_agent(
        self,
        agent_path: str,
        test_cases: list[AgentTestCase],
    ) -> AgentEvaluationResult:
        """Runs all test cases against the agent and computes metrics.

        Args:
            agent_path: Path to the agent to evaluate.
            test_cases: List of test cases to run.

        Returns:
            AgentEvaluationResult containing accuracy and skill metrics.
        """
        total_invoked: set[str] = set()
        total_required: set[str] = set()
        failures: list[str] = []
        passed_count = 0

        for test in test_cases:
            # The runner would execute the agent in a sandbox and return results
            run_result = await self._runner.run(agent_path, test.prompt)

            required = set(test.expected_skills)
            invoked = set(run_result.invoked_skills)

            total_invoked.update(invoked)
            total_required.update(required)

            # Simple pass/fail based on output match
            if run_result.output.strip() == test.expected_output.strip():
                passed_count += 1
            else:
                failures.append(test.name)

        return AgentEvaluationResult(
            objective_accuracy=passed_count / len(test_cases) if test_cases else 1.0,
            skill_precision=calculate_skill_precision(total_invoked, total_required),
            skill_recall=calculate_skill_recall(total_invoked, total_required),
            invoked_skills=list(total_invoked),
            missing_skills=list(total_required - total_invoked),
            extraneous_skills=list(total_invoked - total_required),
            failures=failures,
        )
