```yaml
---
name: test-calculate-stats
version: "1.0.0"
description: >
  Calculate statistical metrics (mean, median, standard deviation) from a list of numbers

metadata:
  domain: general
  category: analytics
  requires-approval: false

# No specific dependencies
allowed-tools: "Bash"
---
```

# Calculate Statistical Metrics

## When to Use
- When analyzing numerical datasets for summary statistics
- When generating reports requiring mean/median/standard deviation
- For quality control checks on numeric inputs

## Prerequisites
- ✅ Python 3.x installed
- ✅ Script file `scripts/test_calculate_stats.py` exists
- ✅ Input is a valid list of numbers

## Input Schema
```json
{
  "numbers": [
    1.5,
    2.3,
    4.7,
    3.1,
    5.9
  ]
}
```

## Actions
### 1. Execute Calculation Script
Run the Python script with input data:
```bash
python scripts/test_calculate_stats.py '{"numbers": [1.5, 2.3, 4.7, 3.1, 5.9]}'
```

### 2. Parse Output
Capture the JSON output containing:
- Mean
- Median
- Standard deviation

### 3. Format Results
Structure output in the required JSON format with calculated values

## Output Schema
```json
{
  "mean": 3.38,
  "median": 3.1,
  "standard_deviation": 1.64
}
```

**CRITICAL:** Return ONLY this exact JSON structure, no additional wrapper fields

## Success Criteria
- ✅ Script executed without errors
- ✅ Output contains all required fields (mean, median, standard_deviation)
- ✅ Calculated values match mathematical definitions

## Failure Handling
| Error Type          | Handling Strategy                          |
|---------------------|--------------------------------------------|
| Invalid input format| Return error message with format requirements |
| Script execution error | Log error and return null result        |
| Calculation error   | Return null values with error flag        |

## Examples
**Input:**
```json
{"numbers": [1, 2, 3, 4, 5]}
```

**Output:**
```json
{
  "mean": 3,
  "median": 3,
  "standard_deviation": 1.5811388300841898
}
```

## Script Execution
The calculation is performed by the script located at `scripts/test_calculate_stats.py`. Execute it using:
```bash
python scripts/test_calculate_stats.py '{"input": "value"}'
```

This script contains an `execute(inputs: dict) -> dict` function that:
- Validates input format
- Performs statistical calculations
- Returns results in the required JSON structure

The script provides deterministic results and should be preferred for calculation operations.

## Output Template
The output should follow the structure defined in `template.md`, which is a table template with:
- No specific placeholders required (flat JSON output)
- Mustache-style syntax for dynamic values ({{mean}}, {{median}}, {{standard_deviation}})
- Strict adherence to the output schema defined above
```