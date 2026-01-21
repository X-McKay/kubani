"""LLM-powered skill improvement system."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from kubani_dev.llm_client import LLMClient

logger = logging.getLogger(__name__)


class SkillImprover:
    """Improve skills based on evaluation results using LLM."""
    
    def __init__(self, llm_client: LLMClient):
        """
        Initialize skill improver.
        
        Args:
            llm_client: LLM client for generation
        """
        self.llm = llm_client
    
    def analyze_evaluation(
        self,
        evaluation_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze evaluation results and identify improvement opportunities.
        
        Args:
            evaluation_results: Results from skill evaluation
        
        Returns:
            Analysis with improvement suggestions
        """
        metrics = evaluation_results["metrics"]
        test_results = evaluation_results["test_results"]
        
        # Identify failed tests
        failed_tests = [t for t in test_results if not t["passed"]]
        
        # Prepare analysis prompt
        prompt = f"""Analyze these skill evaluation results and suggest improvements:

**Metrics:**
- Accuracy: {metrics["accuracy"]:.1f}%
- Tests Passed: {metrics["tests_passed"]}/{metrics["tests_total"]}
- Avg Latency: {metrics["avg_latency_ms"]:.0f} ms
- Avg Tokens: {metrics["avg_tokens_per_test"]["total"]:.0f}

**Failed Tests:**
{json.dumps(failed_tests, indent=2)}

Provide:
1. Root cause analysis of failures
2. Specific improvement suggestions
3. Priority (high/medium/low) for each suggestion
4. Expected impact on metrics

Format as JSON:
{{
  "analysis": "overall analysis",
  "improvements": [
    {{
      "issue": "what's wrong",
      "suggestion": "how to fix",
      "priority": "high|medium|low",
      "expected_impact": "what will improve"
    }}
  ]
}}"""

        messages = [
            {"role": "system", "content": "You are an expert at analyzing AI agent performance and suggesting improvements."},
            {"role": "user", "content": prompt}
        ]
        
        response = self.llm.chat(messages, temperature=0.5)
        content = response["content"]
        
        # Extract JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        try:
            analysis = json.loads(content)
        except json.JSONDecodeError:
            analysis = {
                "analysis": content,
                "improvements": []
            }
        
        return analysis
    
    def improve_skill(
        self,
        skill_dir: Path,
        evaluation_results: Dict[str, Any],
        improvement_goals: List[str]
    ) -> Dict[str, Any]:
        """
        Improve a skill based on evaluation and goals.
        
        Args:
            skill_dir: Path to skill directory
            evaluation_results: Results from evaluation
            improvement_goals: List of goals (e.g., ["accuracy", "latency", "tokens"])
        
        Returns:
            Dict with improved skill content
        """
        # Load current skill
        skill_md_path = skill_dir / "SKILL.md"
        current_skill = skill_md_path.read_text()
        
        # Get analysis
        analysis = self.analyze_evaluation(evaluation_results)
        
        # Generate improved skill
        prompt = f"""Improve this skill based on the evaluation results and analysis.

**Current Skill:**
{current_skill}

**Evaluation Analysis:**
{json.dumps(analysis, indent=2)}

**Improvement Goals:**
{', '.join(improvement_goals)}

**Failed Test Cases:**
{json.dumps([t for t in evaluation_results["test_results"] if not t["passed"]], indent=2)}

Generate an improved version of the SKILL.md that:
1. Fixes the issues identified in failed tests
2. Optimizes for the specified goals
3. Maintains the same input/output interface
4. Adds clearer instructions where needed

Return ONLY the improved SKILL.md content, no explanation."""

        messages = [
            {"role": "system", "content": "You are an expert at improving AI agent skills."},
            {"role": "user", "content": prompt}
        ]
        
        response = self.llm.chat(messages, temperature=0.5)
        improved_skill = response["content"]
        
        # Extract markdown if wrapped
        if "```markdown" in improved_skill:
            improved_skill = improved_skill.split("```markdown")[1].split("```")[0].strip()
        elif "```" in improved_skill:
            improved_skill = improved_skill.split("```")[1].split("```")[0].strip()
        
        return {
            "improved_skill": improved_skill,
            "analysis": analysis,
            "tokens_used": response["tokens"]
        }
    
    def save_improved_skill(
        self,
        skill_dir: Path,
        improved_content: str,
        create_backup: bool = True
    ):
        """
        Save improved skill, optionally creating a backup.
        
        Args:
            skill_dir: Path to skill directory
            improved_content: Improved SKILL.md content
            create_backup: Whether to backup the current version
        """
        skill_md_path = skill_dir / "SKILL.md"
        
        if create_backup and skill_md_path.exists():
            backup_path = skill_dir / "SKILL.md.backup"
            backup_path.write_text(skill_md_path.read_text())
            logger.info(f"Created backup at {backup_path}")
        
        skill_md_path.write_text(improved_content)
        logger.info(f"Saved improved skill to {skill_md_path}")
