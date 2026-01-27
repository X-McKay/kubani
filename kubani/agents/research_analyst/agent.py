"""
Research Analyst Agent - Analyzes papers and repos for digest inclusion.

Implements two skills:
- analyze-arxiv-paper: Deep analysis of research papers for digest inclusion
- analyze-github-repo: Evaluation of repositories for tool spotlight sections

Usage:
    from kubani.agents.research_analyst import ResearchAnalystAgent

    agent = ResearchAnalystAgent()
    paper_analysis = await agent.analyze_paper(paper)
    repo_analysis = await agent.analyze_repo(repo)
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from kubani.agents._base import KubaniAgent

logger = logging.getLogger(__name__)


# ============================================================================
# Models
# ============================================================================


class ResearchType:
    """Types of research papers."""

    NEW_METHOD = "new_method"
    BENCHMARK = "benchmark"
    APPLICATION = "application"
    SURVEY = "survey"
    THEORETICAL = "theoretical"
    DATASET = "dataset"
    SYSTEM = "system"
    OTHER = "other"


class RepoCategory:
    """Categories for repositories."""

    FRAMEWORK = "framework"
    LIBRARY = "library"
    APPLICATION = "application"
    MODEL = "model"
    DATASET = "dataset"
    TOOL = "tool"
    TUTORIAL = "tutorial"
    OTHER = "other"


@dataclass
class RelevanceScores:
    """Relevance scores for a paper."""

    practical_applicability: int = 5
    timeliness: int = 5
    novelty: int = 5
    impact_potential: int = 5

    @property
    def overall(self) -> int:
        """Calculate overall score as weighted average."""
        return round(
            (self.practical_applicability * 0.3)
            + (self.timeliness * 0.2)
            + (self.novelty * 0.25)
            + (self.impact_potential * 0.25)
        )


@dataclass
class PotentialImpacts:
    """Potential impacts of a paper."""

    industry: str = ""
    research: str = ""
    open_source: str = ""
    adoption_timeline: str = "6_months"  # immediate, 6_months, 1_year, longer


@dataclass
class PaperAnalysis:
    """Complete analysis of an arXiv paper."""

    arxiv_id: str
    title: str
    authors: list[str]
    research_type: str = ResearchType.OTHER
    main_claim: str = ""
    key_innovation: str = ""
    results_summary: str = ""
    practitioner_summary: str = ""
    key_takeaways: list[str] = field(default_factory=list)
    relevance_scores: RelevanceScores = field(default_factory=RelevanceScores)
    potential_impacts: PotentialImpacts = field(default_factory=PotentialImpacts)
    topics: list[str] = field(default_factory=list)
    related_to: list[str] = field(default_factory=list)
    digest_worthy: bool = False
    spotlight_candidate: bool = False
    analysis_failed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "research_type": self.research_type,
            "main_claim": self.main_claim,
            "key_innovation": self.key_innovation,
            "results_summary": self.results_summary,
            "practitioner_summary": self.practitioner_summary,
            "key_takeaways": self.key_takeaways,
            "relevance_scores": {
                "practical_applicability": self.relevance_scores.practical_applicability,
                "timeliness": self.relevance_scores.timeliness,
                "novelty": self.relevance_scores.novelty,
                "impact_potential": self.relevance_scores.impact_potential,
                "overall": self.relevance_scores.overall,
            },
            "potential_impacts": {
                "industry": self.potential_impacts.industry,
                "research": self.potential_impacts.research,
                "open_source": self.potential_impacts.open_source,
                "adoption_timeline": self.potential_impacts.adoption_timeline,
            },
            "topics": self.topics,
            "related_to": self.related_to,
            "digest_worthy": self.digest_worthy,
            "spotlight_candidate": self.spotlight_candidate,
            "analysis_failed": self.analysis_failed,
        }


@dataclass
class QualityScores:
    """Quality scores for a repository."""

    documentation: int = 5
    maintenance: int = 5
    community: int = 5
    code_quality: int = 5

    @property
    def overall(self) -> int:
        """Calculate overall score as average."""
        return round(
            (self.documentation + self.maintenance + self.community + self.code_quality) / 4
        )


@dataclass
class RepoAnalysis:
    """Complete analysis of a GitHub repository."""

    full_name: str
    name: str
    category: str = RepoCategory.OTHER
    target_audience: str = ""
    use_cases: list[str] = field(default_factory=list)
    quality_scores: QualityScores = field(default_factory=QualityScores)
    spotlight_summary: str = ""
    best_for: str = ""
    spotlight_worthy: bool = False
    analysis_failed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "full_name": self.full_name,
            "name": self.name,
            "category": self.category,
            "target_audience": self.target_audience,
            "use_cases": self.use_cases,
            "quality_scores": {
                "documentation": self.quality_scores.documentation,
                "maintenance": self.quality_scores.maintenance,
                "community": self.quality_scores.community,
                "code_quality": self.quality_scores.code_quality,
                "overall": self.quality_scores.overall,
            },
            "spotlight_summary": self.spotlight_summary,
            "best_for": self.best_for,
            "spotlight_worthy": self.spotlight_worthy,
            "analysis_failed": self.analysis_failed,
        }


# ============================================================================
# LLM Response Schemas
# ============================================================================


class PaperAnalysisResponse(BaseModel):
    """Structured output from LLM paper analysis."""

    research_type: str
    main_claim: str
    key_innovation: str
    results_summary: str
    practitioner_summary: str
    key_takeaways: list[str]
    practical_applicability: int
    timeliness: int
    novelty: int
    impact_potential: int
    industry_impact: str
    research_impact: str
    open_source_impact: str
    adoption_timeline: str
    topics: list[str]
    related_to: list[str]


class RepoAnalysisResponse(BaseModel):
    """Structured output from LLM repo analysis."""

    category: str
    target_audience: str
    use_cases: list[str]
    documentation_score: int
    maintenance_score: int
    community_score: int
    code_quality_score: int
    spotlight_summary: str
    best_for: str


# ============================================================================
# Prompts
# ============================================================================


PAPER_ANALYSIS_PROMPT = """Analyze this research paper for AI practitioners.

