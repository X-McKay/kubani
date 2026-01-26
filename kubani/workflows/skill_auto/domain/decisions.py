"""Pure decision functions for the skill_auto workflow.

These functions contain no side effects and can be tested
without any Temporal or external service dependencies.
"""


from .models import ContinueDecision, IterationContext, is_plateau


def should_continue_iteration(ctx: IterationContext) -> tuple[bool, str]:
    """
    Determines if the improvement loop should continue based on the provided context.

    This is a pure function with no side effects. It takes all necessary data
    as input and returns a decision without modifying any state.

    Args:
        ctx: An IterationContext object containing all necessary data for the decision.

    Returns:
        A tuple containing:
        - bool: True to continue, False to stop
        - str: The reason for the decision

    Examples:
        >>> ctx = IterationContext(
        ...     current_iteration=5,
        ...     max_iterations=10,
        ...     best_score=0.8,
        ...     target_accuracy=0.9,
        ...     history=[],
        ...     is_cancelled=False,
        ... )
        >>> should_continue, reason = should_continue_iteration(ctx)
        >>> should_continue
        True
        >>> reason
        'continue_improving'
    """
    # Check cancellation first (highest priority)
    if ctx.is_cancelled:
        return False, "cancelled"

    # Check if we've hit the iteration limit
    if ctx.current_iteration >= ctx.max_iterations:
        return False, "max_iterations_reached"

    # Check if we've met the target accuracy
    if ctx.best_score >= ctx.target_accuracy:
        return False, "target_accuracy_met"

    # Check for plateau (requires enough history)
    if len(ctx.history) >= 3 and is_plateau(ctx.history):
        return False, "score_plateaued"

    return True, "continue_improving"


def make_continue_decision(ctx: IterationContext) -> ContinueDecision:
    """
    Alternative interface that returns a structured decision object.

    This provides the same logic as should_continue_iteration but
    returns a typed dataclass instead of a tuple.

    Args:
        ctx: An IterationContext object containing all necessary data.

    Returns:
        ContinueDecision with should_continue and reason fields.
    """
    should_continue, reason = should_continue_iteration(ctx)
    return ContinueDecision(should_continue=should_continue, reason=reason)


__all__ = [
    "should_continue_iteration",
    "make_continue_decision",
]
