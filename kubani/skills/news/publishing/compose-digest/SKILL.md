---
name: compose-digest
description: >
  Compose a formatted news digest from analyzed articles and trends. Groups
  articles by category, highlights trending topics, and formats for readability.
  Supports multiple output formats (Markdown, Discord, HTML). Use after analysis
  to create daily/weekly digest publications.
license: MIT
compatibility: No external dependencies required
metadata:
  kubani:
    domain: news
    category: publishing
    requires_approval: false
    confidence: 0.95
    mcp_servers: []
    version: "1.0.0"
---

# Compose Digest

Compose a formatted news digest from analyzed articles and trends.

## When to Use

Use this skill when you need to:
- Create daily or weekly news digests
- Format articles for publication
- Group articles by category or topic
- Highlight trending topics
- Generate human-readable summaries

## Prerequisites

**Input requirements:**
- List of processed articles with summaries and categories
- Optional: Trending topics from trend detection
- Optional: Breaking news articles
- Optional: Digest configuration (title, date range, format)

## Instructions

### Step 1: Group Articles by Category

Organize articles into logical sections:

```python
from collections import defaultdict
from typing import Dict, List

def group_articles_by_category(articles: list[dict]) -> dict[str, list[dict]]:
    """
    Group articles by category.
    
    Args:
        articles: List of processed articles
    
    Returns:
        Dictionary mapping category -> articles
    """
    grouped = defaultdict(list)
    
    for article in articles:
        category = article.get("category", "general")
        grouped[category].append(article)
    
    # Sort articles within each category by importance
    for category in grouped:
        grouped[category].sort(
            key=lambda a: a.get("importance_score", 0),
            reverse=True
        )
    
    return dict(grouped)
```

### Step 2: Create Digest Header

Generate a header with metadata and summary:

```python
from datetime import datetime, UTC

def create_digest_header(
    title: str,
    date_range: tuple[datetime, datetime] | None = None,
    article_count: int = 0,
    trend_count: int = 0
) -> str:
    """
    Create digest header with metadata.
    
    Args:
        title: Digest title
        date_range: Optional (start, end) date range
        article_count: Number of articles
        trend_count: Number of trends
    
    Returns:
        Formatted header string
    """
    header = f"# {title}\n\n"
    
    # Add date range
    if date_range:
        start, end = date_range
        header += f"**Period:** {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}\n"
    else:
        header += f"**Date:** {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
    
    # Add stats
    header += f"**Articles:** {article_count} | **Trends:** {trend_count}\n\n"
    header += "---\n\n"
    
    return header
```

### Step 3: Format Trending Topics Section

Create a section highlighting trending topics:

```python
def format_trending_section(trends: list[dict]) -> str:
    """
    Format trending topics section.
    
    Args:
        trends: List of trending topics
    
    Returns:
        Formatted trending section
    """
    if not trends:
        return ""
    
    section = "## 🔥 Trending Topics\n\n"
    
    # Group by status
    by_status = defaultdict(list)
    for trend in trends:
        status = trend.get("status", "established")
        by_status[status].append(trend)
    
    # Breaking trends
    if "breaking" in by_status:
        section += "### Breaking\n"
        for trend in by_status["breaking"][:3]:  # Top 3
            section += f"- **{trend['topic']}** ({trend['mention_count']} mentions)\n"
        section += "\n"
    
    # Hot trends
    if "hot" in by_status:
        section += "### Hot\n"
        for trend in by_status["hot"][:5]:  # Top 5
            section += f"- **{trend['topic']}** ({trend['mention_count']} mentions)\n"
        section += "\n"
    
    # Rising trends
    if "rising" in by_status:
        section += "### Rising\n"
        for trend in by_status["rising"][:5]:  # Top 5
            section += f"- **{trend['topic']}** ({trend['mention_count']} mentions)\n"
        section += "\n"
    
    section += "---\n\n"
    return section
```

### Step 4: Format Article Sections

Create sections for each category:

