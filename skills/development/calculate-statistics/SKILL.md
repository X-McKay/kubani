# Skill: Calculate Statistics

## Description
Calculate comprehensive statistics for an array of numbers including mean, median, mode, standard deviation, min, and max.

## Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| numbers | array | Yes | Array of numbers to analyze |

## Output Format

**CRITICAL:** Return ONLY this exact JSON structure, no additional wrapper fields.

```json
{
  "mean": number,
  "median": number,
  "mode": number,
  "std_dev": number,
  "min": number,
  "max": number,
  "count": number
}
```

Example:
- Input: `{"numbers": [1, 2, 3, 4, 5]}`
- Output: `{"mean": 3.0, "median": 3, "mode": 1, "std_dev": 1.41, "min": 1, "max": 5, "count": 5}`

## Execution Steps

1. **Validate input**: Check that `numbers` is an array and not empty
2. **Count**: Store the length of the array as `count`
3. **Calculate mean**: Sum all numbers and divide by count (round to 2 decimal places)
4. **Calculate median**:
   - Sort the numbers in ascending order
   - If count is odd: take the middle number (index = count // 2)
   - If count is even: MUST average the two middle numbers
     - Example: [1, 2, 3, 4] → middle indices are 1 and 2 → (2 + 3) / 2 = 2.5
     - DO NOT just take one middle number, MUST calculate the average
5. **Calculate mode**:
   - Count frequency of each number
   - Return the number with highest frequency
   - If all numbers appear once, return the first number
6. **Calculate standard deviation**:
   - Calculate variance: average of squared differences from mean
   - Take square root of variance
   - Round to 2 decimal places
7. **Find min**: Return the smallest number
8. **Find max**: Return the largest number
9. **Return results**: Return all statistics as JSON

## Error Handling

- If `numbers` is not an array, return: `{"error": "Numbers must be an array"}`
- If `numbers` is empty, return: `{"error": "Numbers array cannot be empty"}`
- If `numbers` contains non-numeric values, return: `{"error": "All elements must be numbers"}`

## Example Usage

**Example 1: Simple dataset**
```
Input: {"numbers": [1, 2, 3, 4, 5]}
Output: {
  "mean": 3.0,
  "median": 3,
  "mode": 1,
  "std_dev": 1.41,
  "min": 1,
  "max": 5,
  "count": 5
}
```

**Example 2: Dataset with duplicates**
```
Input: {"numbers": [1, 2, 2, 3, 3, 3, 4]}
Output: {
  "mean": 2.57,
  "median": 3,
  "mode": 3,
  "std_dev": 0.9,
  "min": 1,
  "max": 4,
  "count": 7
}
```

**Example 3: Even count (median calculation)**
```
Input: {"numbers": [1, 2, 3, 4]}
Output: {
  "mean": 2.5,
  "median": 2.5,
  "mode": 1,
  "std_dev": 1.12,
  "min": 1,
  "max": 4,
  "count": 4
}
```

**Example 4: Single number**
```
Input: {"numbers": [42]}
Output: {
  "mean": 42.0,
  "median": 42,
  "mode": 42,
  "std_dev": 0.0,
  "min": 42,
  "max": 42,
  "count": 1
}
```

**Example 5: Negative numbers**
```
Input: {"numbers": [-5, -2, 0, 3, 7]}
Output: {
  "mean": 0.6,
  "median": 0,
  "mode": -5,
  "std_dev": 4.27,
  "min": -5,
  "max": 7,
  "count": 5
}
```

**Example 6: Error case - empty array**
```
Input: {"numbers": []}
Output: {"error": "Numbers array cannot be empty"}
```
