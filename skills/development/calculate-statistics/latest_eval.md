# Skill Evaluation Report

**Skill:** calculate-statistics  
**Timestamp:** 2026-01-20T21:52:16

## Summary

| Metric | Value |
|--------|-------|
| Accuracy | 96.7% |
| Tests Passed | 6/7 |
| Assertions Passed | 29/30 |
| Avg Latency | 23918 ms |
| Avg Tokens/Test | 1293 |
| Total Tokens | 9054 |

## Test Results

### 1. test_simple_dataset - ✅ PASS

**Description:** Calculate statistics for simple sequential numbers

**Latency:** 101129 ms  
**Tokens:** 1303

**Assertions:**

- ✓ Mean should be 3.0
- ✓ Median should be 3
- ✓ Min should be 1
- ✓ Max should be 5
- ✓ Count should be 5

### 2. test_with_duplicates - ✅ PASS

**Description:** Calculate mode with duplicates

**Latency:** 12546 ms  
**Tokens:** 1312

**Assertions:**

- ✓ Mode should be 3 (appears most frequently)
- ✓ Count should be 7
- ✓ Mean should be calculated
- ✓ Median should be calculated

### 3. test_even_count - ❌ FAIL

**Description:** Calculate median for even count of numbers

**Latency:** 11302 ms  
**Tokens:** 1298

**Assertions:**

- ✓ Mean should be 2.5
- ✗ Median should be 2.5 (average of 2 and 3)
  - Expected: `2.5`
  - Actual: `2`
- ✓ Count should be 4

### 4. test_single_number - ✅ PASS

**Description:** Calculate statistics for single number

**Latency:** 12130 ms  
**Tokens:** 1292

**Assertions:**

- ✓ Mean should be 42.0
- ✓ Median should be 42
- ✓ Mode should be 42
- ✓ Std dev should be 0.0
- ✓ Min should be 42
- ✓ Max should be 42
- ✓ Count should be 1

### 5. test_negative_numbers - ✅ PASS

**Description:** Calculate statistics with negative numbers

**Latency:** 13007 ms  
**Tokens:** 1303

**Assertions:**

- ✓ Min should be -5
- ✓ Max should be 7
- ✓ Count should be 5
- ✓ Mean should be calculated
- ✓ Median should be calculated

### 6. test_decimal_numbers - ✅ PASS

**Description:** Calculate statistics with decimal numbers

**Latency:** 13828 ms  
**Tokens:** 1312

**Assertions:**

- ✓ Mean should be 3.0
- ✓ Count should be 4
- ✓ Min should be calculated
- ✓ Max should be calculated

### 7. test_empty_array - ✅ PASS

**Description:** Handle error for empty array

**Latency:** 3484 ms  
**Tokens:** 1234

**Assertions:**

- ✓ Should return an error
- ✓ Error should mention empty