```python
# Category display names and emojis
CATEGORY_INFO = {
    "research": ("🔬 Research", "Latest research papers and breakthroughs"),
    "business": ("💼 Business", "Company news and market developments"),
    "product": ("🚀 Products", "New releases and product updates"),
    "security": ("🔒 Security", "Security vulnerabilities and updates"),
    "policy": ("⚖️ Policy", "Regulations and policy changes"),
    "general": ("📰 General", "Other AI news and updates"),
}

def format_article_section(
    category: str,
    articles: list[dict],
    max_articles: int = 10
) -> str:
    """
    Format a category section with articles.
    
    Args:
        category: Article category
        articles: Articles in this category
        max_articles: Maximum articles to include
    
    Returns:
        Formatted section string
    """
    if not articles:
        return ""
    
    # Get category info
    title, description = CATEGORY_INFO.get(
        category,
        (f"📌 {category.title()}", "")
    )
    
    section = f"## {title}\n\n"
    if description:
        section += f"*{description}*\n\n"
    
    # Add articles
    for i, article in enumerate(articles[:max_articles], 1):
        section += format_article_entry(article, i)
    
    section += "\n"
    return section

def format_article_entry(article: dict, index: int) -> str:
    """
    Format a single article entry.
    
    Args:
        article: Article to format
        index: Article number in section
    
    Returns:
        Formatted article string
    """
    title = article.get("title", "")
    source = article.get("source", "")
    summary = article.get("ai_summary", article.get("summary", ""))
    url = article.get("url", "")
    importance = article.get("importance_score", 0)
    
    # Importance indicator
    if importance >= 9:
        indicator = "🔴"  # Critical
    elif importance >= 7:
        indicator = "🟠"  # Important
    elif importance >= 5:
        indicator = "🟡"  # Notable
    else:
        indicator = "⚪"  # Minor
    
    entry = f"### {index}. {indicator} {title}\n\n"
    entry += f"**Source:** {source}\n\n"
    entry += f"{summary}\n\n"
    entry += f"[Read more]({url})\n\n"
    
    return entry
```

### Step 5: Compose Full Digest

Combine all sections into final digest:

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class DigestConfig:
    """Configuration for digest composition."""
    title: str = "AI News Digest"
    date_range: tuple[datetime, datetime] | None = None
    include_trends: bool = True
    include_breaking: bool = True
    max_articles_per_category: int = 10
    category_order: list[str] = None
    
    def __post_init__(self):
        if self.category_order is None:
            self.category_order = [
                "security",    # Security first (most urgent)
                "product",     # Product launches
                "research",    # Research papers
                "business",    # Business news
                "policy",      # Policy changes
                "general",     # Everything else
            ]

def compose_digest(
    articles: list[dict],
    trends: list[dict] | None = None,
    breaking: list[dict] | None = None,
    config: DigestConfig | None = None
) -> str:
    """
    Compose a complete news digest.
    
    Args:
        articles: List of processed articles
        trends: Optional trending topics
        breaking: Optional breaking news articles
        config: Optional digest configuration
    
    Returns:
        Formatted digest as Markdown string
    """
    if config is None:
        config = DigestConfig()
    
    digest = ""
    
    # Header
    digest += create_digest_header(
        title=config.title,
        date_range=config.date_range,
        article_count=len(articles),
        trend_count=len(trends) if trends else 0
    )
    
    # Breaking news section (if any)
    if config.include_breaking and breaking:
        digest += format_breaking_section(breaking)
    
    # Trending topics section
    if config.include_trends and trends:
        digest += format_trending_section(trends)
    
    # Group articles by category
    grouped = group_articles_by_category(articles)
    
    # Add category sections in specified order
    for category in config.category_order:
        if category in grouped:
            digest += format_article_section(
                category,
                grouped[category],
                config.max_articles_per_category
            )
    
    # Add any remaining categories not in order
    for category, articles in grouped.items():
        if category not in config.category_order:
            digest += format_article_section(
                category,
                articles,
                config.max_articles_per_category
            )
    
    # Footer
    digest += create_digest_footer()
    
    return digest

def format_breaking_section(breaking: list[dict]) -> str:
    """Format breaking news section."""
    if not breaking:
        return ""
    
    section = "## 🚨 Breaking News\n\n"
    
    for article in breaking[:5]:  # Top 5 breaking
        title = article.get("title", "")
        summary = article.get("ai_summary", "")
        url = article.get("url", "")
        breaking_reason = article.get("breaking_reason", "")
        
        section += f"### {title}\n\n"
        if breaking_reason:
            section += f"*{breaking_reason}*\n\n"
        section += f"{summary}\n\n"
        section += f"[Read more]({url})\n\n"
    
    section += "---\n\n"
    return section

