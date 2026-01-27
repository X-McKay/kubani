---
name: fetch-github-trending
version: "1.0.0"
description: >
  Fetch trending AI/ML repositories from GitHub. Identifies popular new tools,
  libraries, and projects gaining traction in the AI community for tool spotlight
  sections in news digests.
metadata:
  domain: news
  category: collection
  mcp-servers: []
  requires-approval: false
  confidence: 0.75
input:
  - name: language
    type: str
    default: ""
    description: Filter by programming language (e.g., "python", "rust"). Empty for all languages.
  - name: since
    type: str
    default: "weekly"
    description: Time range - "daily", "weekly", or "monthly"
  - name: topics
    type: list[str]
    default: ["machine-learning", "deep-learning", "llm", "artificial-intelligence", "nlp", "transformers"]
    description: GitHub topics to search for AI-relevant repos
  - name: min_stars
    type: int
    default: 100
    description: Minimum star count to consider
  - name: max_results
    type: int
    default: 20
    description: Maximum repos to return
output:
  - name: repos
    type: list[GithubRepo]
    description: List of trending repos with name, description, stars, language, topics, url
  - name: total_found
    type: int
    description: Total matching repos found
  - name: topics_searched
    type: list[str]
    description: Topics that were searched
---

# Fetch GitHub Trending

Discover trending AI/ML repositories on GitHub for tool spotlights and community highlights.

## When to Use

- Daily/weekly collection of trending AI tools
- Finding new libraries and frameworks gaining popularity
- Identifying projects for tool spotlight sections
- Keywords: github, trending, tools, libraries, repositories, open source

## Prerequisites

- Network access to GitHub API (api.github.com)
- GitHub API has rate limits (60 requests/hour unauthenticated, 5000/hour authenticated)

## Input Schema

```json
{
  "language": "python",
  "since": "weekly",
  "topics": ["machine-learning", "llm"],
  "min_stars": 100,
  "max_results": 20
}
```

## Actions

### Step 1: Build GitHub Search Query

Construct a GitHub search query combining:
1. Topics from the input list (OR-ed together)
2. Language filter if specified
3. Star count minimum
4. Created or pushed date filter based on `since`

Query pattern:
```
topic:machine-learning OR topic:llm language:python stars:>100 pushed:>2026-01-20
```

### Step 2: Calculate Date Range

Based on `since` parameter:
- `daily`: pushed in last 1 day
- `weekly`: pushed in last 7 days
- `monthly`: pushed in last 30 days

### Step 3: Query GitHub Search API

Make request to GitHub Search API:
- URL: `https://api.github.com/search/repositories`
- Parameters:
  - `q`: The constructed query
  - `sort`: `stars`
  - `order`: `desc`
  - `per_page`: `max_results`
- Headers:
  - `Accept`: `application/vnd.github.v3+json`
  - `User-Agent`: `Kubani-News-Collector`

### Step 4: Parse Response

For each repository in the response, extract:
1. `full_name`: Owner/repo format (e.g., "huggingface/transformers")
2. `name`: Repository name
3. `description`: Repository description
4. `html_url`: GitHub URL
5. `stargazers_count`: Current star count
6. `forks_count`: Fork count
7. `language`: Primary language
8. `topics`: List of topics
9. `created_at`: Creation date
10. `pushed_at`: Last push date
11. `open_issues_count`: Open issues

### Step 5: Calculate Trending Score

For each repo, calculate a trending score:
```
score = stars + (forks * 2) + (recent_stars_estimate * 10)
```

Where `recent_stars_estimate` is approximated from the star velocity.

### Step 6: Filter AI-Relevant

Apply additional filtering to ensure AI relevance:
- Check if any topic matches AI keywords
- Check if description contains AI-related terms
- Exclude forks unless they have significant independent activity

### Step 7: Sort and Limit

Sort by trending score descending, limit to `max_results`.

### Step 8: Build Output

Return structured output with repo details.

## Output Schema

```json
{
  "repos": [
    {
      "full_name": "owner/repo-name",
      "name": "repo-name",
      "description": "A powerful LLM inference library",
      "url": "https://github.com/owner/repo-name",
      "stars": 15234,
      "forks": 1523,
      "language": "Python",
      "topics": ["llm", "inference", "machine-learning"],
      "created_at": "2025-06-15",
      "pushed_at": "2026-01-26",
      "open_issues": 42,
      "trending_score": 18234
    }
  ],
  "total_found": 15,
  "topics_searched": ["machine-learning", "llm"]
}
```

## Success Criteria

- [ ] At least one repo found (if any exist matching criteria)
- [ ] All repos have valid GitHub URLs
- [ ] Repos are sorted by trending score
- [ ] No duplicate repos in output
- [ ] AI-relevance filter applied

## Failure Handling

| Error Type | Handling Strategy |
|------------|-------------------|
| Rate limit exceeded | Return cached results if available, log warning |
| Network timeout | Retry once with exponential backoff |
| Invalid response | Log error, return empty list |
| No results found | Return empty list (not an error) |

## Examples

### Example 1: Weekly Python AI Tools

**Input:**
```json
{
  "language": "python",
  "since": "weekly",
  "topics": ["machine-learning", "llm"],
  "min_stars": 500,
  "max_results": 5
}
```

**Output:**
```json
{
  "repos": [
    {
      "full_name": "example/llm-toolkit",
      "name": "llm-toolkit",
      "description": "A comprehensive toolkit for building LLM applications",
      "url": "https://github.com/example/llm-toolkit",
      "stars": 8500,
      "forks": 420,
      "language": "Python",
      "topics": ["llm", "langchain", "ai"],
      "created_at": "2025-11-01",
      "pushed_at": "2026-01-26",
      "open_issues": 23,
      "trending_score": 12340
    }
  ],
  "total_found": 1,
  "topics_searched": ["machine-learning", "llm"]
}
```

### Example 2: All Languages, Daily

**Input:**
```json
{
  "language": "",
  "since": "daily",
  "topics": ["artificial-intelligence"],
  "min_stars": 100,
  "max_results": 10
}
```

**Output:**
```json
{
  "repos": [
    {
      "full_name": "new-project/ai-agent",
      "name": "ai-agent",
      "description": "Autonomous AI agent framework",
      "url": "https://github.com/new-project/ai-agent",
      "stars": 234,
      "forks": 12,
      "language": "TypeScript",
      "topics": ["ai-agent", "autonomous", "artificial-intelligence"],
      "created_at": "2026-01-25",
      "pushed_at": "2026-01-27",
      "open_issues": 5,
      "trending_score": 480
    }
  ],
  "total_found": 1,
  "topics_searched": ["artificial-intelligence"]
}
```

### Example 3: No Results

**Input:**
```json
{
  "language": "cobol",
  "since": "daily",
  "topics": ["machine-learning"],
  "min_stars": 10000,
  "max_results": 10
}
```

**Output:**
```json
{
  "repos": [],
  "total_found": 0,
  "topics_searched": ["machine-learning"]
}
```

## Related Skills

- [analyze-github-repo](../../diagnostic/analyze-github-repo/SKILL.md) - Deep analysis of individual repos
- [fetch-rss-feeds](../fetch-rss-feeds/SKILL.md) - General content collection

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-27 | Initial version |
