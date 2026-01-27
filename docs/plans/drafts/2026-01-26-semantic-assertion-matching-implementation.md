# Semantic Assertion Matching Implementation Plan

**Status:** Draft
**Created:** 2026-01-26
**Author:** Claude Code
**Related:** [Idea Document](../ideas/2026-01-26-semantic-assertion-matching.md)

## Overview

Implement semantic assertion matching for skill evaluation, replacing rigid exact string matching with LLM-based semantic judgment as the default, while preserving exact matching for specific use cases.

## Goals

1. Skills with semantically correct output achieve realistic accuracy scores
2. Improvement loops can converge (no more 0% → 0% → 0% → plateau)
3. Maintain fast evaluation for exact-match cases
4. Backward compatible with existing test cases

## Non-Goals

- Changing how skills are executed (only assertion checking changes)
- Modifying the critic evaluation system
- Automatic migration of all existing test cases

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SkillEvaluatorLLM                        │
├─────────────────────────────────────────────────────────────┤
│  evaluate_skill()                                           │
│    └─ _run_test_case()                                      │
│         └─ AssertionRouter.check_assertions()  ◄── NEW      │
│              ├─ SemanticChecker (default)      ◄── NEW      │
│              ├─ ExactChecker                                │
│              ├─ ContainsChecker                             │
│              ├─ RegexChecker                   ◄── NEW      │
│              └─ NumericChecker                 ◄── NEW      │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1: Add Assertion Checker Infrastructure

**Files to create:**
- `platform/cli/src/kubani_dev/assertion_checkers/__init__.py`
- `platform/cli/src/kubani_dev/assertion_checkers/base.py`
- `platform/cli/src/kubani_dev/assertion_checkers/semantic.py`
- `platform/cli/src/kubani_dev/assertion_checkers/exact.py`
- `platform/cli/src/kubani_dev/assertion_checkers/router.py`

**Files to modify:**
- `platform/cli/src/kubani_dev/skill_evaluator_llm.py`

#### Task 1.1: Create Base Types

```python
# platform/cli/src/kubani_dev/assertion_checkers/base.py

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class AssertionResult:
    """Result of checking an assertion."""
    passed: bool
    confidence: float = 1.0  # 1.0 for exact matches, 0.0-1.0 for semantic
    actual: Any = None
    expected: Any = None
    reasoning: str | None = None
    assertion_type: str = "unknown"
    field: str | None = None
    description: str = ""


class AssertionChecker(Protocol):
    """Protocol for assertion checkers."""

    def check(
        self,
        actual: Any,
        expected: Any,
        context: dict[str, Any] | None = None,
    ) -> AssertionResult:
        """Check if actual matches expected."""
        ...


@dataclass
class AssertionSpec:
    """Specification for an assertion from test case."""
    type: str = "semantic"  # semantic, exact, contains, regex, numeric
    field: str | None = None
    expected: Any = None
    value: Any = None  # Alias for expected (backward compat)
    description: str = ""
    tolerance: float | None = None  # For numeric comparisons
    case_sensitive: bool = True  # For string comparisons
    confidence_threshold: float = 0.7  # For semantic matches

    def get_expected(self) -> Any:
        """Get expected value, handling backward compat."""
        return self.expected if self.expected is not None else self.value
```

#### Task 1.2: Implement Exact Checkers

