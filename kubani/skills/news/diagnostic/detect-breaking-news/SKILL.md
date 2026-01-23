---
name: detect-breaking-news
version: "1.0.0"
description: >
  Identify articles that qualify as breaking news requiring immediate alerts.
  Fast check based on article metadata without additional LLM calls.
metadata:
  domain: news
  category: diagnostic
  mcp-servers: []
  requires-approval: false
  confidence: 0.95
input:
  - name: articles
    type: list[ProcessedArticle]
    description: Processed articles with is_breaking flag and importance_score
output:
  - name: breaking_articles
    type: list[ProcessedArticle]
    description: Articles that qualify for breaking news alerts
  - name: breaking_count
    type: int
    description: Number of breaking news articles detected
---

# Detect Breaking News

Identify articles that require immediate breaking news alerts.

## Preconditions

- Articles have been processed with analyze-article skill
- Articles have `is_breaking` flag and `importance_score` set

## Actions

### Step 1: Apply Breaking News Criteria

For each article, check if it meets ALL criteria:

1. **is_breaking**: Must be true (set by LLM during analysis)
2. **importance_score**: Must be >= 8 (high or critical importance)

Both conditions must be met to prevent:
- Low-importance articles flagged as breaking (score < 8)
- High-importance routine updates (is_breaking = false)

### Step 2: Collect Breaking Articles

Add all qualifying articles to the breaking news list.

### Step 3: Return Results

Return list of breaking articles and count.

## Success Criteria

- All articles checked against criteria
- Breaking articles correctly identified
- No false positives (low importance flagged as breaking)
- No false negatives (true breaking news missed)

## Example Breaking News Categories

Typical breaking news includes:
- Major model releases (GPT-5, Claude 4, Gemini 2, etc.)
- Security vulnerabilities in AI systems
- Major company announcements (acquisitions, leadership changes)
- Regulatory decisions affecting AI industry
- Significant research breakthroughs
- Safety incidents or model failures
