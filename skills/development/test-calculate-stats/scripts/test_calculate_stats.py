#!/usr/bin/env python3
"""Script for test-calculate-stats skill."""

from typing import Any, Dict, List, Optional, Union


def execute(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the test-calculate-stats operation.

    Args:
        inputs: Dictionary with input parameters

    Returns:
        Dictionary with operation results
    """
    try:
        # Extract the list of numbers from inputs
        numbers: Optional[List[float]] = inputs.get("numbers")

        if not numbers or not isinstance(numbers, list):
            raise ValueError("Input 'numbers' is not a valid list of numbers.")

        if not numbers:
            return {"result": {"mean": None, "median": None, "std_dev": None}, "success": True}

        # Calculate mean
        mean: float = sum(numbers) / len(numbers)

        # Calculate median
        sorted_numbers = sorted(numbers)
        n: int = len(sorted_numbers)
        mid: int = n // 2
        if n % 2 == 1:
            median: float = sorted_numbers[mid]
        else:
            median: float = (sorted_numbers[mid - 1] + sorted_numbers[mid]) / 2

        # Calculate standard deviation
        if n == 1:
            std_dev: float = 0.0
        else:
            variance = sum((x - mean) ** 2 for x in numbers) / (n - 1)
            std_dev = variance ** 0.5

        result: Dict[str, Union[float, None]] = {
            "mean": mean,
            "median": median,
            "std_dev": std_dev
        }

        return {"result": result, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) > 1:
        inputs = json.loads(sys.argv[1])
    else:
        inputs = {}

    result = execute(inputs)
    print(json.dumps(result, indent=2))