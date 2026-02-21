"""Test infrastructure management utilities.

This module provides utilities for managing Docker Compose test services:
- Starting and stopping test infrastructure
- Waiting for service readiness
- Cleaning up test data
"""

import asyncio
import subprocess
import time
from typing import Optional


class TestInfrastructure:
    """Manager for test infrastructure services."""
    
    def __init__(self, compose_file: str = "docker-compose.test.yml"):
        """Initialize test infrastructure manager.
        
        Args:
            compose_file: Path to docker-compose file
        """
        self.compose_file = compose_file
        self.services = ["postgres-test", "redis-test", "temporal-test"]
    
    def start(self, services: Optional[list[str]] = None, wait: bool = True) -> None:
        """Start test infrastructure services.
        
        Args:
            services: List of services to start (None = all)
            wait: If True, wait for services to be healthy
        """
        cmd = ["docker-compose", "-f", self.compose_file, "up", "-d"]
        
        if services:
            cmd.extend(services)
        
        subprocess.run(cmd, check=True)
        
        if wait:
            self.wait_for_services(services or self.services)
    
    def stop(self, services: Optional[list[str]] = None, remove: bool = True) -> None:
        """Stop test infrastructure services.
        
        Args:
            services: List of services to stop (None = all)
            remove: If True, remove containers
        """
        cmd = ["docker-compose", "-f", self.compose_file]
        
        if remove:
            cmd.append("down")
        else:
            cmd.append("stop")
        
        if services:
            cmd.extend(services)
        
        subprocess.run(cmd, check=True)
    
    def wait_for_services(
        self,
        services: list[str],
        timeout: int = 60,
        poll_interval: float = 2.0,
    ) -> None:
        """Wait for services to be healthy.
        
        Args:
            services: List of service names to wait for
            timeout: Maximum time to wait in seconds
            poll_interval: Time between health checks in seconds
            
        Raises:
            TimeoutError: If services don't become healthy within timeout
        """
        start_time = time.time()
        
        while True:
            all_healthy = True
            
            for service in services:
                if not self._is_service_healthy(service):
                    all_healthy = False
                    break
            
            if all_healthy:
                return
            
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                raise TimeoutError(
                    f"Services did not become healthy within {timeout}s: {services}"
                )
            
            time.sleep(poll_interval)
    
    def _is_service_healthy(self, service: str) -> bool:
        """Check if a service is healthy.
        
        Args:
            service: Service name
            
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            result = subprocess.run(
                [
                    "docker-compose",
                    "-f",
                    self.compose_file,
                    "ps",
                    "--format",
                    "json",
                    service,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            
            # Parse JSON output to check health status
            import json
            containers = json.loads(result.stdout)
            
            if not containers:
                return False
            
            # Check if container is running and healthy
            for container in containers:
                state = container.get("State", "")
                health = container.get("Health", "")
                
                if state != "running":
                    return False
                
                # If health check is defined, check it
                if health and health != "healthy":
                    return False
            
            return True
            
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            return False
    
    def get_connection_string(self, service: str) -> str:
        """Get connection string for a service.
        
        Args:
            service: Service name
            
        Returns:
            Connection string for the service
            
        Raises:
            ValueError: If service is not recognized
        """
        connection_strings = {
            "postgres-test": "postgresql://nexus_test:nexus_test@localhost:15432/nexus_test",
            "redis-test": "redis://localhost:16379",
            "temporal-test": "localhost:17233",
            "qdrant-test": "http://localhost:16333",
        }
        
        if service not in connection_strings:
            raise ValueError(f"Unknown service: {service}")
        
        return connection_strings[service]
    
    def cleanup(self) -> None:
        """Clean up all test infrastructure."""
        self.stop(remove=True)


# Convenience functions for pytest fixtures

def start_test_infrastructure(
    services: Optional[list[str]] = None,
    compose_file: str = "docker-compose.test.yml",
) -> TestInfrastructure:
    """Start test infrastructure and return manager.
    
    Args:
        services: List of services to start (None = all)
        compose_file: Path to docker-compose file
        
    Returns:
        TestInfrastructure manager instance
    """
    infra = TestInfrastructure(compose_file)
    infra.start(services)
    return infra


def stop_test_infrastructure(
    infra: TestInfrastructure,
    remove: bool = True,
) -> None:
    """Stop test infrastructure.
    
    Args:
        infra: TestInfrastructure manager instance
        remove: If True, remove containers
    """
    infra.stop(remove=remove)