```python
# platform/cli/src/kubani_dev/assertion_checkers/exact.py

from typing import Any
import re

from .base import AssertionChecker, AssertionResult


class ExactChecker(AssertionChecker):
    """Check for exact equality."""

    def check(
        self,
        actual: Any,
        expected: Any,
        context: dict[str, Any] | None = None,
    ) -> AssertionResult:
        passed = actual == expected
        return AssertionResult(
            passed=passed,
            confidence=1.0 if passed else 0.0,
            actual=actual,
            expected=expected,
            assertion_type="exact",
        )


class ContainsChecker(AssertionChecker):
    """Check if actual contains expected."""

    def check(
        self,
        actual: Any,
        expected: Any,
        context: dict[str, Any] | None = None,
    ) -> AssertionResult:
        case_sensitive = context.get("case_sensitive", True) if context else True

        if isinstance(actual, str) and isinstance(expected, str):
            if case_sensitive:
                passed = expected in actual
            else:
                passed = expected.lower() in actual.lower()
        elif isinstance(actual, (list, dict)):
            passed = expected in actual
        else:
            passed = False

        return AssertionResult(
            passed=passed,
            confidence=1.0 if passed else 0.0,
            actual=actual,
            expected=expected,
            assertion_type="contains",
        )


class RegexChecker(AssertionChecker):
    """Check if actual matches regex pattern."""

    def check(
        self,
        actual: Any,
        expected: Any,
        context: dict[str, Any] | None = None,
    ) -> AssertionResult:
        if not isinstance(actual, str):
            actual = str(actual) if actual is not None else ""

        try:
            pattern = re.compile(expected)
            match = pattern.search(actual)
            passed = match is not None
        except re.error:
            passed = False

        return AssertionResult(
            passed=passed,
            confidence=1.0 if passed else 0.0,
            actual=actual,
            expected=f"regex: {expected}",
            assertion_type="regex",
        )


class NumericChecker(AssertionChecker):
    """Check numeric values with optional tolerance."""

    def check(
        self,
        actual: Any,
        expected: Any,
        context: dict[str, Any] | None = None,
    ) -> AssertionResult:
        tolerance = context.get("tolerance", 0.0) if context else 0.0

        try:
            actual_num = float(actual)
            expected_num = float(expected)
            diff = abs(actual_num - expected_num)
            passed = diff <= tolerance
            confidence = 1.0 - (diff / max(abs(expected_num), 1.0)) if passed else 0.0
        except (TypeError, ValueError):
            passed = False
            confidence = 0.0

        return AssertionResult(
            passed=passed,
            confidence=max(0.0, min(1.0, confidence)),
            actual=actual,
            expected=expected,
            assertion_type="numeric",
            reasoning=f"tolerance: {tolerance}" if tolerance > 0 else None,
        )


class ExistsChecker(AssertionChecker):
    """Check if field exists in output."""

    def check(
        self,
        actual: Any,
        expected: Any,
        context: dict[str, Any] | None = None,
    ) -> AssertionResult:
        # actual is the value at the field, None if field doesn't exist
        # context should contain "field_exists" bool
        field_exists = context.get("field_exists", actual is not None) if context else actual is not None

        return AssertionResult(
            passed=field_exists,
            confidence=1.0 if field_exists else 0.0,
            actual="exists" if field_exists else "missing",
            expected="exists",
            assertion_type="exists",
        )


class NotEmptyChecker(AssertionChecker):
    """Check if value is not empty."""

    def check(
        self,
        actual: Any,
        expected: Any,
        context: dict[str, Any] | None = None,
    ) -> AssertionResult:
        passed = bool(actual)
        return AssertionResult(
            passed=passed,
            confidence=1.0 if passed else 0.0,
            actual=actual,
            expected="non-empty value",
            assertion_type="not_empty",
        )
```

#### Task 1.3: Implement Semantic Checker

