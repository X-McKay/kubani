---
name: detect-trends
description: >
  Detect trending topics across multiple articles by analyzing entity co-occurrence,
  temporal patterns, and cross-source mentions. Identifies emerging trends, hot
  topics, and fading stories. Use after analyzing articles to identify what topics
  are gaining momentum in the AI news landscape.
license: MIT
compatibility: No external dependencies required
metadata:
  kubani:
    domain: news
    category: analysis
    requires_approval: false
    confidence: 0.85
    mcp_servers: []
    version: "1.0.0"
---

# Detect Trends

Detect trending topics across multiple analyzed articles.

## When to Use

Use this skill when you need to:
- Identify topics mentioned across multiple sources
- Detect emerging trends in AI news
- Track topic momentum over time
- Prioritize topics for digest composition
- Identify fading stories that are losing relevance

## Prerequisites

**Input requirements:**
- List of processed articles with `entities` field
- Optional: Historical trend data for momentum calculation
- Optional: Temporal information (`published_at`) for trend analysis

## Instructions

### Step 1: Extract Entity Mentions

Count entity occurrences across all articles:

```python
from collections import Counter
from typing import List, Dict

def extract_entity_mentions(articles: list[dict]) -> dict[str, list[str]]:
    """
    Extract entity mentions with source tracking.
    
    Args:
        articles: List of processed articles with entities
    
    Returns:
        Dictionary mapping entity -> list of article URLs
    """
    entity_mentions = {}
    
    for article in articles:
        entities = article.get("entities", [])
        url = article.get("url", "")
        
        for entity in entities:
            # Normalize entity (lowercase, strip whitespace)
            normalized = entity.lower().strip()
            
            if normalized not in entity_mentions:
                entity_mentions[normalized] = []
            
            entity_mentions[normalized].append(url)
    
    return entity_mentions
```

### Step 2: Calculate Entity Scores

Score entities based on mention frequency and source diversity:

```python
def calculate_entity_scores(entity_mentions: dict[str, list[str]]) -> dict[str, float]:
    """
    Calculate scores for each entity.
    
    Score = mention_count * source_diversity_bonus
    
    Args:
        entity_mentions: Entity -> list of article URLs
    
    Returns:
        Entity -> score mapping
    """
    scores = {}
    
    for entity, urls in entity_mentions.items():
        mention_count = len(urls)
        unique_sources = len(set(urls))
        
        # Bonus for appearing in multiple sources
        diversity_bonus = 1.0 + (unique_sources - 1) * 0.2
        
        score = mention_count * diversity_bonus
        scores[entity] = score
    
    return scores
```

### Step 3: Identify Trending Topics

Filter entities to find those that qualify as trends:

```python
from dataclasses import dataclass
from datetime import datetime, UTC

@dataclass
class TrendingTopic:
    """A trending topic."""
    topic: str
    status: str  # breaking, hot, rising, established, fading
    article_count: int
    mention_count: int
    sources: list[str]
    related_articles: list[str]
    first_seen: datetime
    last_seen: datetime
    momentum: float

def identify_trending_topics(
    entity_mentions: dict[str, list[str]],
    entity_scores: dict[str, float],
    min_mentions: int = 2,
    min_articles: int = 2
) -> list[TrendingTopic]:
    """
    Identify entities that qualify as trending topics.
    
    Args:
        entity_mentions: Entity -> article URLs
        entity_scores: Entity -> scores
        min_mentions: Minimum mentions to qualify
        min_articles: Minimum articles to qualify
    
    Returns:
        List of trending topics
    """
    trends = []
    now = datetime.now(UTC)
    
    for entity, urls in entity_mentions.items():
        mention_count = len(urls)
        unique_articles = len(set(urls))
        
        # Filter by thresholds
        if mention_count < min_mentions or unique_articles < min_articles:
            continue
        
        # Determine status based on mention count
        if mention_count >= 10:
            status = "hot"
        elif mention_count >= 5:
            status = "rising"
        else:
            status = "established"
        
        trend = TrendingTopic(
            topic=entity,
            status=status,
            article_count=unique_articles,
            mention_count=mention_count,
            sources=list(set(urls)),
            related_articles=urls,
            first_seen=now,
            last_seen=now,
            momentum=entity_scores.get(entity, 0.0),
        )
        
        trends.append(trend)
    
    # Sort by momentum (highest first)
    trends.sort(key=lambda t: t.momentum, reverse=True)
    
    return trends
```

