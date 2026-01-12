"""
Reflection Agent for Cross-Agent Knowledge Synthesis.

The Reflection Agent:
- Monitors all agent executions and interactions
- Synthesizes learnings across agents
- Stores important knowledge in shared memory (Qdrant, Neo4j)
- Identifies cross-cutting patterns and improvements
- Periodically generates reflection reports

Inspired by Voyager's curriculum learning and self-reflection.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class KnowledgeType(Enum):
    """Types of knowledge that can be stored."""

    SKILL_PATTERN = "skill_pattern"
    FAILURE_PATTERN = "failure_pattern"
    SUCCESS_PATTERN = "success_pattern"
    DOMAIN_INSIGHT = "domain_insight"
    TOOL_USAGE = "tool_usage"
    INTERACTION_PATTERN = "interaction_pattern"


class KnowledgeImportance(Enum):
    """Importance levels for knowledge."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Knowledge:
    """A piece of knowledge extracted from agent interactions."""

    id: str
    type: KnowledgeType
    importance: KnowledgeImportance
    title: str
    description: str
    content: dict[str, Any]
    source_agents: list[str]
    source_executions: list[str]
    tags: list[str] = field(default_factory=list)
    embedding: list[float] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    access_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "importance": self.importance.value,
            "title": self.title,
            "description": self.description,
            "content": self.content,
            "source_agents": self.source_agents,
            "source_executions": self.source_executions,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "access_count": self.access_count,
        }


@dataclass
class ReflectionReport:
    """A periodic reflection report synthesizing learnings."""

    period_start: datetime
    period_end: datetime
    total_executions: int
    success_rate: float
    key_learnings: list[Knowledge]
    skill_proposals: list[dict[str, Any]]
    improvement_areas: list[str]
    cross_agent_patterns: list[dict[str, Any]]
    recommendations: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_executions": self.total_executions,
            "success_rate": self.success_rate,
            "key_learnings": [k.to_dict() for k in self.key_learnings],
            "skill_proposals": self.skill_proposals,
            "improvement_areas": self.improvement_areas,
            "cross_agent_patterns": self.cross_agent_patterns,
            "recommendations": self.recommendations,
        }

    def to_discord_message(self) -> str:
        """Format as a Discord message."""
        msg = f"""📊 **Reflection Report**
*{self.period_start.strftime('%Y-%m-%d %H:%M')} - {self.period_end.strftime('%Y-%m-%d %H:%M')} UTC*

**Summary**
• Total Executions: {self.total_executions}
• Success Rate: {self.success_rate:.1%}

**Key Learnings**
"""
        for learning in self.key_learnings[:5]:
            msg += f"• **{learning.title}**: {learning.description[:100]}...\n"

        if self.skill_proposals:
            msg += "\n**Proposed Skills**\n"
            for proposal in self.skill_proposals[:3]:
                msg += f"• {proposal['name']}: {proposal['description'][:80]}...\n"

        if self.improvement_areas:
            msg += "\n**Areas for Improvement**\n"
            for area in self.improvement_areas[:3]:
                msg += f"• {area}\n"

        if self.recommendations:
            msg += "\n**Recommendations**\n"
            for rec in self.recommendations[:3]:
                msg += f"• {rec}\n"

        return msg


