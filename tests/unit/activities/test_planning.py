"""Unit tests for Nexus planning activity.

This module tests the plan_response activity which is the 'brain' of the agent.
It analyzes user input and decides whether to respond directly or create a
multi-step execution plan.

Tests include:
- Direct response for simple greetings
- Structured plan for task requests
- Graceful fallback for invalid LLM output
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from kubani.nexus.orchestrator.activities import plan_response


class TestPlanResponseGreeting:
    """Tests for plan_response with simple conversational messages."""

    @pytest.mark.asyncio
    async def test_plan_response_with_greeting(self):
        """
        Test that plan_response returns direct response for simple greeting.
        
        When a user sends a simple greeting (e.g., "Hello"), the system should
        respond directly without creating a multi-step plan.
        
        Validates: Requirements 4.1
        """
        # Prepare input data
        input_data = {
            "user_message": "Hello! How are you?",
            "conversation_history": [],
            "available_skills": ["search-web", "analyze-code"],
            "memories": []
        }
        
        # Mock LLM response for greeting (direct response, no plan needed)
        llm_response = json.dumps({
            "needs_plan": False,
            "direct_response": "Hello! I'm doing well, thank you for asking. How can I help you today?",
            "goal": "",
            "steps": []
        })
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=llm_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await plan_response(input_data)
            
            # Verify the result
            assert result is not None
            assert isinstance(result, dict)
            
            # Verify needs_plan is False
            assert result["needs_plan"] is False
            
            # Verify direct_response is present
            assert "direct_response" in result
            assert result["direct_response"] is not None
            assert len(result["direct_response"]) > 0
            
            # Verify no plan was created
            assert result["goal"] == ""
            assert result["steps"] == []
            
            # Verify LLM was called with correct parameters
            mock_llm.chat.assert_called_once()
            call_args = mock_llm.chat.call_args
            messages = call_args[1]["messages"]
            
            # Verify system prompt and user message were passed
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"
            assert messages[1]["content"] == "Hello! How are you?"
            
            # Verify heartbeat was called
            assert mock_heartbeat.call_count >= 1

    @pytest.mark.asyncio
    async def test_plan_response_with_question_about_self(self):
        """
        Test that plan_response returns direct response for questions about itself.
        
        Questions like "What can you do?" should get direct responses without plans.
        
        Validates: Requirements 4.1
        """
        # Prepare input data
        input_data = {
            "user_message": "What can you do?",
            "conversation_history": [],
            "available_skills": ["search-web", "analyze-code", "generate-report"],
            "memories": []
        }
        
        # Mock LLM response
        llm_response = json.dumps({
            "needs_plan": False,
            "direct_response": "I can help you with various tasks including web searches, code analysis, and report generation. What would you like me to help you with?",
            "goal": "",
            "steps": []
        })
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=llm_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await plan_response(input_data)
            
            # Verify needs_plan is False
            assert result["needs_plan"] is False
            assert result["direct_response"] is not None
            assert len(result["direct_response"]) > 0


class TestPlanResponseTask:
    """Tests for plan_response with task requests requiring plans."""

    @pytest.mark.asyncio
    async def test_plan_response_with_task(self):
        """
        Test that plan_response creates structured plan for task request.
        
        When a user requests a task (e.g., "Research X and create a report"),
        the system should create a multi-step execution plan.
        
        Validates: Requirements 4.2
        """
        # Prepare input data
        input_data = {
            "user_message": "Research the latest developments in quantum computing and create a summary report",
            "conversation_history": [],
            "available_skills": ["search-web", "analyze-content", "generate-report"],
            "memories": []
        }
        
        # Mock LLM response with structured plan
        llm_response = json.dumps({
            "needs_plan": True,
            "direct_response": None,
            "goal": "Research quantum computing developments and create summary report",
            "steps": [
                {
                    "id": 1,
                    "description": "Search for recent quantum computing news and papers",
                    "skill_name": "search-web"
                },
                {
                    "id": 2,
                    "description": "Analyze and extract key findings from search results",
                    "skill_name": "analyze-content"
                },
                {
                    "id": 3,
                    "description": "Generate formatted summary report",
                    "skill_name": "generate-report"
                }
            ]
        })
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=llm_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await plan_response(input_data)
            
            # Verify the result
            assert result is not None
            assert isinstance(result, dict)
            
            # Verify needs_plan is True
            assert result["needs_plan"] is True
            
            # Verify goal is present
            assert "goal" in result
            assert result["goal"] is not None
            assert len(result["goal"]) > 0
            
            # Verify steps are present
            assert "steps" in result
            assert isinstance(result["steps"], list)
            assert len(result["steps"]) > 0
            
            # Verify step structure
            for step in result["steps"]:
                assert "id" in step
                assert "description" in step
                assert "skill_name" in step
                assert isinstance(step["id"], int)
                assert isinstance(step["description"], str)
            
            # Verify direct_response is None or empty
            assert result.get("direct_response") is None or result.get("direct_response") == ""
            
            # Verify LLM was called
            mock_llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_plan_response_with_conversation_history(self):
        """
        Test that plan_response includes conversation history in context.
        
        The planning activity should consider recent conversation history
        when creating plans.
        
        Validates: Requirements 4.2
        """
        # Prepare input data with conversation history
        input_data = {
            "user_message": "Now analyze the code quality",
            "conversation_history": [
                {"role": "user", "content": "Clone the repository at github.com/example/repo"},
                {"role": "assistant", "content": "I've cloned the repository successfully."}
            ],
            "available_skills": ["analyze-code", "generate-report"],
            "memories": []
        }
        
        # Mock LLM response
        llm_response = json.dumps({
            "needs_plan": True,
            "direct_response": None,
            "goal": "Analyze code quality of the cloned repository",
            "steps": [
                {
                    "id": 1,
                    "description": "Run code quality analysis on repository",
                    "skill_name": "analyze-code"
                },
                {
                    "id": 2,
                    "description": "Generate quality report",
                    "skill_name": "generate-report"
                }
            ]
        })
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=llm_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await plan_response(input_data)
            
            # Verify plan was created
            assert result["needs_plan"] is True
            assert len(result["steps"]) > 0
            
            # Verify LLM received the conversation history in system prompt
            call_args = mock_llm.chat.call_args
            messages = call_args[1]["messages"]
            system_prompt = messages[0]["content"]
            
            # System prompt should include conversation history
            assert "RECENT CONVERSATION" in system_prompt
            assert "Clone the repository" in system_prompt


class TestPlanResponseErrorHandling:
    """Tests for plan_response error handling and fallback behavior."""

    @pytest.mark.asyncio
    async def test_plan_response_with_invalid_llm_output(self):
        """
        Test that plan_response gracefully handles invalid LLM output.
        
        When the LLM returns malformed JSON or unexpected format, the system
        should fall back to treating the response as a direct response.
        
        Validates: Requirements 4.3
        """
        # Prepare input data
        input_data = {
            "user_message": "Hello",
            "conversation_history": [],
            "available_skills": [],
            "memories": []
        }
        
        # Mock LLM response with invalid JSON
        invalid_llm_response = "This is not valid JSON at all! Just plain text."
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=invalid_llm_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await plan_response(input_data)
            
            # Verify graceful fallback
            assert result is not None
            assert isinstance(result, dict)
            
            # Should fall back to direct response mode
            assert result["needs_plan"] is False
            
            # Direct response should contain the raw LLM output
            assert result["direct_response"] == invalid_llm_response
            
            # Plan fields should be empty
            assert result["goal"] == ""
            assert result["steps"] == []

    @pytest.mark.asyncio
    async def test_plan_response_with_malformed_json(self):
        """
        Test that plan_response handles malformed JSON gracefully.
        
        Validates: Requirements 4.3
        """
        # Prepare input data
        input_data = {
            "user_message": "Create a report",
            "conversation_history": [],
            "available_skills": ["generate-report"],
            "memories": []
        }
        
        # Mock LLM response with malformed JSON (missing closing brace)
        malformed_json = '{"needs_plan": true, "goal": "Create report", "steps": ['
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=malformed_json)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await plan_response(input_data)
            
            # Verify graceful fallback
            assert result["needs_plan"] is False
            assert result["direct_response"] == malformed_json
            assert result["goal"] == ""
            assert result["steps"] == []

    @pytest.mark.asyncio
    async def test_plan_response_with_json_in_markdown_code_block(self):
        """
        Test that plan_response can extract JSON from markdown code blocks.
        
        Some LLMs wrap JSON in ```json ... ``` blocks. The activity should
        handle this gracefully.
        
        Validates: Requirements 4.3
        """
        # Prepare input data
        input_data = {
            "user_message": "Hello",
            "conversation_history": [],
            "available_skills": [],
            "memories": []
        }
        
        # Mock LLM response with JSON in markdown code block
        llm_response = """```json
{
    "needs_plan": false,
    "direct_response": "Hello! How can I help you?",
    "goal": "",
    "steps": []
}
```"""
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=llm_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await plan_response(input_data)
            
            # Verify JSON was extracted and parsed correctly
            assert result["needs_plan"] is False
            assert result["direct_response"] == "Hello! How can I help you?"
            assert result["goal"] == ""
            assert result["steps"] == []

    @pytest.mark.asyncio
    async def test_plan_response_with_missing_fields(self):
        """
        Test that plan_response handles JSON with missing fields.
        
        If the LLM returns valid JSON but missing expected fields,
        the activity should use defaults.
        
        Validates: Requirements 4.3
        """
        # Prepare input data
        input_data = {
            "user_message": "Hello",
            "conversation_history": [],
            "available_skills": [],
            "memories": []
        }
        
        # Mock LLM response with missing fields
        llm_response = json.dumps({
            "needs_plan": False
            # Missing: direct_response, goal, steps
        })
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=llm_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await plan_response(input_data)
            
            # Verify defaults are used for missing fields
            assert result["needs_plan"] is False
            assert result["direct_response"] is None
            assert result["goal"] == ""
            assert result["steps"] == []