### Step 4: Calculate Temporal Momentum

Track how trends are evolving over time:

```python
from datetime import timedelta

def calculate_momentum(
    current_trends: list[TrendingTopic],
    historical_trends: dict[str, TrendingTopic] | None = None
) -> list[TrendingTopic]:
    """
    Calculate momentum for trends based on historical data.
    
    Momentum = (current_mentions - historical_mentions) / time_delta
    
    Args:
        current_trends: Current trending topics
        historical_trends: Previous trending topics (optional)
    
    Returns:
        Trends with updated momentum scores
    """
    if not historical_trends:
        # No historical data - use current mention count as momentum
        for trend in current_trends:
            trend.momentum = float(trend.mention_count)
        return current_trends
    
    for trend in current_trends:
        if trend.topic in historical_trends:
            prev = historical_trends[trend.topic]
            
            # Calculate time delta
            time_delta = (trend.last_seen - prev.last_seen).total_seconds() / 3600  # hours
            if time_delta == 0:
                time_delta = 1  # Avoid division by zero
            
            # Calculate mention growth
            mention_growth = trend.mention_count - prev.mention_count
            
            # Momentum = growth rate per hour
            trend.momentum = mention_growth / time_delta
            
            # Update status based on momentum
            if trend.momentum > 5:
                trend.status = "breaking"
            elif trend.momentum > 2:
                trend.status = "hot"
            elif trend.momentum > 0:
                trend.status = "rising"
            elif trend.momentum < -1:
                trend.status = "fading"
            else:
                trend.status = "established"
        else:
            # New trend - use mention count as momentum
            trend.momentum = float(trend.mention_count)
            trend.status = "rising"
    
    return current_trends
```

### Step 5: Group Related Topics

Identify related topics that should be grouped together:

```python
def group_related_topics(trends: list[TrendingTopic]) -> dict[str, list[str]]:
    """
    Group related topics based on article overlap.
    
    Topics are related if they appear in the same articles.
    
    Args:
        trends: List of trending topics
    
    Returns:
        Dictionary mapping primary topic -> related topics
    """
    related = {}
    
    for i, trend1 in enumerate(trends):
        related_topics = []
        
        for j, trend2 in enumerate(trends):
            if i == j:
                continue
            
            # Calculate article overlap
            articles1 = set(trend1.related_articles)
            articles2 = set(trend2.related_articles)
            overlap = len(articles1 & articles2)
            
            # If >50% overlap, consider related
            min_articles = min(len(articles1), len(articles2))
            if overlap / min_articles > 0.5:
                related_topics.append(trend2.topic)
        
        if related_topics:
            related[trend1.topic] = related_topics
    
    return related
```

### Step 6: Filter Noise

Remove topics that are too generic or not meaningful:

```python
# Common stopwords that aren't meaningful trends
STOPWORDS = {
    "ai", "artificial intelligence", "machine learning", "ml",
    "technology", "tech", "company", "research", "model",
    "system", "data", "algorithm", "software", "hardware"
}

def filter_noise(trends: list[TrendingTopic]) -> list[TrendingTopic]:
    """
    Filter out generic or non-meaningful trends.
    
    Args:
        trends: List of trending topics
    
    Returns:
        Filtered list of meaningful trends
    """
    filtered = []
    
    for trend in trends:
        topic_lower = trend.topic.lower()
        
        # Skip stopwords
        if topic_lower in STOPWORDS:
            continue
        
        # Skip very short topics (likely acronyms or noise)
        if len(trend.topic) < 3:
            continue
        
        # Skip topics that are just numbers
        if trend.topic.isdigit():
            continue
        
        filtered.append(trend)
    
    return filtered
```

## Trend Status Definitions

