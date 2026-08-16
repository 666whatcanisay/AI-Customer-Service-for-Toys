from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class BrowserCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class BrowserCommandResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    success: bool
    details: dict[str, Any] = Field(default_factory=dict)


class BrowserAutomationPort(Protocol):
    def execute(self, command: BrowserCommand) -> BrowserCommandResult:
        """Execute a browser command in a future, explicitly authorized adapter."""


class BrowserExecutionDisabled(RuntimeError):
    pass


class DisabledBrowserAdapter:
    def execute(self, command: BrowserCommand) -> BrowserCommandResult:
        raise BrowserExecutionDisabled(
            f"browser execution is disabled in Foundation V1: {command.command_name}"
        )