```python
# platform/cli/src/kubani_dev/assertion_checkers/semantic.py

from typing import Any
import json
import logging

from kubani_dev.llm_client import LLMClient
from .base import AssertionChecker, AssertionResult

logger = logging.getLogger(__name__)

SEMANTIC_JUDGE_PROMPT = """You are evaluating if an LLM's actual output semantically matches the expected output.

Expected output: {expected}
Actual output: {actual}

Context (if any): {context}

Judge if the actual output conveys the same meaning as the expected output.
- Minor wording differences are OK (e.g., "auth error" vs "authentication failure")
- Different structure is OK if meaning is preserved
- Missing critical information should fail
- Extra information is OK if core meaning matches

Respond with JSON only:
{{
  "matches": true or false,
  "confidence": 0.0 to 1.0,
  "reasoning": "brief explanation"
}}"""


class SemanticChecker(AssertionChecker):
    """Use LLM to judge semantic equivalence."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def check(
        self,
        actual: Any,
        expected: Any,
        context: dict[str, Any] | None = None,
    ) -> AssertionResult:
        # Handle None/empty cases
        if actual is None and expected is None:
            return AssertionResult(
                passed=True,
                confidence=1.0,
                actual=actual,
                expected=expected,
                assertion_type="semantic",
                reasoning="Both are None",
            )

        if actual is None or expected is None:
            return AssertionResult(
                passed=False,
                confidence=1.0,
                actual=actual,
                expected=expected,
                assertion_type="semantic",
                reasoning="One value is None",
            )

        # Convert to strings for comparison
        actual_str = json.dumps(actual) if isinstance(actual, (dict, list)) else str(actual)
        expected_str = json.dumps(expected) if isinstance(expected, (dict, list)) else str(expected)

        # Quick exact match check first
        if actual_str.strip().lower() == expected_str.strip().lower():
            return AssertionResult(
                passed=True,
                confidence=1.0,
                actual=actual,
                expected=expected,
                assertion_type="semantic",
                reasoning="Exact match (case-insensitive)",
            )

        # Use LLM for semantic comparison
        try:
            prompt = SEMANTIC_JUDGE_PROMPT.format(
                expected=expected_str,
                actual=actual_str,
                context=json.dumps(context) if context else "None",
            )

            response = self.llm.complete(prompt, timeout=30)
            result = self._parse_response(response)

            confidence_threshold = context.get("confidence_threshold", 0.7) if context else 0.7

            return AssertionResult(
                passed=result["matches"] and result["confidence"] >= confidence_threshold,
                confidence=result["confidence"],
                actual=actual,
                expected=expected,
                assertion_type="semantic",
                reasoning=result["reasoning"],
            )

        except Exception as e:
            logger.warning(f"Semantic check failed, falling back to exact: {e}")
            # Fallback to exact match on error
            passed = actual_str.strip() == expected_str.strip()
            return AssertionResult(
                passed=passed,
                confidence=1.0 if passed else 0.0,
                actual=actual,
                expected=expected,
                assertion_type="semantic",
                reasoning=f"Fallback to exact match (error: {e})",
            )

    def _parse_response(self, response: str) -> dict[str, Any]:
        """Parse LLM response JSON."""
        # Try to extract JSON from response
        response = response.strip()

        # Remove markdown code blocks if present
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        try:
            result = json.loads(response)
            return {
                "matches": bool(result.get("matches", False)),
                "confidence": float(result.get("confidence", 0.0)),
                "reasoning": str(result.get("reasoning", "")),
            }
        except json.JSONDecodeError:
            # Try to extract boolean from response
            lower = response.lower()
            matches = "true" in lower or "yes" in lower or "match" in lower
            return {
                "matches": matches,
                "confidence": 0.5,
                "reasoning": f"Parsed from non-JSON response: {response[:100]}",
            }
```

#### Task 1.4: Implement Assertion Router

