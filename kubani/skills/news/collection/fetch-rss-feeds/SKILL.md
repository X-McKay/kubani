---
name: fetch-rss-feeds
version: "1.0.0"
description: >
  Collect articles from configured RSS feeds. Fetches from multiple AI-focused
  news sources including tech blogs, research feeds, and company announcements.
  Filters articles by age and AI relevance.
metadata:
  domain: news
  category: collection
  mcp-servers: []
  requires-approval: false
  confidence: 0.9
input:
  - name: max_age_hours
    type: int
    default: 24
    description: Maximum age of articles to collect
  - name: filter_ai_relevant
    type: bool
    default: true
    description: Only include AI-relevant articles
output:
  - name: articles
    type: list[RawArticle]
    description: List of collected articles with title, url, source, published_date
---

# Fetch RSS Feeds

Collect articles from all configured RSS news feeds.

## Preconditions

- Network access to RSS feed URLs
- Feed configuration loaded from feeds.py

## Actions

### Step 1: Load Feed Configuration

Load all enabled RSS feeds from configuration, sorted by priority.

Feed categories:
- **Company Blogs** (priority 10): OpenAI, Anthropic, Google AI, Meta AI
- **AI-Focused** (priority 8-9): MIT Tech Review, VentureBeat, TechCrunch
- **Research** (priority 6-7): ArXiv AI, ML, and NLP feeds
- **General Tech** (priority 6-8): Hacker News, Ars Technica, The Verge
- **Security** (priority 5-6): Schneier on Security, The Hacker News

### Step 2: Fetch Each Feed in Parallel

For each enabled feed:
1. Make HTTP GET request to feed URL
2. Parse RSS/Atom XML response
3. Extract article entries with:
   - `title`: Article headline
   - `url`: Link to full article
   - `source`: Feed name
   - `published_date`: Publication timestamp
   - `summary`: Article description/excerpt

Handle errors gracefully - log and continue if individual feeds fail.

### Step 3: Filter by Age

Remove articles older than `max_age_hours` based on `published_date`.

### Step 4: Filter AI Relevance

If `filter_ai_relevant` is true, keep only articles matching AI keywords:
- Model names: GPT, Claude, Gemini, Llama
- Companies: OpenAI, Anthropic, DeepMind, Hugging Face
- Concepts: LLM, machine learning, neural network, AI agent
- Applications: chatbot, copilot, text-to-image

### Step 5: Deduplicate by URL

Remove duplicate articles (same URL from multiple feeds).

## Success Criteria

- At least one feed successfully fetched
- Articles have required fields (title, url, published_date)
- No duplicate URLs in output