### Breaking (Momentum > 5)
- Rapidly emerging topic
- Mentioned in 10+ articles in last hour
- Requires immediate attention
- Example: Major model release announcement

### Hot (Momentum 2-5)
- Actively trending topic
- Mentioned in 5-10 articles recently
- High current interest
- Example: Ongoing product launch coverage

### Rising (Momentum 0-2)
- Emerging topic gaining traction
- Mentioned in 2-5 articles
- Growing interest
- Example: New research area gaining attention

### Established (Momentum ≈ 0)
- Stable topic with consistent coverage
- Mentioned regularly but not growing
- Ongoing interest
- Example: Established products or companies

### Fading (Momentum < -1)
- Topic losing relevance
- Fewer mentions than before
- Declining interest
- Example: Old news or resolved issues

## Advanced Features

### Temporal Bucketing

Analyze trends within time windows:

```python
from datetime import timedelta

def analyze_trends_by_timeframe(
    articles: list[dict],
    window_hours: int = 24
) -> dict[str, list[TrendingTopic]]:
    """
    Analyze trends within time windows.
    
    Args:
        articles: Articles with published_at timestamps
        window_hours: Size of time window in hours
    
    Returns:
        Dictionary mapping timeframe -> trends
    """
    from datetime import datetime, UTC
    
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=window_hours)
    
    # Filter articles by timeframe
    recent_articles = [
        a for a in articles
        if a.get("published_at") and a["published_at"] > cutoff
    ]
    
    # Detect trends in recent articles
    entity_mentions = extract_entity_mentions(recent_articles)
    entity_scores = calculate_entity_scores(entity_mentions)
    trends = identify_trending_topics(entity_mentions, entity_scores)
    
    return {f"last_{window_hours}h": trends}
```

### Category-Specific Trends

Detect trends within specific categories:

```python
def detect_category_trends(
    articles: list[dict],
    category: str
) -> list[TrendingTopic]:
    """
    Detect trends within a specific category.
    
    Args:
        articles: Articles with category field
        category: Category to analyze (research, business, etc.)
    
    Returns:
        Trends specific to that category
    """
    # Filter articles by category
    category_articles = [
        a for a in articles
        if a.get("category") == category
    ]
    
    # Detect trends
    entity_mentions = extract_entity_mentions(category_articles)
    entity_scores = calculate_entity_scores(entity_mentions)
    trends = identify_trending_topics(entity_mentions, entity_scores)
    
    return trends
```

## Common Issues

**Issue: Too many generic trends**
- **Cause:** Stopword list is incomplete
- **Solution:** Expand stopword list with domain-specific generic terms

**Issue: Missing related topics**
- **Cause:** Overlap threshold too high
- **Solution:** Lower overlap threshold to 30-40%

**Issue: False momentum spikes**
- **Cause:** Irregular collection intervals
- **Solution:** Normalize by time delta, use rolling averages

**Issue: Duplicate topics with different names**
- **Cause:** Entity normalization not catching variations
- **Solution:** Add entity aliasing (e.g., "GPT-4" = "GPT4" = "gpt-4")

## Output Format

Return list of trending topics:
```python
[
    {
        "topic": "GPT-5",
        "status": "breaking",
        "article_count": 15,
        "mention_count": 23,
        "sources": ["https://...", "https://..."],
        "related_articles": ["https://...", ...],
        "momentum": 8.5,
        "first_seen": "2026-01-31T10:00:00Z",
        "last_seen": "2026-01-31T12:00:00Z"
    },
    ...
]
```

## Performance Considerations

- **Entity extraction:** O(n*m) where n=articles, m=entities per article
- **Score calculation:** O(e) where e=unique entities
- **Grouping:** O(t²) where t=number of trends (expensive for many trends)
- **Optimization:** Use sets for article overlap calculations
- **Caching:** Cache entity mentions between runs for momentum calculation

## Success Criteria

- Trends accurately reflect current news landscape
- Breaking/hot topics are identified correctly
- Noise is filtered out (no generic terms)
- Related topics are grouped appropriately
- Momentum scores reflect actual trend velocity