```python
# platform/cli/src/kubani_dev/assertion_checkers/router.py

from typing import Any
import logging

from kubani_dev.llm_client import LLMClient
from .base import AssertionResult, AssertionSpec
from .exact import (
    ExactChecker,
    ContainsChecker,
    RegexChecker,
    NumericChecker,
    ExistsChecker,
    NotEmptyChecker,
)
from .semantic import SemanticChecker

logger = logging.getLogger(__name__)


def get_nested_value(obj: dict, field: str) -> tuple[Any, bool]:
    """
    Get nested value from dict using dot notation.

    Returns (value, exists) tuple.
    """
    if not field:
        return obj, True

    parts = field.split(".")
    current = obj

    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None, False

    return current, True


class AssertionRouter:
    """Routes assertions to appropriate checkers."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        default_type: str = "semantic",
    ):
        """
        Initialize router.

        Args:
            llm_client: LLM client for semantic checks (required if using semantic)
            default_type: Default assertion type when not specified
        """
        self.default_type = default_type
        self.llm_client = llm_client

        # Initialize non-LLM checkers
        self._checkers = {
            "exact": ExactChecker(),
            "equals": ExactChecker(),  # Alias
            "contains": ContainsChecker(),
            "regex": RegexChecker(),
            "numeric": NumericChecker(),
            "exists": ExistsChecker(),
            "not_empty": NotEmptyChecker(),
            "greater_than": NumericChecker(),  # Handled specially
            "less_than": NumericChecker(),  # Handled specially
            "length": NumericChecker(),  # Handled specially
            "type": ExactChecker(),  # Handled specially
        }

        # Semantic checker (lazy init)
        self._semantic_checker: SemanticChecker | None = None

    @property
    def semantic_checker(self) -> SemanticChecker:
        """Get or create semantic checker."""
        if self._semantic_checker is None:
            if self.llm_client is None:
                raise ValueError("LLM client required for semantic assertions")
            self._semantic_checker = SemanticChecker(self.llm_client)
        return self._semantic_checker

    def check_assertion(
        self,
        output: dict[str, Any],
        assertion_spec: dict[str, Any],
        expected_output: dict[str, Any] | None = None,
    ) -> AssertionResult:
        """
        Check a single assertion against output.

        Args:
            output: The actual output from skill execution
            assertion_spec: Assertion specification dict
            expected_output: Expected output section (for fallback values)

        Returns:
            AssertionResult with pass/fail and details
        """
        # Parse assertion spec
        assertion_type = assertion_spec.get("type", self.default_type)
        field = assertion_spec.get("field")

        # Get expected value (from assertion or expected_output)
        expected = assertion_spec.get("expected") or assertion_spec.get("value")
        if expected is None and expected_output and field:
            expected = get_nested_value(expected_output, field)[0]

        # Get actual value
        if field:
            actual, field_exists = get_nested_value(output, field)
        else:
            actual, field_exists = output, True

        # Build context
        context = {
            "field": field,
            "field_exists": field_exists,
            "case_sensitive": assertion_spec.get("case_sensitive", True),
            "tolerance": assertion_spec.get("tolerance", 0.0),
            "confidence_threshold": assertion_spec.get("confidence_threshold", 0.7),
        }

        # Handle special assertion types
        if assertion_type == "expect_error":
            # This is handled separately by the evaluator
            return AssertionResult(
                passed=False,
                assertion_type="expect_error",
                reasoning="expect_error handled by evaluator",
            )

        if assertion_type == "greater_than":
            context["tolerance"] = 0.0
            result = self._checkers["numeric"].check(actual, expected, context)
            result.passed = isinstance(actual, (int, float)) and actual > expected
            return result

        if assertion_type == "less_than":
            context["tolerance"] = 0.0
            result = self._checkers["numeric"].check(actual, expected, context)
            result.passed = isinstance(actual, (int, float)) and actual < expected
            return result

        if assertion_type == "length":
            actual_len = len(actual) if hasattr(actual, "__len__") else 0
            return self._checkers["numeric"].check(actual_len, expected, context)

        if assertion_type == "type":
            type_map = {
                "string": str,
                "number": (int, float),
                "boolean": bool,
                "list": list,
                "dict": dict,
            }
            expected_type = type_map.get(expected, str)
            passed = isinstance(actual, expected_type)
            return AssertionResult(
                passed=passed,
                confidence=1.0 if passed else 0.0,
                actual=type(actual).__name__,
                expected=expected,
                assertion_type="type",
            )

        # Route to appropriate checker
        if assertion_type == "semantic":
            checker = self.semantic_checker
        elif assertion_type in self._checkers:
            checker = self._checkers[assertion_type]
        else:
            logger.warning(f"Unknown assertion type '{assertion_type}', using semantic")
            checker = self.semantic_checker

        result = checker.check(actual, expected, context)
        result.field = field
        result.description = assertion_spec.get(
            "description",
            f"{field} {assertion_type} {expected}"
        )

        return result

    def check_assertions(
        self,
        output: dict[str, Any],
        assertions: list[dict[str, Any]],
        expected_output: dict[str, Any] | None = None,
    ) -> list[AssertionResult]:
        """
        Check multiple assertions.

        Args:
            output: The actual output from skill execution
            assertions: List of assertion specifications
            expected_output: Expected output section

        Returns:
            List of AssertionResults
        """
        results = []
        for assertion_spec in assertions:
            result = self.check_assertion(output, assertion_spec, expected_output)
            results.append(result)
        return results
```

