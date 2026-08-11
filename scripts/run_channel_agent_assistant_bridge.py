from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pydantic import ValidationError

from channel_agent.assistant_bridge import (
    ApprovedReplyBridgeError,
    ApprovedReplyRequest,
    ApprovedReplyService,
)
from channel_agent.browser import ChannelAgentBrowserManager
from channel_agent.config import load_agent_config
from channel_agent.logger import SafeAgentLogger
from channel_agent.pdd_login import EdgePDDTargetResolver
from channel_agent.pdd_workspace import (
    ExistingPDDWorkspaceObserver,
    FixedReadOnlyPDDWorkspaceEvaluator,
    PDDWorkspaceSelectorContract,
)
from channel_agent.pdd_workspace_send import (
    ControlledPDDWorkspaceBrowserSender,
    WebSocketPDDWorkspaceActionPort,
)
from channel_engine.browser.cdp_readonly import WebSocketCDPEvaluator
from channel_engine.customer_assistant import SQLiteConversationBuffer
from channel_engine.storage import (
    SqlAlchemyUnitOfWork,
    create_engine_and_session,
    create_schema,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve the local Channel Agent feed and approved-reply boundary."
    )
    parser.add_argument("--data-root", default=".runtime/pdd-login-observation-v1")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8430)
    parser.add_argument(
        "--allowed-origin",
        default="http://127.0.0.1:8421",
    )
    return parser


def _build_service(data_root: Path) -> tuple[ApprovedReplyService, object]:
    config = load_agent_config(data_root / "config" / "agent.json")
    if (
        not config.browser_enabled
        or not config.pdd_login_observation_enabled
        or not config.customer_assistant_enabled
        or not config.manual_approval_required
        or config.auto_reply_enabled
    ):
        raise RuntimeError("Channel Agent controlled-send safety configuration is invalid")
    enabled = os.getenv("PDD_CONTROLLED_SEND_ENABLED", "").casefold() == "true"
    manager = ChannelAgentBrowserManager(
        agent_id=config.agent_id,
        data_root=data_root,
        enabled=config.browser_enabled,
        logger=SafeAgentLogger(data_root / "logs" / "approved-reply-bridge.jsonl"),
    )
    state = manager.browser_status()
    public = state.public_view(data_root)
    manager.close_resources()
    if state.status.value != "READY" or state.pid is None:
        raise RuntimeError("existing Agent-owned Edge session is not READY")

    resolver = EdgePDDTargetResolver(timeout_seconds=1.0)
    observer = ExistingPDDWorkspaceObserver(
        browser_id=state.browser_id,
        profile_path=state.profile_path,
        profile_reference=str(public["profile_reference"]),
        resolver=resolver,
        evaluator=FixedReadOnlyPDDWorkspaceEvaluator(
            WebSocketCDPEvaluator(timeout_seconds=2.0),
            PDDWorkspaceSelectorContract(),
        ),
        human_verified_product_attributes=(
            {
                "applicable_age": os.environ["PDD_PRODUCT_APPLICABLE_AGE"].strip(),
                "applicable_age_source": "operator_confirmed",
            }
            if os.getenv("PDD_PRODUCT_APPLICABLE_AGE", "").strip()
            else None
        ),
    )
    observer.capture()
    assistant_root = data_root / "runtime" / "real-pdd-assistant"
    database_url = f"sqlite:///{(assistant_root / 'channel-engine.sqlite3').as_posix()}"
    engine, session_factory = create_engine_and_session(database_url)
    create_schema(engine)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    buffer = SQLiteConversationBuffer(
        assistant_root / "conversation-buffer.sqlite3",
        clock=lambda: datetime.now(UTC),
    )
    sender = ControlledPDDWorkspaceBrowserSender(
        observer=observer,
        profile_path=state.profile_path,
        resolver=resolver,
        action_port=WebSocketPDDWorkspaceActionPort(timeout_seconds=3.0),
    )
    return (
        ApprovedReplyService(
            feed_path=assistant_root / "assistant-feed.json",
            buffer=buffer,
            uow_factory=uow_factory,
            observer=observer,
            browser_sender=sender,
            controlled_send_enabled=enabled,
        ),
        engine,
    )


class _Server(ThreadingHTTPServer):
    service: ApprovedReplyService
    feed_path: Path
    allowed_origin: str


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(HTTPStatus.OK, self.server.service.health())
            return
        if self.path != "/assistant-feed.json":
            self._json(HTTPStatus.NOT_FOUND, {"error_code": "NOT_FOUND"})
            return
        try:
            payload = self.server.feed_path.read_bytes()
        except OSError:
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error_code": "CHANNEL_AGENT_FEED_UNAVAILABLE"},
            )
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/approved-replies":
            self._json(HTTPStatus.NOT_FOUND, {"error_code": "NOT_FOUND"})
            return
        if self.headers.get("Origin") != self.server.allowed_origin:
            self._json(HTTPStatus.FORBIDDEN, {"error_code": "ORIGIN_DENIED"})
            return
        if self.headers.get("X-Channel-Agent-Intent") != "HUMAN_CONFIRMED_SEND":
            self._json(HTTPStatus.FORBIDDEN, {"error_code": "SEND_INTENT_MISSING"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 1 <= length <= 65_536:
            self._json(HTTPStatus.BAD_REQUEST, {"error_code": "REQUEST_SIZE_INVALID"})
            return
        try:
            request = ApprovedReplyRequest.model_validate_json(self.rfile.read(length))
            response = self.server.service.approve_and_send(request)
        except (UnicodeError, json.JSONDecodeError, ValidationError):
            self._json(HTTPStatus.BAD_REQUEST, {"error_code": "REQUEST_INVALID"})
            return
        except ApprovedReplyBridgeError as exc:
            self._json(exc.status_code, {"error_code": exc.error_code})
            return
        except Exception:
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error_code": "APPROVED_REPLY_BRIDGE_FAILED"},
            )
            return
        self._json(HTTPStatus.OK, response.model_dump(mode="json"))

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, value: object) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.bind not in {"127.0.0.1", "::1"}:
        print("approved reply bridge may bind only to loopback", file=sys.stderr)
        return 4
    data_root = Path(args.data_root).resolve()
    service, engine = _build_service(data_root)
    server = _Server((args.bind, args.port), _Handler)
    server.service = service
    server.feed_path = data_root / "runtime" / "real-pdd-assistant" / "assistant-feed.json"
    server.allowed_origin = args.allowed_origin
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        engine.dispose()  # type: ignore[attr-defined]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
