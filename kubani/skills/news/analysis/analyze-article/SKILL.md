---
name: analyze-article
description: >
  Analyze news articles using LLM to extract insights, categorize content,
  identify key entities, and assess importance. Generates concise summaries
  and detects breaking news that requires immediate attention. Use when
  processing collected articles for digest composition or trend analysis.
license: MIT
compatibility: Requires OpenAI-compatible LLM API access
metadata:
  kubani:
    domain: news
    category: analysis
    requires_approval: false
    confidence: 0.90
    mcp_servers: []
    version: "1.0.0"
---

# Analyze Article

Analyze news articles using LLM to extract insights and assess importance.

## When to Use

Use this skill when you need to:
- Generate concise summaries of news articles
- Categorize articles by topic (research, business, product, security, policy)
- Extract key entities (companies, people, technologies, models)
- Assess article importance on a 1-10 scale
- Detect breaking news that requires immediate notification
- Prepare articles for digest composition

## Prerequisites

**Required dependencies:**
- OpenAI-compatible LLM API (vLLM, OpenAI, etc.)
- `openai` Python package

**Input requirements:**
- Article with `title`, `url`, `source` fields
- Optional: `summary` or `content` for analysis
- Optional: `published_date` for temporal context

## Instructions

### Step 1: Prepare Article Content

Extract and prepare the article content for analysis:

```python
def prepare_article(article: dict) -> dict:
    """
    Prepare article for LLM analysis.
    
    Args:
        article: Article with title, url, source, summary
    
    Returns:
        Prepared article with truncated content
    """
    title = article.get("title", "")
    url = article.get("url", "")
    source = article.get("source", "")
    content = article.get("summary", article.get("content", ""))
    
    # Truncate content to avoid token limits (2000 chars ≈ 500 tokens)
    if len(content) > 2000:
        content = content[:2000] + "..."
    
    return {
        "title": title,
        "url": url,
        "source": source,
        "content": content,
    }
```

**Why truncate:** Long articles can exceed LLM context limits and increase costs. The first 2000 characters usually contain the key information.

### Step 2: Create Analysis Prompt

Build a structured prompt that guides the LLM to extract specific insights:

```python
ANALYSIS_PROMPT = """Analyze the following news article and provide:

1. **Summary**: A concise 2-3 sentence summary highlighting the key points.
2. **Category**: One of: research, business, product, security, policy, general
3. **Entities**: List of key entities mentioned (companies, people, technologies, models)
4. **Importance Score**: 1-10 rating where:
   - 1-3: Minor news, incremental updates
   - 4-6: Notable news, meaningful developments
   - 7-8: Important news, significant impact
   - 9-10: Major news, industry-changing announcements
5. **Is Breaking**: True if this is major breaking news that should trigger an immediate alert
6. **Breaking Reason**: If breaking, explain why (e.g., "Major model release", "Security vulnerability")

Consider these factors for importance:
- Source credibility and significance
- Novelty of the information
- Potential industry impact
- Whether this is from an official company announcement
- Security implications

Article:
Title: {title}
Source: {source}
Content: {content}

Respond in JSON format:
{{
    "summary": "...",
    "category": "research|business|product|security|policy|general",
    "entities": ["entity1", "entity2", ...],
    "importance_score": 1-10,
    "is_breaking": true/false,
    "breaking_reason": "..." or null
}}"""
```

### Step 3: Call LLM with Structured Output

Use the LLM API to analyze the article:

```python
from openai import OpenAI
from pydantic import BaseModel

class ArticleAnalysis(BaseModel):
    """Structured output schema for article analysis."""
    summary: str
    category: str
    entities: list[str]
    importance_score: int
    is_breaking: bool
    breaking_reason: str | None = None

def analyze_article_with_llm(article: dict, llm_client: OpenAI) -> ArticleAnalysis:
    """
    Analyze article using LLM with structured output.
    
    Args:
        article: Prepared article dictionary
        llm_client: OpenAI client
    
    Returns:
        ArticleAnalysis with extracted insights
    """
    prompt = ANALYSIS_PROMPT.format(
        title=article["title"],
        source=article["source"],
        content=article["content"],
    )
    
    response = llm_client.chat.completions.create(
        model="gpt-4o-mini",  # Or your model
        messages=[
            {"role": "system", "content": "You are an AI news analyst."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.0,  # Deterministic for consistency
    )
    
    # Parse JSON response
    import json
    result = json.loads(response.choices[0].message.content)
    
    return ArticleAnalysis(**result)
```

### Step 4: Handle Parsing Errors

Implement robust error handling for malformed LLM responses:

```python
def safe_parse_analysis(response_text: str) -> ArticleAnalysis | None:
    """
    Safely parse LLM response with fallback.
    
    Args:
        response_text: Raw LLM response
    
    Returns:
        ArticleAnalysis or None if parsing fails
    """
    try:
        # Try to parse as JSON
        result = json.loads(response_text)
        return ArticleAnalysis(**result)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        import re
        json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
                return ArticleAnalysis(**result)
            except:
                pass
    except Exception as e:
        print(f"Failed to parse analysis: {e}")
    
    return None
```

### Step 5: Create Processed Article

Combine original article data with LLM analysis:

