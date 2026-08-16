from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError

from channel_agent.assistant_bridge import (
    ApprovedReplyBridgeError,
    ApprovedReplyIntent,
    ApprovedReplyRequest,
    ApprovedReplyService,
)
from channel_agent.browser import ChannelAgentBrowserManager
from channel_agent.config import load_agent_config
from channel_agent.controlled_auto_runtime import ControlledAutoRuntimeStateStore
from channel_agent.controlled_send_grant import (
    ControlledPilotSendWindowStore,
    ControlledSendGrantStore,
)
from channel_agent.logger import SafeAgentLogger
from channel_agent.pdd_login import EdgePDDTargetResolver
from channel_agent.pdd_observer import PDDConversationNotActive
from channel_agent.pdd_readonly_driver import (
    EvidenceBackedPDDReadOnlyDriver,
    load_pdd_observer_evidence,
)
from channel_agent.pdd_workspace_send import (
    ControlledPDDWorkspaceBrowserSender,
    PDDWorkspaceOutboundSelectorContract,
    WebSocketPDDWorkspaceActionPort,
)
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
    parser.add_argument(
        "--assistant-root",
        default=None,
        help="Override the Host assistant runtime containing buffer/feed state.",
    )
    parser.add_argument(
        "--engine-database-path",
        default=None,
        help="Use the canonical Channel Engine database for Approval/Receipt facts.",
    )
    parser.add_argument(
        "--send-selector-contract",
        required=True,
        help="Verified PRODUCTION outbound selector contract JSON.",
    )
    parser.add_argument(
        "--enable-controlled-send",
        action="store_true",
        help="Explicitly enable the one-Grant approved-reply boundary.",
    )
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8430)
    parser.add_argument(
        "--allowed-origin",
        default="http://127.0.0.1:8421",
    )
    return parser


