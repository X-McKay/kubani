# Calculate Percentage

## Description
Calculate what percentage one number is of another.

## Inputs
- `part` (number): The part value
- `whole` (number): The whole value

## Output Format
Return a JSON object with:
```json
{
  "percentage": number,
  "formatted": "string with % sign"
}
```

## Instructions
1. Divide part by whole
2. Multiply by 100
3. Return the result

## Examples
Input: `{"part": 25, "whole": 100}`
Output: `{"percentage": 25, "formatted": "25%"}`

Input: `{"part": 50, "whole": 200}`
Output: `{"percentage": 25, "formatted": "25%"}`
