# kubani/workflows/agent_auto/domain/metrics.py
"""Pure functions for calculating evaluation metrics."""



def calculate_skill_precision(invoked: set[str], required: set[str]) -> float:
    """Calculates precision: Of the skills invoked, how many were correct?"""
    if not invoked:
        return 1.0  # By convention, if nothing was invoked, precision is perfect.

    correctly_invoked = invoked.intersection(required)
    return len(correctly_invoked) / len(invoked)


def calculate_skill_recall(invoked: set[str], required: set[str]) -> float:
    """Calculates recall: Of the skills required, how many were invoked?"""
    if not required:
        return 1.0  # If no skills were required, recall is perfect.

    correctly_invoked = invoked.intersection(required)
    return len(correctly_invoked) / len(required)
