---
name: identify-breaking-news
description: >
  Identify breaking news articles that require immediate notification based on
  importance scores, source credibility, and content analysis. Filters for
  high-impact stories from authoritative sources. Use after article analysis
  to determine which stories warrant real-time alerts.
license: MIT
compatibility: No external dependencies required
metadata:
  kubani:
    domain: news
    category: analysis
    requires_approval: false
    confidence: 0.92
    mcp_servers: []
    version: "1.0.0"
---

# Identify Breaking News

Identify articles that qualify as breaking news requiring immediate notification.

## When to Use

Use this skill when you need to:
- Filter analyzed articles for breaking news
- Determine which stories warrant immediate alerts
- Prioritize high-impact news for real-time notification
- Avoid alert fatigue from non-critical news

## Prerequisites

**Input requirements:**
- List of processed articles with `importance_score` and `is_breaking` fields
- Optional: Source credibility ratings
- Optional: Historical breaking news data for calibration

## Instructions

### Step 1: Define Breaking News Criteria

Establish clear criteria for what qualifies as breaking news:

```python
from dataclasses import dataclass

@dataclass
class BreakingNewsCriteria:
    """Criteria for identifying breaking news."""
    
    # Minimum importance score (1-10)
    min_importance_score: int = 8
    
    # Authoritative sources that lower the threshold
    authoritative_sources: set[str] = None
    
    # Keywords that indicate breaking news
    breaking_keywords: set[str] = None
    
    # Categories that are more likely to be breaking
    priority_categories: set[str] = None
    
    def __post_init__(self):
        if self.authoritative_sources is None:
            self.authoritative_sources = {
                "openai blog", "anthropic blog", "google ai blog",
                "meta ai blog", "microsoft ai blog", "deepmind",
                "arxiv", "nature", "science"
            }
        
        if self.breaking_keywords is None:
            self.breaking_keywords = {
                "release", "launch", "announce", "breakthrough",
                "vulnerability", "security", "critical", "urgent",
                "breaking", "major", "significant"
            }
        
        if self.priority_categories is None:
            self.priority_categories = {
                "security", "product", "research"
            }
```

### Step 2: Score Article Breaking Potential

Calculate a breaking news score for each article:

```python
def calculate_breaking_score(
    article: dict,
    criteria: BreakingNewsCriteria
) -> float:
    """
    Calculate breaking news score (0-100).
    
    Higher scores indicate more likely to be breaking news.
    
    Args:
        article: Processed article with analysis
        criteria: Breaking news criteria
    
    Returns:
        Breaking score (0-100)
    """
    score = 0.0
    
    # Base score from importance (0-50 points)
    importance = article.get("importance_score", 5)
    score += importance * 5  # Scale to 0-50
    
    # Source credibility bonus (0-20 points)
    source = article.get("source", "").lower()
    if any(auth in source for auth in criteria.authoritative_sources):
        score += 20
    
    # LLM breaking flag (0-20 points)
    if article.get("is_breaking", False):
        score += 20
    
    # Category bonus (0-10 points)
    category = article.get("category", "")
    if category in criteria.priority_categories:
        score += 10
    
    # Keyword bonus (0-10 points)
    title = article.get("title", "").lower()
    summary = article.get("ai_summary", "").lower()
    content = title + " " + summary
    
    keyword_matches = sum(
        1 for keyword in criteria.breaking_keywords
        if keyword in content
    )
    score += min(keyword_matches * 2, 10)
    
    return min(score, 100)  # Cap at 100
```

### Step 3: Filter for Breaking News

Apply threshold to identify breaking articles:

```python
def identify_breaking_articles(
    articles: list[dict],
    criteria: BreakingNewsCriteria,
    threshold: float = 70.0
) -> list[dict]:
    """
    Identify articles that qualify as breaking news.
    
    Args:
        articles: List of processed articles
        criteria: Breaking news criteria
        threshold: Minimum breaking score to qualify
    
    Returns:
        List of breaking news articles
    """
    breaking = []
    
    for article in articles:
        score = calculate_breaking_score(article, criteria)
        
        if score >= threshold:
            # Add breaking score to article
            article["breaking_score"] = score
            breaking.append(article)
    
    # Sort by breaking score (highest first)
    breaking.sort(key=lambda a: a["breaking_score"], reverse=True)
    
    return breaking
```

### Step 4: Deduplicate Breaking News

Avoid multiple alerts for the same story:

```python
def deduplicate_breaking_news(
    breaking_articles: list[dict],
    seen_hashes: set[str] | None = None
) -> tuple[list[dict], set[str]]:
    """
    Remove duplicate breaking news stories.
    
    Args:
        breaking_articles: List of breaking articles
        seen_hashes: Set of previously seen content hashes
    
    Returns:
        Tuple of (unique_articles, updated_seen_hashes)
    """
    if seen_hashes is None:
        seen_hashes = set()
    
    unique = []
    
    for article in breaking_articles:
        content_hash = article.get("content_hash")
        
        if not content_hash:
            # Generate hash if missing
            import hashlib
            content = f"{article['title']}:{article['url']}".lower()
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            article["content_hash"] = content_hash
        
        if content_hash not in seen_hashes:
            seen_hashes.add(content_hash)
            unique.append(article)
    
    return unique, seen_hashes
```

### Step 5: Rate Limit Notifications

Prevent alert fatigue by limiting notification frequency:

