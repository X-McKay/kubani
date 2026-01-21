"""LLM-powered skill drafting system."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from kubani_dev.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Patterns that indicate a skill needs deterministic scripts
SCRIPT_TRIGGER_PATTERNS = [
    # Math/calculations
    r"\b(calculate|compute|sum|average|mean|median|factorial|fibonacci)\b",
    r"\b(multiply|divide|add|subtract|percentage|ratio)\b",
    r"\b(math|arithmetic|formula|equation)\b",
    # Data parsing/transformation
    r"\b(parse|extract|transform|convert|format)\b",
    r"\b(json|yaml|xml|csv|regex)\b",
    # Encoding/hashing
    r"\b(encode|decode|hash|encrypt|decrypt|base64)\b",
    # Validation
    r"\b(validate|verify|check format|sanitize)\b",
]

# Compiled patterns for efficiency
SCRIPT_TRIGGER_COMPILED = [re.compile(p, re.IGNORECASE) for p in SCRIPT_TRIGGER_PATTERNS]

# Tool detection patterns - maps keywords to allowed tools
TOOL_DETECTION_PATTERNS = {
    # Kubernetes operations
    r"\b(kubernetes|k8s|pod|deployment|service|namespace|kubectl)\b": [
        "mcp__kubernetes-mcp-server__pods_list",
        "mcp__kubernetes-mcp-server__pods_get",
        "mcp__kubernetes-mcp-server__pods_log",
        "mcp__kubernetes-mcp-server__resources_list",
        "mcp__kubernetes-mcp-server__resources_get",
    ],
    # Temporal workflows
    r"\b(temporal|workflow|activity)\b": [
        "mcp__temporal-mcp-server__list_workflows",
        "mcp__temporal-mcp-server__get_workflow",
        "mcp__temporal-mcp-server__get_workflow_history",
    ],
    # File operations
    r"\b(read file|file content|file system)\b": ["Read", "Glob"],
    # Search operations
    r"\b(search|find|grep|pattern)\b": ["Grep", "Glob"],
    # Web operations
    r"\b(fetch|http|url|api call|web)\b": ["WebFetch"],
    # Discord
    r"\b(discord|message|channel|notification)\b": [
        "mcp__discord-mcp__send_message",
        "mcp__discord-mcp__get_messages",
    ],
    # Git operations
    r"\b(git|commit|branch|repository)\b": ["Bash"],
    # Shell/Bash operations
    r"\b(shell|bash|command|execute|run)\b": ["Bash"],
}

# Compiled tool patterns
TOOL_PATTERNS_COMPILED = {
    re.compile(pattern, re.IGNORECASE): tools for pattern, tools in TOOL_DETECTION_PATTERNS.items()
}

# Patterns that indicate structured output (needs template.md)
STRUCTURED_OUTPUT_PATTERNS = [
    r"\b(report|summary|status|dashboard)\b",
    r"\b(table|markdown|formatted)\b",
    r"\b(list of|array of|collection of)\b",
    r"\b(json output|structured|schema)\b",
    r"\b(health check|overview|metrics)\b",
]

STRUCTURED_OUTPUT_COMPILED = [re.compile(p, re.IGNORECASE) for p in STRUCTURED_OUTPUT_PATTERNS]


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
   - Concrete examples (can you provide 1-2 real examples with input and expected output?)

2. Be conversational and helpful
3. Ask 2-3 questions at a time, not overwhelming
4. IMPORTANT: Always ask for at least one concrete example with input/output before finalizing
5. Once you have enough information AND at least one example, summarize the spec for confirmation

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

IMPORTANT: You MUST have at least one concrete example with input and expected output before being ready.

If YES (you have all info AND at least one example): Respond with "READY:" followed by a JSON spec with these fields:
- name: skill name (kebab-case)
- description: one-line description
- inputs: dict of {param_name: {type, description, required}}
- outputs: dict of {field_name: {type, description}}
- steps: list of execution steps
- error_handling: list of potential errors and how to handle them
- examples: list of {name: str, description: str, input: dict, expected_output: dict}
  (REQUIRED: at least 1 example, ideally 2-3 covering happy path and edge cases)

If NO: Ask for the missing information. If you don't have examples yet, ask: "Can you provide a concrete example with input values and expected output?"
"""

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

    def _detect_script_requirement(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect if a skill requires deterministic scripts.

        Analyzes the skill spec to determine if operations are better suited
        for deterministic Python execution rather than LLM-based execution.

        Args:
            spec: Skill specification

        Returns:
            Dict with 'requires_scripts' (bool) and 'script_type' (str)
        """
        result = {"requires_scripts": False, "script_type": None, "operations": []}

        # Build text to analyze from spec
        text_to_analyze = " ".join(
            [
                spec.get("name", ""),
                spec.get("description", ""),
                " ".join(spec.get("steps", [])),
                json.dumps(spec.get("inputs", {})),
                json.dumps(spec.get("outputs", {})),
            ]
        )

        # Check for trigger patterns
        matched_patterns = []
        for pattern in SCRIPT_TRIGGER_COMPILED:
            matches = pattern.findall(text_to_analyze)
            if matches:
                matched_patterns.extend(matches)

        if matched_patterns:
            result["requires_scripts"] = True
            result["operations"] = list(set(matched_patterns))

            # Determine script type based on patterns
            math_patterns = {"calculate", "compute", "sum", "average", "factorial", "fibonacci"}
            parse_patterns = {"parse", "extract", "transform", "convert", "format"}
            encode_patterns = {"encode", "decode", "hash", "encrypt", "base64"}

            operations_lower = {op.lower() for op in matched_patterns}

            if operations_lower & math_patterns:
                result["script_type"] = "calculation"
            elif operations_lower & parse_patterns:
                result["script_type"] = "transformation"
            elif operations_lower & encode_patterns:
                result["script_type"] = "encoding"
            else:
                result["script_type"] = "utility"

            logger.info(
                f"Detected script requirement: type={result['script_type']}, "
                f"operations={result['operations']}"
            )

        return result

    def _detect_allowed_tools(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect which tools a skill needs based on its description and steps.

        Args:
            spec: Skill specification

        Returns:
            Dict with 'allowed_tools' list and 'tool_categories' detected
        """
        result = {"allowed_tools": [], "tool_categories": []}

        # Build text to analyze from spec
        text_to_analyze = " ".join(
            [
                spec.get("name", ""),
                spec.get("description", ""),
                " ".join(spec.get("steps", [])),
            ]
        )

        # Check for tool patterns
        detected_tools = set()
        categories = set()

        for pattern, tools in TOOL_PATTERNS_COMPILED.items():
            if pattern.search(text_to_analyze):
                detected_tools.update(tools)
                # Extract category from pattern description
                pattern_str = pattern.pattern
                if "kubernetes" in pattern_str or "k8s" in pattern_str:
                    categories.add("kubernetes")
                elif "temporal" in pattern_str:
                    categories.add("temporal")
                elif "discord" in pattern_str:
                    categories.add("discord")
                elif "file" in pattern_str or "read" in pattern_str:
                    categories.add("file-operations")
                elif "web" in pattern_str or "http" in pattern_str:
                    categories.add("web")
                elif "git" in pattern_str:
                    categories.add("git")
                elif "bash" in pattern_str or "shell" in pattern_str:
                    categories.add("shell")

        if detected_tools:
            result["allowed_tools"] = sorted(list(detected_tools))
            result["tool_categories"] = sorted(list(categories))
            logger.info(
                f"Detected allowed tools: categories={result['tool_categories']}, "
                f"tools={len(result['allowed_tools'])}"
            )

        return result

    def _detect_structured_output(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect if a skill produces structured output that needs a template.

        Args:
            spec: Skill specification

        Returns:
            Dict with 'has_template' (bool) and 'output_fields' (list)
        """
        result = {"has_template": False, "output_fields": [], "template_type": None}

        # Build text to analyze
        text_to_analyze = " ".join(
            [
                spec.get("name", ""),
                spec.get("description", ""),
                " ".join(spec.get("steps", [])),
                json.dumps(spec.get("outputs", {})),
            ]
        )

        # Check for structured output patterns
        for pattern in STRUCTURED_OUTPUT_COMPILED:
            if pattern.search(text_to_analyze):
                result["has_template"] = True
                break

        # Also check if outputs have multiple fields
        outputs = spec.get("outputs", {})
        if len(outputs) >= 2:
            result["has_template"] = True

        if result["has_template"]:
            # Extract output field names
            result["output_fields"] = list(outputs.keys()) if outputs else []

            # Determine template type
            desc_lower = spec.get("description", "").lower()
            if "report" in desc_lower or "summary" in desc_lower:
                result["template_type"] = "report"
            elif "table" in desc_lower or "list" in desc_lower:
                result["template_type"] = "table"
            elif "status" in desc_lower or "health" in desc_lower:
                result["template_type"] = "status"
            else:
                result["template_type"] = "generic"

            logger.info(
                f"Detected structured output: type={result['template_type']}, "
                f"fields={result['output_fields']}"
            )

        return result

    def _generate_template_md(self, spec: Dict[str, Any], template_info: Dict[str, Any]) -> str:
        """
        Generate a template.md file for structured output.

        Args:
            spec: Skill specification
            template_info: Template detection info with 'template_type' and 'output_fields'

        Returns:
            Template markdown content with placeholders
        """
        name = spec.get("name", "Skill")
        description = spec.get("description", "")
        template_type = template_info.get("template_type", "generic")
        output_fields = template_info.get("output_fields", [])

        # Build placeholder section
        placeholders = []
        for field in output_fields:
            placeholders.append(f"- `{{{{{field}}}}}`")

        placeholders_section = "\n".join(placeholders) if placeholders else "- `{{result}}`"

        # Format name for title (avoid duplicating type suffix)
        title_name = name.replace("-", " ").title()

        # Generate template based on type
        if template_type == "report":
            # Avoid "Report Report" if name already contains "Report"
            title_suffix = "" if "report" in name.lower() else " Report"
            template = f"""# {title_name}{title_suffix}

## Summary

{{{{summary}}}}

## Details

"""
            for field in output_fields:
                template += f"### {field.replace('_', ' ').title()}\n\n{{{{{field}}}}}\n\n"

            template += """## Conclusion

{{conclusion}}
"""
        elif template_type == "table":
            template = f"""# {title_name}

## Results

| Field | Value |
|-------|-------|
"""
            for field in output_fields:
                template += f"| {field.replace('_', ' ').title()} | {{{{{field}}}}} |\n"

        elif template_type == "status":
            # Avoid "Status Status" if name already contains "Status"
            title_suffix = "" if "status" in name.lower() else " Status"
            template = f"""# {title_name}{title_suffix}

## Current Status

**Status:** {{{{status}}}}

## Metrics

"""
            for field in output_fields:
                if field != "status":
                    template += f"- **{field.replace('_', ' ').title()}:** {{{{{field}}}}}\n"

            template += """
## Health Assessment

{{health_assessment}}
"""
        else:
            # Generic template
            template = f"""# {title_name}

{description}

## Output

"""
            for field in output_fields:
                template += f"### {field.replace('_', ' ').title()}\n\n{{{{{field}}}}}\n\n"

        # Add footer with placeholder reference
        template += f"""---

## Placeholders

This template uses the following placeholders (Mustache-style syntax):

{placeholders_section}

Fill in these placeholders with actual values from the skill execution.
"""
        return template

    def _apply_progressive_disclosure(
        self, skill_md: str, spec: Dict[str, Any], output_dir: Path
    ) -> tuple[str, Dict[str, Path]]:
        """
        Apply progressive disclosure to a SKILL.md that exceeds 500 lines.

        Splits detailed sections into references/ directory to keep the main
        SKILL.md concise and actionable.

        Args:
            skill_md: Original SKILL.md content
            spec: Skill specification
            output_dir: Directory where skill files are being created

        Returns:
            Tuple of (condensed_skill_md, dict of reference files created)
        """
        references = {}
        references_dir = output_dir / "references"

        # Sections that can be moved to references (in order of priority to move)
        movable_sections = [
            ("## Failure Handling", "failure-handling.md", "Failure Handling"),
            ("## Rollback Procedure", "rollback.md", "Rollback Procedure"),
            ("## Examples", "examples.md", "Detailed Examples"),
            ("## Changelog", "changelog.md", "Changelog"),
            ("## Related Skills", "related-skills.md", "Related Skills"),
        ]

        lines = skill_md.split("\n")
        condensed_lines = []
        current_section_header = None
        current_section_content = []
        sections_to_move = {}

        # Parse into sections
        for line in lines:
            if line.startswith("## "):
                # Save previous section if it exists
                if current_section_header and current_section_content:
                    sections_to_move[current_section_header] = "\n".join(current_section_content)
                current_section_header = line
                current_section_content = [line]
            elif current_section_header:
                current_section_content.append(line)
            else:
                condensed_lines.append(line)

        # Don't forget the last section
        if current_section_header and current_section_content:
            sections_to_move[current_section_header] = "\n".join(current_section_content)

        # Calculate current line count and determine what to move
        line_count = len(condensed_lines)
        moved_sections = []

        for section_header, filename, display_name in movable_sections:
            if section_header in sections_to_move:
                section_content = sections_to_move[section_header]
                section_lines = section_content.count("\n") + 1

                # Move this section if it would help us get under 500 lines
                # or if we're still over and this section is substantial (>20 lines)
                if line_count + section_lines > 500 or (line_count > 400 and section_lines > 20):
                    # Create references directory if needed
                    if not references_dir.exists():
                        references_dir.mkdir(exist_ok=True)

                    # Write section to reference file
                    ref_path = references_dir / filename
                    ref_content = f"# {display_name}\n\n{section_content}"
                    ref_path.write_text(ref_content)
                    references[f"references/{filename}"] = ref_path
                    moved_sections.append((section_header, filename, display_name))

                    logger.info(
                        f"Moved {section_header} ({section_lines} lines) to references/{filename}"
                    )
                else:
                    # Keep this section in main file
                    condensed_lines.append("")
                    condensed_lines.extend(section_content.split("\n"))
                    line_count += section_lines
            else:
                # Section not found, check if we should add it back from sections_to_move
                pass

        # Add remaining sections that weren't candidates for moving
        for section_header, content in sections_to_move.items():
            already_moved = any(
                section_header == h
                for h, _, _ in movable_sections
                if h in [m[0] for m in moved_sections]
            )
            already_in_condensed = section_header in "\n".join(condensed_lines)

            if not already_moved and not already_in_condensed:
                condensed_lines.append("")
                condensed_lines.extend(content.split("\n"))

        # Add references section to condensed SKILL.md
        if moved_sections:
            condensed_lines.append("")
            condensed_lines.append("## References")
            condensed_lines.append("")
            condensed_lines.append(
                "The following sections have been moved to separate files for clarity:"
            )
            condensed_lines.append("")
            for _, filename, display_name in moved_sections:
                condensed_lines.append(f"- [{display_name}](references/{filename})")

        final_skill_md = "\n".join(condensed_lines)

        # Log final stats
        final_lines = final_skill_md.count("\n") + 1
        logger.info(
            f"Progressive disclosure complete: {len(lines)} -> {final_lines} lines, "
            f"{len(moved_sections)} sections moved to references/"
        )

        return final_skill_md, references

    def _generate_script(self, spec: Dict[str, Any], script_info: Dict[str, Any]) -> str:
        """
        Generate a Python script for deterministic operations.

        Args:
            spec: Skill specification
            script_info: Script detection info with 'script_type' and 'operations'

        Returns:
            Python script content as string
        """
        script_name = spec["name"].replace("-", "_")

        prompt = f"""Generate a Python script for this skill that performs deterministic operations.

Skill: {spec["name"]}
Description: {spec["description"]}
Script Type: {script_info["script_type"]}
Operations: {script_info["operations"]}

Input Parameters:
{json.dumps(spec.get("inputs", {}), indent=2)}

Expected Output:
{json.dumps(spec.get("outputs", {}), indent=2)}

REQUIREMENTS:
1. The script MUST have an `execute(inputs: dict) -> dict` function as the entry point
2. Use type hints throughout
3. Include proper error handling with try/except
4. Only use Python standard library (no external dependencies)
5. Add docstrings for the execute function
6. Handle edge cases gracefully
7. Return a dict matching the expected output schema

Example structure:
```python
#!/usr/bin/env python3
\"\"\"Script for {spec["name"]} skill.\"\"\"

from typing import Any, Dict


def execute(inputs: Dict[str, Any]) -> Dict[str, Any]:
    \"\"\"
    Execute the {spec["name"]} operation.

    Args:
        inputs: Dictionary with input parameters

    Returns:
        Dictionary with operation results
    \"\"\"
    try:
        # Implementation here
        result = ...
        return {{"result": result, "success": True}}
    except Exception as e:
        return {{"error": str(e), "success": False}}


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) > 1:
        inputs = json.loads(sys.argv[1])
    else:
        inputs = {{}}

    result = execute(inputs)
    print(json.dumps(result, indent=2))
```

Return ONLY the Python code, no explanation."""

        messages = [
            {
                "role": "system",
                "content": "You are an expert Python developer creating reliable, deterministic scripts.",
            },
            {"role": "user", "content": prompt},
        ]

        response = self.llm.chat(messages, temperature=0.3)
        content = response["content"]

        # Strip thinking tags
        content = self.llm._strip_thinking_tags(content)

        # Extract Python code if wrapped in code blocks
        if "```python" in content:
            content = content.split("```python")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return content

    def _validate_script(self, script_content: str) -> List[str]:
        """
        Validate a generated Python script.

        Args:
            script_content: Python script content

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check syntax
        try:
            compile(script_content, "<string>", "exec")
        except SyntaxError as e:
            errors.append(f"Syntax error: {e}")
            return errors  # Can't do further validation with syntax errors

        # Check for execute function
        if "def execute(" not in script_content:
            errors.append("Missing required 'execute' function")

        # Check for type hints on execute
        if (
            "def execute(inputs: Dict" not in script_content
            and "def execute(inputs: dict" not in script_content
        ):
            errors.append(
                "Missing type hints on 'execute' function (should be 'inputs: Dict[str, Any]')"
            )

        # Check for return type hint
        if "-> Dict" not in script_content and "-> dict" not in script_content:
            errors.append("Missing return type hint on 'execute' function")

        return errors

    def _generate_example_md(self, example: Dict[str, Any], index: int) -> str:
        """
        Generate a markdown file for a single example.

        Args:
            example: Example dict with name, description, input, expected_output
            index: Example index (1-based)

        Returns:
            Markdown content for the example
        """
        name = example.get("name", f"Example {index}")
        description = example.get("description", "")
        input_data = example.get("input", {})
        expected_output = example.get("expected_output", {})

        content = f"""# {name}

{description}

## Input

```json
{json.dumps(input_data, indent=2)}
```

## Expected Output

```json
{json.dumps(expected_output, indent=2)}
```

## Notes

- This example demonstrates a typical use case for this skill
- Use this as a reference for expected input/output format
- The output structure should match exactly for test validation
"""
        return content

    def generate_skill_files(
        self, spec: Dict[str, Any], output_dir: Path, max_retries: int = 2
    ) -> Dict[str, Path]:
        """
        Generate skill files from spec with retry logic for LLM calls.

        Args:
            spec: Skill specification
            output_dir: Directory to create files in
            max_retries: Number of retries for each LLM call on failure

        Returns:
            Dict of {filename: path}

        Raises:
            RuntimeError: If file generation fails after all retries
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        files = {}

        # Detect if scripts are needed for deterministic operations
        script_info = self._detect_script_requirement(spec)

        # Detect allowed tools based on skill description
        tools_info = self._detect_allowed_tools(spec)
        if tools_info["allowed_tools"]:
            spec["_tools_info"] = {
                "has_allowed_tools": True,
                "allowed_tools": tools_info["allowed_tools"],
                "tool_categories": tools_info["tool_categories"],
            }

        # Generate scripts if needed (before SKILL.md so we can reference them)
        if script_info["requires_scripts"]:
            scripts_dir = output_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)

            script_name = spec["name"].replace("-", "_") + ".py"
            logger.info(f"Generating script: {script_name}")

            script_content = self._generate_with_retry(
                lambda: self._generate_script(spec, script_info),
                f"scripts/{script_name}",
                max_retries,
            )

            # Validate the generated script
            script_errors = self._validate_script(script_content)
            if script_errors:
                logger.warning(f"Script validation warnings: {script_errors}")

            script_path = scripts_dir / script_name
            script_path.write_text(script_content)
            script_path.chmod(0o755)  # Make executable
            files[f"scripts/{script_name}"] = script_path

            # Store script info in spec for SKILL.md generation
            spec["_script_info"] = {
                "has_script": True,
                "script_path": f"scripts/{script_name}",
                "script_type": script_info["script_type"],
            }

        # Generate examples/ directory if examples are provided
        examples = spec.get("examples", [])
        if examples:
            examples_dir = output_dir / "examples"
            examples_dir.mkdir(exist_ok=True)

            for i, example in enumerate(examples, 1):
                example_filename = f"example-{i}.md"
                example_content = self._generate_example_md(example, i)
                example_path = examples_dir / example_filename
                example_path.write_text(example_content)
                files[f"examples/{example_filename}"] = example_path
                logger.info(f"Generated example: {example_filename}")

            # Store example info for SKILL.md and test case generation
            spec["_examples_info"] = {
                "has_examples": True,
                "count": len(examples),
                "examples": examples,
            }

        # Detect if structured output needs a template
        template_info = self._detect_structured_output(spec)
        if template_info["has_template"]:
            logger.info(
                f"Generating template.md (type: {template_info['template_type']}, "
                f"fields: {template_info['output_fields']})"
            )
            template_content = self._generate_template_md(spec, template_info)
            template_path = output_dir / "template.md"
            template_path.write_text(template_content)
            files["template.md"] = template_path

            # Store template info in spec for SKILL.md generation
            spec["_template_info"] = {
                "has_template": True,
                "template_type": template_info["template_type"],
                "output_fields": template_info["output_fields"],
            }

        # Generate SKILL.md with retry
        skill_md = self._generate_with_retry(
            lambda: self._generate_skill_md(spec),
            "SKILL.md",
            max_retries,
        )

        # Progressive disclosure: split if SKILL.md is too long
        skill_md_lines = skill_md.count("\n") + 1
        if skill_md_lines > 500:
            logger.info(
                f"SKILL.md has {skill_md_lines} lines (>500), applying progressive disclosure"
            )
            skill_md, references = self._apply_progressive_disclosure(skill_md, spec, output_dir)
            files.update(references)

        skill_md_path = output_dir / "SKILL.md"
        skill_md_path.write_text(skill_md)
        files["SKILL.md"] = skill_md_path

        # Extract output schema from SKILL.md to ensure test case consistency
        output_schema = self._extract_output_schema(skill_md)
        if output_schema.get("fields"):
            logger.info(f"Extracted output fields from SKILL.md: {output_schema['fields']}")
        else:
            logger.warning(
                "Could not extract output schema from SKILL.md - test cases may have mismatched fields"
            )

        # Generate test_cases.yaml with retry, passing the schema for consistency
        test_cases = self._generate_with_retry(
            lambda: self._generate_test_cases(spec, output_schema),
            "test_cases.yaml",
            max_retries,
        )
        test_cases_path = output_dir / "test_cases.yaml"
        test_cases_path.write_text(test_cases)
        files["test_cases.yaml"] = test_cases_path

        # Generate metadata.json (no LLM call needed)
        metadata = {
            "name": spec["name"],
            "description": spec["description"],
            "version": "0.1.0",
            "inputs": spec.get("inputs", {}),
            "outputs": spec.get("outputs", {}),
            "created_by": "llm",
            "status": "draft",
        }

        # Add script info to metadata if scripts were generated
        if script_info["requires_scripts"]:
            metadata["has_scripts"] = True
            metadata["scripts"] = {
                "main": f"scripts/{spec['name'].replace('-', '_')}.py",
                "type": script_info["script_type"],
            }

        # Add allowed_tools info to metadata if detected
        if tools_info["allowed_tools"]:
            metadata["allowed_tools"] = tools_info["allowed_tools"]
            metadata["tool_categories"] = tools_info["tool_categories"]

        # Add template info to metadata if generated
        if template_info["has_template"]:
            metadata["has_template"] = True
            metadata["template"] = {
                "file": "template.md",
                "type": template_info["template_type"],
                "fields": template_info["output_fields"],
            }

        metadata_path = output_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2))
        files["metadata.json"] = metadata_path

        # Validate field consistency between SKILL.md and test_cases.yaml
        validation_warnings = self._validate_field_consistency(output_schema, test_cases)
        for warning in validation_warnings:
            logger.warning(warning)

        return files

    def _validate_field_consistency(
        self, output_schema: Dict[str, Any], test_cases_yaml: str
    ) -> List[str]:
        """
        Validate that test_cases.yaml assertions reference fields from SKILL.md schema.

        Args:
            output_schema: Extracted output schema from SKILL.md
            test_cases_yaml: Generated test_cases.yaml content

        Returns:
            List of warning messages for any inconsistencies
        """
        import yaml

        warnings = []
        schema_fields = set(output_schema.get("fields", []))

        if not schema_fields:
            return ["Could not validate fields - no schema extracted from SKILL.md"]

        try:
            test_data = yaml.safe_load(test_cases_yaml)
            if not test_data or "test_cases" not in test_data:
                return ["Could not validate fields - invalid test_cases.yaml structure"]

            test_fields = set()
            for test_case in test_data.get("test_cases", []):
                # Check expected_outputs fields
                for field in test_case.get("expected_outputs", {}).keys():
                    test_fields.add(field)

                # Check assertion fields
                for assertion in test_case.get("assertions", []):
                    if "field" in assertion:
                        test_fields.add(assertion["field"])

            # Find mismatched fields
            unknown_fields = test_fields - schema_fields
            if unknown_fields:
                warnings.append(
                    f"Test cases reference fields not in SKILL.md schema: {unknown_fields}. "
                    f"Expected fields: {schema_fields}"
                )

            unused_fields = schema_fields - test_fields
            if unused_fields:
                warnings.append(f"SKILL.md schema fields not tested: {unused_fields}")

        except yaml.YAMLError as e:
            warnings.append(f"Could not parse test_cases.yaml for validation: {e}")

        return warnings

    def _generate_with_retry(self, generate_func, file_name: str, max_retries: int) -> str:
        """
        Execute a generation function with retry logic.

        Args:
            generate_func: Function that generates content
            file_name: Name of file being generated (for logging)
            max_retries: Number of retries on failure

        Returns:
            Generated content string

        Raises:
            RuntimeError: If generation fails after all retries
        """
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return generate_func()
            except Exception as e:
                last_error = e
                is_timeout = "timeout" in str(e).lower() or "timed out" in str(e).lower()

                if attempt < max_retries:
                    logger.warning(
                        f"Failed to generate {file_name} (attempt {attempt + 1}/{max_retries + 1}): {e}"
                    )
                    if is_timeout:
                        logger.info("Retrying with extended timeout...")
                    continue
                else:
                    error_msg = (
                        f"Failed to generate {file_name} after {max_retries + 1} attempts: {e}"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from last_error

        # Should not reach here
        raise RuntimeError(f"Unexpected error generating {file_name}")

    def _extract_output_schema(self, skill_md: str) -> Dict[str, Any]:
        """
        Extract output schema from generated SKILL.md.

        Parses the Output Format section to find JSON field names.

        Args:
            skill_md: Generated SKILL.md content

        Returns:
            Dict with 'fields' list and 'example' if found
        """
        schema = {"fields": [], "example": None}

        # Try to find JSON schema in code blocks
        json_patterns = [
            r"```json\s*\n({[^`]+})\s*\n```",  # ```json { ... } ```
            r"```\s*\n({[^`]+})\s*\n```",  # ``` { ... } ```
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, skill_md, re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict):
                        schema["fields"] = list(parsed.keys())
                        schema["example"] = parsed
                        break
                except json.JSONDecodeError:
                    continue
            if schema["fields"]:
                break

        # Fallback: look for field names in schema description
        if not schema["fields"]:
            # Look for patterns like "field_name": "type"
            field_pattern = r'"(\w+)":\s*"?(string|integer|number|boolean|array|object)'
            matches = re.findall(field_pattern, skill_md)
            schema["fields"] = [m[0] for m in matches]

        logger.debug(f"Extracted output schema: {schema}")
        return schema

    def _generate_skill_md(self, spec: Dict[str, Any]) -> str:
        """Generate SKILL.md content from spec."""
        # Check if this skill has scripts
        script_section = ""
        if spec.get("_script_info", {}).get("has_script"):
            script_info = spec["_script_info"]
            script_section = f"""

IMPORTANT - This skill has a companion Python script:
- Script path: `{script_info["script_path"]}`
- Script type: {script_info["script_type"]}

Include a "## Script Execution" section in the SKILL.md that explains:
1. The script location: `{script_info["script_path"]}`
2. How to execute it: `python {script_info["script_path"]} '{{"input": "value"}}'`
3. That the script has an `execute(inputs: dict) -> dict` function
4. The script provides deterministic results and should be preferred for {script_info["script_type"]} operations
"""

        # Check if this skill has examples
        examples_section = ""
        examples_info = spec.get("_examples_info", {})
        if examples_info.get("has_examples"):
            examples_count = examples_info.get("count", 0)
            examples_section = f"""

This skill has {examples_count} documented example(s) in the examples/ directory.
Include a "## Examples" section that references these files:
- Link to examples/example-1.md, examples/example-2.md, etc.
- Briefly describe what each example demonstrates
"""

        # Check if this skill has allowed-tools detected
        tools_section = ""
        tools_info = spec.get("_tools_info", {})
        if tools_info.get("has_allowed_tools"):
            tools_list = ", ".join(tools_info["allowed_tools"][:5])  # Limit to first 5 for brevity
            if len(tools_info["allowed_tools"]) > 5:
                tools_list += f" (and {len(tools_info['allowed_tools']) - 5} more)"
            tools_section = f"""

IMPORTANT - This skill should have YAML frontmatter with allowed-tools restriction:
```yaml
---
name: {spec.get("name", "skill-name")}
description: {spec.get("description", "...")[:100]}
allowed-tools: "{tools_list}"
---
```

The skill is restricted to only these tools: {tools_info["allowed_tools"]}
Tool categories: {tools_info["tool_categories"]}
"""

        # Check if this skill has a template for structured output
        template_section = ""
        template_info = spec.get("_template_info", {})
        if template_info.get("has_template"):
            fields_list = ", ".join(template_info.get("output_fields", []))
            template_section = f"""

IMPORTANT - This skill has a structured output template:
- Template file: `template.md`
- Template type: {template_info.get("template_type", "generic")}
- Output fields: {fields_list}

Include a "## Output Template" section in the SKILL.md that explains:
1. Reference the template file: `template.md`
2. List the placeholders that need to be filled: {template_info.get("output_fields", [])}
3. Explain that the output should follow the template structure
4. Note that placeholders use Mustache-style syntax: {{{{field_name}}}}
"""

        # Build rich frontmatter
        tools_info = spec.get("_tools_info", {})
        allowed_tools_yaml = ""
        dependencies_yaml = ""
        if tools_info.get("has_allowed_tools"):
            tools_list = tools_info.get("allowed_tools", [])
            allowed_tools_yaml = f'allowed-tools: "{", ".join(tools_list[:10])}"'
            # Extract MCP servers from tool names
            mcp_servers = set()
            for tool in tools_list:
                if tool.startswith("mcp__"):
                    parts = tool.split("__")
                    if len(parts) >= 2:
                        mcp_servers.add(parts[1])
            if mcp_servers:
                deps_list = "\n    ".join(f"- {s}" for s in sorted(mcp_servers))
                dependencies_yaml = f"""dependencies:
  mcp-servers:
    {deps_list}"""

        # Determine domain and category
        domain = "general"
        category = "utility"
        desc_lower = spec.get("description", "").lower()
        if any(kw in desc_lower for kw in ["kubernetes", "k8s", "pod", "deployment", "namespace"]):
            domain = "k8s"
        elif any(kw in desc_lower for kw in ["news", "article", "digest", "rss"]):
            domain = "news"
        elif any(kw in desc_lower for kw in ["temporal", "workflow"]):
            domain = "temporal"

        if any(kw in desc_lower for kw in ["fix", "repair", "remediat", "heal"]):
            category = "remediation"
        elif any(kw in desc_lower for kw in ["diagnos", "investigat", "debug", "troubleshoot"]):
            category = "diagnostic"
        elif any(kw in desc_lower for kw in ["collect", "gather", "fetch", "get"]):
            category = "collection"
        elif any(kw in desc_lower for kw in ["analyz", "report", "summariz", "statistic"]):
            category = "analytics"
        elif any(kw in desc_lower for kw in ["calculate", "compute", "convert"]):
            category = "calculation"

        prompt = f"""Generate a complete SKILL.md file following this exact structure:

---START SKILL SPECIFICATION---
{json.dumps(spec, indent=2)}
---END SKILL SPECIFICATION---
{script_section}
{examples_section}
{tools_section}
{template_section}

Generate the SKILL.md with these sections IN THIS EXACT ORDER:

1. **YAML Frontmatter** (required):
```yaml
---
name: {spec.get("name", "skill-name")}
version: "1.0.0"
description: >
  {spec.get("description", "Description here")}

metadata:
  domain: {domain}
  category: {category}
  requires-approval: false

{dependencies_yaml if dependencies_yaml else "# No specific dependencies"}
{allowed_tools_yaml if allowed_tools_yaml else ""}
---
```

2. **# Skill Display Name** - Human-readable title

3. **## When to Use** - Bullet list of specific situations when this skill applies

4. **## Prerequisites** - Checklist of conditions that must be true

5. **## Input Schema** - JSON code block showing expected inputs with descriptions

6. **## Actions** - Numbered subsections (### 1. First Action, etc.) with step-by-step execution

7. **## Output Schema** - JSON code block showing exact output format:
   - Use flat JSON structure (no nested objects unless explicitly needed)
   - Specify EXACT JSON field names: {list(spec.get("outputs", {}).keys())}
   - Add note: "CRITICAL: Return ONLY this exact JSON structure, no additional wrapper fields"

8. **## Success Criteria** - Checklist of what defines success

9. **## Failure Handling** - Table of error types and handling strategies

10. **## Examples** - At least one complete input/output example

IMPORTANT RULES:
- Keep the document under 300 lines if possible
- Use clear, actionable language
- Be precise about input/output field names
- Make it executable by an AI agent

Return ONLY the SKILL.md content, starting with the --- frontmatter."""

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

    def _generate_test_cases(
        self, spec: Dict[str, Any], output_schema: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate test_cases.yaml from spec.

        Args:
            spec: Skill specification
            output_schema: Optional output schema extracted from SKILL.md
                          to ensure field name consistency

        Returns:
            Generated test_cases.yaml content
        """
        # Build schema hint for the prompt
        schema_hint = ""
        if output_schema and output_schema.get("fields"):
            fields = output_schema["fields"]
            schema_hint = f"""
CRITICAL: The SKILL.md defines these exact output fields: {fields}
You MUST use these exact field names in expected_outputs and assertions.
Example output structure from SKILL.md: {json.dumps(output_schema.get("example", {}), indent=2)}
"""

        # Build examples hint if examples are provided
        examples_hint = ""
        examples_info = spec.get("_examples_info", {})
        if examples_info.get("has_examples"):
            examples = examples_info.get("examples", [])
            examples_hint = f"""
SEED TEST CASES FROM EXAMPLES:
The user provided {len(examples)} concrete example(s). Use these as the FIRST test cases:
"""
            for i, ex in enumerate(examples, 1):
                examples_hint += f"""
Example {i}: {ex.get("name", f"Example {i}")}
- Input: {json.dumps(ex.get("input", {}))}
- Expected Output: {json.dumps(ex.get("expected_output", {}))}
"""
            examples_hint += """
Create test cases from these examples FIRST, then add additional edge cases and error cases.
"""

        prompt = f"""Generate a test_cases.yaml file for this skill:

{json.dumps(spec, indent=2)}
{schema_hint}
{examples_hint}
Create 5-8 comprehensive test cases covering:
1. Happy path (normal execution) - USE THE PROVIDED EXAMPLES FIRST
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
