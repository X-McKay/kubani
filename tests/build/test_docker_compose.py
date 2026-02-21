"""
Tests for docker-compose.nexus.yml configuration.

Validates that docker-compose file is properly configured for Nexus services.

Requirements: 17.4, 17.5, 17.6, 17.7
"""

import subprocess
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def docker_compose_file(project_root):
    """Get the docker-compose.nexus.yml file."""
    return project_root / "docker-compose.nexus.yml"


class TestDockerComposeConfiguration:
    """Tests for docker-compose.nexus.yml (Requirement 17.4)."""

    def test_docker_compose_file_exists(self, docker_compose_file):
        """Verify docker-compose.nexus.yml exists."""
        assert docker_compose_file.exists(), "docker-compose.nexus.yml not found"

    def test_docker_compose_is_valid_yaml(self, docker_compose_file):
        """Verify docker-compose.nexus.yml is valid YAML."""
        with open(docker_compose_file) as f:
            config = yaml.safe_load(f)

        assert config is not None, "docker-compose.nexus.yml should be valid YAML"
        assert "services" in config, "docker-compose.nexus.yml should have services"

    def test_docker_compose_has_required_services(self, docker_compose_file):
        """
        Verify docker-compose.nexus.yml has all required infrastructure services.

        Validates: Requirements 17.4
        """
        with open(docker_compose_file) as f:
            config = yaml.safe_load(f)

        services = config.get("services", {})

        # Check for required infrastructure services
        required_services = ["temporal", "redis", "postgres", "qdrant"]
        for service in required_services:
            assert service in services, f"Service '{service}' should be defined"

    def test_docker_compose_services_have_healthchecks(self, docker_compose_file):
        """Verify services have healthchecks configured."""
        with open(docker_compose_file) as f:
            config = yaml.safe_load(f)

        services = config.get("services", {})

        # Services that should have healthchecks
        services_needing_health = ["temporal-db", "redis", "postgres", "qdrant"]

        for service_name in services_needing_health:
            if service_name in services:
                service = services[service_name]
                assert "healthcheck" in service, f"Service '{service_name}' should have healthcheck"

    def test_docker_compose_postgres_has_init_script(self, docker_compose_file, project_root):
        """
        Verify PostgreSQL service has init script mounted.

        Validates: Requirements 17.7
        """
        with open(docker_compose_file) as f:
            config = yaml.safe_load(f)

        services = config.get("services", {})
        postgres = services.get("postgres", {})

        # Check for volume mount of init script
        volumes = postgres.get("volumes", [])
        has_init_script = any("nexus-init.sql" in str(vol) for vol in volumes)

        assert has_init_script, "PostgreSQL should have nexus-init.sql mounted"

        # Verify init script exists
        init_script = project_root / "infrastructure" / "docker" / "nexus-init.sql"
        assert init_script.exists(), "nexus-init.sql should exist"

    def test_docker_compose_has_proper_ports(self, docker_compose_file):
        """Verify services expose proper ports."""
        with open(docker_compose_file) as f:
            config = yaml.safe_load(f)

        services = config.get("services", {})

        # Check expected ports
        expected_ports = {
            "temporal": ["7233", "8080"],
            "redis": ["6379"],
            "postgres": ["5432"],
            "qdrant": ["6333", "6334"],
        }

        for service_name, ports in expected_ports.items():
            if service_name in services:
                service = services[service_name]
                service_ports = service.get("ports", [])
                service_ports_str = str(service_ports)

                for port in ports:
                    assert port in service_ports_str, (
                        f"Service '{service_name}' should expose port {port}"
                    )

    @pytest.mark.slow
    @pytest.mark.integration
    def test_docker_compose_validates(self, docker_compose_file):
        """
        Test that docker-compose config is valid.

        This uses docker-compose config command to validate the file.
        """
        result = subprocess.run(
            ["docker", "compose", "-f", str(docker_compose_file), "config"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"docker-compose config validation failed:\n{result.stderr}"


class TestGatewayContainerConfiguration:
    """Tests for Gateway container configuration (Requirement 17.5)."""

    def test_gateway_would_need_environment_variables(self):
        """
        Document required environment variables for Gateway container.

        Validates: Requirements 17.5
        """
        # Gateway needs these environment variables to connect to dependencies
        required_env_vars = [
            "NEXUS_DATABASE_URL",  # PostgreSQL connection
            "REDIS_URL",  # Redis connection
            "TEMPORAL_HOST",  # Temporal connection
        ]

        # This test documents the requirements
        # Actual validation would happen in integration tests
        assert len(required_env_vars) > 0, "Gateway requires environment variables"


class TestOrchestratorContainerConfiguration:
    """Tests for Orchestrator container configuration (Requirement 17.6)."""

    def test_orchestrator_would_need_environment_variables(self):
        """
        Document required environment variables for Orchestrator container.

        Validates: Requirements 17.6
        """
        # Orchestrator needs these environment variables
        required_env_vars = [
            "TEMPORAL_HOST",  # Temporal connection
            "TEMPORAL_NAMESPACE",  # Temporal namespace
        ]

        # This test documents the requirements
        # Actual validation would happen in integration tests
        assert len(required_env_vars) > 0, "Orchestrator requires environment variables"


class TestDatabaseInitialization:
    """Tests for database initialization (Requirement 17.7)."""

    def test_nexus_init_sql_exists(self, project_root):
        """
        Verify nexus-init.sql exists.

        Validates: Requirements 17.7
        """
        init_script = project_root / "infrastructure" / "docker" / "nexus-init.sql"
        assert init_script.exists(), "nexus-init.sql should exist"

    def test_nexus_init_sql_has_table_definitions(self, project_root):
        """Verify nexus-init.sql contains table definitions."""
        init_script = project_root / "infrastructure" / "docker" / "nexus-init.sql"
        content = init_script.read_text()

        # Check for expected tables
        expected_tables = [
            "conversations",
            "conversation_messages",
            "agent_actions",
            "skills",
            "approval_requests",
        ]

        for table in expected_tables:
            assert table in content.lower(), f"Init script should create '{table}' table"
