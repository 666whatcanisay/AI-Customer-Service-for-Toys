from __future__ import annotations

import argparse
import ipaddress
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response

from app.gateway.contract import (
    DECISION_PATH,
    HEALTH_PATH,
    GatewayErrorCode,
    GatewayProblem,
)
from app.gateway.routes import gateway_problem_response


_FORWARDED_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "content-type",
        "idempotency-key",
        "x-ai-cs-content-sha256",
        "x-ai-cs-contract-version",
        "x-ai-cs-nonce",
        "x-ai-cs-timestamp",
        "x-correlation-id",
        "x-request-id",
    }
)
_FORWARDED_RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "idempotency-replayed",
        "retry-after",
        "x-ai-cs-contract-version",
        "x-correlation-id",
        "x-request-id",
    }
)
_RFC1918_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


def _private_ipv4(value: str) -> ipaddress.IPv4Address:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError("Gateway LAN bind address must be a valid IPv4 address") from exc
    if not isinstance(address, ipaddress.IPv4Address) or not any(
        address in network for network in _RFC1918_NETWORKS
    ):
        raise ValueError("Gateway LAN bind address must be a private IPv4 address")
    if address.is_loopback or address.is_link_local or address.is_multicast:
        raise ValueError("Gateway LAN bind address must be a routable private IPv4 address")
    return address


