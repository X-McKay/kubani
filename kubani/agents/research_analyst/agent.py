"""
Research Analyst Agent - Skills-centric paper and repo analysis.

Thin orchestrator that delegates to diagnostic skills:
- analyze-arxiv-paper: Deep analysis of research papers
- analyze-github-repo: Repository evaluation for tool spotlights

Usage:
    from kubani.agents.research_analyst import ResearchAnalystAgent

    agent = ResearchAnalystAgent()
    paper_analysis = await agent.analyze_paper(paper)
    repo_analysis = await agent.analyze_repo(repo)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kubani.agents._base import SkillsOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class PaperAnalysis:
    """Analysis result for an arXiv paper."""

    arxiv_id: str
    title: str
    authors: list[str]
    research_type: str = "other"
    main_claim: str = ""
    key_innovation: str = ""
    practitioner_summary: str = ""
    key_takeaways: list[str] = field(default_factory=list)
    relevance_score: int = 5
    topics: list[str] = field(default_factory=list)
    digest_worthy: bool = False
    spotlight_candidate: bool = False
    analysis_failed: bool = False


@dataclass
class RepoAnalysis:
    """Analysis result for a GitHub repository."""

    full_name: str
    name: str
    category: str = "other"
    target_audience: str = ""
    use_cases: list[str] = field(default_factory=list)
    quality_score: int = 5
    spotlight_summary: str = ""
    best_for: str = ""
    spotlight_worthy: bool = False
    analysis_failed: bool = False


class ResearchAnalystAgent(SkillsOrchestrator):
    """
    Skills-centric research analyst.

    Discovers and delegates to news/diagnostic skills:
    - analyze-arxiv-paper
    - analyze-github-repo
    """

    AGENT_DIR = Path(__file__).parent
    SKILLS_DOMAIN = "news"
    SKILLS_CATEGORY = "diagnostic"

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Research Analyst agent."""
        super().__init__(agent_dir)

        analyst_config = self.config.get("analyst", {})
        self.digest_threshold = analyst_config.get("digest_threshold", 7)
        self.spotlight_threshold = analyst_config.get("spotlight_threshold", 8)
        self.min_stars_for_spotlight = analyst_config.get("min_stars_for_spotlight", 500)

    async def analyze_paper(self, paper: dict[str, Any]) -> PaperAnalysis:
        """Analyze an arXiv paper using analyze-arxiv-paper skill."""
        arxiv_id = paper.get("arxiv_id", "")
        title = paper.get("title", "")
        authors = paper.get("authors", [])
        abstract = paper.get("abstract", "")

        analysis = PaperAnalysis(arxiv_id=arxiv_id, title=title, authors=authors)

        if len(abstract) < 100:
            logger.warning(f"Abstract too short for {arxiv_id}")
            analysis.analysis_failed = True
            return analysis

        task_prompt = f"""Analyze this research paper using the analyze-arxiv-paper skill.

Paper:
- Title: {title}
- Authors: {', '.join(authors[:5])}
- Abstract: {abstract[:2000]}

Return JSON with: research_type, main_claim, key_innovation, practitioner_summary,
key_takeaways, relevance_score (1-10), topics, digest_worthy, spotlight_candidate"""

        try:
            response = await self.run(task_prompt)
            return self._parse_paper_analysis(response, analysis)
        except Exception as e:
            logger.error(f"Failed to analyze paper {arxiv_id}: {e}")
            analysis.analysis_failed = True
            return analysis

    async def analyze_papers_batch(self, papers: list[dict[str, Any]]) -> list[PaperAnalysis]:
        """Analyze multiple papers."""
        return [await self.analyze_paper(paper) for paper in papers]

    async def analyze_repo(self, repo: dict[str, Any]) -> RepoAnalysis:
        """Analyze a GitHub repository using analyze-github-repo skill."""
        full_name = repo.get("full_name", "")
        name = repo.get("name", "")
        description = repo.get("description", "") or ""
        stars = repo.get("stars", 0)

        analysis = RepoAnalysis(full_name=full_name, name=name)

        if len(description) < 20:
            logger.warning(f"Description too short for {full_name}")
            analysis.analysis_failed = True
            return analysis

        task_prompt = f"""Analyze this repository using the analyze-github-repo skill.

Repository:
- Name: {full_name}
- Description: {description[:500]}
- Stars: {stars}
- Language: {repo.get('language', 'Unknown')}
- Topics: {', '.join(repo.get('topics', [])[:10])}

Return JSON with: category, target_audience, use_cases, quality_score (1-10),
spotlight_summary, best_for, spotlight_worthy"""

        try:
            response = await self.run(task_prompt)
            return self._parse_repo_analysis(response, analysis, stars)
        except Exception as e:
            logger.error(f"Failed to analyze repo {full_name}: {e}")
            analysis.analysis_failed = True
            return analysis

    async def analyze_repos_batch(self, repos: list[dict[str, Any]]) -> list[RepoAnalysis]:
        """Analyze multiple repositories."""
        return [await self.analyze_repo(repo) for repo in repos]

    def _parse_paper_analysis(self, response: str, analysis: PaperAnalysis) -> PaperAnalysis:
        """Parse LLM response into PaperAnalysis."""
        try:
            data = self._extract_json(response)
            analysis.research_type = data.get("research_type", "other")
            analysis.main_claim = data.get("main_claim", "")
            analysis.key_innovation = data.get("key_innovation", "")
            analysis.practitioner_summary = data.get("practitioner_summary", "")
            analysis.key_takeaways = data.get("key_takeaways", [])
            analysis.relevance_score = min(max(data.get("relevance_score", 5), 1), 10)
            analysis.topics = data.get("topics", [])
            analysis.digest_worthy = data.get("digest_worthy", analysis.relevance_score >= self.digest_threshold)
            analysis.spotlight_candidate = data.get("spotlight_candidate", analysis.relevance_score >= self.spotlight_threshold)
        except Exception as e:
            logger.warning(f"Failed to parse paper analysis: {e}")
            analysis.analysis_failed = True
        return analysis

    def _parse_repo_analysis(self, response: str, analysis: RepoAnalysis, stars: int) -> RepoAnalysis:
        """Parse LLM response into RepoAnalysis."""
        try:
            data = self._extract_json(response)
            analysis.category = data.get("category", "other")
            analysis.target_audience = data.get("target_audience", "")
            analysis.use_cases = data.get("use_cases", [])
            analysis.quality_score = min(max(data.get("quality_score", 5), 1), 10)
            analysis.spotlight_summary = data.get("spotlight_summary", "")
            analysis.best_for = data.get("best_for", "")
            analysis.spotlight_worthy = data.get(
                "spotlight_worthy",
                stars >= self.min_stars_for_spotlight and analysis.quality_score >= 7
            )
        except Exception as e:
            logger.warning(f"Failed to parse repo analysis: {e}")
            analysis.analysis_failed = True
        return analysis

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = not result.get("analysis_failed", False)
        await self.record_outcome(skill_name, result, success=success)