class ReflectionAgent:
    """
    Reflection Agent that synthesizes knowledge across agents.

    Responsibilities:
    1. Monitor execution logs and Discord interactions
    2. Extract and store knowledge in shared memory
    3. Generate periodic reflection reports
    4. Propose cross-cutting improvements
    """

    KNOWLEDGE_EXTRACTION_PROMPT = """You are a Reflection Agent analyzing agent executions to extract reusable knowledge.

Recent Executions (last {hours} hours):
{executions}

Discord Interactions:
{interactions}

Analyze these and extract:
1. Successful patterns that should be remembered
2. Failure patterns to avoid
3. Domain insights learned
4. Tool usage patterns
5. Cross-agent patterns (things multiple agents could benefit from)

For each piece of knowledge, assess its importance (critical/high/medium/low).

Respond as JSON:
{{
    "knowledge_items": [
        {{
            "type": "<skill_pattern|failure_pattern|success_pattern|domain_insight|tool_usage|interaction_pattern>",
            "importance": "<critical|high|medium|low>",
            "title": "<short title>",
            "description": "<detailed description>",
            "content": {{<structured content>}},
            "source_agents": ["<agent1>", ...],
            "tags": ["<tag1>", ...]
        }}
    ],
    "skill_proposals": [
        {{
            "name": "<skill_name>",
            "description": "<what it does>",
            "trigger": "<when to use>",
            "applicable_agents": ["<agent1>", ...]
        }}
    ],
    "cross_agent_patterns": [
        {{
            "pattern": "<pattern description>",
            "agents": ["<agent1>", ...],
            "recommendation": "<how to leverage>"
        }}
    ]
}}"""

    REFLECTION_PROMPT = """You are a Reflection Agent generating a periodic report.

Period: {period_start} to {period_end}

Execution Statistics:
- Total: {total_executions}
- Successful: {successful}
- Failed: {failed}

Knowledge Extracted:
{knowledge_summary}

Skill Proposals:
{skill_proposals}

Generate a reflection report with:
1. Key insights from this period
2. Areas needing improvement
3. Recommendations for the team
4. Priority actions

Respond as JSON:
{{
    "improvement_areas": ["<area 1>", ...],
    "recommendations": ["<recommendation 1>", ...],
    "priority_actions": ["<action 1>", ...]
}}"""

    def __init__(
        self,
        llm_api_url: str,
        llm_model: str,
        qdrant_client: Any = None,
        neo4j_driver: Any = None,
        embeddings_api_url: str | None = None,
    ):
        self.llm_api_url = llm_api_url
        self.llm_model = llm_model
        self.qdrant_client = qdrant_client
        self.neo4j_driver = neo4j_driver
        self.embeddings_api_url = embeddings_api_url
        self.knowledge_cache: list[Knowledge] = []

    async def extract_knowledge(
        self,
        executions: list[dict[str, Any]],
        interactions: list[dict[str, Any]],
        hours: int = 24,
    ) -> list[Knowledge]:
        """Extract knowledge from recent executions and interactions."""
        prompt = self.KNOWLEDGE_EXTRACTION_PROMPT.format(
            hours=hours,
            executions=json.dumps(executions[:20], indent=2),  # Limit for context
            interactions=json.dumps(interactions[:20], indent=2),
        )

        try:
            response = await self._call_llm(prompt)
            data = self._parse_json_response(response)

            knowledge_items = []
            for item in data.get("knowledge_items", []):
                knowledge = Knowledge(
                    id=f"k_{datetime.now(UTC).timestamp()}_{len(knowledge_items)}",
                    type=KnowledgeType(item["type"]),
                    importance=KnowledgeImportance(item["importance"]),
                    title=item["title"],
                    description=item["description"],
                    content=item.get("content", {}),
                    source_agents=item.get("source_agents", []),
                    source_executions=[],
                    tags=item.get("tags", []),
                )
                knowledge_items.append(knowledge)

            # Store in memory systems
            await self._store_knowledge(knowledge_items)

            return knowledge_items

        except Exception as e:
            logger.error(f"Knowledge extraction failed: {e}")
            return []

    async def generate_reflection_report(
        self,
        period_hours: int = 24,
    ) -> ReflectionReport:
        """Generate a periodic reflection report."""
        period_end = datetime.now(UTC)
        period_start = period_end - timedelta(hours=period_hours)

        # Get execution statistics (placeholder - would query actual logs)
        total_executions = 100
        successful = 85
        failed = 15

        # Get recent knowledge
        knowledge_summary = json.dumps(
            [k.to_dict() for k in self.knowledge_cache[-20:]],
            indent=2,
        )

        prompt = self.REFLECTION_PROMPT.format(
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            total_executions=total_executions,
            successful=successful,
            failed=failed,
            knowledge_summary=knowledge_summary,
            skill_proposals="[]",  # Would come from Critic Agent
        )

        try:
            response = await self._call_llm(prompt)
            data = self._parse_json_response(response)

            return ReflectionReport(
                period_start=period_start,
                period_end=period_end,
                total_executions=total_executions,
                success_rate=successful / total_executions if total_executions > 0 else 0,
                key_learnings=self.knowledge_cache[-10:],
                skill_proposals=[],
                improvement_areas=data.get("improvement_areas", []),
                cross_agent_patterns=[],
                recommendations=data.get("recommendations", []),
            )

        except Exception as e:
            logger.error(f"Reflection report generation failed: {e}")
            return ReflectionReport(
                period_start=period_start,
                period_end=period_end,
                total_executions=0,
                success_rate=0,
                key_learnings=[],
                skill_proposals=[],
                improvement_areas=[f"Report generation failed: {e}"],
                cross_agent_patterns=[],
                recommendations=[],
            )

    async def _store_knowledge(self, knowledge_items: list[Knowledge]) -> None:
        """Store knowledge in Qdrant and Neo4j."""
        for knowledge in knowledge_items:
            # Generate embedding
            if self.embeddings_api_url:
                knowledge.embedding = await self._get_embedding(
                    f"{knowledge.title} {knowledge.description}"
                )

            # Store in Qdrant for semantic search
            if self.qdrant_client and knowledge.embedding:
                await self._store_in_qdrant(knowledge)

            # Store relationships in Neo4j
            if self.neo4j_driver:
                await self._store_in_neo4j(knowledge)

            # Add to local cache
            self.knowledge_cache.append(knowledge)

    async def _store_in_qdrant(self, knowledge: Knowledge) -> None:
        """Store knowledge in Qdrant for semantic search."""
        try:
            from qdrant_client.models import PointStruct

            point = PointStruct(
                id=hash(knowledge.id) % (2**63),
                vector=knowledge.embedding,
                payload=knowledge.to_dict(),
            )

            self.qdrant_client.upsert(
                collection_name="kubani_knowledge",
                points=[point],
            )
        except Exception as e:
            logger.warning(f"Failed to store in Qdrant: {e}")

    async def _store_in_neo4j(self, knowledge: Knowledge) -> None:
        """Store knowledge relationships in Neo4j."""
        try:
            async with self.neo4j_driver.session() as session:
                # Create knowledge node
                await session.run(
                    """
                    MERGE (k:Knowledge {id: $id})
                    SET k.type = $type,
                        k.importance = $importance,
                        k.title = $title,
                        k.description = $description,
                        k.created_at = $created_at
                    """,
                    id=knowledge.id,
                    type=knowledge.type.value,
                    importance=knowledge.importance.value,
                    title=knowledge.title,
                    description=knowledge.description,
                    created_at=knowledge.created_at.isoformat(),
                )

                # Create relationships to agents
                for agent in knowledge.source_agents:
                    await session.run(
                        """
                        MERGE (a:Agent {name: $agent_name})
                        MERGE (k:Knowledge {id: $knowledge_id})
                        MERGE (a)-[:LEARNED]->(k)
                        """,
                        agent_name=agent,
                        knowledge_id=knowledge.id,
                    )

                # Create tag relationships
                for tag in knowledge.tags:
                    await session.run(
                        """
                        MERGE (t:Tag {name: $tag})
                        MERGE (k:Knowledge {id: $knowledge_id})
                        MERGE (k)-[:TAGGED]->(t)
                        """,
                        tag=tag,
                        knowledge_id=knowledge.id,
                    )

        except Exception as e:
            logger.warning(f"Failed to store in Neo4j: {e}")

    async def _get_embedding(self, text: str) -> list[float]:
        """Get embedding for text."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.embeddings_api_url}/embeddings",
                    json={"input": text, "model": "BAAI/bge-large-en-v1.5"},
                    timeout=30.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data["data"][0]["embedding"]
        except Exception as e:
            logger.warning(f"Failed to get embedding: {e}")
        return []

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM API."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.llm_api_url}/chat/completions",
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 4096,
                },
                timeout=90.0,
            )

            if response.status_code != 200:
                raise RuntimeError(f"LLM API error: {response.status_code}")

            data = response.json()
            return data["choices"][0]["message"]["content"]

    def _parse_json_response(self, response: str) -> dict[str, Any]:
        """Parse JSON from LLM response."""
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(response[json_start:json_end])
        raise ValueError("No valid JSON found in response")
