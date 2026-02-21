"""Unit tests for sandbox environment sanitization.

Tests that the sandbox executor properly strips sensitive environment
variables before executing skills.

Requirements: 9.3
"""

import os

import pytest


class TestSandboxEnvironmentSanitization:
    """Test sandbox environment variable sanitization."""

    def test_build_safe_environment_strips_blocked_vars(self):
        """
        Test that _build_safe_environment removes all BLOCKED_ENV_VARS.
        
        Requirements: 9.3
        """
        from kubani.nexus.sandbox.executor import _build_safe_environment

        workspace = "/tmp/test-workspace"

        # Set up environment with blocked variables
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("OPENAI_API_KEY", "sk-test-key")
            mp.setenv("DISCORD_BOT_TOKEN", "discord-token")
            mp.setenv("GITHUB_TOKEN", "github-token")
            mp.setenv("AWS_ACCESS_KEY_ID", "aws-key")
            mp.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
            mp.setenv("DATABASE_URL", "postgresql://localhost/db")
            mp.setenv("NEXUS_DATABASE_URL", "postgresql://localhost/nexus")
            mp.setenv("REDIS_URL", "redis://localhost:6379")
            mp.setenv("SAFE_VAR", "safe-value")

            safe_env = _build_safe_environment(workspace)

            # Verify blocked variables are not present
            assert "OPENAI_API_KEY" not in safe_env
            assert "DISCORD_BOT_TOKEN" not in safe_env
            assert "GITHUB_TOKEN" not in safe_env
            assert "AWS_ACCESS_KEY_ID" not in safe_env
            assert "AWS_SECRET_ACCESS_KEY" not in safe_env
            assert "DATABASE_URL" not in safe_env
            assert "NEXUS_DATABASE_URL" not in safe_env
            assert "REDIS_URL" not in safe_env

            # Verify safe variables are present
            assert safe_env.get("SAFE_VAR") == "safe-value"

    def test_build_safe_environment_strips_prefix_patterns(self):
        """
        Test that _build_safe_environment removes variables with dangerous prefixes.
        
        Requirements: 9.3
        """
        from kubani.nexus.sandbox.executor import _build_safe_environment

        workspace = "/tmp/test-workspace"

        # Set up environment with prefix-based dangerous variables
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("AWS_REGION", "us-east-1")
            mp.setenv("AWS_DEFAULT_REGION", "us-west-2")
            mp.setenv("GITHUB_API_TOKEN", "github-api-token")
            mp.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/webhook")
            mp.setenv("OCI_USERNAME", "oci-user")
            mp.setenv("NEO4J_URI", "bolt://localhost:7687")
            mp.setenv("SAFE_VAR", "safe-value")

            safe_env = _build_safe_environment(workspace)

            # Verify prefix-based dangerous variables are not present
            assert "AWS_REGION" not in safe_env
            assert "AWS_DEFAULT_REGION" not in safe_env
            assert "GITHUB_API_TOKEN" not in safe_env
            assert "DISCORD_WEBHOOK_URL" not in safe_env
            assert "OCI_USERNAME" not in safe_env
            assert "NEO4J_URI" not in safe_env

            # Verify safe variables are present
            assert safe_env.get("SAFE_VAR") == "safe-value"

    def test_build_safe_environment_sets_safe_defaults(self):
        """
        Test that _build_safe_environment sets safe default values.
        
        Requirements: 9.3
        """
        from kubani.nexus.sandbox.executor import _build_safe_environment

        workspace = "/tmp/test-workspace"

        safe_env = _build_safe_environment(workspace)

        # Verify safe defaults are set
        assert safe_env["HOME"] == workspace
        assert safe_env["TMPDIR"] == workspace
        assert safe_env["PYTHONDONTWRITEBYTECODE"] == "1"

    def test_build_safe_environment_overrides_home_and_tmpdir(self):
        """
        Test that _build_safe_environment overrides HOME and TMPDIR even if set.
        
        Requirements: 9.3
        """
        from kubani.nexus.sandbox.executor import _build_safe_environment

        workspace = "/tmp/test-workspace"

        # Set up environment with HOME and TMPDIR
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("HOME", "/home/user")
            mp.setenv("TMPDIR", "/tmp")

            safe_env = _build_safe_environment(workspace)

            # Verify they were overridden
            assert safe_env["HOME"] == workspace
            assert safe_env["TMPDIR"] == workspace

    def test_build_safe_environment_preserves_safe_variables(self):
        """
        Test that _build_safe_environment preserves safe environment variables.
        
        Requirements: 9.3
        """
        from kubani.nexus.sandbox.executor import _build_safe_environment

        workspace = "/tmp/test-workspace"

        # Set up environment with various safe variables
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("PATH", "/usr/bin:/bin")
            mp.setenv("LANG", "en_US.UTF-8")
            mp.setenv("USER", "testuser")
            mp.setenv("SHELL", "/bin/bash")
            mp.setenv("CUSTOM_VAR", "custom-value")

            safe_env = _build_safe_environment(workspace)

            # Verify safe variables are preserved
            assert safe_env.get("PATH") == "/usr/bin:/bin"
            assert safe_env.get("LANG") == "en_US.UTF-8"
            assert safe_env.get("USER") == "testuser"
            assert safe_env.get("SHELL") == "/bin/bash"
            assert safe_env.get("CUSTOM_VAR") == "custom-value"

    def test_blocked_env_vars_constant_is_comprehensive(self):
        """
        Test that BLOCKED_ENV_VARS includes all critical secrets.
        
        Requirements: 9.3
        """
        from kubani.nexus.sandbox.executor import BLOCKED_ENV_VARS

        # Verify critical secrets are in the blocked list
        critical_secrets = {
            "OPENAI_API_KEY",
            "DISCORD_BOT_TOKEN",
            "GITHUB_TOKEN",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "DATABASE_URL",
            "NEXUS_DATABASE_URL",
            "REDIS_URL",
            "OCI_PASSWORD",
            "NEO4J_PASSWORD",
        }

        assert critical_secrets.issubset(BLOCKED_ENV_VARS)

    @pytest.mark.asyncio
    async def test_execute_skill_uses_sanitized_environment(self):
        """
        Test that execute_skill_in_sandbox uses the sanitized environment.
        
        This is an integration test that verifies the sanitization is actually
        applied during skill execution.
        
        Requirements: 9.3
        """
        from kubani.nexus.sandbox.executor import execute_skill_in_sandbox

        # Create a skill that tries to access environment variables
        skill_content = """
import os
import json

def main(inputs):
    return {
        "openai_key": os.environ.get("OPENAI_API_KEY", "NOT_FOUND"),
        "discord_token": os.environ.get("DISCORD_BOT_TOKEN", "NOT_FOUND"),
        "github_token": os.environ.get("GITHUB_TOKEN", "NOT_FOUND"),
        "safe_var": os.environ.get("SAFE_VAR", "NOT_FOUND"),
        "home": os.environ.get("HOME", "NOT_FOUND"),
    }
"""

        # Set up environment with secrets
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("OPENAI_API_KEY", "sk-secret-key")
            mp.setenv("DISCORD_BOT_TOKEN", "discord-secret")
            mp.setenv("GITHUB_TOKEN", "github-secret")
            mp.setenv("SAFE_VAR", "safe-value")

            result = await execute_skill_in_sandbox(
                skill_name="test-env-access",
                inputs={},
                timeout_seconds=10,
                skill_content=skill_content,
            )

            # Verify the skill executed successfully
            assert result.success is True

            # Parse the output
            import json
            output_data = json.loads(result.output)

            # Verify secrets were NOT accessible
            assert output_data["openai_key"] == "NOT_FOUND"
            assert output_data["discord_token"] == "NOT_FOUND"
            assert output_data["github_token"] == "NOT_FOUND"

            # Verify safe variables were accessible
            assert output_data["safe_var"] == "safe-value"

            # Verify HOME was overridden to workspace
            assert output_data["home"] != "/home/user"
            assert "nexus-sandbox-" in output_data["home"]
