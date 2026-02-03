"""
Research Collector Agent - Skills-centric arXiv and GitHub collection.

Thin orchestrator that delegates to collection skills:
- fetch-arxiv-papers: Fetch recent AI/ML papers from arXiv
- fetch-github-trending: Fetch trending AI repositories from GitHub

Usage:
    from kubani.agents.research_collector import ResearchCollectorAgent

    agent = ResearchCollectorAgent()
    result = await agent.collect_all()
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kubani.agents._base import SkillsOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class ArxivPaper:
    """Paper fetched from arXiv."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    pdf_url: str
    published_date: str | None = None


@dataclass
class GitHubRepo:
    """Repository fetched from GitHub."""

    full_name: str
    name: str
    description: str
    url: str
    stars: int
    forks: int
    language: str | None
    topics: list[str]
    trending_score: float = 0.0


@dataclass
class ResearchCollectionResult:
    """Result from running collection."""

    papers: list[ArxivPaper] = field(default_factory=list)
    repos: list[GitHubRepo] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


class ResearchCollectorAgent(SkillsOrchestrator):
    """
    Skills-centric research collector.

    Discovers and delegates to news/collection skills:
    - fetch-arxiv-papers
    - fetch-github-trending
    """

    AGENT_DIR = Path(__file__).parent
    SKILLS_DOMAIN = "news"
    SKILLS_CATEGORY = "collection"

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Research Collector agent."""
        super().__init__(agent_dir)

        # Research-specific configuration
        research_config = self.config.get("research", {})
        self.default_categories = research_config.get(
            "categories", ["cs.AI", "cs.LG", "cs.CL"]
        )
        self.default_topics = research_config.get(
            "topics", ["machine-learning", "llm", "deep-learning"]
        )
        self.default_min_stars = research_config.get("min_stars", 100)

    async def fetch_arxiv_papers(
        self,
        categories: list[str] | None = None,
        max_age_days: int = 7,
    ) -> list[ArxivPaper]:
        """Fetch arXiv papers using fetch-arxiv-papers skill."""
        categories = categories or self.default_categories

        task_prompt = f"""Fetch recent AI/ML papers from arXiv.

Use the fetch-arxiv-papers skill to:
1. Query arXiv RSS feeds for categories: {categories}
2. Filter papers from the last {max_age_days} days
3. Extract title, authors, abstract, arxiv_id, categories, pdf_url
4. Deduplicate by arxiv_id

Return JSON:
```json
{{"papers": [{{"arxiv_id": "...", "title": "...", "authors": [...], "abstract": "...", "categories": [...], "pdf_url": "...", "published_date": "..."}}], "total_fetched": N}}
```

Read the SKILL.md for detailed instructions."""

        response = await self.run(task_prompt)
        return self._parse_papers(response)

    async def fetch_github_trending(
        self,
        topics: list[str] | None = None,
        min_stars: int | None = None,
    ) -> list[GitHubRepo]:
        """Fetch trending GitHub repos using fetch-github-trending skill."""
        topics = topics or self.default_topics
        min_stars = min_stars if min_stars is not None else self.default_min_stars

        task_prompt = f"""Fetch trending AI/ML repositories from GitHub.

Use the fetch-github-trending skill to:
1. Search GitHub for topics: {topics}
2. Filter repos with >= {min_stars} stars
3. Calculate trending scores
4. Return top results sorted by score

Return JSON:
```json
{{"repos": [{{"full_name": "...", "name": "...", "description": "...", "url": "...", "stars": N, "forks": N, "language": "...", "topics": [...], "trending_score": N}}], "total_found": N}}
```

Read the SKILL.md for detailed instructions."""

        response = await self.run(task_prompt)
        return self._parse_repos(response)

    async def collect_all(self) -> ResearchCollectionResult:
        """Run complete research collection."""
        papers = await self.fetch_arxiv_papers()
        repos = await self.fetch_github_trending()

        await self.on_skill_complete(
            "collect_all",
            {"papers": len(papers), "repos": len(repos)},
        )

        return ResearchCollectionResult(
            papers=papers,
            repos=repos,
            stats={"total_papers": len(papers), "total_repos": len(repos)},
        )

    def _parse_papers(self, response: str) -> list[ArxivPaper]:
        """Parse LLM response into ArxivPaper list."""
        try:
            data = self._extract_json(response)
            papers = data.get("papers", []) if isinstance(data, dict) else data
            return [
                ArxivPaper(
                    arxiv_id=p.get("arxiv_id", ""),
                    title=p.get("title", ""),
                    authors=p.get("authors", []),
                    abstract=p.get("abstract", ""),
                    categories=p.get("categories", []),
                    pdf_url=p.get("pdf_url", ""),
                    published_date=p.get("published_date"),
                )
                for p in papers
            ]
        except Exception as e:
            logger.warning(f"Failed to parse papers: {e}")
            return []

    def _parse_repos(self, response: str) -> list[GitHubRepo]:
        """Parse LLM response into GitHubRepo list."""
        try:
            data = self._extract_json(response)
            repos = data.get("repos", []) if isinstance(data, dict) else data
            return [
                GitHubRepo(
                    full_name=r.get("full_name", ""),
                    name=r.get("name", ""),
                    description=r.get("description", ""),
                    url=r.get("url", ""),
                    stars=r.get("stars", 0),
                    forks=r.get("forks", 0),
                    language=r.get("language"),
                    topics=r.get("topics", []),
                    trending_score=r.get("trending_score", 0.0),
                )
                for r in repos
            ]
        except Exception as e:
            logger.warning(f"Failed to parse repos: {e}")
            return []

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        total = result.get("papers", 0) + result.get("repos", 0)
        success = total > 0
        await self.record_outcome(skill_name, result, success=success)