#### Task 1.5: Create Package Init

```python
# platform/cli/src/kubani_dev/assertion_checkers/__init__.py

from .base import AssertionResult, AssertionSpec, AssertionChecker
from .exact import (
    ExactChecker,
    ContainsChecker,
    RegexChecker,
    NumericChecker,
    ExistsChecker,
    NotEmptyChecker,
)
from .semantic import SemanticChecker
from .router import AssertionRouter, get_nested_value

__all__ = [
    "AssertionResult",
    "AssertionSpec",
    "AssertionChecker",
    "ExactChecker",
    "ContainsChecker",
    "RegexChecker",
    "NumericChecker",
    "ExistsChecker",
    "NotEmptyChecker",
    "SemanticChecker",
    "AssertionRouter",
    "get_nested_value",
]
```

### Phase 2: Integrate with Evaluator

**Files to modify:**
- `platform/cli/src/kubani_dev/skill_evaluator_llm.py`

#### Task 2.1: Update SkillEvaluatorLLM

Replace `_check_assertion` method with `AssertionRouter`:

```python
# In skill_evaluator_llm.py

from kubani_dev.assertion_checkers import AssertionRouter

class SkillEvaluatorLLM:
    def __init__(self, llm_client: LLMClient, default_assertion_type: str = "semantic"):
        self.llm = llm_client
        self.assertion_router = AssertionRouter(
            llm_client=llm_client,
            default_type=default_assertion_type,
        )

    def _run_test_case(self, ...):
        # ... existing code ...

        # Replace assertion checking loop with:
        assertion_results = self.assertion_router.check_assertions(
            output=output,
            assertions=test_case.get("assertions", []),
            expected_output=test_case.get("expected", {}),
        )

        # Convert to dict format for backward compatibility
        assertions = [
            {
                "type": r.assertion_type,
                "field": r.field,
                "expected": r.expected,
                "actual": r.actual,
                "passed": r.passed,
                "confidence": r.confidence,
                "reasoning": r.reasoning,
                "description": r.description,
            }
            for r in assertion_results
        ]

        # ... rest of existing code ...
```

#### Task 2.2: Add Configuration Support

```python
# In skill_evaluator_llm.py

class SkillEvaluatorLLM:
    def __init__(
        self,
        llm_client: LLMClient,
        default_assertion_type: str = "semantic",
        semantic_confidence_threshold: float = 0.7,
    ):
        self.llm = llm_client
        self.default_assertion_type = default_assertion_type
        self.semantic_confidence_threshold = semantic_confidence_threshold
        self.assertion_router = AssertionRouter(
            llm_client=llm_client,
            default_type=default_assertion_type,
        )
```

### Phase 3: Add Batch Optimization

**Files to modify:**
- `platform/cli/src/kubani_dev/assertion_checkers/semantic.py`
- `platform/cli/src/kubani_dev/assertion_checkers/router.py`

#### Task 3.1: Add Batch Semantic Checking

