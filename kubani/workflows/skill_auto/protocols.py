"""Protocol definitions for external dependencies.

These protocols define the contracts for external dependencies used by
the capability layer. By programming to these protocols, capabilities can be
easily tested with mock implementations.

Common protocols are imported from kubani.framework.protocols.
Workflow-specific protocols are defined here.
"""

# Re-export common protocols from framework
from kubani.framework.protocols import (
    DiscordClientProtocol,
    FileSystemProtocol,
    LLMProtocol,
    RegistryClientProtocol,
)

# Aliases for backwards compatibility with existing code
LLMClient = LLMProtocol
FileSystem = FileSystemProtocol
DiscordClient = DiscordClientProtocol
RegistryClient = RegistryClientProtocol

__all__ = [
    # Framework protocols (canonical names)
    "LLMProtocol",
    "FileSystemProtocol",
    "DiscordClientProtocol",
    "RegistryClientProtocol",
    # Backwards compatibility aliases
    "LLMClient",
    "FileSystem",
    "DiscordClient",
    "RegistryClient",
]
