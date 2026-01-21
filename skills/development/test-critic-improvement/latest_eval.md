# Skill Evaluation Report

**Skill:** test-critic-improvement  
**Timestamp:** 2026-01-20T22:44:03

## Summary

| Metric | Value |
|--------|-------|
| Accuracy | 80.0% |
| Tests Passed | 2/4 |
| Assertions Passed | 4/5 |
| Avg Latency | 64121 ms |
| Avg Tokens/Test | 529 |
| Total Tokens | 2116 |

## Test Results

### 1. test_basic - ✅ PASS

**Description:** Basic percentage calculation

**Latency:** 40767 ms  
**Tokens:** 372

**Assertions:**

- ✓ Percentage should be 25

### 2. test_decimal_result - ✅ PASS

**Description:** Result with decimal places

**Latency:** 116284 ms  
**Tokens:** 507

**Assertions:**

- ✓ Should have percentage field
- ✓ Should have formatted field

### 3. test_zero_whole - ❌ FAIL

**Description:** Division by zero case

**Latency:** 57144 ms  
**Tokens:** 632

**Assertions:**

- ✗ Should return error for zero whole
  - Expected: `None`
  - Actual: `None`

### 4. test_negative_values - ❌ FAIL

**Description:** Negative percentage

**Latency:** 42288 ms  
**Tokens:** 605

**Assertions:**

- ✓ Should handle negative values

