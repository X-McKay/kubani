# Skill: Filter JSON Data

## Description
Filter an array of JSON objects based on specified criteria and return only the matching items. Supports filtering by field values, ranges, and existence checks.

## Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| data | array | Yes | Array of JSON objects to filter |
| filters | object | Yes | Filter criteria with field names as keys |

## Output Format

**CRITICAL:** Return ONLY this exact JSON structure, no additional wrapper fields.

```json
{
  "filtered_data": array,
  "count": number,
  "original_count": number
}
```

Example:
- Input: `{"data": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}], "filters": {"age": 30}}`
- Output: `{"filtered_data": [{"name": "Alice", "age": 30}], "count": 1, "original_count": 2}`

## Execution Steps

1. **Validate inputs**: Check that `data` is an array and `filters` is an object
2. **Count original data**: Store the length of the input array as `original_count`
3. **Apply filters**: For each item in `data`:
   - Check if all filter criteria match
   - If a filter key exists in the item, compare values (exact match)
   - If all filters match, include the item in results
4. **Count filtered data**: Store the length of filtered results as `count`
5. **Return results**: Return the filtered data with counts

## Filter Matching Rules

- **Exact match**: Filter value must equal item value exactly
- **Type sensitive**: "25" (string) does not match 25 (number)
- **All filters must match**: Item must satisfy ALL filter criteria (AND logic)
- **Missing fields**: If filter key doesn't exist in item, item is excluded

## Error Handling

- If `data` is not an array, return: `{"error": "Data must be an array"}`
- If `filters` is not an object, return: `{"error": "Filters must be an object"}`
- If `data` is empty, return: `{"filtered_data": [], "count": 0, "original_count": 0}`
- If no items match filters, return: `{"filtered_data": [], "count": 0, "original_count": N}` where N is the original count

## Example Usage

**Example 1: Filter by single field**
```
Input: {
  "data": [
    {"name": "Alice", "age": 30, "city": "NYC"},
    {"name": "Bob", "age": 25, "city": "LA"},
    {"name": "Charlie", "age": 30, "city": "SF"}
  ],
  "filters": {"age": 30}
}
Output: {
  "filtered_data": [
    {"name": "Alice", "age": 30, "city": "NYC"},
    {"name": "Charlie", "age": 30, "city": "SF"}
  ],
  "count": 2,
  "original_count": 3
}
```

**Example 2: Filter by multiple fields**
```
Input: {
  "data": [
    {"name": "Alice", "age": 30, "city": "NYC"},
    {"name": "Bob", "age": 25, "city": "LA"},
    {"name": "Charlie", "age": 30, "city": "NYC"}
  ],
  "filters": {"age": 30, "city": "NYC"}
}
Output: {
  "filtered_data": [
    {"name": "Alice", "age": 30, "city": "NYC"},
    {"name": "Charlie", "age": 30, "city": "NYC"}
  ],
  "count": 2,
  "original_count": 3
}
```

**Example 3: No matches**
```
Input: {
  "data": [
    {"name": "Alice", "age": 30},
    {"name": "Bob", "age": 25}
  ],
  "filters": {"age": 40}
}
Output: {
  "filtered_data": [],
  "count": 0,
  "original_count": 2
}
```

**Example 4: Empty data**
```
Input: {
  "data": [],
  "filters": {"age": 30}
}
Output: {
  "filtered_data": [],
  "count": 0,
  "original_count": 0
}
```

**Example 5: Error case**
```
Input: {
  "data": "not an array",
  "filters": {"age": 30}
}
Output: {
  "error": "Data must be an array"
}
```
