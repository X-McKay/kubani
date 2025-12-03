"""Custom exceptions for cluster manager."""


class ClusterManagerError(Exception):
    """Base exception for all cluster manager errors."""

    def __init__(self, message: str, details: str = None):
        """Initialize the exception.

        Args:
            message: Main error message
            details: Additional details or suggestions
        """
        self.message = message
        self.details = details
        super().__init__(self.format_message())

    def format_message(self) -> str:
        """Format the complete error message.

        Returns:
            Formatted error message with details
        """
        if self.details:
            return f"{self.message}\n\nDetails: {self.details}"
        return self.message


class TailscaleError(ClusterManagerError):
    """Exception raised for Tailscale-related errors."""

    pass


class KubernetesError(ClusterManagerError):
    """Exception raised for Kubernetes API errors."""

    pass


class AnsibleError(ClusterManagerError):
    """Exception raised for Ansible execution errors."""

    pass


class ValidationError(ClusterManagerError):
    """Exception raised for validation errors."""

    pass


class ConfigurationError(ClusterManagerError):
    """Exception raised for configuration errors."""

    pass
