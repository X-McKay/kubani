"""
Structured fact extraction using Strands agents.

Provides reliable fact extraction for mem0 memory storage by using
Strands structured outputs. This ensures the LLM always returns a valid
Pydantic model, avoiding the KeyError: 'facts' issue in mem0.

Usage:
    from core_agents.memory import extract_facts

    # Extract facts from content
    facts = await extract_facts("OpenAI released GPT-5 with improved reasoning")
    print(facts.facts)  # ["OpenAI released GPT-5", "GPT-5 has improved reasoning"]

    # For empty or invalid input, returns empty list
    facts = await extract_facts("")
    print(facts.facts)  # []

Integration with mem0:
    Use extracted facts with mem0's infer=False to skip built-in fact extraction:

    facts = await extract_facts(content)
    # Store with pre-extracted facts (if mem0 supports it) or just use infer=False
    memory.add(content, user_id=..., metadata=..., infer=False)
"""

import logging
from typing import Any

from pydantic import BaseModel, Field
from strands import Agent

from core_agents.base import create_model

logger = logging.getLogger(__name__)


class ExtractedFacts(BaseModel):
    """Structured output model for fact extraction."""

    facts: list[str] = Field(
        default_factory=list,
        description="List of factual statements extracted from the input. "
        "Each fact should be a single, concise statement (under 20 words). "
        "Returns empty list if no facts can be extracted.",
    )


FACT_EXTRACTION_PROMPT = """You are a fact extraction system. Your task is to extract key factual statements from text.

Rules:
1. Extract only factual information, not opinions or speculation
2. Keep each fact concise (under 20 words)
3. Return an empty list if the input is empty, unclear, or contains no extractable facts
4. Focus on specific, actionable information

Examples of good facts:
- "OpenAI released GPT-5"
- "Model scores 95% on benchmarks"
- "Article published on ArXiv"

Examples of what NOT to extract:
- Vague statements: "AI is changing everything"
- Opinions: "This is the best model ever"
- Speculation: "This might lead to AGI"

Extract facts from the provided text. If there are no extractable facts, return an empty list."""


async def extract_facts(
    content: str,
    model: Any | None = None,
) -> ExtractedFacts:
    """
    Extract facts from content using Strands structured output.

    This provides reliable, type-safe fact extraction that always returns
    a valid ExtractedFacts model, avoiding the JSON parsing issues that
    can occur with raw LLM responses.

    Args:
        content: Text content to extract facts from
        model: Optional pre-configured model (uses create_model() if not provided)

    Returns:
        ExtractedFacts with list of extracted fact strings (may be empty)
    """
    # Handle empty/whitespace input without calling LLM
    if not content or not content.strip():
        return ExtractedFacts(facts=[])

    # Truncate very long content to avoid token limits
    max_chars = 4000
    truncated_content = content[:max_chars] if len(content) > max_chars else content

    try:
        agent_model = model or create_model(
            temperature=0.1,  # Low temperature for consistent extraction
            max_tokens=512,  # Facts should be concise
        )

        agent = Agent(
            model=agent_model,
            name="fact-extractor",
            description="Extracts factual statements from text",
            system_prompt=FACT_EXTRACTION_PROMPT,
            tools=[],  # No tools needed for extraction
        )

        # Use structured output to ensure valid response
        result = await agent.structured_output_async(
            f"Extract facts from the following text:\n\n{truncated_content}",
            output_model=ExtractedFacts,
        )

        logger.debug(f"Extracted {len(result.facts)} facts from content")
        return result

    except Exception as e:
        logger.warning(f"Fact extraction failed, returning empty: {e}")
        return ExtractedFacts(facts=[])


def extract_facts_sync(
    content: str,
    model: Any | None = None,
) -> ExtractedFacts:
    """
    Synchronous version of extract_facts.

    Args:
        content: Text content to extract facts from
        model: Optional pre-configured model

    Returns:
        ExtractedFacts with list of extracted fact strings
    """
    import asyncio

    # Get or create event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If there's already a running loop, we can't use run_until_complete
            # Fall back to empty facts rather than blocking
            logger.warning("Event loop already running, skipping async extraction")
            return ExtractedFacts(facts=[])
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(extract_facts(content, model))
