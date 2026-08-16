from __future__ import annotations

from typing import Any

from .client import ChannelEngineClient
from .config import ChannelAgentConfig
from .security import DeviceCredentialStore


class LegacyChannelEngineClient(ChannelEngineClient):
    """One-RC compatibility shim for historical loopback tests only.

    The 2.0 production composition does not package this module and the production
    Host Control application does not mount the corresponding routes.
    """

    def __init__(
        self,
        config: ChannelAgentConfig,
        *,
        http_client: Any | None = None,
        credential_store: DeviceCredentialStore | None = None,
        allow_legacy_control: bool = False,
    ) -> None:
        if not allow_legacy_control:
            raise PermissionError("legacy Agent Control V1 requires explicit test opt-in")
        super().__init__(
            config,
            http_client=http_client,
            credential_store=credential_store,
        )

    def _control_path(self, suffix: str) -> str:
        if self._signer is not None:
            return super()._control_path(suffix)
        return f"/channel-agent/v1{suffix}"


__all__ = ["LegacyChannelEngineClient"]
