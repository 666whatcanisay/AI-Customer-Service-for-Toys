"""Standalone customer-service computer Agent foundation."""

from .config import AgentConfigError, ChannelAgentConfig, load_agent_config
from .binding import AgentBindingStore, AgentRuntimeBinding
from .contract import AgentRuntimeStatus, ManagedAgentConfig
from .identity import AgentIdentity, AgentIdentityStatus
from .runtime import AgentRuntimeSnapshot, ChannelAgentRuntime
from .version import AGENT_PROTOCOL_VERSION, AGENT_VERSION
from .windows import WINDOWS_CLIENT_VERSION, WindowsAgentHost, WindowsClientState

__all__ = [
    "AGENT_PROTOCOL_VERSION",
    "AGENT_VERSION",
    "AgentConfigError",
    "AgentBindingStore",
    "AgentIdentity",
    "AgentIdentityStatus",
    "AgentRuntimeSnapshot",
    "AgentRuntimeBinding",
    "AgentRuntimeStatus",
    "ChannelAgentConfig",
    "ChannelAgentRuntime",
    "ManagedAgentConfig",
    "WINDOWS_CLIENT_VERSION",
    "WindowsAgentHost",
    "WindowsClientState",
    "load_agent_config",
]
