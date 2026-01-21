# Skill Evaluation Report

**Skill:** analyze-text  
**Timestamp:** 2026-01-20T21:21:49

## Summary

| Metric | Value |
|--------|-------|
| Accuracy | 90.0% |
| Tests Passed | 6/8 |
| Assertions Passed | 18/20 |
| Avg Latency | 17812 ms |
| Avg Tokens/Test | 903 |
| Total Tokens | 7224 |

## Test Results

### 1. test_positive_sentiment - ✅ PASS

**Description:** Analyze text with positive sentiment

**Latency:** 75348 ms  
**Tokens:** 909

**Assertions:**

- ✓ Should count 8 words
- ✓ Should count 2 sentences
- ✓ Should detect positive sentiment
- ✓ Should identify longest word

### 2. test_negative_sentiment - ✅ PASS

**Description:** Analyze text with negative sentiment

**Latency:** 10012 ms  
**Tokens:** 908

**Assertions:**

- ✓ Should count 6 words
- ✓ Should count 2 sentences
- ✓ Should detect negative sentiment

### 3. test_neutral_sentiment - ✅ PASS

**Description:** Analyze text with neutral sentiment

**Latency:** 9817 ms  
**Tokens:** 904

**Assertions:**

- ✓ Should count 4 words
- ✓ Should count 1 sentence
- ✓ Should detect neutral sentiment

### 4. test_complex_text - ❌ FAIL

**Description:** Analyze longer text with multiple sentences

**Latency:** 11572 ms  
**Tokens:** 920

**Assertions:**

- ✗ Should count 18 words
  - Expected: `18`
  - Actual: `24`
- ✓ Should count 3 sentences
- ✓ Should calculate average word length
- ✓ Should identify longest word

### 5. test_single_word - ❌ FAIL

**Description:** Analyze single word

**Latency:** 9608 ms  
**Tokens:** 901

**Assertions:**

- ✗ Should count 1 word
  - Expected: `1`
  - Actual: `2`
- ✓ Should count 1 sentence
- ✓ Longest word should be Hello

### 6. test_empty_text - ✅ PASS

**Description:** Handle empty text error case

**Latency:** 4049 ms  
**Tokens:** 866

**Assertions:**

- ✓ Should return an error for empty text

### 7. test_positive_keywords - ✅ PASS

**Description:** Test sentiment detection with positive keywords

**Latency:** 11287 ms  
**Tokens:** 907

**Assertions:**

- ✓ Should detect positive sentiment from keywords

### 8. test_negative_keywords - ✅ PASS

**Description:** Test sentiment detection with negative keywords

**Latency:** 10804 ms  
**Tokens:** 909

**Assertions:**

- ✓ Should detect negative sentiment from keywords