```python
from dataclasses import dataclass
from datetime import datetime, UTC

@dataclass
class ProcessedArticle:
    """Article with LLM analysis."""
    url: str
    title: str
    source: str
    source_category: str
    published_at: datetime | None
    original_summary: str
    ai_summary: str
    category: str
    entities: list[str]
    importance_score: int
    is_breaking: bool
    breaking_reason: str | None
    content_hash: str
    processed_at: datetime

def create_processed_article(
    original: dict,
    analysis: ArticleAnalysis
) -> ProcessedArticle:
    """
    Create processed article from original + analysis.
    
    Args:
        original: Original article dictionary
        analysis: LLM analysis result
    
    Returns:
        ProcessedArticle with combined data
    """
    # Generate content hash for deduplication
    import hashlib
    content = f"{original['title']}:{original['url']}".lower()
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    # Parse published date
    published_at = original.get("published_date")
    if isinstance(published_at, str) and published_at:
        try:
            published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except:
            published_at = None
    
    return ProcessedArticle(
        url=original["url"],
        title=original["title"],
        source=original["source"],
        source_category=original.get("source_category", ""),
        published_at=published_at,
        original_summary=original.get("summary", ""),
        ai_summary=analysis.summary,
        category=analysis.category,
        entities=analysis.entities,
        importance_score=analysis.importance_score,
        is_breaking=analysis.is_breaking,
        breaking_reason=analysis.breaking_reason,
        content_hash=content_hash,
        processed_at=datetime.now(UTC),
    )
```

### Step 6: Batch Processing with Concurrency

Process multiple articles in parallel for efficiency:

```python
import asyncio
from typing import List

async def analyze_articles_batch(
    articles: list[dict],
    llm_client: OpenAI,
    max_workers: int = 8
) -> list[ProcessedArticle]:
    """
    Analyze multiple articles in parallel.
    
    Args:
        articles: List of articles to analyze
        llm_client: OpenAI client
        max_workers: Maximum concurrent LLM calls
    
    Returns:
        List of processed articles
    """
    semaphore = asyncio.Semaphore(max_workers)
    
    async def analyze_one(article: dict) -> ProcessedArticle | None:
        async with semaphore:
            try:
                prepared = prepare_article(article)
                analysis = analyze_article_with_llm(prepared, llm_client)
                return create_processed_article(article, analysis)
            except Exception as e:
                print(f"Failed to analyze {article.get('url')}: {e}")
                return None
    
    # Process all articles concurrently
    tasks = [analyze_one(article) for article in articles]
    results = await asyncio.gather(*tasks)
    
    # Filter out failures
    return [r for r in results if r is not None]
```

## Importance Scoring Guidelines

### Score 1-3: Minor News
- Incremental product updates
- Minor bug fixes or patches
- Routine announcements
- Example: "Company X releases version 1.2.3 with minor improvements"

### Score 4-6: Notable News
- New features or capabilities
- Meaningful partnerships
- Research paper publications
- Example: "New study shows 10% improvement in model efficiency"

### Score 7-8: Important News
- Major product launches
- Significant research breakthroughs
- Important policy changes
- Example: "Company X launches new AI model with novel architecture"

### Score 9-10: Major News
- Industry-changing announcements
- Major security vulnerabilities
- Breakthrough research results
- Regulatory decisions with broad impact
- Example: "GPT-5 released with AGI capabilities"

## Breaking News Criteria

Mark as breaking if ANY of these apply:
- **Major model release** from leading AI companies (OpenAI, Anthropic, Google, Meta)
- **Critical security vulnerability** affecting widely-used AI systems
- **Regulatory action** with immediate industry impact
- **Breakthrough research** that changes fundamental understanding
- **Major acquisition or partnership** between AI leaders

## Common Issues

**Issue: LLM returns malformed JSON**
- **Cause:** Model doesn't follow format instructions
- **Solution:** Use structured output mode or parse with regex fallback

**Issue: Inconsistent importance scores**
- **Cause:** Different models have different scoring tendencies
- **Solution:** Calibrate scores based on model, add examples to prompt

**Issue: Missing entities**
- **Cause:** LLM doesn't recognize domain-specific terms
- **Solution:** Provide entity examples in prompt, use few-shot learning

**Issue: False breaking news alerts**
- **Cause:** Overly sensitive breaking news detection
- **Solution:** Increase importance threshold, add more specific criteria

## Output Format

Return processed article with:
```python
{
    "url": "https://...",
    "title": "Article title",
    "source": "Source name",
    "ai_summary": "LLM-generated summary",
    "category": "research|business|product|security|policy|general",
    "entities": ["OpenAI", "GPT-4", "Sam Altman"],
    "importance_score": 8,
    "is_breaking": false,
    "breaking_reason": null,
    "content_hash": "abc123...",
    "processed_at": "2026-01-31T12:00:00Z"
}
```

## Performance Considerations

- **Batch processing:** Use semaphore to limit concurrent LLM calls (8-16 workers)
- **Content truncation:** Limit to 2000 chars to reduce tokens and costs
- **Caching:** Cache analysis results by content hash to avoid reprocessing
- **Temperature:** Use 0.0 for deterministic, consistent analysis
- **Timeout:** Set reasonable timeouts (30-60 seconds) for LLM calls

## Success Criteria

- All articles have valid summaries and categories
- Importance scores are calibrated and consistent
- Breaking news detection has <5% false positive rate
- Entities are accurately extracted
- Processing completes within reasonable time (< 5 seconds per article)
