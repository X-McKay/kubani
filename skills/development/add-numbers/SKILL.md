# Skill: Add Two Numbers

## Description
Add two numbers together and return their sum.

## Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| a | number | Yes | First number |
| b | number | Yes | Second number |

## Output Format

**CRITICAL:** Return ONLY this exact JSON structure, no additional wrapper fields.

```json
{
  "sum": number
}
```

Example:
- Input: `{"a": 5, "b": 3}`
- Output: `{"sum": 8}`

## Execution Steps

1. Read the input parameters `a` and `b`
2. Calculate the sum: `sum = a + b`
3. Return the result as JSON with field name "sum"

## Error Handling

- If `a` or `b` is not a number, return: `{"error": "Invalid input: both a and b must be numbers"}`
- If `a` or `b` is missing, return: `{"error": "Missing required parameter"}`

## Example Usage

**Example 1: Normal addition**
```
Input: {"a": 10, "b": 20}
Output: {"sum": 30}
```

**Example 2: Negative numbers**
```
Input: {"a": -5, "b": 3}
Output: {"sum": -2}
```

**Example 3: Zero**
```
Input: {"a": 0, "b": 0}
Output: {"sum": 0}
```

**Example 4: Error case**
```
Input: {"a": "hello", "b": 5}
Output: {"error": "Invalid input: both a and b must be numbers"}
```
