"""Research Collector Agent - Fetches arXiv papers and GitHub repos."""

from .agent import (
    ArxivCollectionResult,
    ArxivPaper,
    GitHubCollectionResult,
    GitHubRepo,
    ResearchCollectorAgent,
)

__all__ = [
    "ResearchCollectorAgent",
    "ArxivPaper",
    "ArxivCollectionResult",
    "GitHubRepo",
    "GitHubCollectionResult",
]
