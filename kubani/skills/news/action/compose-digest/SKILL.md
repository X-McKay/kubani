---
name: compose-digest
version: "1.0.0"
description: >
  Compose a formatted news digest from processed articles and trends.
  Uses LLM to generate cohesive narrative summary with embedded citations.
  Formats for Discord readability.
metadata:
  domain: news
  category: action
  mcp-servers: []
  requires-approval: false
  confidence: 0.85
input:
  - name: articles
    type: list[ProcessedArticle]
    description: Processed articles to include in digest
  - name: trends
    type: list[TrendingTopic]
    description: Identified trends for the period
  - name: period_hours
    type: int
    default: 12
    description: Hours covered by this digest
output:
  - name: digest
    type: NewsDigest
    description: Complete formatted news digest
  - name: discord_formatted
    type: str
    description: Digest formatted for Discord posting
---

# Compose Digest

Create a formatted news digest from articles and trends.

## Preconditions

- Articles processed with analyze-article skill
- Trends analyzed with analyze-trends skill
- LLM API available for summary generation

## Actions

### Step 1: Select Articles by Importance

Sort articles by importance score and select:
1. **All high importance** (score >= 7)
2. **Top 5 medium importance** (score 5-6)
3. **Fallback**: If no notable articles, take top 5 by score

### Step 2: Generate LLM Summary

Send selected articles to LLM with prompt:

```
Write a cohesive, professional summary of these news items:
1. Be written as flowing paragraphs, not bullet points
2. Embed source citations inline using markdown [Source](url)
3. Highlight the most important developments first
4. Group related news naturally in the narrative
5. Be concise but comprehensive

Write 2-4 paragraphs summarizing the key AI news.
```

### Step 3: Parse and Clean Response

- Strip Qwen3 thinking tags (`<think>...</think>`)
- Clean up any formatting artifacts
- If LLM fails, use fallback bullet-point format

### Step 4: Build NewsDigest Object

Create digest with:
- Unique ID: `digest-{uuid[:8]}`
- Created timestamp
- Period start/end based on `period_hours`
- Generated headline summary
- Top 5 trends
- Article count
- Sources used

### Step 5: Format for Discord

Format digest with sections:

```markdown
# AI News Digest - {date} ({Morning/Evening})

{LLM-generated summary with citations}

**Trending Topics:**
- {topic} (covered by {n} sources)

**Emerging Themes:**
- {rising topic}

---
*{n} articles from {n} sources*
```

## Success Criteria

- Coherent summary generated
- Citations properly embedded
- Trends highlighted appropriately
- Format fits Discord constraints

## Fallback Behavior

If LLM unavailable:
```markdown
**Today's AI News Highlights:**

- [{title}]({url}) ({source}): {summary}...
```