def create_digest_footer() -> str:
    """Create digest footer."""
    footer = "---\n\n"
    footer += "*This digest was automatically generated by Kubani AI News Monitor.*\n"
    return footer
```

### Step 6: Format for Different Platforms

Convert digest to platform-specific formats:

```python
def format_for_discord(digest_markdown: str) -> str:
    """
    Format digest for Discord (character limits, emoji support).
    
    Discord has 2000 char limit per message, so split if needed.
    
    Args:
        digest_markdown: Markdown digest
    
    Returns:
        Discord-formatted string (may need splitting)
    """
    # Discord supports most markdown, but limit length
    if len(digest_markdown) <= 2000:
        return digest_markdown
    
    # Split into chunks
    chunks = []
    current_chunk = ""
    
    for line in digest_markdown.split("\n"):
        if len(current_chunk) + len(line) + 1 > 1900:  # Leave buffer
            chunks.append(current_chunk)
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

def format_for_html(digest_markdown: str) -> str:
    """
    Convert digest to HTML.
    
    Args:
        digest_markdown: Markdown digest
    
    Returns:
        HTML string
    """
    import markdown
    
    html = markdown.markdown(
        digest_markdown,
        extensions=['extra', 'codehilite']
    )
    
    # Wrap in HTML template
    html_doc = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AI News Digest</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #666; border-bottom: 2px solid #ddd; padding-bottom: 5px; }}
        h3 {{ color: #888; }}
        a {{ color: #0066cc; }}
    </style>
</head>
<body>
{html}
</body>
</html>"""
    
    return html_doc
```

## Digest Formatting Best Practices

### Structure
1. **Header** - Title, date, stats
2. **Breaking News** - Urgent stories first
3. **Trending Topics** - What's hot right now
4. **Category Sections** - Organized by topic
5. **Footer** - Attribution, links

### Prioritization
- Security issues first (most urgent)
- Product launches second (time-sensitive)
- Research third (valuable but not urgent)
- Business/policy fourth (context)
- General last (everything else)

### Length Guidelines
- **Daily digest:** 10-20 articles, 2-3 pages
- **Weekly digest:** 30-50 articles, 5-10 pages
- **Breaking alerts:** 1-3 articles, immediate

### Readability
- Use emojis for visual scanning
- Include importance indicators (🔴🟠🟡⚪)
- Keep summaries to 2-3 sentences
- Provide direct links to sources

## Common Issues

**Issue: Digest too long**
- **Cause:** Too many articles or verbose summaries
- **Solution:** Limit articles per category, use max_articles parameter

**Issue: Poor category distribution**
- **Cause:** Most articles in one category
- **Solution:** Adjust category order, balance article selection

**Issue: Missing important stories**
- **Cause:** Importance-based sorting buries good stories
- **Solution:** Review importance scoring, adjust thresholds

**Issue: Duplicate content**
- **Cause:** Same story in multiple categories
- **Solution:** Deduplicate before grouping, use primary category only

## Output Format

Return formatted digest as string:
```markdown
# AI News Digest

**Date:** 2026-01-31
**Articles:** 25 | **Trends:** 8

---

## 🚨 Breaking News

### GPT-5 Released with AGI Capabilities

*Major model release from leading AI company*

OpenAI has released GPT-5, claiming significant advances...

[Read more](https://...)

---

## 🔥 Trending Topics

### Breaking
- **GPT-5** (15 mentions)
- **AGI** (12 mentions)

### Hot
- **Claude 4** (8 mentions)
- **Gemini Pro** (7 mentions)

---

## 🔒 Security

### 1. 🔴 Critical Vulnerability in Popular AI Framework

**Source:** Security Research Blog

Researchers have discovered a critical vulnerability...

[Read more](https://...)

---
```

## Performance Considerations

- **Grouping:** O(n) where n=number of articles
- **Sorting:** O(n log n) per category
- **Formatting:** O(n) for string concatenation
- **Platform conversion:** O(n) for markdown parsing
- **Optimization:** Use string builder for large digests

## Success Criteria

- Digest is well-structured and readable
- Articles are grouped logically by category
- Important stories are prominently featured
- Trending topics are highlighted
- Format is appropriate for target platform
- Length is reasonable for consumption
