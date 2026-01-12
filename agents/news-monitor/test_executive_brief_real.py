#!/usr/bin/env python3
"""
Quick test script to verify ExecutiveBrief format with real data from Qdrant.

This bypasses Temporal and LLM calls to test the digest format directly.
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


async def main():
    print("Starting test...", flush=True)

    # Import after path setup
    print("Importing modules...", flush=True)
    from news_monitor.digest.executive_brief import ExecutiveBriefComposer
    from news_monitor.memory import query_articles_since
    from news_monitor.models import ProcessedArticle, TrendingTopic, TrendStatus

    print("  - All modules imported", flush=True)

    print("=" * 70, flush=True)
    print("ExecutiveBrief Real Data Test", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)

    # Query recent articles from Qdrant (last 24 hours)
    print("Querying recent articles from Qdrant...", flush=True)
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    article_dicts = query_articles_since(cutoff)

    if not article_dicts:
        print("No articles found in the last 24 hours!", flush=True)
        print("Trying 48 hours...", flush=True)
        cutoff = datetime.now(UTC) - timedelta(hours=48)
        article_dicts = query_articles_since(cutoff)

    if not article_dicts:
        print("No articles found. Cannot test with real data.", flush=True)
        return

    print(f"Found {len(article_dicts)} articles", flush=True)
    print(flush=True)

    # Convert to ProcessedArticle objects
    import contextlib

    articles = []
    for data in article_dicts:
        with contextlib.suppress(Exception):
            articles.append(ProcessedArticle(**data))

    print(f"Parsed {len(articles)} articles", flush=True)
    print(flush=True)

    # Sample of article titles
    print("Sample articles:", flush=True)
    for i, article in enumerate(articles[:5]):
        title = article.title[:60] if article.title else "No title"
        print(f"  {i + 1}. {title}...", flush=True)
    print(flush=True)

    # Create mock trends based on article categories
    print("Creating trends from article categories...", flush=True)
    category_counts: dict[str, int] = {}
    for article in articles:
        cat = article.category or "uncategorized"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    trends = []
    now = datetime.now(UTC)
    for category, count in sorted(category_counts.items(), key=lambda x: -x[1])[:5]:
        trends.append(
            TrendingTopic(
                topic=category.replace("_", " ").title(),
                article_count=count,
                status=TrendStatus.RISING if count < 5 else TrendStatus.HOT,
                key_entities=[],
                summary=f"Articles about {category}",
                first_seen=cutoff,
                last_seen=now,
            )
        )

    print(f"Created {len(trends)} trends", flush=True)
    print(flush=True)

    # Compose digest with ExecutiveBrief format
    print("Composing ExecutiveBrief digest...", flush=True)
    composer = ExecutiveBriefComposer()
    period_start = cutoff
    period_end = datetime.now(UTC)

    executive_brief = await composer.compose_executive_brief(
        articles=articles,
        trends=trends,
        period_start=period_start,
        period_end=period_end,
    )

    formatted = executive_brief.to_discord_message()

    print(flush=True)
    print("=" * 70, flush=True)
    print("EXECUTIVE BRIEF OUTPUT (Monolithic):", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)
    print(formatted, flush=True)
    print(flush=True)

    # Test granular messages
    print("=" * 70, flush=True)
    print("GRANULAR MESSAGES (For feedback isolation):", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)

    granular_messages = executive_brief.to_granular_messages()
    print(f"Generated {len(granular_messages)} separate messages:", flush=True)
    print(flush=True)

    for i, msg in enumerate(granular_messages, 1):
        category = msg.get("category", "unknown")
        reactions = msg.get("reactions", [])
        content = msg.get("content", "")

        print(f"--- Message {i}: {category} ---", flush=True)
        print(f"Reactions: {' '.join(reactions)}", flush=True)
        print(content, flush=True)
        print(flush=True)

    print("=" * 70, flush=True)
    print("Test complete!", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
