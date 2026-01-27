"""
Research Collector Agent - Fetches papers from arXiv and trending repos from GitHub.

Implements two skills:
- fetch-arxiv-papers: Fetches recent AI/ML papers from arXiv RSS feeds
- fetch-github-trending: Fetches trending AI repositories from GitHub

Usage:
    from kubani.agents.research_collector import ResearchCollectorAgent

    agent = ResearchCollectorAgent()
    papers = await agent.fetch_arxiv_papers(categories=["cs.AI", "cs.LG"])
    repos = await agent.fetch_github_trending(topics=["llm", "machine-learning"])
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from kubani.agents._base import KubaniAgent

logger = logging.getLogger(__name__)


# ============================================================================
# Models
# ============================================================================


@dataclass
class ArxivPaper:
    """Paper fetched from arXiv."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    pdf_url: str
    published_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "categories": self.categories,
            "pdf_url": self.pdf_url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


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
    created_at: datetime | None = None
    pushed_at: datetime | None = None
    open_issues: int = 0
    watchers: int = 0
    trending_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "full_name": self.full_name,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "stars": self.stars,
            "forks": self.forks,
            "language": self.language,
            "topics": self.topics,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "pushed_at": self.pushed_at.isoformat() if self.pushed_at else None,
            "open_issues": self.open_issues,
            "watchers": self.watchers,
            "trending_score": self.trending_score,
        }


@dataclass
class ArxivCollectionResult:
    """Result from fetching arXiv papers."""

    papers: list[ArxivPaper] = field(default_factory=list)
    total_fetched: int = 0
    categories_queried: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class GitHubCollectionResult:
    """Result from fetching GitHub repos."""

    repos: list[GitHubRepo] = field(default_factory=list)
    total_fetched: int = 0
    topics_queried: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ============================================================================
# Agent Implementation
# ============================================================================


