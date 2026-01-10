"""
Pattern Recognition for Continuous Learning.

Provides pattern matching and recognition capabilities
for identifying recurring behaviors and outcomes.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PatternType(str, Enum):
    """Types of patterns that can be recognized."""

    INPUT_OUTPUT = "input_output"  # Input -> Output mapping
    SEQUENCE = "sequence"  # Sequence of actions
    FAILURE = "failure"  # Failure patterns
    RECOVERY = "recovery"  # Recovery patterns
    TEMPORAL = "temporal"  # Time-based patterns


@dataclass
class Pattern:
    """A recognized pattern."""

    id: str
    pattern_type: PatternType
    template: dict[str, Any]
    confidence: float
    occurrences: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class PatternMatcher:
    """
    Matches data against learned patterns.

    Features:
    - Fuzzy matching with confidence scores
    - Template-based pattern recognition
    - Variable extraction from patterns
    """

    def __init__(self):
        self._patterns: list[Pattern] = []

    def add_pattern(self, pattern: Pattern) -> None:
        """Add a pattern to the matcher."""
        self._patterns.append(pattern)

    def match(
        self,
        data: dict[str, Any],
        pattern_type: PatternType | None = None,
        min_confidence: float = 0.5,
    ) -> list[tuple[Pattern, float, dict[str, Any]]]:
        """
        Match data against patterns.

        Args:
            data: Data to match
            pattern_type: Filter by pattern type
            min_confidence: Minimum confidence threshold

        Returns:
            List of (pattern, score, extracted_variables) tuples
        """
        matches = []

        for pattern in self._patterns:
            # Filter by type
            if pattern_type and pattern.pattern_type != pattern_type:
                continue

            # Calculate match score
            score, variables = self._calculate_match_score(data, pattern.template)

            if score >= min_confidence:
                matches.append((pattern, score, variables))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def _calculate_match_score(
        self,
        data: dict[str, Any],
        template: dict[str, Any],
    ) -> tuple[float, dict[str, Any]]:
        """
        Calculate match score between data and template.

        Returns:
            Tuple of (score, extracted_variables)
        """
        if not template:
            return 0.0, {}

        total_fields = len(template)
        matched_fields = 0
        variables = {}

        for key, expected in template.items():
            if key not in data:
                continue

            actual = data[key]

            # Handle variable fields
            if isinstance(expected, dict) and expected.get("_variable"):
                # Variable field - extract value
                expected_type = expected.get("_type", "str")
                if self._check_type(actual, expected_type):
                    matched_fields += 1
                    variables[key] = actual
            elif (
                isinstance(expected, str) and expected.startswith("{{") and expected.endswith("}}")
            ):
                # Template variable
                var_name = expected[2:-2].strip()
                variables[var_name] = actual
                matched_fields += 1
            elif self._values_match(actual, expected):
                matched_fields += 1

        score = matched_fields / total_fields if total_fields > 0 else 0.0
        return score, variables

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        type_map = {
            "str": str,
            "int": int,
            "float": (int, float),
            "bool": bool,
            "list": list,
            "dict": dict,
        }

        expected = type_map.get(expected_type, str)
        return isinstance(value, expected)

    def _values_match(self, actual: Any, expected: Any) -> bool:
        """Check if two values match."""
        if actual == expected:
            return True

        # String pattern matching
        if isinstance(expected, str) and isinstance(actual, str):
            # Check if expected is a regex pattern
            if expected.startswith("^") or expected.endswith("$"):
                try:
                    return bool(re.match(expected, actual))
                except re.error:
                    pass

            # Fuzzy string matching
            return self._fuzzy_match(actual, expected) > 0.8

        # Numeric tolerance
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            tolerance = abs(expected) * 0.1 if expected != 0 else 0.1
            return abs(actual - expected) <= tolerance

        return False

    def _fuzzy_match(self, s1: str, s2: str) -> float:
        """Calculate fuzzy match score between strings."""
        if s1 == s2:
            return 1.0

        # Simple Jaccard similarity on words
        words1 = set(s1.lower().split())
        words2 = set(s2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)

    def find_best_match(
        self,
        data: dict[str, Any],
        pattern_type: PatternType | None = None,
    ) -> tuple[Pattern, float, dict[str, Any]] | None:
        """Find the best matching pattern."""
        matches = self.match(data, pattern_type)
        return matches[0] if matches else None

    def extract_pattern(
        self,
        data_samples: list[dict[str, Any]],
        pattern_type: PatternType = PatternType.INPUT_OUTPUT,
    ) -> Pattern | None:
        """
        Extract a pattern from multiple data samples.

        Args:
            data_samples: List of similar data samples
            pattern_type: Type of pattern to create

        Returns:
            Extracted Pattern or None
        """
        if len(data_samples) < 2:
            return None

        import uuid

        # Find common keys
        common_keys = set(data_samples[0].keys())
        for sample in data_samples[1:]:
            common_keys &= set(sample.keys())

        # Build template
        template = {}
        for key in common_keys:
            values = [sample.get(key) for sample in data_samples]
            unique_values = set(str(v) for v in values)

            if len(unique_values) == 1:
                # Constant value
                template[key] = values[0]
            else:
                # Variable value
                template[key] = {
                    "_variable": True,
                    "_type": type(values[0]).__name__,
                }

        return Pattern(
            id=str(uuid.uuid4()),
            pattern_type=pattern_type,
            template=template,
            confidence=1.0,
            occurrences=len(data_samples),
        )
