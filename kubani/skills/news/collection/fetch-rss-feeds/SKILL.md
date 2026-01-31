---
name: fetch-rss-feeds
description: >
  Fetch articles from RSS/Atom feeds with retry logic and error handling.
  Parses feed XML, extracts article metadata (title, URL, date, summary),
  and handles malformed feeds gracefully. Use when collecting content from
  RSS feeds, news sources, or blog aggregators.
license: MIT
compatibility: Requires feedparser and httpx Python packages
metadata:
  kubani:
    domain: news
    category: collection
    requires_approval: false
    confidence: 0.95
    mcp_servers: []
    version: "1.0.0"
---

# Fetch RSS Feeds

Fetch and parse articles from RSS/Atom feeds with robust error handling.

## When to Use

Use this skill when you need to:
- Collect articles from RSS or Atom feeds
- Parse feed XML and extract article metadata
- Handle feed parsing errors gracefully
- Fetch multiple feeds in parallel or sequence

## Prerequisites

**Required Python packages:**
- `feedparser` - RSS/Atom feed parsing
- `httpx` - HTTP client with timeout and retry support

**Input requirements:**
- List of feed URLs or feed configurations
- Optional: User-Agent header for feeds that block bots
- Optional: Timeout and retry settings

## Instructions

### Step 1: Prepare Feed List

Create a list of feeds to fetch. Each feed should include:
- `url`: The RSS/Atom feed URL
- `name`: Human-readable feed name (for logging)
- `category`: Feed category (e.g., "company_blogs", "research")

Example:
```python
feeds = [
    {"url": "https://openai.com/blog/rss/", "name": "OpenAI Blog", "category": "company_blogs"},
    {"url": "https://www.anthropic.com/blog/rss", "name": "Anthropic Blog", "category": "company_blogs"},
]
```

### Step 2: Configure HTTP Client

Set up an HTTP client with appropriate headers and timeouts:

```python
import httpx

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
client = httpx.Client(timeout=30.0, follow_redirects=True, headers=headers)
```

**Why this matters:** Many feeds block requests without a User-Agent header or with bot-like user agents.

### Step 3: Fetch and Parse Each Feed

For each feed:

1. **Make HTTP request:**
   ```python
   response = client.get(feed["url"])
   response.raise_for_status()
   ```

2. **Parse with feedparser:**
   ```python
   import feedparser
   parsed = feedparser.parse(response.text)
   ```

3. **Check for parse errors:**
   ```python
   if parsed.bozo and parsed.bozo_exception:
       # Log warning but continue - feed may still be usable
       print(f"Parse warning: {parsed.bozo_exception}")
   ```

4. **Extract articles from entries:**
   ```python
   for entry in parsed.entries:
       article = {
           "title": entry.get("title", "").strip(),
           "url": entry.get("link", ""),
           "summary": entry.get("summary", entry.get("description", "")).strip(),
           "author": entry.get("author"),
           "published_date": parse_date(entry),
       }
   ```

### Step 4: Parse Published Dates

RSS feeds use different date fields. Handle both:

```python
from datetime import datetime, UTC

def parse_date(entry):
    """Parse published date from RSS entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=UTC)
    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime(*entry.updated_parsed[:6], tzinfo=UTC)
    return None
```

### Step 5: Handle Errors Gracefully

Wrap each feed fetch in try-except to prevent one failed feed from stopping the entire collection:

```python
failed_feeds = []
all_articles = []

for feed in feeds:
    try:
        articles = fetch_feed(feed)
        all_articles.extend(articles)
    except Exception as e:
        print(f"Failed to fetch {feed['name']}: {e}")
        failed_feeds.append(feed['name'])
```

### Step 6: Return Results

Return a structured result with:
- List of articles
- Count of successful feeds
- List of failed feeds (for monitoring)

```python
return {
    "articles": all_articles,
    "sources_fetched": len(feeds) - len(failed_feeds),
    "failed_feeds": failed_feeds,
}
```

## Common Issues

**Issue: 403 Forbidden errors**
- **Cause:** Feed blocks requests without proper User-Agent
- **Solution:** Use a browser-like User-Agent header

**Issue: Timeout errors**
- **Cause:** Feed server is slow or unresponsive
- **Solution:** Increase timeout or skip slow feeds

**Issue: Parse errors (bozo=True)**
- **Cause:** Malformed XML in feed
- **Solution:** Log warning but continue - feedparser often recovers

**Issue: Missing required fields**
- **Cause:** Feed doesn't include title or link
- **Solution:** Skip entries without required fields

## Output Format

Each article should include:
- `title` (string, required): Article headline
- `url` (string, required): Link to full article
- `source` (string, required): Feed name
- `published_date` (datetime, optional): Publication timestamp
- `summary` (string, optional): Article excerpt/description
- `author` (string, optional): Article author
- `tags` (list, optional): Article tags/categories

## Performance Considerations

- **Parallel fetching:** Use `asyncio` or threading for faster collection
- **Caching:** Cache feed responses to avoid redundant requests
- **Rate limiting:** Respect feed server rate limits
- **Timeout:** Set reasonable timeouts (15-30 seconds)

## Success Criteria

- At least one feed successfully fetched
- Articles have required fields (title, url)
- Failed feeds are logged but don't stop collection
- Parse errors are handled gracefully
