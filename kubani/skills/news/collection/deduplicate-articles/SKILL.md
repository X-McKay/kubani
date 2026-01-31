---
name: deduplicate-articles
description: >
  Remove duplicate articles using URL-based deduplication with Redis persistence.
  Handles both within-run duplicates (same article from multiple feeds) and
  cross-run duplicates (articles seen in previous runs). Use when collecting
  from multiple overlapping feeds or maintaining state across collection runs.
license: MIT
compatibility: Requires Redis for persistent deduplication (optional fallback to in-memory)
metadata:
  kubani:
    domain: news
    category: collection
    requires_approval: false
    confidence: 0.98
    mcp_servers: []
    version: "1.0.0"
---

# Deduplicate Articles

Remove duplicate articles using URL-based deduplication with optional persistence.

## When to Use

Use this skill when you need to:
- Remove duplicate articles from multiple feeds
- Track previously seen articles across runs
- Prevent reprocessing the same content
- Handle overlapping feed sources

## Prerequisites

**Optional dependencies:**
- Redis server (for persistent deduplication)
- `redis` Python package

**Input requirements:**
- List of articles with `url` field
- Optional: Redis connection details for persistence

## Instructions

### Step 1: Within-Run Deduplication

Remove duplicates within a single collection run using a set:

```python
def deduplicate_within_run(articles: list[dict]) -> list[dict]:
    """
    Remove duplicate articles by URL within a single run.
    
    Args:
        articles: List of articles with 'url' field
    
    Returns:
        Deduplicated list (first occurrence kept)
    """
    seen_urls = set()
    unique_articles = []
    
    for article in articles:
        url = article.get("url")
        if not url:
            continue  # Skip articles without URL
        
        if url not in seen_urls:
            seen_urls.add(url)
            unique_articles.append(article)
    
    return unique_articles
```

**Why this matters:** The same article may appear in multiple feeds (e.g., Hacker News and original source).

### Step 2: Cross-Run Deduplication (Redis)

Track seen URLs across runs using Redis with TTL:

```python
import redis
from datetime import timedelta

class DedupService:
    """Persistent deduplication using Redis."""
    
    def __init__(self, redis_url: str, namespace: str = "articles", ttl_days: int = 7):
        """
        Initialize deduplication service.
        
        Args:
            redis_url: Redis connection URL
            namespace: Key namespace for isolation
            ttl_days: How long to remember URLs (days)
        """
        self.redis = redis.from_url(redis_url)
        self.namespace = namespace
        self.ttl_seconds = ttl_days * 24 * 3600
    
    def is_seen(self, url: str) -> bool:
        """Check if URL has been seen before."""
        key = f"{self.namespace}:{url}"
        return self.redis.exists(key) > 0
    
    def mark_seen(self, url: str) -> None:
        """Mark URL as seen with TTL."""
        key = f"{self.namespace}:{url}"
        self.redis.setex(key, self.ttl_seconds, "1")
    
    def filter_unseen(self, urls: list[str]) -> list[str]:
        """
        Filter list to only unseen URLs.
        
        Args:
            urls: List of URLs to check
        
        Returns:
            List of URLs not seen before
        """
        unseen = []
        for url in urls:
            if not self.is_seen(url):
                unseen.append(url)
        return unseen
    
    def mark_seen_batch(self, urls: list[str]) -> None:
        """Mark multiple URLs as seen (batch operation)."""
        pipe = self.redis.pipeline()
        for url in urls:
            key = f"{self.namespace}:{url}"
            pipe.setex(key, self.ttl_seconds, "1")
        pipe.execute()
```

### Step 3: Combined Deduplication Pipeline

Combine both approaches for maximum efficiency:

```python
def deduplicate_articles(
    articles: list[dict],
    dedup_service: DedupService | None = None
) -> tuple[list[dict], dict]:
    """
    Deduplicate articles using two-phase approach.
    
    Phase 1: Within-run deduplication (fast, in-memory)
    Phase 2: Cross-run deduplication (persistent, Redis)
    
    Args:
        articles: List of articles to deduplicate
        dedup_service: Optional persistent dedup service
    
    Returns:
        Tuple of (unique_articles, stats)
    """
    original_count = len(articles)
    
    # Phase 1: Within-run dedup
    run_unique = deduplicate_within_run(articles)
    within_run_dupes = original_count - len(run_unique)
    
    # Phase 2: Cross-run dedup (if Redis available)
    if dedup_service:
        urls = [a["url"] for a in run_unique]
        unseen_urls = dedup_service.filter_unseen(urls)
        unseen_url_set = set(unseen_urls)
        
        unique_articles = [a for a in run_unique if a["url"] in unseen_url_set]
        cross_run_dupes = len(run_unique) - len(unique_articles)
        
        # Mark new articles as seen
        if unique_articles:
            new_urls = [a["url"] for a in unique_articles]
            dedup_service.mark_seen_batch(new_urls)
    else:
        unique_articles = run_unique
        cross_run_dupes = 0
    
    stats = {
        "original_count": original_count,
        "unique_count": len(unique_articles),
        "within_run_dupes": within_run_dupes,
        "cross_run_dupes": cross_run_dupes,
        "total_dupes": within_run_dupes + cross_run_dupes,
    }
    
    return unique_articles, stats
```

