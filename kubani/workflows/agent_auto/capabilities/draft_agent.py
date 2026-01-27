"""Capability for drafting new agents."""

from ..protocols import FileSystem, LLMClient, SkillRepository
from .analysis import analyze_agent_requirements
from .generation import generate_agent_config, generate_agent_prompt


class DraftingService:
    """Service responsible for the initial drafting of an agent.

    Orchestrates the process of analyzing requirements, identifying
    skill gaps, and generating the initial agent files.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        fs: FileSystem,
        skill_repo: SkillRepository,
    ):
        self._llm = llm_client
        self._fs = fs
        self._skill_repo = skill_repo

    async def draft_agent(self, description: str) -> dict:
        """
        Orchestrates the agent drafting process.

        1. Analyzes description to get an AgentSpec.
        2. Checks which required skills already exist.
        3. Returns a list of missing skills and the generated agent files.

        Args:
            description: High-level description of what the agent should do.

        Returns:
            Dictionary containing:
            - missing_skills: List of skill names that need to be created
            - files_to_create: Dict mapping file paths to their content
        """
        # In a real scenario, this would use the LLM, but we use the pure function
        agent_spec = analyze_agent_requirements(description)

        existing_skills = self._skill_repo.get_skills_by_name(agent_spec.required_skills)
        existing_skill_names = {s.name for s in existing_skills}
        missing_skills = [s for s in agent_spec.required_skills if s not in existing_skill_names]

        # Don't write files yet; the workflow will do that after creating missing skills.
        # Instead, return the content to be written.
        agent_prompt = generate_agent_prompt(agent_spec)
        agent_config = generate_agent_config(agent_spec)

        return {
            "agent_spec": agent_spec,
            "missing_skills": missing_skills,
            "files_to_create": {
                f"agents/{agent_spec.name}/prompt.md": agent_prompt,
                f"agents/{agent_spec.name}/config.yaml": agent_config,
            },
        }