```python
# In semantic.py

BATCH_SEMANTIC_PROMPT = """You are evaluating if multiple LLM outputs semantically match their expected values.

For each item, judge if the actual output conveys the same meaning as expected.
Minor wording differences are OK. Missing critical information should fail.

Items to evaluate:
{items}

Respond with JSON array:
[
  {{"index": 0, "matches": true/false, "confidence": 0.0-1.0, "reasoning": "..."}},
  ...
]"""


class SemanticChecker(AssertionChecker):
    # ... existing code ...

    def check_batch(
        self,
        items: list[tuple[Any, Any, dict[str, Any] | None]],
    ) -> list[AssertionResult]:
        """
        Check multiple assertions in a single LLM call.

        Args:
            items: List of (actual, expected, context) tuples

        Returns:
            List of AssertionResults
        """
        if not items:
            return []

        # Build prompt
        items_text = ""
        for i, (actual, expected, context) in enumerate(items):
            actual_str = json.dumps(actual) if isinstance(actual, (dict, list)) else str(actual)
            expected_str = json.dumps(expected) if isinstance(expected, (dict, list)) else str(expected)
            items_text += f"\n{i}. Expected: {expected_str}\n   Actual: {actual_str}\n"

        prompt = BATCH_SEMANTIC_PROMPT.format(items=items_text)

        try:
            response = self.llm.complete(prompt, timeout=60)
            results = self._parse_batch_response(response, len(items))

            return [
                AssertionResult(
                    passed=r["matches"] and r["confidence"] >= (items[i][2] or {}).get("confidence_threshold", 0.7),
                    confidence=r["confidence"],
                    actual=items[i][0],
                    expected=items[i][1],
                    assertion_type="semantic",
                    reasoning=r["reasoning"],
                )
                for i, r in enumerate(results)
            ]

        except Exception as e:
            logger.warning(f"Batch semantic check failed: {e}")
            # Fallback to individual checks
            return [self.check(actual, expected, context) for actual, expected, context in items]

    def _parse_batch_response(self, response: str, expected_count: int) -> list[dict]:
        """Parse batch response JSON array."""
        # ... implementation ...
```

#### Task 3.2: Update Router for Batching

```python
# In router.py

class AssertionRouter:
    def __init__(self, ..., batch_semantic: bool = True, batch_size: int = 5):
        self.batch_semantic = batch_semantic
        self.batch_size = batch_size
        # ... existing init ...

    def check_assertions(
        self,
        output: dict[str, Any],
        assertions: list[dict[str, Any]],
        expected_output: dict[str, Any] | None = None,
    ) -> list[AssertionResult]:
        """Check multiple assertions with batching."""

        # Separate semantic vs non-semantic assertions
        semantic_indices = []
        non_semantic_results = {}

        for i, assertion_spec in enumerate(assertions):
            assertion_type = assertion_spec.get("type", self.default_type)
            if assertion_type == "semantic" and self.batch_semantic:
                semantic_indices.append(i)
            else:
                result = self.check_assertion(output, assertion_spec, expected_output)
                non_semantic_results[i] = result

        # Batch process semantic assertions
        if semantic_indices and self.batch_semantic:
            semantic_items = []
            for i in semantic_indices:
                spec = assertions[i]
                field = spec.get("field")
                expected = spec.get("expected") or spec.get("value")
                if expected is None and expected_output and field:
                    expected = get_nested_value(expected_output, field)[0]
                actual = get_nested_value(output, field)[0] if field else output
                context = {"confidence_threshold": spec.get("confidence_threshold", 0.7)}
                semantic_items.append((actual, expected, context))

            # Process in batches
            semantic_results = []
            for batch_start in range(0, len(semantic_items), self.batch_size):
                batch = semantic_items[batch_start:batch_start + self.batch_size]
                batch_results = self.semantic_checker.check_batch(batch)
                semantic_results.extend(batch_results)

            # Add descriptions and fields
            for j, i in enumerate(semantic_indices):
                semantic_results[j].field = assertions[i].get("field")
                semantic_results[j].description = assertions[i].get(
                    "description",
                    f"{assertions[i].get('field')} semantic match"
                )
                non_semantic_results[i] = semantic_results[j]

        # Reconstruct ordered results
        return [non_semantic_results[i] for i in range(len(assertions))]
```

### Phase 4: Testing

**Files to create:**
- `platform/cli/tests/assertion_checkers/__init__.py`
- `platform/cli/tests/assertion_checkers/test_exact.py`
- `platform/cli/tests/assertion_checkers/test_semantic.py`
- `platform/cli/tests/assertion_checkers/test_router.py`

#### Task 4.1: Test Exact Checkers

