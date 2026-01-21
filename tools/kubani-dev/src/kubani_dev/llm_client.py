"""LLM client for skill development workflow."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for interacting with LLMs (Ollama or OpenAI-compatible endpoints)."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        timeout: int = 120
    ):
        """
        Initialize LLM client.
        
        Args:
            base_url: Base URL for the LLM API (Ollama or OpenAI-compatible)
            model: Model name to use
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.is_ollama = "11434" in base_url  # Simple heuristic
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Send a chat completion request.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
        
        Returns:
            Response dict with 'content', 'tokens', 'latency_ms'
        """
        start_time = time.time()
        
        if self.is_ollama:
            return self._chat_ollama(messages, temperature, stream)
        else:
            return self._chat_openai(messages, temperature, max_tokens, stream)
    
    def _chat_ollama(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        stream: bool
    ) -> Dict[str, Any]:
        """Chat using Ollama API."""
        url = f"{self.base_url}/api/chat"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature
            }
        }
        
        start_time = time.time()
        
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            latency_ms = (time.time() - start_time) * 1000
            
            return {
                "content": result.get("message", {}).get("content", ""),
                "tokens": {
                    "prompt": result.get("prompt_eval_count", 0),
                    "completion": result.get("eval_count", 0),
                    "total": result.get("prompt_eval_count", 0) + result.get("eval_count", 0)
                },
                "latency_ms": latency_ms,
                "model": self.model
            }
            
        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            raise
    
    def _chat_openai(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool
    ) -> Dict[str, Any]:
        """Chat using OpenAI-compatible API."""
        url = f"{self.base_url}/v1/chat/completions"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        start_time = time.time()
        
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            latency_ms = (time.time() - start_time) * 1000
            
            choice = result["choices"][0]
            usage = result.get("usage", {})
            
            return {
                "content": choice["message"]["content"],
                "tokens": {
                    "prompt": usage.get("prompt_tokens", 0),
                    "completion": usage.get("completion_tokens", 0),
                    "total": usage.get("total_tokens", 0)
                },
                "latency_ms": latency_ms,
                "model": self.model
            }
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise
    
    def generate_skill(
        self,
        description: str,
        context: Optional[str] = None
    ) -> str:
        """
        Generate a skill SOP from a description.
        
        Args:
            description: Natural language description of the skill
            context: Additional context about the skill
        
        Returns:
            Generated SKILL.md content
        """
        system_prompt = """You are an expert at creating AI agent skills. Generate a complete SKILL.md file in markdown format.

The skill should include:
1. A clear title and description
2. Input parameters with types and descriptions
3. Output format specification
4. Step-by-step instructions for execution
5. Error handling guidelines
6. Example usage

Format the skill as a professional markdown document."""

        user_prompt = f"""Create a skill with the following description:

{description}"""

        if context:
            user_prompt += f"\n\nAdditional context:\n{context}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.chat(messages, temperature=0.7)
        return response["content"]
    
    def execute_skill(
        self,
        skill_sop: str,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a skill by having the LLM follow the SOP.
        
        Args:
            skill_sop: The skill's standard operating procedure (SKILL.md content)
            inputs: Input parameters for the skill
        
        Returns:
            Dict with 'output', 'tokens', 'latency_ms'
        """
        system_prompt = f"""You are an AI agent executing a skill. Follow the instructions in the skill SOP exactly.

SKILL SOP:
{skill_sop}

CRITICAL INSTRUCTIONS:
1. Read the "Output Format" section carefully
2. Return ONLY a JSON object with the EXACT field names specified
3. Do NOT add wrapper fields like "output", "result", or "response"
4. Do NOT add explanatory text before or after the JSON
5. The JSON must be parseable and match the schema exactly

Example: If the SOP says return {{"sum": number}}, return {{"sum": 8}}, NOT {{"output": {{"sum": 8}}}}"""

        user_prompt = f"""Execute the skill with these inputs:

{json.dumps(inputs, indent=2)}

Follow the SOP instructions and return the output as JSON."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.chat(messages, temperature=0.3)
        
        # Try to parse JSON from response
        content = response["content"]
        try:
            # Extract JSON if it's wrapped in markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            output = json.loads(content)
        except json.JSONDecodeError:
            # If not valid JSON, return as-is
            output = {"result": content}
        
        return {
            "output": output,
            "tokens": response["tokens"],
            "latency_ms": response["latency_ms"]
        }
