"""Pure functions for generating agent artifacts."""

import yaml

from ..models import AgentSpec


def generate_agent_prompt(spec: AgentSpec) -> str:
    """
    Generates the agent prompt markdown from an AgentSpec.

    This is a pure function that creates the prompt template for an agent.
    """
    skills_list = "\n".join(f"- {skill}" for skill in spec.required_skills)

    return f"""# {spec.name}

## Description

{spec.description}

## Required Skills

{skills_list if skills_list else "- No specific skills required"}

## Instructions

You are an AI agent designed to {spec.description.lower()}.

When handling requests, follow these guidelines:
1. Analyze the user's request carefully
2. Use the appropriate skills to accomplish the task
3. Report results clearly and concisely
"""


def generate_agent_config(spec: AgentSpec) -> str:
    """
    Generates the agent configuration YAML from an AgentSpec.

    This is a pure function that creates the config.yaml content for an agent.
    """
    config = {
        "name": spec.name,
        "description": spec.description,
        "version": "0.1.0",
        "skills": {
            "required": spec.required_skills,
            "allowed": spec.config_patterns.get("skills.allowed", ["*"]),
        },
        "model": spec.config_patterns.get("model", "gpt-4.1-mini"),
        "settings": {
            "max_iterations": 10,
            "timeout_seconds": 300,
        },
    }

    return yaml.dump(config, default_flow_style=False, sort_keys=False)
