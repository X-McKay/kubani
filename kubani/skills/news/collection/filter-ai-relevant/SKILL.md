---
name: filter-ai-relevant
description: >
  Filter articles for AI/ML relevance using keyword matching and pattern detection.
  Identifies articles about AI models, companies, research, and applications.
  Use when filtering general tech news for AI-specific content or reducing
  noise from broad news feeds.
license: MIT
compatibility: No external dependencies required
metadata:
  kubani:
    domain: news
    category: collection
    requires_approval: false
    confidence: 0.85
    mcp_servers: []
    version: "1.0.0"
---

# Filter AI-Relevant Articles

Filter articles for AI/ML relevance using keyword matching.

## When to Use

Use this skill when you need to:
- Filter general tech news for AI-specific content
- Reduce noise from broad RSS feeds
- Identify articles about AI models, companies, or research
- Focus collection on AI/ML topics

## Prerequisites

**Input requirements:**
- List of articles with `title` and `summary` fields
- Optional: Custom keyword list for domain-specific filtering

## Instructions

### Step 1: Define AI Relevance Keywords

Create a comprehensive keyword list covering:

**AI Models and Technologies:**
- Model names: GPT, Claude, Gemini, Llama, PaLM, Mistral, Phi
- Model types: LLM, transformer, diffusion model, neural network
- Techniques: fine-tuning, RLHF, prompt engineering, RAG

**AI Companies:**
- OpenAI, Anthropic, Google DeepMind, Meta AI, Hugging Face
- Microsoft AI, Amazon Bedrock, Cohere, Stability AI

**AI Concepts:**
- Machine learning, deep learning, artificial intelligence
- Natural language processing, computer vision, speech recognition
- Generative AI, multimodal AI, AI agents, autonomous agents

**AI Applications:**
- Chatbot, copilot, AI assistant, code generation
- Text-to-image, text-to-video, text-to-speech
- AI safety, alignment, interpretability

```python
AI_KEYWORDS = [
    # Models
    "gpt", "claude", "gemini", "llama", "palm", "mistral", "phi",
    "llm", "large language model", "transformer", "diffusion",
    
    # Companies
    "openai", "anthropic", "deepmind", "hugging face", "meta ai",
    
    # Concepts
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "generative ai", "ai agent",
    
    # Applications
    "chatbot", "copilot", "text-to-image", "code generation",
]
```

### Step 2: Implement Keyword Matching

Create a function to check if text contains AI keywords:

```python
def is_ai_relevant(text: str, keywords: list[str]) -> bool:
    """
    Check if text contains AI-relevant keywords.
    
    Args:
        text: Text to check (title or summary)
        keywords: List of AI keywords
    
    Returns:
        True if text contains any keyword
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    for keyword in keywords:
        if keyword.lower() in text_lower:
            return True
    
    return False
```

### Step 3: Filter Article List

Apply the filter to both title and summary:

```python
def filter_ai_articles(articles: list[dict]) -> list[dict]:
    """
    Filter articles for AI relevance.
    
    Args:
        articles: List of articles with title and summary
    
    Returns:
        Filtered list of AI-relevant articles
    """
    ai_articles = []
    
    for article in articles:
        title = article.get("title", "")
        summary = article.get("summary", "")
        
        # Check both title and summary
        if is_ai_relevant(title, AI_KEYWORDS) or is_ai_relevant(summary, AI_KEYWORDS):
            ai_articles.append(article)
    
    return ai_articles
```

### Step 4: Log Filtering Stats

Track how many articles were filtered:

```python
original_count = len(articles)
filtered_articles = filter_ai_articles(articles)
filtered_count = original_count - len(filtered_articles)

print(f"Filtered {filtered_count} non-AI articles ({len(filtered_articles)} remaining)")
```

### Step 5: Handle Edge Cases

**Empty or missing fields:**
```python
# Skip articles without title or summary
if not article.get("title") and not article.get("summary"):
    continue
```

**Case sensitivity:**
```python
# Always use case-insensitive matching
text_lower = text.lower()
keyword_lower = keyword.lower()
```

**Partial matches:**
```python
# Use 'in' operator for substring matching
if "machine learning" in text_lower:  # Matches "machine learning" anywhere
    return True
```

## Advanced Filtering

### Category-Specific Filtering

Apply different filters based on feed category:

```python
def should_filter(article: dict, feed_category: str) -> bool:
    """
    Determine if article should be filtered based on category.
    
    Args:
        article: Article to check
        feed_category: Category of source feed
    
    Returns:
        True if article should be filtered
    """
    # Always keep articles from AI-focused feeds
    if feed_category in ["company_blogs", "ai_focused", "research"]:
        return False
    
    # Filter general tech feeds for AI relevance
    if feed_category == "general_tech":
        return not is_ai_relevant(article.get("title", ""), AI_KEYWORDS)
    
    return False
```

### Confidence Scoring

Assign confidence scores based on keyword matches:

```python
def calculate_relevance_score(text: str, keywords: list[str]) -> float:
    """
    Calculate AI relevance score (0.0 to 1.0).
    
    Higher scores indicate stronger AI relevance.
    """
    if not text:
        return 0.0
    
    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text_lower)
    
    # Normalize to 0-1 range (cap at 5 matches)
    return min(matches / 5.0, 1.0)
```

### Negative Keywords

Exclude articles with certain keywords:

```python
NEGATIVE_KEYWORDS = [
    "crypto", "blockchain", "nft",  # Crypto topics
    "stock price", "earnings",      # Financial news
]

def has_negative_keywords(text: str) -> bool:
    """Check if text contains negative keywords."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in NEGATIVE_KEYWORDS)
```

## Common Issues

**Issue: Too aggressive filtering**
- **Cause:** Keyword list is too narrow
- **Solution:** Add more keywords, include synonyms

**Issue: False positives**
- **Cause:** Keywords match unrelated content (e.g., "meta" matches "metadata")
- **Solution:** Use more specific keywords or phrase matching

**Issue: Missing relevant articles**
- **Cause:** Article uses different terminology
- **Solution:** Expand keyword list, add domain-specific terms

## Output Format

Return filtered articles with optional relevance metadata:

```python
{
    "articles": filtered_articles,
    "original_count": len(articles),
    "filtered_count": len(filtered_articles),
    "filter_rate": (original_count - len(filtered_articles)) / original_count,
}
```

## Performance Considerations

- **Keyword list size:** Larger lists increase processing time
- **Text length:** Longer summaries take more time to process
- **Optimization:** Use set lookups for faster keyword checking
- **Caching:** Cache keyword matching results for repeated checks

## Success Criteria

- Filter removes non-AI articles from general tech feeds
- AI-focused feeds are not over-filtered
- Filtering stats are logged for monitoring
- No articles with clear AI keywords are removed
