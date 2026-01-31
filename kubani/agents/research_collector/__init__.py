"""Research Collector Agent - Fetches arXiv papers and GitHub repos."""

from .agent import (
    ArxivPaper,
    GitHubRepo,
    ResearchCollectionResult,
    ResearchCollectorAgent,
)

__all__ = [
    "ResearchCollectorAgent",
    "ArxivPaper",
    "GitHubRepo",
    "ResearchCollectionResult",
]