def _private_ipv4_network(value: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(value, strict=True)
    except ValueError as exc:
        raise ValueError(
            "Gateway allowed networks must be canonical private IPv4 CIDRs"
        ) from exc
    if not isinstance(network, ipaddress.IPv4Network) or not any(
        network.subnet_of(private_network) for private_network in _RFC1918_NETWORKS
    ):
        raise ValueError("Gateway allowed networks must be private IPv4 CIDRs")
    if network.is_loopback or network.is_link_local or network.is_multicast:
        raise ValueError("Gateway allowed networks must be routable private IPv4 CIDRs")
    return network


def _loopback_upstream(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Gateway LAN upstream must be an explicit loopback HTTP origin"
        )
    return f"http://127.0.0.1:{parsed.port}"


@dataclass(frozen=True)
class GatewayLanProxyConfig:
    bind_address: ipaddress.IPv4Address
    port: int
    interface_network: ipaddress.IPv4Network
    allowed_networks: tuple[ipaddress.IPv4Network, ...]
    upstream_origin: str
    upstream_timeout_seconds: float = 180.0

    @classmethod
    def build(
        cls,
        *,
        bind_address: str,
        port: int,
        interface_network: str,
        allowed_networks: Sequence[str],
        upstream_origin: str,
        upstream_timeout_seconds: float = 180.0,
    ) -> "GatewayLanProxyConfig":
        if port < 1 or port > 65535:
            raise ValueError("Gateway LAN port must be between 1 and 65535")
        if not allowed_networks:
            raise ValueError("At least one Gateway allowed network is required")
        bind = _private_ipv4(bind_address)
        physical_network = _private_ipv4_network(interface_network)
        networks = tuple(_private_ipv4_network(item) for item in allowed_networks)
        if len(set(networks)) != len(networks):
            raise ValueError("Gateway allowed networks must be unique")
        if bind not in physical_network:
            raise ValueError("Gateway LAN bind address must belong to the interface network")
        if any(not network.subnet_of(physical_network) for network in networks):
            raise ValueError(
                "Gateway allowed networks must stay within the interface network"
            )
        if upstream_timeout_seconds <= 0 or upstream_timeout_seconds > 600:
            raise ValueError("Gateway upstream timeout must be between 0 and 600 seconds")
        return cls(
            bind_address=bind,
            port=port,
            interface_network=physical_network,
            allowed_networks=networks,
            upstream_origin=_loopback_upstream(upstream_origin),
            upstream_timeout_seconds=upstream_timeout_seconds,
        )

    def allows(self, client_host: str) -> bool:
        try:
            address = ipaddress.ip_address(client_host)
        except ValueError:
            return False
        return isinstance(address, ipaddress.IPv4Address) and any(
            address in network for network in self.allowed_networks
        )


def _safe_identifier(request: Request, header: str) -> str | None:
    value = request.headers.get(header)
    if value and len(value) <= 128 and value[0].isalnum() and all(
        character.isalnum() or character in "._:-" for character in value
    ):
        return value
    return None


def _problem(
    request: Request,
    *,
    status_code: int,
    code: GatewayErrorCode,
    message: str,
) -> Response:
    return gateway_problem_response(
        GatewayProblem(
            status_code=status_code,
            code=code,
            message=message,
            request_id=_safe_identifier(request, "X-Request-ID"),
            correlation_id=_safe_identifier(request, "X-Correlation-ID"),
        )
    )


def create_gateway_lan_proxy_app(
    config: GatewayLanProxyConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    client_host_resolver: Callable[[Request], str] | None = None,
) -> FastAPI:
    """Create an allowlisted LAN edge that leaves contract handling to A Core."""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.upstream_client = httpx.AsyncClient(
            base_url=config.upstream_origin,
            timeout=config.upstream_timeout_seconds,
            transport=transport,
            follow_redirects=False,
        )
        yield
        await application.state.upstream_client.aclose()

    application = FastAPI(
        title="AI-CS Gateway LAN Edge",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.router.redirect_slashes = False

    @application.middleware("http")
    async def enforce_source_network(request: Request, call_next):
        client_host = (
            client_host_resolver(request)
            if client_host_resolver is not None
            else request.client.host
            if request.client
            else ""
        )
        if not config.allows(client_host):
            return _problem(
                request,
                status_code=403,
                code=GatewayErrorCode.AUTHORIZATION_DENIED,
                message="Gateway LAN source network is not allowed.",
            )
        return await call_next(request)

    async def forward(request: Request) -> Response:
        if request.url.query:
            return _problem(
                request,
                status_code=400,
                code=GatewayErrorCode.INVALID_REQUEST,
                message="Gateway LAN requests must not contain a query string.",
            )
        if any(
            len(request.headers.getlist(header_name)) != 1
            for header_name in _FORWARDED_REQUEST_HEADERS
            if header_name in request.headers
        ):
            return _problem(
                request,
                status_code=400,
                code=GatewayErrorCode.INVALID_REQUEST,
                message="Gateway LAN request contains a duplicate contract header.",
            )
        body = await request.body()
        headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() in _FORWARDED_REQUEST_HEADERS
        }
        try:
            upstream_response = await request.app.state.upstream_client.request(
                request.method,
                request.url.path,
                content=body,
                headers=headers,
            )
        except httpx.HTTPError:
            return _problem(
                request,
                status_code=503,
                code=GatewayErrorCode.SERVICE_UNAVAILABLE,
                message="Gateway Core is unavailable.",
            )
        response_headers = {
            name: value
            for name, value in upstream_response.headers.items()
            if name.lower() in _FORWARDED_RESPONSE_HEADERS
        }
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=response_headers,
        )

    methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
    application.add_api_route(HEALTH_PATH, forward, methods=methods)
    application.add_api_route(DECISION_PATH, forward, methods=methods)

    @application.api_route(
        "/gateway/v1/{unapproved_path:path}", methods=methods, include_in_schema=False
    )
    async def reject_unapproved_gateway_path(request: Request) -> Response:
        return _problem(
            request,
            status_code=404,
            code=GatewayErrorCode.RESOURCE_NOT_FOUND,
            message="Gateway resource was not found.",
        )

    return application


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the controlled AI-CS LAN edge")
    parser.add_argument("--bind-address", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--interface-network", required=True)
    parser.add_argument("--allowed-network", action="append", required=True)
    parser.add_argument("--upstream-origin", required=True)
    parser.add_argument("--upstream-timeout-seconds", type=float, default=180.0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = GatewayLanProxyConfig.build(
        bind_address=args.bind_address,
        port=args.port,
        interface_network=args.interface_network,
        allowed_networks=args.allowed_network,
        upstream_origin=args.upstream_origin,
        upstream_timeout_seconds=args.upstream_timeout_seconds,
    )
    uvicorn.run(
        create_gateway_lan_proxy_app(config),
        host=str(config.bind_address),
        port=config.port,
        access_log=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
