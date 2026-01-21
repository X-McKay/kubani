# Skill: Analyze Text

## Description
Analyze a given text and extract key metrics including word count, sentence count, average word length, and sentiment (positive, negative, or neutral).

## Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| text | string | Yes | The text to analyze |

## Output Format

**CRITICAL:** Return ONLY this exact JSON structure, no additional wrapper fields.

```json
{
  "word_count": number,
  "sentence_count": number,
  "avg_word_length": number,
  "sentiment": "positive" | "negative" | "neutral",
  "longest_word": string
}
```

Example:
- Input: `{"text": "Hello world! This is great."}`
- Output: `{"word_count": 5, "sentence_count": 2, "avg_word_length": 4.4, "sentiment": "positive", "longest_word": "Hello"}`

## Execution Steps

1. **Count words**: Split the text by whitespace and count non-empty tokens
2. **Count sentences**: Count periods, exclamation marks, and question marks
3. **Calculate average word length**: Sum the length of all words and divide by word count (round to 1 decimal place)
4. **Find longest word**: Identify the word with the most characters
5. **Determine sentiment**:
   - If text contains positive words (good, great, excellent, happy, love, wonderful, amazing), classify as "positive"
   - If text contains negative words (bad, terrible, awful, hate, sad, poor, worst), classify as "negative"
   - Otherwise, classify as "neutral"
6. Return the results as JSON

## Error Handling

- If `text` is empty or missing, return: `{"error": "Text parameter is required and cannot be empty"}`
- If `text` is not a string, return: `{"error": "Text must be a string"}`

## Example Usage

**Example 1: Positive sentiment**
```
Input: {"text": "This is a great day! I love programming."}
Output: {
  "word_count": 8,
  "sentence_count": 2,
  "avg_word_length": 4.4,
  "sentiment": "positive",
  "longest_word": "programming"
}
```

**Example 2: Negative sentiment**
```
Input: {"text": "This is terrible. I hate bugs."}
Output: {
  "word_count": 6,
  "sentence_count": 2,
  "avg_word_length": 4.2,
  "sentiment": "negative",
  "longest_word": "terrible"
}
```

**Example 3: Neutral sentiment**
```
Input: {"text": "The sky is blue."}
Output: {
  "word_count": 4,
  "sentence_count": 1,
  "avg_word_length": 3.5,
  "sentiment": "neutral",
  "longest_word": "blue"
}
```

**Example 4: Error case**
```
Input: {"text": ""}
Output: {"error": "Text parameter is required and cannot be empty"}
```