```python
# platform/cli/tests/assertion_checkers/test_exact.py

import pytest
from kubani_dev.assertion_checkers import (
    ExactChecker,
    ContainsChecker,
    RegexChecker,
    NumericChecker,
)


class TestExactChecker:
    def test_exact_match(self):
        checker = ExactChecker()
        result = checker.check("hello", "hello")
        assert result.passed is True
        assert result.confidence == 1.0

    def test_exact_mismatch(self):
        checker = ExactChecker()
        result = checker.check("hello", "world")
        assert result.passed is False


class TestContainsChecker:
    def test_contains_substring(self):
        checker = ContainsChecker()
        result = checker.check("hello world", "world")
        assert result.passed is True

    def test_case_insensitive(self):
        checker = ContainsChecker()
        result = checker.check("Hello World", "world", {"case_sensitive": False})
        assert result.passed is True


class TestRegexChecker:
    def test_regex_match(self):
        checker = RegexChecker()
        result = checker.check("error-123", r"error-\d+")
        assert result.passed is True

    def test_regex_no_match(self):
        checker = RegexChecker()
        result = checker.check("warning-abc", r"error-\d+")
        assert result.passed is False


class TestNumericChecker:
    def test_exact_numeric(self):
        checker = NumericChecker()
        result = checker.check(42, 42)
        assert result.passed is True

    def test_within_tolerance(self):
        checker = NumericChecker()
        result = checker.check(42.5, 42, {"tolerance": 1.0})
        assert result.passed is True

    def test_outside_tolerance(self):
        checker = NumericChecker()
        result = checker.check(44, 42, {"tolerance": 1.0})
        assert result.passed is False
```

#### Task 4.2: Test Semantic Checker

```python
# platform/cli/tests/assertion_checkers/test_semantic.py

import pytest
from unittest.mock import Mock, MagicMock

from kubani_dev.assertion_checkers import SemanticChecker


class TestSemanticChecker:
    @pytest.fixture
    def mock_llm(self):
        llm = Mock()
        llm.complete = MagicMock()
        return llm

    def test_exact_match_shortcut(self, mock_llm):
        """Exact matches should skip LLM call."""
        checker = SemanticChecker(mock_llm)
        result = checker.check("auth failure", "auth failure")
        assert result.passed is True
        assert result.confidence == 1.0
        mock_llm.complete.assert_not_called()

    def test_semantic_match(self, mock_llm):
        mock_llm.complete.return_value = '{"matches": true, "confidence": 0.9, "reasoning": "Same meaning"}'
        checker = SemanticChecker(mock_llm)
        result = checker.check("authentication error", "auth failure")
        assert result.passed is True
        assert result.confidence == 0.9

    def test_semantic_mismatch(self, mock_llm):
        mock_llm.complete.return_value = '{"matches": false, "confidence": 0.2, "reasoning": "Different meaning"}'
        checker = SemanticChecker(mock_llm)
        result = checker.check("network timeout", "auth failure")
        assert result.passed is False

    def test_confidence_threshold(self, mock_llm):
        mock_llm.complete.return_value = '{"matches": true, "confidence": 0.5, "reasoning": "Partial match"}'
        checker = SemanticChecker(mock_llm)
        result = checker.check("auth issue", "auth failure", {"confidence_threshold": 0.7})
        assert result.passed is False  # Below threshold
```

#### Task 4.3: Test Router

```python
# platform/cli/tests/assertion_checkers/test_router.py

import pytest
from unittest.mock import Mock

from kubani_dev.assertion_checkers import AssertionRouter, get_nested_value


class TestGetNestedValue:
    def test_simple_field(self):
        obj = {"name": "test"}
        value, exists = get_nested_value(obj, "name")
        assert value == "test"
        assert exists is True

    def test_nested_field(self):
        obj = {"root": {"nested": {"deep": "value"}}}
        value, exists = get_nested_value(obj, "root.nested.deep")
        assert value == "value"
        assert exists is True

    def test_missing_field(self):
        obj = {"name": "test"}
        value, exists = get_nested_value(obj, "missing")
        assert value is None
        assert exists is False


class TestAssertionRouter:
    @pytest.fixture
    def mock_llm(self):
        llm = Mock()
        llm.complete = Mock(return_value='{"matches": true, "confidence": 0.9, "reasoning": "ok"}')
        return llm

    def test_routes_to_exact(self, mock_llm):
        router = AssertionRouter(llm_client=mock_llm, default_type="exact")
        result = router.check_assertion(
            output={"status": "ok"},
            assertion_spec={"type": "exact", "field": "status", "value": "ok"},
        )
        assert result.passed is True
        mock_llm.complete.assert_not_called()

    def test_routes_to_semantic(self, mock_llm):
        router = AssertionRouter(llm_client=mock_llm, default_type="semantic")
        result = router.check_assertion(
            output={"message": "auth error occurred"},
            assertion_spec={"type": "semantic", "field": "message", "expected": "authentication failure"},
        )
        assert result.passed is True
        mock_llm.complete.assert_called_once()

    def test_default_type_semantic(self, mock_llm):
        router = AssertionRouter(llm_client=mock_llm, default_type="semantic")
        result = router.check_assertion(
            output={"status": "auth failed"},
            assertion_spec={"field": "status", "expected": "authentication failure"},  # No type specified
        )
        mock_llm.complete.assert_called_once()  # Should use semantic
```

