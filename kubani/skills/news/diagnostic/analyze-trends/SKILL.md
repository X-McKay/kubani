---
name: analyze-trends
version: "1.0.0"
description: >
  Analyze patterns and trends across a batch of articles. Identifies hot topics
  covered by multiple sources, tracks topic momentum, and detects emerging themes.
metadata:
  domain: news
  category: diagnostic
  mcp-servers: []
  requires-approval: false
  confidence: 0.8
input:
  - name: articles
    type: list[ProcessedArticle]
    description: Processed articles with entities extracted
  - name: hot_threshold
    type: int
    default: 3
    description: Minimum sources for a topic to be considered "hot"
  - name: lookback_days
    type: int
    default: 7
    description: Days to look back for historical trend data
output:
  - name: trends
    type: list[TrendingTopic]
    description: Identified trends with status (hot/rising/established/fading)
  - name: entity_clusters
    type: list[EntityCluster]
    description: Groups of entities that frequently appear together
---

# Analyze Trends

Identify trending topics and patterns across news articles.

## Preconditions

- Articles have entities extracted by analyze-article skill
- Memory system (Qdrant) available for historical comparison

## Actions

### Step 1: Extract Topics from Entities

Group articles by shared entities:
- Collect all entities from all articles
- Filter entities shorter than 3 characters
- Map each entity to list of articles mentioning it
- Keep only entities appearing in 2+ articles

### Step 2: Detect Hot Topics

For each topic (entity):
1. Count unique sources covering it
2. If sources >= `hot_threshold` (default 3), mark as HOT
3. Calculate momentum based on source coverage

### Step 3: Compare to Historical Data

Query memory for historical theme data from past `lookback_days`:
- Calculate trend status based on comparison:
  - **BREAKING**: New topic with high immediate coverage
  - **HOT**: Multiple sources covering simultaneously
  - **RISING**: Increasing coverage compared to history
  - **ESTABLISHED**: Consistent coverage over time
  - **FADING**: Decreasing coverage compared to history

### Step 4: Calculate Momentum

For each topic:
```
momentum = (current_article_count - historical_average) / historical_average
```
- Positive momentum: increasing coverage
- Negative momentum: decreasing coverage
- Zero/undefined: new topic or no history

### Step 5: Detect Entity Clusters

Find entities that frequently co-occur in articles:
- Build co-occurrence matrix
- Identify pairs appearing together 2+ times
- Group into clusters with total mention counts

### Step 6: Store Theme for Future Tracking

Store each trend in memory for future comparisons.

## Success Criteria

- Topics correctly grouped by entity
- Hot topics identified (multi-source coverage)
- Trend status accurately reflects momentum
- Entity clusters reveal related concepts

## Trend Status Priority (for sorting)

1. BREAKING - Immediate, new, high-impact
2. HOT - Multiple sources, active coverage
3. RISING - Growing in coverage
4. ESTABLISHED - Ongoing coverage
5. FADING - Decreasing coverage