**Paper:**
- Title: {title}
- Authors: {authors}
- Categories: {categories}
- Abstract: {abstract}

**Analysis Tasks:**

1. **Research Type**: Classify as one of: new_method, benchmark, application, survey, theoretical, dataset, system, other

2. **Main Claim**: What does the paper claim to achieve? (1 sentence)

3. **Key Innovation**: What's novel about the approach? (1 sentence)

4. **Results Summary**: What results are reported? (1 sentence)

5. **Practitioner Summary**: Write 2-3 paragraphs explaining:
   - What the paper does in accessible terms
   - Why practitioners should care
   - Any limitations or caveats
   - Potential applications

6. **Key Takeaways**: List 3-5 bullet points of key insights

7. **Relevance Scores** (1-10 each):
   - practical_applicability: Can this be used in real applications?
   - timeliness: Does this address current hot topics?
   - novelty: How new is the approach?
   - impact_potential: Could this change how things are done?

8. **Potential Impacts**:
   - industry_impact: Near-term commercial applications
   - research_impact: Future research directions
   - open_source_impact: Likely open-source implementations
   - adoption_timeline: immediate, 6_months, 1_year, longer

9. **Topics**: List 3-5 topic keywords

10. **Related To**: List related techniques/frameworks

Respond with JSON:
{{
    "research_type": "...",
    "main_claim": "...",
    "key_innovation": "...",
    "results_summary": "...",
    "practitioner_summary": "...",
    "key_takeaways": ["...", "..."],
    "practical_applicability": 1-10,
    "timeliness": 1-10,
    "novelty": 1-10,
    "impact_potential": 1-10,
    "industry_impact": "...",
    "research_impact": "...",
    "open_source_impact": "...",
    "adoption_timeline": "...",
    "topics": ["...", "..."],
    "related_to": ["...", "..."]
}}"""


REPO_ANALYSIS_PROMPT = """Analyze this GitHub repository for potential inclusion in an AI tools spotlight.