class ResearchCollectorAgent(KubaniAgent):
    """
    Collects research papers and trending repositories.

    Implements fetch-arxiv-papers and fetch-github-trending skill logic.
    """

    AGENT_DIR = Path(__file__).parent

    # Default arXiv categories for AI/ML research
    DEFAULT_ARXIV_CATEGORIES = ["cs.AI", "cs.LG", "cs.CL"]

    # Default GitHub topics for AI tools
    DEFAULT_GITHUB_TOPICS = [
        "machine-learning",
        "deep-learning",
        "llm",
        "langchain",
        "ai",
        "transformers",
    ]

    # arXiv RSS feed URL template
    ARXIV_RSS_URL = "https://rss.arxiv.org/rss/{category}"

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Research Collector agent."""
        super().__init__(agent_dir)

        # Research-specific configuration
        research_config = self.config.get("research", {})
        self.max_papers_per_category = research_config.get("max_papers_per_category", 20)
        self.max_repos = research_config.get("max_repos", 30)
        self.min_stars = research_config.get("min_stars", 100)

        # HTTP client - lazy initialization
        self._http_client = None

    def _get_http_client(self):
        """Get or create HTTP client."""
        if self._http_client is None:
            import httpx

            headers = {"User-Agent": "Kubani-ResearchCollector/1.0 (https://github.com/kubani)"}
            self._http_client = httpx.Client(timeout=30.0, follow_redirects=True, headers=headers)
        return self._http_client

    # ========================================================================
    # fetch-arxiv-papers skill implementation
    # ========================================================================

    def _extract_arxiv_id(self, link: str) -> str:
        """Extract arXiv ID from URL."""
        # Pattern: https://arxiv.org/abs/2601.12345 or http://arxiv.org/abs/2601.12345v1
        match = re.search(r"arxiv\.org/abs/(\d+\.\d+)", link)
        if match:
            return match.group(1)
        return link

    def _parse_arxiv_feed(self, feed_content: str, category: str) -> list[ArxivPaper]:
        """Parse arXiv RSS feed content."""
        import feedparser

        papers = []
        parsed = feedparser.parse(feed_content)

        if parsed.bozo and parsed.bozo_exception:
            logger.warning(f"Feed parse warning for {category}: {parsed.bozo_exception}")

        for entry in parsed.entries:
            try:
                # Extract arXiv ID from link
                link = entry.get("link", "")
                arxiv_id = self._extract_arxiv_id(link)

                if not arxiv_id:
                    continue

                # Get title (clean up whitespace)
                title = entry.get("title", "").strip()
                title = re.sub(r"\s+", " ", title)  # Normalize whitespace

                # Get authors
                authors = []
                if hasattr(entry, "authors"):
                    authors = [a.get("name", "") for a in entry.authors if a.get("name")]
                elif hasattr(entry, "author"):
                    authors = [entry.author]

                # Get abstract (from description or summary)
                abstract = entry.get("description", entry.get("summary", "")).strip()
                # Clean HTML tags if present
                abstract = re.sub(r"<[^>]+>", "", abstract)
                abstract = re.sub(r"\s+", " ", abstract)

                # Get categories
                categories = [category]
                if hasattr(entry, "tags"):
                    categories.extend([t.get("term", "") for t in entry.tags if t.get("term")])
                categories = list(set(categories))  # Dedupe

                # Parse dates
                published_at = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=UTC)

                updated_at = None
                if hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    updated_at = datetime(*entry.updated_parsed[:6], tzinfo=UTC)

                # Build PDF URL
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

                paper = ArxivPaper(
                    arxiv_id=arxiv_id,
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    categories=categories,
                    pdf_url=pdf_url,
                    published_at=published_at,
                    updated_at=updated_at,
                )
                papers.append(paper)

            except Exception as e:
                logger.warning(f"Failed to parse arXiv entry: {e}")
                continue

        return papers

    def _fetch_arxiv_category(self, category: str) -> list[ArxivPaper]:
        """Fetch papers from a single arXiv category."""
        url = self.ARXIV_RSS_URL.format(category=category)

        try:
            client = self._get_http_client()
            response = client.get(url)
            response.raise_for_status()

            papers = self._parse_arxiv_feed(response.text, category)
            logger.info(f"Fetched {len(papers)} papers from arXiv {category}")
            return papers

        except Exception as e:
            logger.error(f"Error fetching arXiv {category}: {e}")
            return []

    async def fetch_arxiv_papers(
        self,
        categories: list[str] | None = None,
        max_results: int | None = None,
        days_back: int = 7,
    ) -> ArxivCollectionResult:
        """
        Fetch recent papers from arXiv.

        Implements the fetch-arxiv-papers skill.

        Args:
            categories: arXiv categories to query (default: cs.AI, cs.LG, cs.CL)
            max_results: Maximum papers to return (default from config)
            days_back: Only include papers from last N days

        Returns:
            ArxivCollectionResult with papers and stats
        """
        result = ArxivCollectionResult()

        categories = categories or self.DEFAULT_ARXIV_CATEGORIES
        max_results = max_results or (self.max_papers_per_category * len(categories))

        result.categories_queried = categories
        cutoff = datetime.now(UTC) - timedelta(days=days_back)

        logger.info(f"Fetching arXiv papers from categories: {categories}")

        all_papers: dict[str, ArxivPaper] = {}  # Dedupe by arxiv_id

        for category in categories:
            try:
                papers = self._fetch_arxiv_category(category)

                for paper in papers:
                    # Filter by date
                    paper_date = paper.updated_at or paper.published_at
                    if paper_date and paper_date < cutoff:
                        continue

                    # Dedupe by arxiv_id
                    if paper.arxiv_id not in all_papers:
                        all_papers[paper.arxiv_id] = paper
                    else:
                        # Merge categories
                        existing = all_papers[paper.arxiv_id]
                        existing.categories = list(set(existing.categories + paper.categories))

            except Exception as e:
                error_msg = f"Failed to fetch {category}: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        # Sort by date and limit
        papers_list = list(all_papers.values())
        papers_list.sort(
            key=lambda p: p.updated_at or p.published_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

        result.papers = papers_list[:max_results]
        result.total_fetched = len(result.papers)

        logger.info(f"Collected {result.total_fetched} unique arXiv papers")
        return result

    async def fetch_arxiv_papers_as_dicts(
        self,
        categories: list[str] | None = None,
        max_results: int | None = None,
        days_back: int = 7,
    ) -> list[dict[str, Any]]:
        """Convenience method returning dicts for Temporal activities."""
        result = await self.fetch_arxiv_papers(categories, max_results, days_back)
        return [p.to_dict() for p in result.papers]

    # ========================================================================
    # fetch-github-trending skill implementation
    # ========================================================================

    def _calculate_trending_score(
        self,
        repo: dict[str, Any],
        pushed_within_days: int = 7,
    ) -> float:
        """
        Calculate trending score for a repo.

        Score = stars + (forks * 2) + (recent_push_bonus)
        """
        stars = repo.get("stargazers_count", 0)
        forks = repo.get("forks_count", 0)

        # Bonus for recent activity
        recent_bonus = 0
        pushed_at = repo.get("pushed_at")
        if pushed_at:
            try:
                pushed_date = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                days_since_push = (datetime.now(UTC) - pushed_date).days
                if days_since_push <= pushed_within_days:
                    recent_bonus = 500 * (1 - days_since_push / pushed_within_days)
            except Exception:
                pass

        return stars + (forks * 2) + recent_bonus

    def _search_github_repos(
        self,
        query: str,
        sort: str = "stars",
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """Search GitHub repos using the API."""
        github_token = os.environ.get("GITHUB_TOKEN")

        headers = {
            "Accept": "application/vnd.github+json",
        }
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        url = "https://api.github.com/search/repositories"
        params = {
            "q": query,
            "sort": sort,
            "order": "desc",
            "per_page": per_page,
        }

        try:
            client = self._get_http_client()
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()

            data = response.json()
            return data.get("items", [])

        except Exception as e:
            logger.error(f"GitHub API error: {e}")
            return []

    def _parse_github_repo(self, repo_data: dict[str, Any]) -> GitHubRepo:
        """Parse GitHub API response into GitHubRepo."""
        import contextlib

        # Parse dates
        created_at = None
        if repo_data.get("created_at"):
            with contextlib.suppress(Exception):
                created_at = datetime.fromisoformat(repo_data["created_at"].replace("Z", "+00:00"))

        pushed_at = None
        if repo_data.get("pushed_at"):
            with contextlib.suppress(Exception):
                pushed_at = datetime.fromisoformat(repo_data["pushed_at"].replace("Z", "+00:00"))

        return GitHubRepo(
            full_name=repo_data.get("full_name", ""),
            name=repo_data.get("name", ""),
            description=repo_data.get("description", "") or "",
            url=repo_data.get("html_url", ""),
            stars=repo_data.get("stargazers_count", 0),
            forks=repo_data.get("forks_count", 0),
            language=repo_data.get("language"),
            topics=repo_data.get("topics", []),
            created_at=created_at,
            pushed_at=pushed_at,
            open_issues=repo_data.get("open_issues_count", 0),
            watchers=repo_data.get("watchers_count", 0),
            trending_score=self._calculate_trending_score(repo_data),
        )

    async def fetch_github_trending(
        self,
        topics: list[str] | None = None,
        language: str | None = None,
        min_stars: int | None = None,
        max_results: int | None = None,
        since_days: int = 30,
    ) -> GitHubCollectionResult:
        """
        Fetch trending AI repositories from GitHub.

        Implements the fetch-github-trending skill.

        Args:
            topics: Topics to search for (default: AI/ML related)
            language: Filter by programming language
            min_stars: Minimum star count
            max_results: Maximum repos to return
            since_days: Only repos created or updated within N days

        Returns:
            GitHubCollectionResult with repos and stats
        """
        result = GitHubCollectionResult()

        topics = topics or self.DEFAULT_GITHUB_TOPICS
        min_stars = min_stars if min_stars is not None else self.min_stars
        max_results = max_results or self.max_repos

        result.topics_queried = topics

        logger.info(f"Fetching GitHub repos for topics: {topics}")

        # Build search queries
        all_repos: dict[str, GitHubRepo] = {}  # Dedupe by full_name

        for topic in topics:
            # Build query string
            query_parts = [f"topic:{topic}"]
            query_parts.append(f"stars:>={min_stars}")

            if language:
                query_parts.append(f"language:{language}")

            # Recent activity filter
            since_date = (datetime.now(UTC) - timedelta(days=since_days)).strftime("%Y-%m-%d")
            query_parts.append(f"pushed:>={since_date}")

            query = " ".join(query_parts)

            try:
                repos_data = self._search_github_repos(query, per_page=30)

                for repo_data in repos_data:
                    repo = self._parse_github_repo(repo_data)

                    # Dedupe by full_name
                    if (
                        repo.full_name not in all_repos
                        or repo.trending_score > all_repos[repo.full_name].trending_score
                    ):
                        all_repos[repo.full_name] = repo

            except Exception as e:
                error_msg = f"Failed to search topic {topic}: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        # Sort by trending score and limit
        repos_list = list(all_repos.values())
        repos_list.sort(key=lambda r: r.trending_score, reverse=True)

        result.repos = repos_list[:max_results]
        result.total_fetched = len(result.repos)

        logger.info(f"Collected {result.total_fetched} trending GitHub repos")
        return result

    async def fetch_github_trending_as_dicts(
        self,
        topics: list[str] | None = None,
        language: str | None = None,
        min_stars: int | None = None,
        max_results: int | None = None,
        since_days: int = 30,
    ) -> list[dict[str, Any]]:
        """Convenience method returning dicts for Temporal activities."""
        result = await self.fetch_github_trending(
            topics, language, min_stars, max_results, since_days
        )
        return [r.to_dict() for r in result.repos]

    # ========================================================================
    # Learning integration
    # ========================================================================

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        total = result.get("total_fetched", 0)
        success = total > 0
        await self.record_outcome(skill_name, result, success=success)

    def close(self):
        """Close HTTP client."""
        if self._http_client:
            self._http_client.close()
            self._http_client = None

    def __del__(self):
        """Cleanup on deletion."""
        self.close()
