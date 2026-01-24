"""
RSS feed configuration for the feed collector.

Curated list of AI-relevant news sources organized by category.
"""

from dataclasses import dataclass
from enum import Enum


class FeedCategory(str, Enum):
    """Categories for organizing news sources."""

    GENERAL_TECH = "general_tech"
    AI_FOCUSED = "ai_focused"
    RESEARCH = "research"
    COMPANY_BLOGS = "company_blogs"
    SECURITY = "security"
    BUSINESS = "business"


@dataclass
class FeedConfig:
    """Configuration for a single RSS feed."""

    name: str
    url: str
    category: FeedCategory
    priority: int = 5  # 1-10, higher = more important
    enabled: bool = True


# Curated list of AI-relevant RSS feeds
FEEDS: list[FeedConfig] = [
    # ==========================================================================
    # General Tech News (often covers AI)
    # ==========================================================================
    FeedConfig(
        name="Hacker News",
        url="https://hnrss.org/frontpage",
        category=FeedCategory.GENERAL_TECH,
        priority=8,
    ),
    FeedConfig(
        name="Hacker News - AI filtered",
        url="https://hnrss.org/newest?q=AI+OR+LLM+OR+GPT+OR+Claude+OR+machine+learning",
        category=FeedCategory.GENERAL_TECH,
        priority=9,
    ),
    FeedConfig(
        name="Ars Technica - AI",
        url="https://feeds.arstechnica.com/arstechnica/technology-lab",
        category=FeedCategory.GENERAL_TECH,
        priority=7,
    ),
    FeedConfig(
        name="The Verge - AI",
        url="https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        category=FeedCategory.GENERAL_TECH,
        priority=7,
    ),
    FeedConfig(
        name="Wired - AI",
        url="https://www.wired.com/feed/tag/ai/latest/rss",
        category=FeedCategory.GENERAL_TECH,
        priority=6,
    ),
    # ==========================================================================
    # AI-Focused Publications
    # ==========================================================================
    FeedConfig(
        name="MIT Technology Review - AI",
        url="https://www.technologyreview.com/topic/artificial-intelligence/feed",
        category=FeedCategory.AI_FOCUSED,
        priority=9,
    ),
    FeedConfig(
        name="VentureBeat - AI",
        url="https://venturebeat.com/category/ai/feed/",
        category=FeedCategory.AI_FOCUSED,
        priority=7,
    ),
    FeedConfig(
        name="TechCrunch - AI",
        url="https://techcrunch.com/category/artificial-intelligence/feed/",
        category=FeedCategory.AI_FOCUSED,
        priority=7,
    ),
    FeedConfig(
        name="The Batch (DeepLearning.AI)",
        url="https://www.deeplearning.ai/the-batch/feed/",
        category=FeedCategory.AI_FOCUSED,
        priority=8,
    ),
    # ==========================================================================
    # Research (ArXiv)
    # ==========================================================================
    FeedConfig(
        name="ArXiv - Artificial Intelligence",
        url="https://rss.arxiv.org/rss/cs.AI",
        category=FeedCategory.RESEARCH,
        priority=6,
    ),
    FeedConfig(
        name="ArXiv - Machine Learning",
        url="https://rss.arxiv.org/rss/cs.LG",
        category=FeedCategory.RESEARCH,
        priority=6,
    ),
    FeedConfig(
        name="ArXiv - Computation and Language",
        url="https://rss.arxiv.org/rss/cs.CL",
        category=FeedCategory.RESEARCH,
        priority=7,
    ),
    # ==========================================================================
    # Company Blogs
    # ==========================================================================
    FeedConfig(
        name="OpenAI Blog",
        url="https://openai.com/news/rss.xml",
        category=FeedCategory.COMPANY_BLOGS,
        priority=10,
    ),
    FeedConfig(
        name="Anthropic News",
        url="https://www.anthropic.com/news/rss",
        category=FeedCategory.COMPANY_BLOGS,
        priority=10,
        enabled=False,  # No public RSS feed available (verified 2026-01-23)
    ),
    FeedConfig(
        name="Google AI Blog",
        url="https://blog.google/technology/ai/rss/",
        category=FeedCategory.COMPANY_BLOGS,
        priority=9,
    ),
    FeedConfig(
        name="Meta AI Blog",
        url="https://ai.meta.com/blog/rss/",
        category=FeedCategory.COMPANY_BLOGS,
        priority=8,
    ),
    FeedConfig(
        name="Microsoft AI Blog",
        url="https://blogs.microsoft.com/ai/feed/",
        category=FeedCategory.COMPANY_BLOGS,
        priority=8,
    ),
    FeedConfig(
        name="NVIDIA AI Blog",
        url="https://blogs.nvidia.com/feed/",
        category=FeedCategory.COMPANY_BLOGS,
        priority=7,
    ),
    FeedConfig(
        name="Hugging Face Blog",
        url="https://huggingface.co/blog/feed.xml",
        category=FeedCategory.COMPANY_BLOGS,
        priority=8,
    ),
    # ==========================================================================
    # Security & Safety
    # ==========================================================================
    FeedConfig(
        name="Schneier on Security",
        url="https://www.schneier.com/feed/",
        category=FeedCategory.SECURITY,
        priority=6,
    ),
    FeedConfig(
        name="The Hacker News (Security)",
        url="https://feeds.feedburner.com/TheHackersNews",
        category=FeedCategory.SECURITY,
        priority=5,
    ),
    # ==========================================================================
    # Business & Industry
    # ==========================================================================
    FeedConfig(
        name="Reuters - Technology",
        url="https://www.reutersagency.com/feed/?best-topics=tech",
        category=FeedCategory.BUSINESS,
        priority=7,
        enabled=False,  # RSS feed discontinued, returns 401 (verified 2026-01-23)
    ),
]


def get_enabled_feeds() -> list[FeedConfig]:
    """Get all enabled feeds sorted by priority (highest first)."""
    return sorted(
        [f for f in FEEDS if f.enabled],
        key=lambda f: f.priority,
        reverse=True,
    )


def get_feeds_by_category(category: FeedCategory) -> list[FeedConfig]:
    """Get enabled feeds for a specific category."""
    return [f for f in get_enabled_feeds() if f.category == category]


# Keywords for filtering AI-relevant content from general feeds
AI_KEYWORDS = [
    # General AI terms
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "neural network",
    "large language model",
    "LLM",
    "generative AI",
    "GenAI",
    # Models and techniques
    "transformer",
    "GPT",
    "Claude",
    "Gemini",
    "Llama",
    "diffusion model",
    "reinforcement learning",
    "fine-tuning",
    "RAG",
    "retrieval augmented",
    "embedding",
    "vector database",
    # Companies
    "OpenAI",
    "Anthropic",
    "DeepMind",
    "Hugging Face",
    "Stability AI",
    "Mistral",
    "Cohere",
    # Applications
    "chatbot",
    "AI agent",
    "AI assistant",
    "copilot",
    "text-to-image",
    "text-to-video",
    "speech recognition",
    "computer vision",
    # Safety and ethics
    "AI safety",
    "AI alignment",
    "AI regulation",
    "AI governance",
    "AI ethics",
    "AI bias",
    "AI risk",
    # Technical
    "inference",
    "training run",
    "GPU cluster",
    "TPU",
    "model weights",
    "benchmark",
    "MMLU",
    "tokenizer",
]


def is_ai_relevant(text: str) -> bool:
    """Check if text contains AI-relevant keywords."""
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in AI_KEYWORDS)
