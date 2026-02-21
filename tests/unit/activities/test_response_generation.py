"""Unit tests for Nexus response generation activity.

This module tests the generate_response activity which synthesizes a final
response from execution results using the LLM.

Tests include:
- Response generation from successful step results
- Response generation from failed step results
- Response text extraction
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from kubani.nexus.orchestrator.activities import generate_response


class TestGenerateResponse:
    """Tests for generate_response activity."""

    @pytest.mark.asyncio
    async def test_generate_response_with_successful_steps(self):
        """
        Test that generate_response synthesizes response from successful steps.
        
        When all plan steps execute successfully, the system should synthesize
        a coherent response that summarizes the results.
        
        Validates: Requirements 4.5
        """
        # Prepare input data with successful step results
        input_data = {
            "user_message": "Research quantum computing and create a report",
            "goal": "Research quantum computing developments and create summary report",
            "step_results": [
                {
                    "success": True,
                    "output": "Found 15 recent articles on quantum computing breakthroughs",
                    "error": None
                },
                {
                    "success": True,
                    "output": "Analyzed key findings: quantum supremacy, error correction advances",
                    "error": None
                },
                {
                    "success": True,
                    "output": "Generated comprehensive report with 3 sections",
                    "error": None
                }
            ],
            "conversation_history": []
        }
        
        # Mock LLM response
        expected_response = """I've completed your research on quantum computing. Here's what I found:

**Key Findings:**
- Found 15 recent articles covering the latest breakthroughs
- Identified major advances in quantum supremacy and error correction
- Created a comprehensive 3-section report

The research is complete and the report is ready for your review."""
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=expected_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await generate_response(input_data)
            
            # Verify the result
            assert result is not None
            assert isinstance(result, dict)
            
            # Verify response_text is present and extracted correctly
            assert "response_text" in result
            assert result["response_text"] is not None
            assert isinstance(result["response_text"], str)
            assert len(result["response_text"]) > 0
            
            # Verify the response text matches what LLM returned
            assert result["response_text"] == expected_response
            
            # Verify LLM was called with correct parameters
            mock_llm.chat.assert_called_once()
            call_args = mock_llm.chat.call_args
            messages = call_args[1]["messages"]
            
            # Verify system prompt and user prompt were passed
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"
            
            # Verify user prompt contains the original message and results
            user_prompt = messages[1]["content"]
            assert "Research quantum computing and create a report" in user_prompt
            assert "Research quantum computing developments" in user_prompt
            assert "Step 1" in user_prompt
            assert "succeeded" in user_prompt
            
            # Verify heartbeat was called
            mock_heartbeat.assert_called_once_with("Generating response")

    @pytest.mark.asyncio
    async def test_generate_response_with_failed_steps(self):
        """
        Test that generate_response handles failed step results.
        
        When some steps fail, the system should synthesize a response that
        explains what went wrong and suggests next steps.
        
        Validates: Requirements 4.5
        """
        # Prepare input data with mixed success/failure
        input_data = {
            "user_message": "Deploy the application to production",
            "goal": "Deploy application to production environment",
            "step_results": [
                {
                    "success": True,
                    "output": "Built Docker image successfully",
                    "error": None
                },
                {
                    "success": False,
                    "output": "",
                    "error": "Failed to push image: authentication failed"
                },
                {
                    "success": False,
                    "output": "",
                    "error": "Deployment skipped due to previous failure"
                }
            ],
            "conversation_history": []
        }
        
        # Mock LLM response for failure scenario
        expected_response = """I encountered an issue while deploying your application:

**What Succeeded:**
- ✓ Built Docker image successfully

**What Failed:**
- ✗ Failed to push image due to authentication failure
- ✗ Deployment was skipped as a result

