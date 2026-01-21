# Skill Evaluation Report

**Skill:** filter-json-data  
**Timestamp:** 2026-01-20T21:49:01

## Summary

| Metric | Value |
|--------|-------|
| Accuracy | 100.0% |
| Tests Passed | 8/8 |
| Assertions Passed | 18/18 |
| Avg Latency | 26598 ms |
| Avg Tokens/Test | 1352 |
| Total Tokens | 10812 |

## Test Results

### 1. test_filter_single_field - ✅ PASS

**Description:** Filter by a single field

**Latency:** 122602 ms  
**Tokens:** 1413

**Assertions:**

- ✓ Should find 2 matching items
- ✓ Original count should be 3
- ✓ Filtered data should exist

### 2. test_filter_multiple_fields - ✅ PASS

**Description:** Filter by multiple fields (AND logic)

**Latency:** 17452 ms  
**Tokens:** 1423

**Assertions:**

- ✓ Should find 2 items matching both criteria
- ✓ Original count should be 3

### 3. test_no_matches - ✅ PASS

**Description:** Filter with no matching items

**Latency:** 8761 ms  
**Tokens:** 1317

**Assertions:**

- ✓ Should find 0 matching items
- ✓ Original count should be 2
- ✓ Filtered data should be empty array

### 4. test_empty_data - ✅ PASS

**Description:** Filter empty array

**Latency:** 7584 ms  
**Tokens:** 1281

**Assertions:**

- ✓ Count should be 0
- ✓ Original count should be 0

### 5. test_all_match - ✅ PASS

**Description:** All items match the filter

**Latency:** 20814 ms  
**Tokens:** 1388

**Assertions:**

- ✓ All 3 items should match
- ✓ Original count should be 3

### 6. test_string_filter - ✅ PASS

**Description:** Filter by string value

**Latency:** 16448 ms  
**Tokens:** 1370

**Assertions:**

- ✓ Should find 2 admins
- ✓ Original count should be 3

### 7. test_missing_field - ✅ PASS

**Description:** Filter by field that doesn't exist in some items

**Latency:** 13642 ms  
**Tokens:** 1349

**Assertions:**

- ✓ Only 1 item has age 30
- ✓ Original count should be 3

### 8. test_error_invalid_data - ✅ PASS

**Description:** Handle error when data is not an array

**Latency:** 5485 ms  
**Tokens:** 1271

**Assertions:**

- ✓ Should return an error
- ✓ Error should mention array

