---
name: filter-duplicates
version: "1.0.0"
description: >
  Fast pre-filter to remove articles already processed. Uses Redis for O(1) URL
  lookup to avoid wasting LLM calls on previously seen content.
metadata:
  domain: news
  category: collection
  mcp-servers: []
  requires-approval: false
  confidence: 0.95
input:
  - name: articles
    type: list[RawArticle]
    description: Articles to filter
output:
  - name: new_articles
    type: list[RawArticle]
    description: Articles not previously seen
  - name: seen_count
    type: int
    description: Number of articles filtered as duplicates
---

# Filter Duplicates

Remove articles that have already been processed using fast Redis lookup.

## Preconditions

- Redis connection available
- Articles have valid URL field

## Actions

### Step 1: Connect to Redis

Establish connection to Redis for URL lookup.

### Step 2: Check Each Article URL

For each article in input:
1. Generate URL hash/key
2. Check if key exists in Redis `seen_urls` set
3. If not seen, add to output list

### Step 3: Return Filtered Results

Return list of articles not previously seen, along with count of filtered duplicates.

## Success Criteria

- All article URLs checked against Redis
- No previously processed articles in output
- New articles preserved for processing