class _ActiveEvidenceBackedSnapshotProvider:
    """Expose the formal live-reader identities to the unique send boundary."""

    def __init__(self, driver: EvidenceBackedPDDReadOnlyDriver) -> None:
        self._driver = driver
        self._active_conversation_id: str | None = None

    def capture(self):
        summaries = self._driver.scan_conversations()
        ordered = sorted(
            summaries,
            key=lambda item: item.conversation_id != self._active_conversation_id,
        )
        for summary in ordered:
            try:
                snapshot = self._driver.capture_conversation(summary)
            except PDDConversationNotActive:
                continue
            self._active_conversation_id = summary.conversation_id
            # Host buffering intentionally derives the privacy-safe customer
            # reference from the formal Store + conversation identity. Use the
            # same canonical value at the send boundary; the page-local hash is
            # not the public Observation/Decision identity.
            customer_reference = "sha256:" + hashlib.sha256(
                json.dumps(
                    [snapshot.store_id, snapshot.conversation_id],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            return SimpleNamespace(
                store_id=snapshot.store_id,
                platform_store_id=snapshot.platform_store_id,
                conversation_id=snapshot.conversation_id,
                customer_reference=customer_reference,
                product=SimpleNamespace(
                    product_reference=snapshot.product.product_id,
                    product_name=snapshot.product.product_name,
                    sku_reference=snapshot.product.sku_id,
                    sku_name=snapshot.product.sku_name,
                    attributes=snapshot.product.attributes,
                ),
                visible_history=tuple(
                    SimpleNamespace(
                        external_message_id=item.external_message_id,
                        sender=item.sender.casefold(),
                        content=item.content,
                        timestamp=item.timestamp,
                    )
                    for item in snapshot.messages
                    if item.sender != "UNKNOWN"
                ),
                captured_at=snapshot.captured_at,
            )
        raise RuntimeError("the active PDD conversation cannot be identified uniquely")


def _build_service(
    data_root: Path,
    *,
    assistant_root: Path,
    engine_database_path: Path,
    send_selector_contract_path: Path,
    controlled_send_enabled: bool,
) -> tuple[ApprovedReplyService, object]:
    config = load_agent_config(data_root / "config" / "agent.json")
    if (
        not config.browser_enabled
        or not config.pdd_login_observation_enabled
        or not config.customer_assistant_enabled
        or not config.manual_approval_required
        or config.auto_reply_enabled
    ):
        raise RuntimeError("Channel Agent controlled-send safety configuration is invalid")
    enabled = controlled_send_enabled or (
        os.getenv("PDD_CONTROLLED_SEND_ENABLED", "").casefold() == "true"
    )
    manager = ChannelAgentBrowserManager(
        agent_id=config.agent_id,
        data_root=data_root,
        enabled=config.browser_enabled,
        logger=SafeAgentLogger(data_root / "logs" / "approved-reply-bridge.jsonl"),
    )
    state = manager.browser_status()
    manager.close_resources()
    if state.status.value != "READY" or state.pid is None:
        raise RuntimeError("existing Agent-owned Edge session is not READY")

    state_path = data_root / "runtime" / "channel-agent-state.json"
    state_value = json.loads(state_path.read_text(encoding="utf-8"))
    ai_cs_store_id = state_value.get("active_store_id")
    platform_store_id = state_value.get("pdd_store_id")
    if (
        not isinstance(ai_cs_store_id, str)
        or not ai_cs_store_id.strip()
        or not isinstance(platform_store_id, str)
        or not platform_store_id.strip()
    ):
        raise RuntimeError("current double Store identity is unavailable")
    evidence_path = config.pdd_observation_evidence_path
    if evidence_path is None:
        raise RuntimeError("verified PDD observation evidence is unavailable")
    if not evidence_path.is_absolute():
        evidence_path = (data_root / "config" / evidence_path).resolve()
    resolver = EdgePDDTargetResolver(timeout_seconds=1.0)
    observer = _ActiveEvidenceBackedSnapshotProvider(
        EvidenceBackedPDDReadOnlyDriver(
            profile_path=state.profile_path,
            store_id=ai_cs_store_id.strip(),
            platform_store_id=platform_store_id.strip(),
            evidence=load_pdd_observer_evidence(evidence_path),
            resolver=resolver,
        )
    )
    observer.capture()
    send_selector_contract = PDDWorkspaceOutboundSelectorContract.model_validate_json(
        send_selector_contract_path.read_text(encoding="utf-8")
    )
    database_url = f"sqlite:///{engine_database_path.as_posix()}"
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
        contract=send_selector_contract,
    )
    auto_runtime_store = ControlledAutoRuntimeStateStore(
        assistant_root / "controlled-auto-runtime.sqlite3"
    )

    def current_store_identity() -> tuple[str, str]:
        value = json.loads(state_path.read_text(encoding="utf-8"))
        ai_cs_store_id = value.get("active_store_id")
        platform_store_id = value.get("pdd_store_id")
        if (
            not isinstance(ai_cs_store_id, str)
            or not ai_cs_store_id.strip()
            or not isinstance(platform_store_id, str)
            or not platform_store_id.strip()
        ):
            raise RuntimeError("current double Store identity is unavailable")
        return ai_cs_store_id.strip(), platform_store_id.strip()

    return (
        ApprovedReplyService(
            feed_path=assistant_root / "assistant-feed.json",
            buffer=buffer,
            uow_factory=uow_factory,
            observer=observer,
            browser_sender=sender,
            controlled_send_grant_store=ControlledSendGrantStore(
                assistant_root / "controlled-send-grants.sqlite3"
            ),
            controlled_pilot_window_store=ControlledPilotSendWindowStore(
                assistant_root / "controlled-pilot-send-window.sqlite3"
            ),
            controlled_auto_runtime_store=auto_runtime_store,
            store_identity_provider=current_store_identity,
            require_double_store_identity=True,
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

    def do_GET(self) -> None:
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

    def do_POST(self) -> None:
        if self.path != "/v1/approved-replies":
            self._json(HTTPStatus.NOT_FOUND, {"error_code": "NOT_FOUND"})
            return
        if self.headers.get("Origin") != self.server.allowed_origin:
            self._json(HTTPStatus.FORBIDDEN, {"error_code": "ORIGIN_DENIED"})
            return
        raw_intent = self.headers.get("X-Channel-Agent-Intent")
        if raw_intent not in {"HUMAN_CONFIRMED_SEND", "AUTO_POLICY_PILOT_SEND"}:
            self._json(HTTPStatus.FORBIDDEN, {"error_code": "SEND_INTENT_MISSING"})
            return
        intent: ApprovedReplyIntent = raw_intent
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 1 <= length <= 65_536:
            self._json(HTTPStatus.BAD_REQUEST, {"error_code": "REQUEST_SIZE_INVALID"})
            return
        try:
            request = ApprovedReplyRequest.model_validate_json(self.rfile.read(length))
            response = self.server.service.approve_and_send(request, intent=intent)
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
    assistant_root = (
        Path(args.assistant_root).resolve()
        if args.assistant_root
        else data_root / "runtime" / "real-pdd-assistant"
    )
    engine_database_path = (
        Path(args.engine_database_path).resolve()
        if args.engine_database_path
        else assistant_root / "channel-engine.sqlite3"
    )
    service, engine = _build_service(
        data_root,
        assistant_root=assistant_root,
        engine_database_path=engine_database_path,
        send_selector_contract_path=Path(args.send_selector_contract).resolve(),
        controlled_send_enabled=args.enable_controlled_send,
    )
    server = _Server((args.bind, args.port), _Handler)
    server.service = service
    server.feed_path = assistant_root / "assistant-feed.json"
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
