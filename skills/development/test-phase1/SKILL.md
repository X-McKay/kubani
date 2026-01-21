# Determine if Number is Prime

## Description
Check if a given number is prime (only divisible by 1 and itself).

## Inputs
- `number` (integer): The number to check

## Output Format
Return a JSON object with:
```json
{
  "is_prime": boolean,
  "reason": "string explaining why"
}
```

## Instructions
1. Check if the number is less than 2 (not prime)
2. Check if the number is 2 (prime)
3. Check if the number is even (not prime)
4. Check divisibility from 3 to sqrt(number)
5. Return result with explanation

## Examples
Input: `{"number": 7}`
Output: `{"is_prime": true, "reason": "7 is only divisible by 1 and itself"}`

Input: `{"number": 4}`
Output: `{"is_prime": false, "reason": "4 is divisible by 2"}`
