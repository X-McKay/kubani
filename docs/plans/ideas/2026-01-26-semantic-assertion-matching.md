# Semantic Assertion Matching for Skill Evaluation

**Status:** Idea
**Created:** 2026-01-26
**Author:** Claude Code

## Problem Statement

The current skill evaluation system uses exact string matching for assertions, which is too rigid for LLM-generated output. A skill that correctly identifies "auth-service authentication error caused cascading failures" will fail an assertion expecting exactly "Authentication failure".

This leads to:
- 0% accuracy scores for semantically correct skills
- Frustrating improvement loops that can't converge
- Test cases that don't reflect real-world usage

### Example of the Problem

**Test case assertion:**
```yaml
assertions:
  - type: contains
    field: root_cause.failure_mode
    value: "Authentication failure"
```

**Skill output:**
```json
{
  "root_cause": {
    "failure_mode": "The auth-service experienced an authentication error"
  }
}
```

**Result:** FAIL (even though semantically correct)

## Proposed Solution

Introduce semantic assertion matching as the default, with exact matching available as an opt-in for specific use cases.

### Assertion Types

| Type | Description | Use Case |
|------|-------------|----------|
| `semantic` (default) | LLM judges if output matches expected meaning | Natural language responses |
| `contains` | Check if output contains substring | Keywords, partial matches |
| `exact` | Exact string equality | Error codes, IDs, specific values |
| `regex` | Regular expression match | Patterns, formats |
| `numeric` | Numeric comparison with tolerance | Metrics, counts |

### Example Test Case

```yaml
test_cases:
  - name: identify_root_cause
    inputs:
      traces: [...]
    expected:
      root_cause:
        service: "auth-service"
        failure_mode: "authentication failure causing downstream errors"
    assertions:
      # Semantic match (default) - LLM judges meaning
      - type: semantic
        field: root_cause.failure_mode
        expected: "authentication failure causing downstream errors"

      # Exact match - for specific identifiers
      - type: exact
        field: root_cause.service
        value: "auth-service"

      # Contains - for keyword presence
      - type: contains
        field: root_cause.impact
        value: "cascad"  # matches "cascading", "cascaded"
```

## Implementation Design

### 1. Assertion Checker Interface

```python
class AssertionChecker(Protocol):
    """Protocol for assertion checkers."""

    async def check(
        self,
        actual: Any,
        expected: Any,
        context: str | None = None,
    ) -> AssertionResult:
        """Check if actual matches expected."""
        ...

@dataclass
class AssertionResult:
    passed: bool
    confidence: float  # 0.0-1.0 for semantic matches
    reasoning: str | None = None
    actual_value: Any = None
    expected_value: Any = None
```

### 2. Semantic Assertion Checker

```python
class SemanticAssertionChecker:
    """Uses LLM to judge semantic equivalence."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def check(
        self,
        actual: Any,
        expected: Any,
        context: str | None = None,
    ) -> AssertionResult:
        prompt = f"""Judge if the actual output matches the expected meaning.

Expected: {expected}
Actual: {actual}
Context: {context or "None"}

Respond with JSON:
{{
  "matches": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}
"""
        response = await self.llm.complete(prompt)
        result = parse_json(response)

        return AssertionResult(
            passed=result["matches"],
            confidence=result["confidence"],
            reasoning=result["reasoning"],
            actual_value=actual,
            expected_value=expected,
        )
```

### 3. Assertion Router

```python
class AssertionRouter:
    """Routes assertions to appropriate checkers."""

    def __init__(self, llm_client: LLMClient):
        self.checkers = {
            "semantic": SemanticAssertionChecker(llm_client),
            "exact": ExactAssertionChecker(),
            "contains": ContainsAssertionChecker(),
            "regex": RegexAssertionChecker(),
            "numeric": NumericAssertionChecker(),
        }
        self.default_type = "semantic"

    async def check(
        self,
        assertion_spec: dict,
        output: dict,
    ) -> AssertionResult:
        assertion_type = assertion_spec.get("type", self.default_type)
        checker = self.checkers[assertion_type]

        field = assertion_spec["field"]
        actual = get_nested_value(output, field)
        expected = assertion_spec.get("expected") or assertion_spec.get("value")

        return await checker.check(actual, expected)
```

### 4. Batch Optimization

To reduce LLM calls, batch multiple semantic assertions into a single prompt:

```python
async def check_semantic_batch(
    self,
    assertions: list[dict],
    output: dict,
) -> list[AssertionResult]:
    """Check multiple semantic assertions in one LLM call."""

    prompt = "Judge if each actual output matches its expected meaning.\n\n"
    for i, assertion in enumerate(assertions):
        field = assertion["field"]
        actual = get_nested_value(output, field)
        expected = assertion.get("expected")
        prompt += f"{i+1}. Expected: {expected}\n   Actual: {actual}\n\n"

    prompt += "Respond with JSON array of results..."
    # Single LLM call for all assertions
```

## Migration Path

### Phase 1: Add Semantic Checker (Non-Breaking)

1. Implement `SemanticAssertionChecker`
2. Add `type: semantic` as explicit option
3. Existing tests continue to work with `contains`/`exact`

### Phase 2: Change Default (Breaking)

1. Change default assertion type from `contains` to `semantic`
2. Update test case generation to use new format
3. Migrate existing test cases or mark with explicit `type: contains`

### Phase 3: Optimize

1. Add batch processing for multiple assertions
2. Cache common semantic judgments
3. Add confidence thresholds for pass/fail decisions

## Configuration

```yaml
# config/default.yaml
evaluation:
  assertions:
    default_type: semantic  # or "contains" for backward compat
    semantic:
      model: "llm.almckay.io"  # Can use smaller/faster model
      confidence_threshold: 0.7  # Minimum confidence to pass
      batch_size: 5  # Max assertions per LLM call
    cache:
      enabled: true
      ttl_seconds: 3600
```

## Trade-offs

### Pros
- More realistic evaluation of LLM-generated content
- Skills can pass with semantically correct but differently-worded output
- Better alignment with human judgment
- Improvement loops can actually converge

### Cons
- Slower evaluation (LLM calls for semantic checks)
- Higher cost (more LLM tokens)
- Non-deterministic (LLM judgment may vary)
- Requires confidence threshold tuning

### Mitigations
- Use smaller/faster model for semantic checks
- Batch assertions to reduce calls
- Cache common judgments
- Allow exact matching for deterministic cases

## Success Criteria

1. Skills with semantically correct output achieve >80% accuracy
2. Evaluation time increases by <50% with batching
3. Improvement loops converge within max iterations
4. No regression for exact-match use cases

## Alternatives Considered

### 1. Fuzzy String Matching (Levenshtein, etc.)
- Faster but misses semantic equivalence
- "auth error" vs "authentication failure" would still fail

### 2. Keyword Extraction
- Check for key terms rather than exact strings
- Better but still misses paraphrases

### 3. Embedding Similarity
- Compare vector embeddings of expected vs actual
- Faster than LLM but less accurate for nuanced cases

### 4. Fix Test Case Generation Only
- Generate less rigid test cases
- Doesn't solve fundamental mismatch

## Related Work

- LLM-as-judge evaluation patterns
- Semantic similarity in NLP evaluation
- BLEU/ROUGE scores for text generation

## References

- Current evaluator: `platform/cli/src/kubani_dev/skill_evaluator_llm.py`
- Test case format: `kubani/skills/*/test_cases.yaml`
- Evaluation service: `kubani/workflows/skill_auto/eval_service.py`
