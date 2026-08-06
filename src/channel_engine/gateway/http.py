from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self

import httpx

from .auth import GatewayRequestSigner
from .client import (
    AICSGatewayClient,
    DECISION_TIMEOUT_SECONDS,
    GatewayContractViolation,
    GatewayRetryPolicy,
    GatewayTransportError,
    GatewayTransportResponse,
    GatewayTransportTimeout,
)


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class GatewayEnvironment(StrEnum):
    MOCK = "mock"
    STAGING = "staging"
    PRODUCTION = "production"


class GatewayEnvironmentError(ValueError):
    pass


class ProductionGatewayDisabled(GatewayEnvironmentError):
    pass


def _parse_boolean(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise GatewayEnvironmentError(f"{name} must be an explicit boolean")


@dataclass(frozen=True, slots=True)
class GatewayAdapterConfig:
    environment: GatewayEnvironment = GatewayEnvironment.MOCK
    base_url: str = "http://127.0.0.1:18021"
    client_id: str = "channel-engine"
    key_id: str = "foundation-http-key"
    production_enabled: bool = False
    timeout_seconds: float = DECISION_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not isinstance(self.environment, GatewayEnvironment):
            try:
                object.__setattr__(
                    self,
                    "environment",
                    GatewayEnvironment(str(self.environment).strip().lower()),
                )
            except ValueError as exc:
                raise GatewayEnvironmentError("gateway environment is invalid") from exc
        if not self.base_url.strip():
            raise GatewayEnvironmentError("gateway base_url is required")
        if not _IDENTIFIER_PATTERN.fullmatch(self.client_id):
            raise GatewayEnvironmentError("gateway client_id is not a Contract V1 ID")
        if not _IDENTIFIER_PATTERN.fullmatch(self.key_id):
            raise GatewayEnvironmentError("gateway key_id is not a Contract V1 ID")
        if not isinstance(self.production_enabled, bool):
            raise GatewayEnvironmentError("production_enabled must be boolean")
        if self.timeout_seconds <= 0:
            raise GatewayEnvironmentError("gateway timeout_seconds must be positive")

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> Self:
        source = os.environ if environ is None else environ
        raw_environment = source.get("CHANNEL_ENGINE_GATEWAY_ENVIRONMENT", "mock")
        try:
            environment = GatewayEnvironment(raw_environment.strip().lower())
        except ValueError as exc:
            raise GatewayEnvironmentError(
                "CHANNEL_ENGINE_GATEWAY_ENVIRONMENT must be mock, staging or production"
            ) from exc
        default_url = (
            "http://127.0.0.1:18021"
            if environment is GatewayEnvironment.MOCK
            else ""
        )
        production_enabled = _parse_boolean(
            source.get("CHANNEL_ENGINE_GATEWAY_PRODUCTION_ENABLED", "false"),
            "CHANNEL_ENGINE_GATEWAY_PRODUCTION_ENABLED",
        )
        timeout_value = source.get(
            "CHANNEL_ENGINE_GATEWAY_TIMEOUT_SECONDS",
            str(DECISION_TIMEOUT_SECONDS),
        )
        try:
            timeout_seconds = float(timeout_value)
        except ValueError as exc:
            raise GatewayEnvironmentError(
                "CHANNEL_ENGINE_GATEWAY_TIMEOUT_SECONDS must be numeric"
            ) from exc
        return cls(
            environment=environment,
            base_url=source.get("CHANNEL_ENGINE_GATEWAY_BASE_URL", default_url),
            client_id=source.get(
                "CHANNEL_ENGINE_GATEWAY_CLIENT_ID",
                "channel-engine",
            ),
            key_id=source.get(
                "CHANNEL_ENGINE_GATEWAY_KEY_ID",
                "foundation-http-key",
            ),
            production_enabled=production_enabled,
            timeout_seconds=timeout_seconds,
        )


def validate_gateway_environment(config: GatewayAdapterConfig) -> httpx.URL:
    if (
        config.environment is GatewayEnvironment.PRODUCTION
        and not config.production_enabled
    ):
        raise ProductionGatewayDisabled(
            "production AI-CS gateway is disabled; explicit enablement is required"
        )
    try:
        url = httpx.URL(config.base_url)
    except (TypeError, ValueError) as exc:
        raise GatewayEnvironmentError("gateway base_url is invalid") from exc
    if not url.is_absolute_url or url.host is None:
        raise GatewayEnvironmentError("gateway base_url must be absolute")
    if url.username or url.password:
        raise GatewayEnvironmentError("gateway base_url cannot contain credentials")
    if url.query or url.fragment:
        raise GatewayEnvironmentError("gateway base_url cannot contain query or fragment")
    if url.path not in {"", "/"}:
        raise GatewayEnvironmentError("gateway base_url cannot contain a path prefix")

    if config.environment is GatewayEnvironment.MOCK:
        if url.scheme not in {"http", "https"}:
            raise GatewayEnvironmentError("mock gateway requires HTTP or HTTPS")
        if url.host.lower() not in {"localhost", "127.0.0.1", "::1"}:
            raise GatewayEnvironmentError("mock gateway must use a loopback host")
    elif url.scheme != "https":
        raise GatewayEnvironmentError("staging and production gateways require HTTPS")
    return url.copy_with(path="")


class HttpGatewayTransport:
    """Synchronous HTTP transport with redirects and environment proxies disabled."""

    def __init__(
        self,
        config: GatewayAdapterConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.base_url = validate_gateway_environment(config)
        self._owns_client = client is None
        self._client = client or httpx.Client(
            verify=True,
            trust_env=False,
            follow_redirects=False,
        )

    def request(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> GatewayTransportResponse:
        if not path.startswith("/") or "?" in path or "#" in path:
            raise GatewayContractViolation("gateway path must be exact and query-free")
        if timeout_seconds <= 0:
            raise GatewayContractViolation("gateway timeout must be positive")
        url = self.base_url.copy_with(path=path)
        try:
            response = self._client.request(
                method=method.upper(),
                url=url,
                content=body,
                headers=dict(headers),
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise GatewayTransportTimeout("AI-CS HTTP request timed out") from exc
        except httpx.TransportError as exc:
            raise GatewayTransportError("AI-CS HTTP transport failed") from exc
        if response.is_redirect:
            raise GatewayContractViolation("AI-CS gateway redirects are forbidden")
        return GatewayTransportResponse(
            status_code=response.status_code,
            body=response.content,
            headers=dict(response.headers),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class ProductionGatewayClient(AICSGatewayClient):
    """Production-grade adapter; production environment remains opt-in and locked."""

    def __init__(
        self,
        config: GatewayAdapterConfig,
        secret: bytes,
        *,
        http_client: httpx.Client | None = None,
        retry_policy: GatewayRetryPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
        nonce_factory: Callable[[], str] | None = None,
        sleeper: Callable[[float], None] | None = None,
        random_source: Callable[[], float] | None = None,
    ) -> None:
        transport = HttpGatewayTransport(config, client=http_client)
        signer_kwargs: dict[str, object] = {}
        if clock is not None:
            signer_kwargs["clock"] = clock
        if nonce_factory is not None:
            signer_kwargs["nonce_factory"] = nonce_factory
        signer = GatewayRequestSigner(
            client_id=config.client_id,
            key_id=config.key_id,
            secret=secret,
            **signer_kwargs,
        )
        client_kwargs: dict[str, object] = {}
        if sleeper is not None:
            client_kwargs["sleeper"] = sleeper
        if random_source is not None:
            client_kwargs["random_source"] = random_source
        super().__init__(
            transport,
            signer,
            retry_policy=retry_policy,
            timeout_seconds=config.timeout_seconds,
            **client_kwargs,
        )
        self.config = config
        self.http_transport = transport

    @property
    def environment(self) -> GatewayEnvironment:
        return self.config.environment

    def close(self) -> None:
        self.http_transport.close()

    def __enter__(self) -> ProductionGatewayClient:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


__all__ = [
    "GatewayAdapterConfig",
    "GatewayEnvironment",
    "GatewayEnvironmentError",
    "HttpGatewayTransport",
    "ProductionGatewayClient",
    "ProductionGatewayDisabled",
    "validate_gateway_environment",
]
