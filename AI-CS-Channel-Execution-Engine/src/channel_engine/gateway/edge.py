from __future__ import annotations

import hashlib
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from enum import StrEnum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import RLock, Thread
from typing import Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.models.entities import new_id, utc_now

from .client import GatewayTransportResponse
from .contract import (
    CONTRACT_VERSION,
    ErrorEnvelope,
    GatewayError,
    GatewayErrorCode,
)
from .mock_server import MockAICSServerTimeout


GATEWAY_EDGE_SANDBOX_VERSION = "1.0"
GATEWAY_EDGE_BODY_LIMIT_BYTES = 1024 * 1024


class GatewayEdgeFault(StrEnum):
    PASS_THROUGH = "PASS_THROUGH"
    TIMEOUT = "TIMEOUT"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"


@runtime_checkable
class GatewayEdgeBackend(Protocol):
    def handle_request(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> GatewayTransportResponse: ...


class GatewayEdgeRequest(BaseModel):
    """Safe request evidence: no body, Authorization value or credential material."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    method: str = Field(min_length=1, max_length=16)
    path: str = Field(min_length=1, max_length=512)
    request_id: str | None = Field(default=None, max_length=128)
    correlation_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)
    body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_present: bool
    status_code: int | None = Field(default=None, ge=100, le=599)
    received_at: AwareDatetime


class SandboxGatewayEdgeServer:
    """Real loopback HTTP edge backed by the controlled AI-CS sandbox.

    This test server deliberately cannot bind a non-loopback address. It records
    only request identity and a body digest, never request bodies or auth values.
    """

    def __init__(
        self,
        backend: GatewayEdgeBackend,
        *,
        faults: Iterable[GatewayEdgeFault] = (),
        timeout_delay_seconds: float = 0.2,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not isinstance(backend, GatewayEdgeBackend):
            raise TypeError("backend does not implement GatewayEdgeBackend")
        if timeout_delay_seconds <= 0:
            raise ValueError("timeout_delay_seconds must be positive")
        self._backend = backend
        self._faults = deque(faults)
        self._timeout_delay_seconds = timeout_delay_seconds
        self._clock = clock
        self._requests: list[GatewayEdgeRequest] = []
        self._lock = RLock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    @property
    def base_url(self) -> str:
        server = self._server
        if server is None:
            raise RuntimeError("sandbox gateway edge is not running")
        return f"http://127.0.0.1:{server.server_address[1]}"

    @property
    def requests(self) -> tuple[GatewayEdgeRequest, ...]:
        with self._lock:
            return tuple(self._requests)

    def start(self) -> SandboxGatewayEdgeServer:
        if self._server is not None:
            return self
        edge = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                edge._handle(self)

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
                edge._handle(self)

            def do_PUT(self) -> None:  # noqa: N802 - stdlib handler API
                edge._handle(self)

            def log_message(self, _format: str, *args: object) -> None:
                # The default handler writes raw request data to stderr.
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        self._server = server
        self._thread = Thread(
            target=lambda: server.serve_forever(poll_interval=0.01),
            name="ai-cs-sandbox-gateway-edge",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=2)
        self._server = None
        self._thread = None

    def __enter__(self) -> SandboxGatewayEdgeServer:
        return self.start()

    def __exit__(self, *_exc_info: object) -> None:
        self.stop()

    def _next_fault(self) -> GatewayEdgeFault:
        with self._lock:
            return (
                self._faults.popleft()
                if self._faults
                else GatewayEdgeFault.PASS_THROUGH
            )

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        headers = {name: value for name, value in handler.headers.items()}
        normalized = {name.lower(): value for name, value in headers.items()}
        try:
            length = int(normalized.get("content-length", "0"))
        except ValueError:
            length = GATEWAY_EDGE_BODY_LIMIT_BYTES + 1
        if length < 0 or length > GATEWAY_EDGE_BODY_LIMIT_BYTES:
            body = b""
            response = self._error_response(
                GatewayErrorCode.PAYLOAD_TOO_LARGE,
                normalized,
            )
            self._record(handler.command, handler.path, normalized, body, 413)
            self._write(handler, response)
            return
        body = handler.rfile.read(length) if length else b""
        fault = self._next_fault()
        if fault is GatewayEdgeFault.TIMEOUT:
            self._record(handler.command, handler.path, normalized, body, None)
            time.sleep(self._timeout_delay_seconds)
            handler.close_connection = True
            return
        if fault is GatewayEdgeFault.AUTHENTICATION_FAILED:
            response = self._error_response(
                GatewayErrorCode.AUTHENTICATION_FAILED,
                normalized,
            )
        elif fault is GatewayEdgeFault.AUTHORIZATION_DENIED:
            response = self._error_response(
                GatewayErrorCode.AUTHORIZATION_DENIED,
                normalized,
            )
        else:
            try:
                response = self._backend.handle_request(
                    method=handler.command,
                    path=handler.path,
                    body=body,
                    headers=headers,
                )
            except MockAICSServerTimeout:
                self._record(handler.command, handler.path, normalized, body, None)
                time.sleep(self._timeout_delay_seconds)
                handler.close_connection = True
                return
        self._record(
            handler.command,
            handler.path,
            normalized,
            body,
            response.status_code,
        )
        self._write(handler, response)

    def _record(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes,
        status_code: int | None,
    ) -> None:
        record = GatewayEdgeRequest(
            method=method.upper(),
            path=path,
            request_id=headers.get("x-request-id"),
            correlation_id=headers.get("x-correlation-id"),
            idempotency_key=headers.get("idempotency-key"),
            body_sha256=hashlib.sha256(body).hexdigest(),
            authorization_present="authorization" in headers,
            status_code=status_code,
            received_at=_aware(self._clock()),
        )
        with self._lock:
            self._requests.append(record)

    def _error_response(
        self,
        code: GatewayErrorCode,
        headers: Mapping[str, str],
    ) -> GatewayTransportResponse:
        status = {
            GatewayErrorCode.AUTHENTICATION_FAILED: 401,
            GatewayErrorCode.AUTHORIZATION_DENIED: 403,
            GatewayErrorCode.PAYLOAD_TOO_LARGE: 413,
        }[code]
        envelope = ErrorEnvelope(
            contract_version=CONTRACT_VERSION,
            error=GatewayError(
                error_id=new_id("gateway-edge-error"),
                code=code,
                message=f"Sandbox Gateway Edge rejected request: {code.value}",
                retryable=False,
                request_id=headers.get("x-request-id"),
                correlation_id=headers.get("x-correlation-id"),
                details={
                    "mode": "SANDBOX_EDGE",
                    "real_ai_cs_called": False,
                },
                occurred_at=_aware(self._clock()),
            ),
        )
        return GatewayTransportResponse(
            status_code=status,
            body=envelope.model_dump_json().encode("utf-8"),
            headers={"X-AI-CS-Contract-Version": CONTRACT_VERSION},
        )

    @staticmethod
    def _write(
        handler: BaseHTTPRequestHandler,
        response: GatewayTransportResponse,
    ) -> None:
        try:
            handler.send_response(response.status_code)
            for name, value in response.headers.items():
                handler.send_header(name, value)
            handler.send_header("Content-Length", str(len(response.body)))
            handler.send_header("Connection", "close")
            handler.end_headers()
            if response.body:
                handler.wfile.write(response.body)
        except (BrokenPipeError, ConnectionResetError):
            # Expected when the client enforces a shorter timeout than the sandbox.
            return


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


__all__ = [
    "GATEWAY_EDGE_BODY_LIMIT_BYTES",
    "GATEWAY_EDGE_SANDBOX_VERSION",
    "GatewayEdgeBackend",
    "GatewayEdgeFault",
    "GatewayEdgeRequest",
    "SandboxGatewayEdgeServer",
]