### Phase 5: Documentation and Migration

**Files to create/modify:**
- Update test case YAML schema documentation
- Add migration guide for existing test cases

#### Task 5.1: Update Test Case Schema

```yaml
# docs/kubani/skills/test-case-schema.yaml
test_cases:
  - name: string  # Required
    description: string  # Optional
    inputs: object  # Required - inputs to skill
    expected: object  # Optional - expected output structure
    assertions:  # Required - list of assertions
      - type: string  # semantic (default), exact, contains, regex, numeric, exists, not_empty
        field: string  # Dot-notation path to field (e.g., "root_cause.service")
        expected: any  # Expected value (for semantic/exact/contains)
        value: any  # Alias for expected (backward compat)
        description: string  # Human-readable description
        # Type-specific options:
        tolerance: number  # For numeric: acceptable difference
        case_sensitive: boolean  # For contains: case sensitivity (default: true)
        confidence_threshold: number  # For semantic: minimum confidence (default: 0.7)
```

## Migration Path

### Backward Compatibility

The implementation maintains full backward compatibility:

1. **Default type change is configurable** - Can set `default_assertion_type="contains"` to keep old behavior
2. **Existing assertion types work unchanged** - `equals`, `contains`, `exists`, etc.
3. **`value` alias preserved** - Both `value` and `expected` work

### Recommended Migration

For new test cases, use explicit types:

```yaml
# Before (implicit contains)
assertions:
  - field: root_cause.service
    value: "auth-service"

# After (explicit semantic with fallback)
assertions:
  - type: semantic
    field: root_cause.service
    expected: "auth-service was the originating service"

  # Or for exact match requirements
  - type: exact
    field: error_code
    value: "ERR_001"
```

## Configuration

```yaml
# config/default.yaml
evaluation:
  assertions:
    default_type: semantic  # semantic, contains, exact
    semantic:
      confidence_threshold: 0.7
      batch_enabled: true
      batch_size: 5
```

## Success Criteria

1. [ ] All existing tests pass with `default_type="contains"`
2. [ ] New semantic tests achieve >80% accuracy for semantically correct output
3. [ ] Batch optimization reduces LLM calls by >50% for multi-assertion tests
4. [ ] Evaluation time increase <50% with batching enabled
5. [ ] Documentation updated with new assertion types

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Slower evaluation | Batch optimization, exact-match shortcut |
| Non-deterministic results | Confidence thresholds, fallback to exact |
| Breaking existing tests | Configurable default, backward compat |
| LLM costs increase | Use smaller model for semantic checks |

## Timeline Estimate

| Phase | Tasks | Complexity |
|-------|-------|------------|
| Phase 1 | Checker infrastructure | Medium |
| Phase 2 | Evaluator integration | Low |
| Phase 3 | Batch optimization | Medium |
| Phase 4 | Testing | Medium |
| Phase 5 | Documentation | Low |

## References

- Current evaluator: `platform/cli/src/kubani_dev/skill_evaluator_llm.py`
- Idea document: `docs/plans/ideas/2026-01-26-semantic-assertion-matching.md`
- Test case examples: `kubani/skills/*/test_cases.yaml`
