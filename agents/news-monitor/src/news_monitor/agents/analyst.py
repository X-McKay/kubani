"""
Content Analyst Agent - Processes and enriches articles using LLM.

Responsible for:
- Generating concise summaries
- Extracting entities (companies, people, technologies)
- Classifying articles by category
- Assigning importance scores
- Detecting breaking news
"""

import logging
import os
from datetime import datetime

from openai import OpenAI
from pydantic import BaseModel

from news_monitor.memory import generate_content_hash
from news_monitor.models import ArticleCategory, ProcessedArticle, RawArticle

logger = logging.getLogger(__name__)


class ArticleAnalysis(BaseModel):
    """Structured output from article analysis."""

    summary: str
    category: str
    entities: list[str]
    importance_score: int
    is_breaking: bool
    breaking_reason: str | None = None


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


class ContentAnalystAgent:
    """Agent for analyzing and enriching article content."""

    def __init__(self):
        """Initialize the analyst with LLM client."""
        self.client = OpenAI(
            api_key="not-needed",
            base_url=os.environ.get(
                "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
            ),
        )
        self.model = os.environ.get("VLLM_MODEL", "Qwen/Qwen3-14B-FP8")

    def analyze_article(self, article: RawArticle) -> ProcessedArticle:
        """
        Analyze a single article and produce enriched ProcessedArticle.

        Args:
            article: The raw article to analyze

        Returns:
            ProcessedArticle with AI-generated summary, entities, etc.
        """
        try:
            # Prepare content (title + summary)
            content = f"{article.title}\n\n{article.summary}"
            if len(content) > 2000:
                content = content[:2000] + "..."

            # Call LLM for analysis
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI news analyst. Analyze articles and provide structured analysis in JSON format.",
                    },
                    {
                        "role": "user",
                        "content": ANALYSIS_PROMPT.format(
                            title=article.title,
                            source=article.source,
                            content=content,
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=500,
            )

            # Parse response
            response_text = response.choices[0].message.content
            analysis = self._parse_analysis(response_text)

            # Map category string to enum
            category_map = {
                "research": ArticleCategory.RESEARCH,
                "business": ArticleCategory.BUSINESS,
                "product": ArticleCategory.PRODUCT,
                "security": ArticleCategory.SECURITY,
                "policy": ArticleCategory.POLICY,
                "general": ArticleCategory.GENERAL,
            }
            category = category_map.get(analysis.category.lower(), ArticleCategory.GENERAL)

            # Boost importance for company blog posts (official announcements)
            importance = analysis.importance_score
            if article.source_category == "company_blogs" and importance < 7:
                importance = min(importance + 2, 10)

            return ProcessedArticle(
                url=article.url,
                title=article.title,
                source=article.source,
                source_category=article.source_category,
                published_at=article.published_at,
                original_summary=article.summary,
                ai_summary=analysis.summary,
                category=category,
                entities=analysis.entities,
                importance_score=importance,
                is_breaking=analysis.is_breaking,
                content_hash=generate_content_hash(article.title, article.url),
                processed_at=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(f"Failed to analyze article '{article.title[:50]}...': {e}")
            # Return basic processed article without AI enrichment
            return ProcessedArticle(
                url=article.url,
                title=article.title,
                source=article.source,
                source_category=article.source_category,
                published_at=article.published_at,
                original_summary=article.summary,
                ai_summary=article.summary,  # Use original summary
                category=ArticleCategory.GENERAL,
                entities=[],
                importance_score=5,
                is_breaking=False,
                content_hash=generate_content_hash(article.title, article.url),
                processed_at=datetime.utcnow(),
            )

    def _parse_analysis(self, response_text: str) -> ArticleAnalysis:
        """Parse LLM response into ArticleAnalysis."""
        import json

        # Try to extract JSON from response
        try:
            # Find JSON in response (may have markdown code blocks)
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            data = json.loads(response_text)

            return ArticleAnalysis(
                summary=data.get("summary", ""),
                category=data.get("category", "general"),
                entities=data.get("entities", []),
                importance_score=min(max(data.get("importance_score", 5), 1), 10),
                is_breaking=data.get("is_breaking", False),
                breaking_reason=data.get("breaking_reason"),
            )

        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from response: {response_text[:200]}")
            return ArticleAnalysis(
                summary="",
                category="general",
                entities=[],
                importance_score=5,
                is_breaking=False,
            )

    def analyze_batch(self, articles: list[RawArticle]) -> list[ProcessedArticle]:
        """
        Analyze multiple articles.

        Args:
            articles: List of raw articles to analyze

        Returns:
            List of processed articles
        """
        processed = []
        for i, article in enumerate(articles):
            logger.debug(f"Analyzing article {i+1}/{len(articles)}: {article.title[:50]}...")
            processed_article = self.analyze_article(article)
            processed.append(processed_article)

        return processed
