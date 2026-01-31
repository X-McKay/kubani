---
name: fetch-arxiv-papers
description: >
  Fetch recent AI/ML research papers from arXiv RSS feeds. Retrieves papers from
  cs.AI, cs.LG, and cs.CL categories, extracting title, authors, abstract, and
  arXiv ID for further analysis.
license: MIT
compatibility: Requires feedparser and httpx packages, internet access to arXiv
metadata:
  kubani:
    domain: news
    category: collection
    version: "1.0.0"
    mcp_servers: []
    requires_approval: false
    confidence: 0.8
input:
  - name: categories
    type: list[str]
    default: ["cs.AI", "cs.LG", "cs.CL"]
    description: ArXiv categories to fetch (cs.AI=Artificial Intelligence, cs.LG=Machine Learning, cs.CL=Computation and Language)
  - name: max_results
    type: int
    default: 50
    description: Maximum number of papers to return per category
  - name: days_back
    type: int
    default: 3
    description: Only include papers from the last N days
output:
  - name: papers
    type: list[ArxivPaper]
    description: List of papers with id, title, authors, abstract, categories, published_date, pdf_url
  - name: total_fetched
    type: int
    description: Total number of papers fetched across all categories
  - name: categories_fetched
    type: list[str]
    description: Categories that were successfully fetched
---

# Fetch ArXiv Papers

Retrieve recent AI and machine learning research papers from arXiv for analysis and inclusion in news digests.

## When to Use

- Daily collection of new research papers for digest
- Finding papers on specific AI topics
- Building research deep-dive candidates
- Keywords: arxiv, research, papers, AI research, machine learning papers

## Prerequisites

- Network access to export.arxiv.org
- Valid arXiv category codes

## Input Schema

```json
{
  "categories": ["cs.AI", "cs.LG", "cs.CL"],
  "max_results": 50,
  "days_back": 3
}
```

## Actions

### Step 1: Construct ArXiv API URLs

For each category, construct the arXiv RSS feed URL:
- Base URL: `https://export.arxiv.org/rss/{category}`
- Example: `https://export.arxiv.org/rss/cs.AI`

### Step 2: Fetch RSS Feeds

For each category URL:
1. Make HTTP GET request with appropriate timeout (30 seconds)
2. Set User-Agent header to avoid rate limiting
3. Handle HTTP errors gracefully (log and continue to next category)

### Step 3: Parse RSS Response

For each successful response, parse the RSS/XML:
1. Extract each `<item>` element
2. For each item, extract:
   - `title`: Paper title (clean up any newlines/extra whitespace)
   - `link`: ArXiv abstract page URL
   - `description`: Paper abstract (may contain HTML, strip tags)
   - `dc:creator`: Author list (comma-separated)
   - `arxiv:primary_category`: Primary category
   - `pubDate` or `dc:date`: Publication date

### Step 4: Extract ArXiv ID

From the link URL, extract the arXiv ID:
- Pattern: `https://arxiv.org/abs/{arxiv_id}`
- Example: `https://arxiv.org/abs/2401.12345` → `2401.12345`

### Step 5: Construct PDF URL

Build the PDF URL from the arXiv ID:
- Pattern: `https://arxiv.org/pdf/{arxiv_id}.pdf`

### Step 6: Filter by Date

Filter papers to only include those published within `days_back`:
1. Parse the publication date
2. Compare against current date minus `days_back`
3. Exclude papers older than the cutoff

### Step 7: Deduplicate

Papers may appear in multiple categories. Deduplicate by arXiv ID, keeping the first occurrence.

### Step 8: Build Output

Return structured output with:
- List of ArxivPaper objects
- Total count
- List of successfully fetched categories

## Output Schema

```json
{
  "papers": [
    {
      "arxiv_id": "2401.12345",
      "title": "Advances in Large Language Model Reasoning",
      "authors": ["Alice Smith", "Bob Jones"],
      "abstract": "We present a novel approach to...",
      "categories": ["cs.AI", "cs.CL"],
      "published_date": "2026-01-25",
      "pdf_url": "https://arxiv.org/pdf/2401.12345.pdf",
      "abstract_url": "https://arxiv.org/abs/2401.12345"
    }
  ],
  "total_fetched": 42,
  "categories_fetched": ["cs.AI", "cs.LG", "cs.CL"]
}
```

## Success Criteria

- [ ] At least one category successfully fetched
- [ ] Papers have valid arXiv IDs
- [ ] Papers have non-empty titles and abstracts
- [ ] Date filtering applied correctly
- [ ] No duplicate papers in output

## Failure Handling

| Error Type | Handling Strategy |
|------------|-------------------|
| Network timeout | Log warning, continue to next category |
| Invalid RSS | Log error, skip category |
| All categories fail | Return empty list with error flag |
| Parse error on item | Skip item, continue processing |

## Examples

### Example 1: Default Fetch

**Input:**
```json
{
  "categories": ["cs.AI", "cs.LG"],
  "max_results": 10,
  "days_back": 1
}
```

**Output:**
```json
{
  "papers": [
    {
      "arxiv_id": "2601.15234",
      "title": "Efficient Fine-tuning of Large Language Models via LoRA Variants",
      "authors": ["Jane Doe", "John Smith"],
      "abstract": "We propose an improved method for parameter-efficient fine-tuning...",
      "categories": ["cs.LG", "cs.AI"],
      "published_date": "2026-01-26",
      "pdf_url": "https://arxiv.org/pdf/2601.15234.pdf",
      "abstract_url": "https://arxiv.org/abs/2601.15234"
    }
  ],
  "total_fetched": 1,
  "categories_fetched": ["cs.AI", "cs.LG"]
}
```

### Example 2: Single Category

**Input:**
```json
{
  "categories": ["cs.CL"],
  "max_results": 5,
  "days_back": 7
}
```

**Output:**
```json
{
  "papers": [
    {
      "arxiv_id": "2601.14567",
      "title": "Multilingual Instruction Tuning for Low-Resource Languages",
      "authors": ["Research Team"],
      "abstract": "This paper addresses the challenge of...",
      "categories": ["cs.CL"],
      "published_date": "2026-01-24",
      "pdf_url": "https://arxiv.org/pdf/2601.14567.pdf",
      "abstract_url": "https://arxiv.org/abs/2601.14567"
    }
  ],
  "total_fetched": 1,
  "categories_fetched": ["cs.CL"]
}
```

### Example 3: No Recent Papers

**Input:**
```json
{
  "categories": ["cs.AI"],
  "max_results": 10,
  "days_back": 0
}
```

**Output:**
```json
{
  "papers": [],
  "total_fetched": 0,
  "categories_fetched": ["cs.AI"]
}
```

## Related Skills

- [analyze-arxiv-paper](../../diagnostic/analyze-arxiv-paper/SKILL.md) - Analyze fetched papers for digest inclusion
- [fetch-rss-feeds](../fetch-rss-feeds/SKILL.md) - General RSS feed fetching

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-27 | Initial version |
