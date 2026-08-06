"""Production-only Windows Channel Agent release candidate."""

from .config import AgentConfig, ConfigError, load_config
from .models import AGENT_VERSION
from .runtime import AgentRuntime

__all__ = ["AgentConfig", "AgentRuntime", "ConfigError", "load_config"]
__version__ = AGENT_VERSION
