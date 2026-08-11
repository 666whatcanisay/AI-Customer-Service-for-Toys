"""Standalone customer-service computer Agent foundation."""

from .config import (
    AgentConfigError,
    ChannelAgentConfig,
    load_agent_config,
    migrate_agent_config,
    save_agent_config,
)
from .desktop import DesktopAssistantError, DesktopAssistantServer
from .browser import (
    BrowserCommandInterface,
    BrowserSessionState,
    BrowserSessionStatus,
    ChannelAgentBrowserManager,
)
from .pdd_login import (
    PDDLoginObservation,
    PDDLoginObservationAdapter,
    PDDLoginState,
    PDDStoreIdentity,
)
from .binding import AgentBindingStore, AgentRuntimeBinding
from .contract import AgentRuntimeStatus, ManagedAgentConfig
from .identity import AgentIdentity, AgentIdentityStatus
from .runtime import AgentRuntimeSnapshot, ChannelAgentRuntime
from .version import (
    AGENT_CONTROL_PROTOCOL_VERSION,
    AGENT_PROTOCOL_VERSION,
    AGENT_VERSION,
)
from .windows import (
    WINDOWS_CLIENT_VERSION,
    AgentExperienceStatus,
    WindowsAgentHost,
    WindowsClientState,
)

__all__ = [
    "AGENT_CONTROL_PROTOCOL_VERSION",
    "AGENT_PROTOCOL_VERSION",
    "AGENT_VERSION",
    "AgentConfigError",
    "AgentBindingStore",
    "AgentIdentity",
    "AgentIdentityStatus",
    "AgentRuntimeSnapshot",
    "AgentRuntimeBinding",
    "AgentRuntimeStatus",
    "AgentExperienceStatus",
    "BrowserCommandInterface",
    "BrowserSessionState",
    "BrowserSessionStatus",
    "ChannelAgentConfig",
    "DesktopAssistantError",
    "DesktopAssistantServer",
    "ChannelAgentBrowserManager",
    "PDDLoginObservation",
    "PDDLoginObservationAdapter",
    "PDDLoginState",
    "PDDStoreIdentity",
    "ChannelAgentRuntime",
    "ManagedAgentConfig",
    "WINDOWS_CLIENT_VERSION",
    "WindowsAgentHost",
    "WindowsClientState",
    "load_agent_config",
    "migrate_agent_config",
    "save_agent_config",
]
