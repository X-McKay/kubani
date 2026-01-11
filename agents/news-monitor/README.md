# News Monitor Agent

AI-powered news monitoring agent that aggregates, analyzes, and publishes AI news digests to Discord.

## Features

- **RSS Collection**: Fetches from 20+ curated AI-relevant RSS feeds
- **Content Analysis**: LLM-powered summarization and categorization
- **Trend Detection**: Identifies hot topics and emerging themes
- **Memory System**: Deduplication via mem0/pgvector to avoid republishing
- **Breaking Alerts**: Immediate notifications for high-importance news
- **12-Hour Digests**: Cohesive paragraph-style summaries with embedded citations

## Architecture

```
Temporal Workflow (12hr schedule)
├── RSS Collector Agent     - Fetch from configured feeds
├── Content Analyst Agent   - Summarize, categorize, score importance
├── Trend Analyzer Agent    - Detect hot topics, track momentum
├── Memory System (mem0)    - Deduplication, theme history
├── Digest Composer Agent   - Format cohesive summary with citations
└── Discord Publisher Agent - Post to #ai-news channel
```

## RSS Feeds

Curated sources organized by category:

- **Company Blogs**: OpenAI, Anthropic, Google AI, Meta AI, Microsoft AI, NVIDIA, Hugging Face
- **AI Publications**: MIT Technology Review, VentureBeat, TechCrunch, The Batch
- **Research**: ArXiv cs.AI, cs.LG, cs.CL
- **General Tech**: Hacker News (filtered), Ars Technica, The Verge, Wired
- **Security**: Schneier on Security, The Hacker News

## Usage

```bash
# Run the Temporal worker
news-monitor-worker worker

# Start scheduled 12-hour digests
news-monitor-worker schedule

# Start hourly breaking news checks
news-monitor-worker schedule-breaking

# Start both schedules
news-monitor-worker schedule-all

# Run a single digest (testing)
news-monitor-worker digest
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_MCP_URL` | Discord MCP server URL | `https://discord-mcp.almckay.io/mcp` |
| `DISCORD_CHANNEL` | Discord channel for news | `ai-news` |
| `TEMPORAL_HOST` | Temporal server address | `temporal-frontend.temporal.svc.cluster.local:7233` |
| `VLLM_API_URL` | vLLM API endpoint | `http://llm-api.vllm.svc.cluster.local:8000/v1` |
| `VLLM_MODEL` | LLM model name | `Qwen/Qwen3-14B-FP8` |
| `MEMORY_PG_HOST` | PostgreSQL host | `postgresql.database.svc.cluster.local` |
| `MEMORY_PG_PASSWORD` | PostgreSQL password | Required |

## Building

```bash
# Build Docker image
earthly +docker

# Build and push
earthly --push +push --VERSION=main-abc123

# Run tests
earthly +test

# Run linting
earthly +lint
```

## Development

```bash
cd agents/news-monitor
uv sync
uv run pytest
uv run ruff check src/ tests/
```