**Repository:**
- Name: {full_name}
- Description: {description}
- Language: {language}
- Stars: {stars}
- Forks: {forks}
- Topics: {topics}
- Recent Activity: {pushed_at}

**Analysis Tasks:**

1. **Category**: Classify as one of: framework, library, application, model, dataset, tool, tutorial, other

2. **Target Audience**: Who would benefit most from this repo?

3. **Use Cases**: List 3-5 specific use cases

4. **Quality Scores** (1-10 each based on stars, activity, etc.):
   - documentation_score: Infer from description clarity
   - maintenance_score: Based on recent activity
   - community_score: Based on stars and forks
   - code_quality_score: Infer from language and structure

5. **Spotlight Summary**: 2-3 sentences explaining why practitioners should check this out

6. **Best For**: One sentence describing ideal users

Respond with JSON:
{{
    "category": "...",
    "target_audience": "...",
    "use_cases": ["...", "...", "..."],
    "documentation_score": 1-10,
    "maintenance_score": 1-10,
    "community_score": 1-10,
    "code_quality_score": 1-10,
    "spotlight_summary": "...",
    "best_for": "..."
}}"""


# ============================================================================
# Major Labs for digest worthiness
# ============================================================================

MAJOR_LABS = [
    "openai",
    "anthropic",
    "google",
    "deepmind",
    "meta",
    "microsoft",
    "nvidia",
    "hugging face",
    "huggingface",
    "mistral",
    "cohere",
    "xai",
    "stability",
    "midjourney",
]


# ============================================================================
# Agent Implementation
# ============================================================================


class ResearchAnalystAgent(KubaniAgent):
    """
    Analyzes research papers and repositories for digest inclusion.

    Implements analyze-arxiv-paper and analyze-github-repo skill logic.
    """

    AGENT_DIR = Path(__file__).parent

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Research Analyst agent."""
        super().__init__(agent_dir)

        # Analyst-specific configuration
        analyst_config = self.config.get("analyst", {})
        self.digest_threshold = analyst_config.get("digest_threshold", 7)
        self.spotlight_threshold = analyst_config.get("spotlight_threshold", 8)
        self.min_stars_for_spotlight = analyst_config.get("min_stars_for_spotlight", 500)

        # LLM client - lazy initialization
        self._llm_client = None

    def _get_llm_client(self):
        """Get or create LLM client."""
        if self._llm_client is None:
            from openai import OpenAI

            self._llm_client = OpenAI(
                api_key="not-needed",
                base_url=os.environ.get(
                    "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
                ),
            )
        return self._llm_client

    def _get_model(self) -> str:
        """Get the LLM model name."""
        return os.environ.get("VLLM_MODEL", "nvidia/Qwen3-14B-FP4")

    def _strip_thinking_tags(self, content: str) -> str:
        """Strip thinking tags from LLM response."""
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
        return content.strip()

    def _extract_json(self, content: str) -> dict[str, Any]:
        """Extract JSON from LLM response."""
        import json

        content = self._strip_thinking_tags(content)

        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return json.loads(content)

    def _is_from_major_lab(self, authors: list[str], title: str) -> bool:
        """Check if paper is from a major AI lab."""
        text = " ".join(authors).lower() + " " + title.lower()
        return any(lab in text for lab in MAJOR_LABS)

    # ========================================================================
    # analyze-arxiv-paper skill implementation
    # ========================================================================

    async def analyze_paper(
        self,
        paper: dict[str, Any],
        analysis_depth: str = "standard",
    ) -> PaperAnalysis:
        """
        Analyze an arXiv paper for digest inclusion.

        Implements the analyze-arxiv-paper skill.

        Args:
            paper: Paper dict with arxiv_id, title, authors, abstract, etc.
            analysis_depth: "standard" or "deep" for more thorough analysis

        Returns:
            PaperAnalysis with comprehensive analysis
        """
        arxiv_id = paper.get("arxiv_id", "")
        title = paper.get("title", "")
        authors = paper.get("authors", [])
        abstract = paper.get("abstract", "")
        categories = paper.get("categories", [])

        logger.info(f"Analyzing paper: {title[:50]}...")

        # Create base analysis
        analysis = PaperAnalysis(
            arxiv_id=arxiv_id,
            title=title,
            authors=authors,
        )

        # Check for short/missing abstract
        if len(abstract) < 100:
            logger.warning(f"Abstract too short for {arxiv_id}, using basic analysis")
            analysis.analysis_failed = True
            analysis.practitioner_summary = f"Paper: {title}"
            analysis.key_takeaways = ["Full abstract not available"]
            return analysis

        try:
            # Call LLM for analysis
            client = self._get_llm_client()
            response = client.chat.completions.create(
                model=self._get_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI research analyst. Analyze papers and provide structured analysis in JSON format. Focus on practical implications for practitioners.",
                    },
                    {
                        "role": "user",
                        "content": PAPER_ANALYSIS_PROMPT.format(
                            title=title,
                            authors=", ".join(authors[:5]),  # Limit authors
                            categories=", ".join(categories),
                            abstract=abstract[:2000],  # Limit length
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=1500 if analysis_depth == "deep" else 1000,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            response_text = response.choices[0].message.content
            data = self._extract_json(response_text)

            # Populate analysis from LLM response
            analysis.research_type = data.get("research_type", ResearchType.OTHER)
            analysis.main_claim = data.get("main_claim", "")
            analysis.key_innovation = data.get("key_innovation", "")
            analysis.results_summary = data.get("results_summary", "")
            analysis.practitioner_summary = data.get("practitioner_summary", "")
            analysis.key_takeaways = data.get("key_takeaways", [])

            analysis.relevance_scores = RelevanceScores(
                practical_applicability=min(max(data.get("practical_applicability", 5), 1), 10),
                timeliness=min(max(data.get("timeliness", 5), 1), 10),
                novelty=min(max(data.get("novelty", 5), 1), 10),
                impact_potential=min(max(data.get("impact_potential", 5), 1), 10),
            )

            analysis.potential_impacts = PotentialImpacts(
                industry=data.get("industry_impact", ""),
                research=data.get("research_impact", ""),
                open_source=data.get("open_source_impact", ""),
                adoption_timeline=data.get("adoption_timeline", "6_months"),
            )

            analysis.topics = data.get("topics", [])
            analysis.related_to = data.get("related_to", [])

            # Determine digest worthiness per skill spec
            overall_score = analysis.relevance_scores.overall
            is_major_lab = self._is_from_major_lab(authors, title)

            analysis.digest_worthy = overall_score >= self.digest_threshold or is_major_lab

            # Determine spotlight candidacy
            analysis.spotlight_candidate = (
                overall_score >= self.spotlight_threshold
                and analysis.relevance_scores.practical_applicability >= 7
            )

            logger.info(
                f"Paper analysis complete: {arxiv_id} "
                f"(score={overall_score}, digest={analysis.digest_worthy})"
            )

        except Exception as e:
            logger.error(f"Failed to analyze paper {arxiv_id}: {e}")
            analysis.analysis_failed = True
            analysis.practitioner_summary = f"Analysis failed for: {title}"
            analysis.key_takeaways = ["Analysis error - manual review recommended"]

        return analysis

    async def analyze_papers_batch(
        self,
        papers: list[dict[str, Any]],
        analysis_depth: str = "standard",
    ) -> list[PaperAnalysis]:
        """Analyze multiple papers."""
        results = []
        for paper in papers:
            analysis = await self.analyze_paper(paper, analysis_depth)
            results.append(analysis)
        return results

    # ========================================================================
    # analyze-github-repo skill implementation
    # ========================================================================

    async def analyze_repo(
        self,
        repo: dict[str, Any],
        include_readme: bool = False,
    ) -> RepoAnalysis:
        """
        Analyze a GitHub repository for tool spotlight.

        Implements the analyze-github-repo skill.

        Args:
            repo: Repo dict with full_name, description, stars, etc.
            include_readme: Whether to fetch and analyze README (future enhancement)

        Returns:
            RepoAnalysis with comprehensive analysis
        """
        full_name = repo.get("full_name", "")
        name = repo.get("name", "")
        description = repo.get("description", "") or ""
        language = repo.get("language", "")
        stars = repo.get("stars", 0)
        forks = repo.get("forks", 0)
        topics = repo.get("topics", [])
        pushed_at = repo.get("pushed_at", "")

        logger.info(f"Analyzing repo: {full_name}")

        # Create base analysis
        analysis = RepoAnalysis(
            full_name=full_name,
            name=name,
        )

        # Check for minimum requirements
        if not description or len(description) < 20:
            logger.warning(f"Description too short for {full_name}")
            analysis.analysis_failed = True
            analysis.spotlight_summary = f"Repository: {full_name}"
            return analysis

        try:
            # Call LLM for analysis
            client = self._get_llm_client()
            response = client.chat.completions.create(
                model=self._get_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "You are a developer tools analyst. Analyze repositories and provide structured analysis in JSON format.",
                    },
                    {
                        "role": "user",
                        "content": REPO_ANALYSIS_PROMPT.format(
                            full_name=full_name,
                            description=description[:500],
                            language=language or "Unknown",
                            stars=stars,
                            forks=forks,
                            topics=", ".join(topics[:10]),
                            pushed_at=pushed_at[:10] if pushed_at else "Unknown",
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=800,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            response_text = response.choices[0].message.content
            data = self._extract_json(response_text)

            # Populate analysis from LLM response
            analysis.category = data.get("category", RepoCategory.OTHER)
            analysis.target_audience = data.get("target_audience", "")
            analysis.use_cases = data.get("use_cases", [])

            analysis.quality_scores = QualityScores(
                documentation=min(max(data.get("documentation_score", 5), 1), 10),
                maintenance=min(max(data.get("maintenance_score", 5), 1), 10),
                community=min(max(data.get("community_score", 5), 1), 10),
                code_quality=min(max(data.get("code_quality_score", 5), 1), 10),
            )

            analysis.spotlight_summary = data.get("spotlight_summary", "")
            analysis.best_for = data.get("best_for", "")

            # Determine spotlight worthiness
            overall_quality = analysis.quality_scores.overall
            analysis.spotlight_worthy = (
                stars >= self.min_stars_for_spotlight and overall_quality >= 7
            )

            logger.info(
                f"Repo analysis complete: {full_name} "
                f"(quality={overall_quality}, spotlight={analysis.spotlight_worthy})"
            )

        except Exception as e:
            logger.error(f"Failed to analyze repo {full_name}: {e}")
            analysis.analysis_failed = True
            analysis.spotlight_summary = f"Analysis failed for: {full_name}"

        return analysis

    async def analyze_repos_batch(
        self,
        repos: list[dict[str, Any]],
        include_readme: bool = False,
    ) -> list[RepoAnalysis]:
        """Analyze multiple repositories."""
        results = []
        for repo in repos:
            analysis = await self.analyze_repo(repo, include_readme)
            results.append(analysis)
        return results

    # ========================================================================
    # Learning integration
    # ========================================================================

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = not result.get("analysis_failed", False)
        await self.record_outcome(skill_name, result, success=success)