```python
from datetime import datetime, timedelta, UTC

class BreakingNewsRateLimiter:
    """Rate limiter for breaking news notifications."""
    
    def __init__(
        self,
        max_per_hour: int = 5,
        max_per_day: int = 20
    ):
        """
        Initialize rate limiter.
        
        Args:
            max_per_hour: Maximum notifications per hour
            max_per_day: Maximum notifications per day
        """
        self.max_per_hour = max_per_hour
        self.max_per_day = max_per_day
        self.notification_times: list[datetime] = []
    
    def can_notify(self) -> bool:
        """Check if we can send another notification."""
        now = datetime.now(UTC)
        
        # Remove old notifications
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)
        
        self.notification_times = [
            t for t in self.notification_times
            if t > day_ago
        ]
        
        # Count recent notifications
        hour_count = sum(1 for t in self.notification_times if t > hour_ago)
        day_count = len(self.notification_times)
        
        # Check limits
        if hour_count >= self.max_per_hour:
            return False
        if day_count >= self.max_per_day:
            return False
        
        return True
    
    def record_notification(self):
        """Record that a notification was sent."""
        self.notification_times.append(datetime.now(UTC))
    
    def filter_by_rate_limit(
        self,
        breaking_articles: list[dict]
    ) -> list[dict]:
        """
        Filter breaking articles by rate limit.
        
        Returns only articles that can be notified.
        """
        filtered = []
        
        for article in breaking_articles:
            if self.can_notify():
                filtered.append(article)
                self.record_notification()
            else:
                break  # Stop when limit reached
        
        return filtered
```

### Step 6: Format Breaking News Alert

Create formatted alert message:

```python
def format_breaking_alert(article: dict) -> str:
    """
    Format breaking news article for notification.
    
    Args:
        article: Breaking news article
    
    Returns:
        Formatted alert message
    """
    title = article.get("title", "")
    source = article.get("source", "")
    summary = article.get("ai_summary", "")
    url = article.get("url", "")
    importance = article.get("importance_score", 0)
    breaking_reason = article.get("breaking_reason", "")
    
    # Build alert message
    alert = f"🚨 **BREAKING NEWS** (Importance: {importance}/10)\n\n"
    alert += f"**{title}**\n\n"
    alert += f"Source: {source}\n\n"
    
    if breaking_reason:
        alert += f"Why breaking: {breaking_reason}\n\n"
    
    alert += f"{summary}\n\n"
    alert += f"Read more: {url}"
    
    return alert
```

## Breaking News Score Components

### Importance Score (0-50 points)
- Based on LLM-assigned importance (1-10)
- Scaled to 0-50 point range
- Primary indicator of news significance

### Source Credibility (0-20 points)
- Authoritative sources get full 20 points
- Official company blogs, research journals
- Reduces false positives from unreliable sources

### LLM Breaking Flag (0-20 points)
- LLM explicitly marked as breaking
- Based on content analysis
- Catches stories with breaking characteristics

### Category Bonus (0-10 points)
- Security, product, research categories
- Higher likelihood of breaking news
- Prioritizes impactful categories

### Keyword Bonus (0-10 points)
- Breaking-related keywords in title/summary
- "release", "launch", "breakthrough", "critical"
- Captures urgency signals

## Threshold Guidelines

### Score 90-100: Critical Breaking News
- Major model releases (GPT-5, Claude 4)
- Critical security vulnerabilities
- Regulatory decisions with immediate impact
- **Action:** Immediate notification, highest priority

### Score 80-89: High-Priority Breaking News
- Significant product launches
- Important research breakthroughs
- Major partnerships or acquisitions
- **Action:** Notify within 15 minutes

### Score 70-79: Notable Breaking News
- Meaningful product updates
- Interesting research results
- Industry developments
- **Action:** Notify within 1 hour

### Score <70: Not Breaking
- Regular news, incremental updates
- **Action:** Include in regular digest only

## Common Issues

**Issue: Too many false positives**
- **Cause:** Threshold too low or criteria too broad
- **Solution:** Increase threshold to 75-80, tighten criteria

**Issue: Missing important stories**
- **Cause:** Threshold too high or missing authoritative sources
- **Solution:** Lower threshold to 65-70, expand source list

**Issue: Alert fatigue**
- **Cause:** Too frequent notifications
- **Solution:** Implement rate limiting (5/hour, 20/day)

**Issue: Duplicate alerts**
- **Cause:** Same story from multiple sources
- **Solution:** Use content hash deduplication

## Output Format

Return breaking news articles with scores:
```python
[
    {
        "url": "https://...",
        "title": "GPT-5 Released with AGI Capabilities",
        "source": "OpenAI Blog",
        "ai_summary": "...",
        "importance_score": 10,
        "is_breaking": true,
        "breaking_reason": "Major model release from leading AI company",
        "breaking_score": 95.0,
        "category": "product",
        "content_hash": "abc123..."
    },
    ...
]
```

## Performance Considerations

- **Scoring:** O(n) where n=number of articles
- **Deduplication:** O(n) with hash set lookups
- **Rate limiting:** O(m) where m=notification history size
- **Optimization:** Use sets for keyword matching
- **Caching:** Cache breaking scores for reprocessing

## Success Criteria

- Breaking news is identified within 15 minutes of publication
- False positive rate < 10% (verified by manual review)
- No duplicate alerts for the same story
- Rate limits prevent alert fatigue
- Critical stories (score >90) are never missed