### Step 4: Graceful Degradation

Handle Redis unavailability gracefully:

```python
def create_dedup_service(redis_url: str | None) -> DedupService | None:
    """
    Create dedup service with fallback to in-memory.
    
    Args:
        redis_url: Redis connection URL (optional)
    
    Returns:
        DedupService if Redis available, None otherwise
    """
    if not redis_url:
        print("No Redis URL provided - using in-memory dedup only")
        return None
    
    try:
        service = DedupService(redis_url)
        # Test connection
        service.redis.ping()
        print("Connected to Redis for persistent deduplication")
        return service
    except Exception as e:
        print(f"Failed to connect to Redis: {e}")
        print("Falling back to in-memory deduplication")
        return None
```

### Step 5: Configure TTL

Choose appropriate TTL based on collection frequency:

**Daily collection:**
- TTL: 7 days (remember articles for a week)
- Rationale: Prevents reprocessing recent articles

**Hourly collection:**
- TTL: 24 hours (remember articles for a day)
- Rationale: Shorter memory window for frequent runs

**Weekly collection:**
- TTL: 30 days (remember articles for a month)
- Rationale: Longer memory for infrequent runs

```python
# Example: Daily collection with 7-day memory
dedup_service = DedupService(
    redis_url="redis://localhost:6379",
    namespace="feed_collector",
    ttl_days=7
)
```

## Advanced Features

### URL Normalization

Normalize URLs before deduplication to catch variations:

```python
from urllib.parse import urlparse, urlunparse

def normalize_url(url: str) -> str:
    """
    Normalize URL for consistent deduplication.
    
    - Remove query parameters (except essential ones)
    - Remove fragments (#section)
    - Lowercase domain
    - Remove trailing slashes
    """
    parsed = urlparse(url)
    
    # Lowercase domain
    netloc = parsed.netloc.lower()
    
    # Remove trailing slash from path
    path = parsed.path.rstrip("/")
    
    # Remove query and fragment
    normalized = urlunparse((
        parsed.scheme,
        netloc,
        path,
        "",  # params
        "",  # query
        "",  # fragment
    ))
    
    return normalized
```

### Content-Based Deduplication

For cases where URLs differ but content is the same:

```python
import hashlib

def content_hash(article: dict) -> str:
    """
    Generate hash from article content.
    
    Uses title + first 200 chars of summary.
    """
    title = article.get("title", "").lower().strip()
    summary = article.get("summary", "")[:200].lower().strip()
    
    content = f"{title}|{summary}"
    return hashlib.md5(content.encode()).hexdigest()

def deduplicate_by_content(articles: list[dict]) -> list[dict]:
    """Remove articles with duplicate content."""
    seen_hashes = set()
    unique = []
    
    for article in articles:
        h = content_hash(article)
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique.append(article)
    
    return unique
```

### Monitoring and Metrics

Track deduplication effectiveness:

```python
def log_dedup_stats(stats: dict) -> None:
    """Log deduplication statistics."""
    print(f"Deduplication Results:")
    print(f"  Original: {stats['original_count']}")
    print(f"  Unique: {stats['unique_count']}")
    print(f"  Within-run dupes: {stats['within_run_dupes']}")
    print(f"  Cross-run dupes: {stats['cross_run_dupes']}")
    print(f"  Total removed: {stats['total_dupes']}")
    
    if stats['original_count'] > 0:
        dupe_rate = stats['total_dupes'] / stats['original_count'] * 100
        print(f"  Duplicate rate: {dupe_rate:.1f}%")
```

## Common Issues

**Issue: High duplicate rate**
- **Cause:** Multiple overlapping feeds or frequent collection
- **Solution:** Increase TTL or reduce feed overlap

**Issue: Redis connection errors**
- **Cause:** Redis server unavailable
- **Solution:** Implement graceful fallback to in-memory dedup

**Issue: Memory usage growth**
- **Cause:** TTL too long or high article volume
- **Solution:** Reduce TTL or use Redis eviction policies

**Issue: Same article different URLs**
- **Cause:** URL variations (query params, redirects)
- **Solution:** Implement URL normalization or content-based dedup

## Output Format

Return deduplicated articles with statistics:

```python
{
    "articles": unique_articles,
    "stats": {
        "original_count": 100,
        "unique_count": 75,
        "within_run_dupes": 15,
        "cross_run_dupes": 10,
        "total_dupes": 25,
    }
}
```

## Performance Considerations

- **Batch operations:** Use Redis pipelines for batch marking
- **Memory usage:** In-memory dedup uses O(n) memory for URLs
- **Redis performance:** Use connection pooling for high throughput
- **TTL strategy:** Balance memory usage vs. duplicate prevention

## Success Criteria

- No duplicate URLs in output
- Previously seen articles are filtered out
- Deduplication stats are logged
- Graceful fallback if Redis unavailable
- Performance scales with article volume