**Next Steps:**
Please verify your Docker registry credentials and try again. You may need to run `docker login` first."""
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=expected_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await generate_response(input_data)
            
            # Verify response_text is present
            assert "response_text" in result
            assert result["response_text"] == expected_response
            
            # Verify LLM received error information
            call_args = mock_llm.chat.call_args
            messages = call_args[1]["messages"]
            user_prompt = messages[1]["content"]
            
            # Verify error messages are included in prompt
            assert "authentication failed" in user_prompt
            assert "failed" in user_prompt.lower()
            assert "Error:" in user_prompt

    @pytest.mark.asyncio
    async def test_generate_response_with_empty_results(self):
        """
        Test that generate_response handles empty step results.
        
        Validates: Requirements 4.5
        """
        # Prepare input data with no step results
        input_data = {
            "user_message": "Hello",
            "goal": "",
            "step_results": [],
            "conversation_history": []
        }
        
        # Mock LLM response
        expected_response = "Hello! How can I help you today?"
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=expected_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await generate_response(input_data)
            
            # Verify response_text is present
            assert "response_text" in result
            assert result["response_text"] == expected_response

    @pytest.mark.asyncio
    async def test_generate_response_truncates_long_output(self):
        """
        Test that generate_response truncates very long step outputs.
        
        To avoid overwhelming the LLM context, long outputs should be truncated
        to 500 characters.
        
        Validates: Requirements 4.5
        """
        # Prepare input data with very long output
        long_output = "x" * 1000  # 1000 character output
        input_data = {
            "user_message": "Analyze the logs",
            "goal": "Analyze application logs",
            "step_results": [
                {
                    "success": True,
                    "output": long_output,
                    "error": None
                }
            ],
            "conversation_history": []
        }
        
        # Mock LLM response
        expected_response = "I've analyzed the logs and found several interesting patterns."
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=expected_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await generate_response(input_data)
            
            # Verify response was generated
            assert "response_text" in result
            assert result["response_text"] == expected_response
            
            # Verify the prompt sent to LLM had truncated output
            call_args = mock_llm.chat.call_args
            messages = call_args[1]["messages"]
            user_prompt = messages[1]["content"]
            
            # The full 1000 character output should not be in the prompt
            # Only first 500 characters should be included
            assert long_output not in user_prompt
            assert long_output[:500] in user_prompt

    @pytest.mark.asyncio
    async def test_generate_response_with_markdown_formatting(self):
        """
        Test that generate_response preserves markdown formatting.
        
        The LLM may return responses with markdown formatting, which should
        be preserved in the response_text.
        
        Validates: Requirements 4.5
        """
        # Prepare input data
        input_data = {
            "user_message": "Create a summary",
            "goal": "Create summary of findings",
            "step_results": [
                {
                    "success": True,
                    "output": "Analysis complete",
                    "error": None
                }
            ],
            "conversation_history": []
        }
        
        # Mock LLM response with markdown
        expected_response = """# Summary

Here are the key findings:

1. **First finding**: Important detail
2. **Second finding**: Another detail

```python
# Example code
print("Hello")
```

*Analysis complete*"""
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=expected_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await generate_response(input_data)
            
            # Verify markdown is preserved
            assert "response_text" in result
            assert result["response_text"] == expected_response
            assert "# Summary" in result["response_text"]
            assert "**First finding**" in result["response_text"]
            assert "```python" in result["response_text"]
            assert "*Analysis complete*" in result["response_text"]

    @pytest.mark.asyncio
    async def test_generate_response_system_prompt_content(self):
        """
        Test that generate_response uses correct system prompt.
        
        The system prompt should instruct the LLM to synthesize results
        into a clear, helpful response with markdown formatting.
        
        Validates: Requirements 4.5
        """
        # Prepare input data
        input_data = {
            "user_message": "Test message",
            "goal": "Test goal",
            "step_results": [
                {
                    "success": True,
                    "output": "Test output",
                    "error": None
                }
            ],
            "conversation_history": []
        }
        
        # Mock LLM response
        expected_response = "Test response"
        
        # Mock the LLM client and activity context
        with patch('kubani.framework.llm.get_llm') as mock_get_llm, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(return_value=expected_response)
            mock_get_llm.return_value = mock_llm
            
            # Execute the activity
            result = await generate_response(input_data)
            
            # Verify system prompt content
            call_args = mock_llm.chat.call_args
            messages = call_args[1]["messages"]
            system_prompt = messages[0]["content"]
            
            # Verify key instructions are in system prompt
            assert "Kubani Nexus" in system_prompt
            assert "Synthesize" in system_prompt or "synthesize" in system_prompt
            assert "clear" in system_prompt
            assert "helpful" in system_prompt
            assert "Markdown" in system_prompt or "markdown" in system_prompt
