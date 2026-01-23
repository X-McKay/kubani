---
name: analyze-article
version: "1.0.0"
description: >
  Use LLM to analyze a raw article. Generates summary, extracts entities,
  categorizes content, assigns importance score, and detects breaking news.
metadata:
  domain: news
  category: diagnostic
  mcp-servers: []
  requires-approval: false
  confidence: 0.85
input:
  - name: article
    type: RawArticle
    description: Raw article with title, url, source, summary, published_at
output:
  - name: processed_article
    type: ProcessedArticle
    description: Enriched article with AI-generated metadata
---

# Analyze Article

Use LLM to analyze and enrich a single news article.

## Preconditions

- Article has valid title and summary/content
- LLM API (vLLM) is accessible

## Actions

### Step 1: Prepare Content

Combine article title and summary for analysis. Truncate if longer than 2000 characters.

### Step 2: Call LLM for Analysis

Send article to LLM with structured prompt requesting:

1. **Summary**: 2-3 sentence summary of key points
2. **Category**: One of `research`, `business`, `product`, `security`, `policy`, `general`
3. **Entities**: List of companies, people, technologies, models mentioned
4. **Importance Score**: 1-10 rating where:
   - 1-3: Minor news, incremental updates
   - 4-6: Notable news, meaningful developments
   - 7-8: Important news, significant impact
   - 9-10: Major news, industry-changing announcements
5. **Is Breaking**: True if major breaking news requiring immediate alert
6. **Breaking Reason**: Explanation if breaking (e.g., "Major model release")

### Step 3: Parse LLM Response

Extract structured data from JSON response. Handle:
- Qwen3 thinking tags (`<think>...</think>`) - strip them
- Markdown code blocks around JSON
- Invalid JSON - return defaults

### Step 4: Apply Importance Boost

Boost importance score by +2 (max 10) for official company blog posts,
as these represent primary source announcements.

### Step 5: Generate Content Hash

Create hash from title + URL for deduplication tracking.

## Success Criteria

- Article enriched with AI summary
- Valid category assigned
- Entities extracted (may be empty)
- Importance score between 1-10
- Breaking news flag set appropriately

## Fallback Behavior

If LLM call fails:
- Use original summary as AI summary
- Set category to `general`
- Set importance to 5
- Set is_breaking to false
- Return entities as empty list
