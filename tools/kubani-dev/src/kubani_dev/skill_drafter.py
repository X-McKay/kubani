"""LLM-powered skill drafting system."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from kubani_dev.llm_client import LLMClient

logger = logging.getLogger(__name__)


class SkillDrafter:
    """Conversational skill drafting using LLM."""

    def __init__(self, llm_client: LLMClient):
        """
        Initialize skill drafter.

        Args:
            llm_client: LLM client for generation
        """
        self.llm = llm_client
        self.conversation_history: List[Dict[str, str]] = []

    def start_conversation(self, user_request: str) -> str:
        """
        Start a conversation to draft a skill.

        Args:
            user_request: Initial skill description from user

        Returns:
            LLM's response with clarifying questions
        """
        system_prompt = """You are an expert AI agent skill designer. Your job is to help users create high-quality skills for AI agents.

When a user describes a skill they want to create, you should:
1. Ask clarifying questions about:
   - Input parameters (what data does the skill need?)
   - Output format (what should the skill return?)
   - Execution steps (how should the skill work?)
   - Error handling (what could go wrong?)
   - Evaluation criteria (how to measure success?)

2. Be conversational and helpful
3. Ask 2-3 questions at a time, not overwhelming
4. Once you have enough information, summarize the spec for confirmation

Keep responses concise and focused."""

        self.conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"I want to create a skill: {user_request}"},
        ]

        response = self.llm.chat(self.conversation_history, temperature=0.7)
        assistant_message = response["content"]

        self.conversation_history.append({"role": "assistant", "content": assistant_message})

        return assistant_message

    def continue_conversation(self, user_response: str) -> Dict[str, Any]:
        """
        Continue the conversation.

        Args:
            user_response: User's response to previous questions

        Returns:
            Dict with 'message', 'is_ready' (bool), 'spec' (if ready)
        """
        self.conversation_history.append({"role": "user", "content": user_response})

        # Add instruction to check if we have enough info
        check_prompt = """Based on the conversation so far, determine if you have enough information to create the skill.

If YES: Respond with "READY:" followed by a JSON spec with these fields:
- name: skill name (kebab-case)
- description: one-line description
- inputs: dict of {param_name: {type, description, required}}
- outputs: dict of {field_name: {type, description}}
- steps: list of execution steps
- error_handling: list of potential errors and how to handle them

