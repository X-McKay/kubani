# Skill: Context Compression  
**Compresses large text into minimal tokens while retaining key facts, entities, themes, and events.**  

---

## Input Parameters  
| Parameter Name | Type   | Description                          |  
|----------------|--------|--------------------------------------|  
| (No input parameters defined) |        |                                      |  

---

## Output Format  
**Strict JSON Schema**  
```json
{
  "compressed_text": "string",
  "token_count": "integer"
}
```

**Example Output**  
```json
{
  "compressed_text": "Key entities: [EntityA, EntityB]. Themes: [ThemeX, ThemeY]. Events: [Event1, Event2].",
  "token_count": 24
}
```

**CRITICAL:** Return ONLY this exact JSON structure, no additional wrapper fields.  

---

## Execution Steps  
1. Execute the task as described: Compress the input text into minimal tokens while retaining key facts, entities, themes, and events.  

---

## Error Handling  
- If the input is invalid or unavailable, return an empty `compressed_text` field and `0` for `token_count`.  
- If an unexpected error occurs, return an empty JSON object `{}` with a `token_count` of `0`.  

---

## Example Usage  
**Input:**  
```text
The quick brown fox jumps over the lazy dog. The fox is known for its speed and agility. The dog is a large, friendly animal. Both animals are commonly used in fables and stories.
```  

**Output:**  
```json
{
  "compressed_text": "Entities: [fox, dog]. Themes: [speed, agility, fables]. Events: [jumps over, used in stories].",
  "token_count": 18
}
```