If NO: Ask more clarifying questions (2-3 max)."""

        temp_history = self.conversation_history + [{"role": "system", "content": check_prompt}]

        response = self.llm.chat(temp_history, temperature=0.5)
        assistant_message = response["content"]

        # Strip thinking tags from reasoning models
        assistant_message = self.llm._strip_thinking_tags(assistant_message)

        # Check if ready - look for READY: anywhere in the response
        if "READY:" in assistant_message:
            spec_json = self._extract_json_from_response(assistant_message)

            if spec_json:
                try:
                    spec = json.loads(spec_json)
                    return {
                        "message": "I have all the information needed. Here's the spec:",
                        "is_ready": True,
                        "spec": spec,
                    }
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse spec JSON: {e}")
                    logger.error(f"Extracted JSON was: {spec_json[:500]}...")
                    # Return error to user so they know what happened
                    return {
                        "message": f"I found a spec but couldn't parse the JSON. Error: {e}\n\n"
                        f"Please say 'retry' to try again, or continue the conversation.",
                        "is_ready": False,
                    }
            else:
                logger.error("Found READY: but couldn't extract JSON from response")
                return {
                    "message": "I think the spec is ready but couldn't extract it. "
                    "Please say 'retry' to try again.",
                    "is_ready": False,
                }

        # Not ready, continue conversation
        self.conversation_history.append({"role": "assistant", "content": assistant_message})

        return {"message": assistant_message, "is_ready": False}

    def _extract_json_from_response(self, response: str) -> Optional[str]:
        """
        Extract JSON object from LLM response.

        Handles various formats:
        - READY: {...}
        - READY:\n```json\n{...}\n```
        - READY:\n{...}\n
        - Text before/after the JSON

        Args:
            response: Raw LLM response containing JSON

        Returns:
            Extracted JSON string or None if not found
        """

        # First, try to extract from code blocks
        if "```json" in response:
            match = re.search(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
            if match:
                return match.group(1).strip()

        if "```" in response:
            match = re.search(r"```\s*(\{.*?\})\s*```", response, re.DOTALL)
            if match:
                return match.group(1).strip()

        # Find the JSON object by matching balanced braces
        # Start from the first { after READY:
        ready_pos = response.find("READY:")
        if ready_pos == -1:
            ready_pos = 0
        else:
            ready_pos += len("READY:")

        # Find the first opening brace
        start = response.find("{", ready_pos)
        if start == -1:
            return None

        # Find matching closing brace by counting
        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(response[start:], start):
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return response[start : i + 1]

        return None

    def generate_skill_files(self, spec: Dict[str, Any], output_dir: Path) -> Dict[str, Path]:
        """
        Generate skill files from spec.

        Args:
            spec: Skill specification
            output_dir: Directory to create files in

        Returns:
            Dict of {filename: path}
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        files = {}

        # Generate SKILL.md
        skill_md = self._generate_skill_md(spec)
        skill_md_path = output_dir / "SKILL.md"
        skill_md_path.write_text(skill_md)
        files["SKILL.md"] = skill_md_path

        # Generate test_cases.yaml
        test_cases = self._generate_test_cases(spec)
        test_cases_path = output_dir / "test_cases.yaml"
        test_cases_path.write_text(test_cases)
        files["test_cases.yaml"] = test_cases_path

        # Generate metadata.json
        metadata = {
            "name": spec["name"],
            "description": spec["description"],
            "version": "0.1.0",
            "inputs": spec.get("inputs", {}),
            "outputs": spec.get("outputs", {}),
            "created_by": "llm",
            "status": "draft",
        }
        metadata_path = output_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2))
        files["metadata.json"] = metadata_path

        return files

    def _generate_skill_md(self, spec: Dict[str, Any]) -> str:
        """Generate SKILL.md content from spec."""
        prompt = f"""Generate a complete SKILL.md file for this skill specification:

{json.dumps(spec, indent=2)}

The SKILL.md should be a professional markdown document with:
1. Title and description
2. Input Parameters section (table format)
3. Output Format section with STRICT JSON schema
4. Execution Steps (numbered list)
5. Error Handling section
6. Example Usage section

IMPORTANT for Output Format section:
- Specify EXACT JSON field names that match the test assertions
- Use flat JSON structure (no nested objects unless explicitly needed)
- Show example JSON output
- Add a note: "CRITICAL: Return ONLY this exact JSON structure, no additional wrapper fields"

Make it clear, concise, and actionable for an AI agent to follow."""

        messages = [
            {
                "role": "system",
                "content": "You are a technical writer creating skill documentation.",
            },
            {"role": "user", "content": prompt},
        ]

        response = self.llm.chat(messages, temperature=0.5)
        content = response["content"]

        # Strip thinking tags (Qwen3 and other reasoning models)
        content = self.llm._strip_thinking_tags(content)

        return content

    def _generate_test_cases(self, spec: Dict[str, Any]) -> str:
        """Generate test_cases.yaml from spec."""
        prompt = f"""Generate a test_cases.yaml file for this skill:

{json.dumps(spec, indent=2)}

Create 5-8 comprehensive test cases covering:
1. Happy path (normal execution)
2. Edge cases (boundary conditions)
3. Error cases (invalid inputs)
4. Performance cases (if relevant)

Format as YAML with this structure:
```yaml
test_cases:
  - name: test_name
    description: what this tests
    inputs:
      param1: value1
    expected_outputs:
      field1: value1
    assertions:
      - field: field_name
        type: equals|contains|exists
        value: expected_value
```

Return ONLY the YAML, no explanation."""

        messages = [
            {"role": "system", "content": "You are a QA engineer creating test cases."},
            {"role": "user", "content": prompt},
        ]

        response = self.llm.chat(messages, temperature=0.5)
        content = response["content"]

        # Strip thinking tags (Qwen3 and other reasoning models)
        content = self.llm._strip_thinking_tags(content)

        # Extract YAML if wrapped in code blocks
        if "```yaml" in content:
            content = content.split("```yaml")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return content
