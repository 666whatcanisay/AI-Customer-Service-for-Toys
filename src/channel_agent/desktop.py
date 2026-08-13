from __future__ import annotations

import json
import hmac
import mimetypes
import os
import re
import secrets
import socket
import ssl
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock, Thread
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from channel_agent.version import AGENT_VERSION
from channel_agent.binding import (
    AgentBindingStore,
    AgentRuntimeBinding,
    atomic_write_bytes,
)
from channel_agent.client import (
    AgentClientError,
    AgentConnectionError,
    AgentPairingRequiredError,
    AgentProtocolError,
    AgentRejectedError,
    ChannelEngineClient,
)
from channel_agent.config import AgentConfigError, load_agent_config
from channel_agent.contract import AgentRuntimeStatus
from channel_agent.retention import TransientBusinessDataPolicy
from channel_agent.diagnostics import ChannelAgentOperationsCenter, OperationsCenterError
from channel_agent.assistant_events import AssistantEventJournal


DESKTOP_API_VERSION = "1.0"
_MAX_REQUEST_BYTES = 64 * 1024
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
_BINDING_CODE = re.compile(r"^[A-F0-9]{32}$")
_BOOTSTRAP_HANDOFF_MAX_AGE_SECONDS = 120.0
_BOOTSTRAP_NONCE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")


class DesktopAssistantError(RuntimeError):
    pass


class DesktopAssistantServer:
    """Loopback-only UI host and narrow local Agent API.

    Browser credentials never cross this boundary. Platform traffic can only be
    proxied to one validated, configured AI-CS origin. There is no generic
    browser-action endpoint and controlled sending requires an injected handler.
    """

    def __init__(
        self,
        *,
        data_root: str | Path,
        static_root: str | Path | None = None,
        bind: str = "127.0.0.1",
        port: int = 0,
        platform_origin: str | None = None,
        approved_reply_handler: Callable[[dict[str, Any]], tuple[int, dict[str, Any]]]
        | None = None,
        active_store_handler: Callable[[str, str], dict[str, Any]] | None = None,
        pdd_workspace_launch_handler: Callable[[], dict[str, Any]] | None = None,
        pdd_workspace_status_handler: Callable[[], dict[str, Any]] | None = None,
        pdd_workspace_close_handler: Callable[[], None] | None = None,
        platform_proxy_mode: str = "DIRECT_API",
        platform_ca_certificate: str | Path | None = None,
        config_path: str | Path | None = None,
        operations_center: ChannelAgentOperationsCenter | None = None,
        event_journal: AssistantEventJournal | None = None,
    ) -> None:
        if bind not in {"127.0.0.1", "::1"}:
            raise DesktopAssistantError("desktop assistant must bind to loopback")
        self.data_root = Path(data_root).resolve()
        self.static_root = Path(static_root).resolve() if static_root else None
        self.bind = bind
        self.port = port
        self.platform_origin = self._validate_platform_origin(platform_origin)
        self.approved_reply_handler = approved_reply_handler
        self.active_store_handler = active_store_handler
        self.pdd_workspace_launch_handler = pdd_workspace_launch_handler
        self.pdd_workspace_status_handler = pdd_workspace_status_handler
        self.pdd_workspace_close_handler = pdd_workspace_close_handler
        self._manual_pdd_launch_state: dict[str, Any] | None = None
        self._manual_pdd_launch_requested = False
        self._manual_pdd_refresh_in_flight = False
        if platform_proxy_mode not in {"DIRECT_API", "SAME_ORIGIN_GATEWAY"}:
            raise DesktopAssistantError("unsupported platform proxy mode")
        self.platform_proxy_mode = platform_proxy_mode
        self.config_path = (
            Path(config_path).resolve()
            if config_path is not None
            else self.data_root / "config" / "agent.json"
        )
        self.operations = operations_center or ChannelAgentOperationsCenter(
            data_root=self.data_root,
            config_path=self.config_path,
        )
        self.event_journal = event_journal or AssistantEventJournal(
            self.data_root / "runtime" / "assistant-events.sqlite3"
        )
        context = ssl.create_default_context(
            cafile=(str(platform_ca_certificate) if platform_ca_certificate else None)
        )
        self._platform_opener = build_opener(
            ProxyHandler({}), HTTPSHandler(context=context)
        )
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None
        self._lock = RLock()
        self._bootstrap_nonces: dict[str, float] = {}
        self._handoff_bootstrap_nonce: str | None = None
        self._current_bootstrap_nonce = self._issue_bootstrap_locked()
        self._load_bootstrap_handoff_locked()
        self._launcher_capability = secrets.token_urlsafe(32)
        self._local_session = secrets.token_urlsafe(32)
        self._csrf_token = secrets.token_urlsafe(32)

    @property
    def running(self) -> bool:
        with self._lock:
            return self._server is not None

    @property
    def origin(self) -> str | None:
        with self._lock:
            if self._server is None:
                return None
            host, port = self._server.server_address[:2]
            display_host = "127.0.0.1" if host in {"0.0.0.0", "::1"} else host
            return f"http://{display_host}:{port}"

    @property
    def workspace_url(self) -> str | None:
        origin = self.origin
        if origin is None:
            return None
        return (
            f"{origin}/workspace?channel-agent-desktop=1"
            f"&bootstrap={self._current_bootstrap_nonce}"
        )

    def issue_workspace_url(self, launcher_capability: str | None) -> str:
        """Issue a fresh, short-lived bootstrap URL to the installed launcher.

        The assistant window uses a session cookie which intentionally disappears
        when Edge closes.  Reusing the original one-time URL would therefore load
        the UI without access to the local Agent API.  The launcher proves it is
        the installed local process with a process-lifetime capability and gets a
        new one-time URL for every reopen.
        """

        if launcher_capability is None or not hmac.compare_digest(
            launcher_capability, self._launcher_capability
        ):
            raise DesktopAssistantError("launcher capability is invalid")
        with self._lock:
            self._current_bootstrap_nonce = self._issue_bootstrap_locked()
            workspace_url = self.workspace_url
            if workspace_url is None:
                raise DesktopAssistantError("desktop assistant is not running")
            self._write_runtime_state()
            return workspace_url

    def consume_bootstrap(self, value: str | None) -> bool:
        if value is None:
            return False
        with self._lock:
            self._prune_bootstrap_nonces_locked()
            for nonce in tuple(self._bootstrap_nonces):
                if hmac.compare_digest(value, nonce):
                    self._bootstrap_nonces.pop(nonce, None)
                    if self._handoff_bootstrap_nonce is not None and hmac.compare_digest(
                        value, self._handoff_bootstrap_nonce
                    ):
                        self._handoff_bootstrap_nonce = None
                        self._record_bootstrap_handoff_consumed_locked()
                    return True
            return False

    def prepare_reload_handoff(self) -> None:
        """Let the already-open local workspace re-authenticate exactly once.

        Only an explicit browser-preserving reload calls this method. The file
        contains the nonce that is already present in the loopback workspace
        URL, never a Cookie or CSRF token, and the next Runtime consumes it.
        """

        with self._lock:
            payload = {
                "schema_version": "channel-agent-desktop-bootstrap-handoff.v1",
                "bootstrap_nonce": self._current_bootstrap_nonce,
                "issued_at": datetime.now(UTC).isoformat(),
            }
            path = self._bootstrap_handoff_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._bootstrap_handoff_consumed_path().unlink(missing_ok=True)
            atomic_write_bytes(
                path,
                (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"),
            )

    def _load_bootstrap_handoff_locked(self) -> None:
        path = self._bootstrap_handoff_path()
        try:
            raw = path.read_bytes()
            if len(raw) > 4096:
                return
            payload = json.loads(raw.decode("utf-8"))
            nonce = payload.get("bootstrap_nonce")
            issued_at = datetime.fromisoformat(str(payload.get("issued_at", "")))
            if issued_at.tzinfo is None:
                return
            age = (datetime.now(UTC) - issued_at.astimezone(UTC)).total_seconds()
            if (
                not isinstance(nonce, str)
                or _BOOTSTRAP_NONCE.fullmatch(nonce) is None
                or age < 0
                or age > _BOOTSTRAP_HANDOFF_MAX_AGE_SECONDS
            ):
                return
            remaining = max(1.0, _BOOTSTRAP_HANDOFF_MAX_AGE_SECONDS - age)
            self._bootstrap_nonces[nonce] = time.monotonic() + remaining
            self._handoff_bootstrap_nonce = nonce
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
            return
        finally:
            path.unlink(missing_ok=True)

    def _record_bootstrap_handoff_consumed_locked(self) -> None:
        """Signal that the preserved assistant window recovered successfully.

        The installed tray uses this non-secret marker to avoid opening a
        duplicate window. If no preserved window consumes the handoff before
        the bounded tray deadline, the tray still opens a fresh window.
        """

        path = self._bootstrap_handoff_consumed_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "channel-agent-desktop-bootstrap-consumed.v1",
            "consumed_at": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
        }
        atomic_write_bytes(
            path,
            (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"),
        )

    def _issue_bootstrap_locked(self) -> str:
        self._prune_bootstrap_nonces_locked()
        nonce = secrets.token_urlsafe(32)
        self._bootstrap_nonces[nonce] = time.monotonic() + 60.0
        while len(self._bootstrap_nonces) > 8:
            oldest = next(iter(self._bootstrap_nonces))
            self._bootstrap_nonces.pop(oldest, None)
        return nonce

    def _prune_bootstrap_nonces_locked(self) -> None:
        now = time.monotonic()
        for nonce, expires_at in tuple(self._bootstrap_nonces.items()):
            if expires_at <= now:
                self._bootstrap_nonces.pop(nonce, None)

    def valid_local_session(self, cookie_header: str | None) -> bool:
        if not cookie_header:
            return False
        cookies = {}
        for item in cookie_header.split(";"):
            key, separator, value = item.strip().partition("=")
            if separator:
                cookies[key] = value
        candidate = cookies.get("channel_agent_session", "")
        return hmac.compare_digest(candidate, self._local_session)

    def valid_csrf(self, value: str | None) -> bool:
        return bool(value) and hmac.compare_digest(value, self._csrf_token)

    @property
    def local_session_cookie(self) -> str:
        return (
            f"channel_agent_session={self._local_session}; Path=/; HttpOnly; "
            "SameSite=Strict"
        )

    def start(self) -> str:
        with self._lock:
            if self._server is not None:
                assert self.workspace_url is not None
                return self.workspace_url
            server = _DesktopHTTPServer((self.bind, self.port), _DesktopHandler)
            server.runtime = self
            thread = Thread(
                target=server.serve_forever,
                name="channel-agent-desktop-ui",
                daemon=True,
            )
            self._server = server
            self._thread = thread
            thread.start()
            assert self.workspace_url is not None
            self._write_runtime_state()
            return self.workspace_url

    def stop(self) -> None:
        with self._lock:
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=3)
        if self.pdd_workspace_close_handler is not None:
            self.pdd_workspace_close_handler()
        self._runtime_path().unlink(missing_ok=True)

    def bootstrap(self) -> dict[str, Any]:
        state = self._read_json(
            self.data_root / "runtime" / "channel-agent-state.json"
        )
        secure_control_ready = False
        config = None
        try:
            config = load_agent_config(self.config_path)
            secure_control_ready = config.device_credential_reference is not None
        except AgentConfigError:
            # Bootstrap stays available for recovery even when configuration is
            # incomplete.  Only the non-sensitive readiness fact is exposed.
            pass
        real_pdd_message_observation_enabled = bool(
            config is not None
            and config.development_profile == "STANDARD"
            and config.browser_enabled
            and config.pdd_login_observation_enabled
            and config.message_observation_enabled
        )
        message_source = (
            "REAL_PDD"
            if real_pdd_message_observation_enabled
            else (
                "OFFLINE_REPLAY"
                if config is not None
                and config.development_profile == "OFFLINE_REPLAY"
                else "DISABLED"
            )
        )
        browser_status = state.get("browser_status", "STOPPED")
        pdd_login_state = state.get("pdd_login_state")
        with self._lock:
            launch_requested = self._manual_pdd_launch_requested
            manual_launch_state = self._manual_pdd_launch_state
        if launch_requested and self.pdd_workspace_status_handler is not None:
            try:
                manual_launch_state = self.pdd_workspace_status_handler()
                with self._lock:
                    self._manual_pdd_launch_state = manual_launch_state
            except Exception:
                # A status refresh must not turn the whole local assistant into
                # an error page. The last safe launch state remains visible.
                pass
        if manual_launch_state is not None:
            browser_status = manual_launch_state.get("browser_status", browser_status)
            pdd_login_state = manual_launch_state.get(
                "pdd_login_state", pdd_login_state
            )
        return {
            "schema_version": DESKTOP_API_VERSION,
            "csrf_token": self._csrf_token,
            # A newly opened workspace starts after this cursor.  This keeps
            # historical MESSAGE_ACCEPTED journal entries available for resume
            # while preventing old entries from being announced as new popups.
            "assistant_event_cursor": self.event_journal.last_sequence_id(),
            "agent": {
                "process_status": state.get("process_status", "STARTING"),
                "runtime_status": state.get("runtime_status", "CONNECTING"),
                "version": AGENT_VERSION,
                "node_id": state.get("agent_id"),
            },
            "browser": {
                "status": browser_status,
                "pdd_login_state": pdd_login_state,
                "pdd_workspace_launch_available": (
                    self.pdd_workspace_launch_handler is not None
                ),
                "pdd_workspace_refresh_available": (
                    self.pdd_workspace_status_handler is not None
                ),
                "observer_status": state.get("observer_status", "DISABLED"),
                "observer_restart_available": bool(
                    state.get("message_observation_enabled", False)
                ),
                "message_source": message_source,
                "real_pdd_message_observation_enabled": (
                    real_pdd_message_observation_enabled
                ),
            },
            "binding": {
                "agent_id": state.get("agent_id"),
                "device_id": state.get("device_id"),
                "identity_status": state.get("identity_status", "UNBOUND"),
                "production_eligible": bool(state.get("production_eligible", False)),
                "authorized_store_ids": state.get("authorized_store_ids", []),
                "active_store_id": state.get("active_store_id"),
                "observed_store_id": state.get("pdd_store_id"),
                "store_reference": state.get("active_store_id")
                or state.get("store_id")
                or state.get("pdd_store_reference"),
                "secure_control_ready": secure_control_ready,
            },
            "assistant": self._read_json(
                self.data_root / "runtime" / "real-pdd-assistant" / "status.json"
            ),
            "safety": {
                "manual_approval": True,
                "auto_reply": False,
                "real_send_enabled": False,
                "real_platform_activation_allowed": False,
            },
        }

    def launch_pdd_workspace(self) -> tuple[int, dict[str, Any]]:
        """Open the dedicated PDD Edge profile after an explicit local click.

        This narrow capability only opens or reuses the dedicated browser and
        navigates to the official login/workspace URL.  It does not enable the
        observer, perform login, read customer messages, or send anything.
        """

        if self.pdd_workspace_launch_handler is None:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": {
                    "code": "PDD_WORKSPACE_LAUNCH_NOT_AVAILABLE",
                    "message": "当前 Agent 未提供 PDD 专属窗口启动能力。",
                }
            }
        try:
            result = self.pdd_workspace_launch_handler()
        except Exception:
            return HTTPStatus.CONFLICT, {
                "error": {
                    "code": "PDD_WORKSPACE_LAUNCH_FAILED",
                    "message": "PDD 专属窗口暂时无法启动，请检查 Edge 后重试。",
                }
            }
        safe_result = {
            "schema_version": "channel-agent-pdd-window-launch.v1",
            "status": str(result.get("status", "OPENING")),
            "browser_status": str(result.get("browser_status", "OPENED")),
            "pdd_login_state": result.get("pdd_login_state"),
            "human_login_required": True,
            "observer_started": False,
            "real_send_enabled": False,
        }
        with self._lock:
            self._manual_pdd_launch_state = safe_result
            self._manual_pdd_launch_requested = True
        return HTTPStatus.ACCEPTED, safe_result

    def refresh_pdd_workspace(self) -> tuple[int, dict[str, Any]]:
        """Re-inspect the already open dedicated PDD page without navigation."""

        if self.pdd_workspace_status_handler is None:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": {"code": "PDD_WORKSPACE_REFRESH_NOT_AVAILABLE"}
            }
        with self._lock:
            if self._manual_pdd_refresh_in_flight:
                current = self._manual_pdd_launch_state or {}
                return HTTPStatus.ACCEPTED, {
                    "schema_version": "channel-agent-pdd-workspace-refresh.v1",
                    "status": "REFRESHING",
                    "browser_status": str(current.get("browser_status", "OPENED")),
                    "pdd_login_state": current.get("pdd_login_state"),
                    "observer_started": False,
                    "real_send_enabled": False,
                }
            self._manual_pdd_refresh_in_flight = True
        try:
            result = self.pdd_workspace_status_handler()
            safe_result = {
                "schema_version": "channel-agent-pdd-workspace-refresh.v1",
                "status": str(result.get("status", "OPENING")),
                "browser_status": str(result.get("browser_status", "OPENED")),
                "pdd_login_state": result.get("pdd_login_state"),
                "observer_started": False,
                "real_send_enabled": False,
            }
            with self._lock:
                self._manual_pdd_launch_state = safe_result
                self._manual_pdd_launch_requested = True
            return HTTPStatus.OK, safe_result
        except Exception:
            return HTTPStatus.CONFLICT, {
                "error": {"code": "PDD_WORKSPACE_REFRESH_FAILED"}
            }
        finally:
            with self._lock:
                self._manual_pdd_refresh_in_flight = False

    def request_pdd_observer_restart(self) -> tuple[int, dict[str, Any]]:
        """Queue one explicit restart; never changes read/send configuration."""

        state = self._read_json(
            self.data_root / "runtime" / "channel-agent-state.json"
        )
        if not state.get("message_observation_enabled", False):
            return HTTPStatus.CONFLICT, {
                "error": {"code": "PDD_OBSERVER_NOT_ENABLED"}
            }
        if state.get("pdd_login_state") != "CUSTOMER_SERVICE_READY":
            return HTTPStatus.CONFLICT, {
                "error": {"code": "PDD_WORKSPACE_NOT_READY"}
            }
        if state.get("identity_status") != "ACTIVE":
            return HTTPStatus.CONFLICT, {
                "error": {"code": "AGENT_IDENTITY_NOT_ACTIVE"}
            }
        path = self.data_root / "runtime" / "pdd-observer-restart.request"
        with self._lock:
            if path.exists():
                return HTTPStatus.ACCEPTED, {
                    "status": "ALREADY_REQUESTED",
                    "real_send_enabled": False,
                }
            atomic_write_bytes(
                path,
                (json.dumps({
                    "schema_version": "channel-agent-pdd-observer-restart-request.v1",
                    "requested_at": datetime.now(UTC).isoformat(),
                    "human_intent": True,
                }, separators=(",", ":")) + "\n").encode("utf-8"),
            )
        return HTTPStatus.ACCEPTED, {
            "status": "RESTART_REQUESTED",
            "real_send_enabled": False,
        }

    def assistant_feed(self) -> dict[str, Any]:
        TransientBusinessDataPolicy().purge_expired(self.data_root)
        snapshots_reader = getattr(self.event_journal, "assistant_snapshots", None)
        snapshots = snapshots_reader() if callable(snapshots_reader) else ()
        if snapshots:
            return self._with_read_state(self._snapshots_feed(
                tuple(item.model_dump(mode="json") for item in snapshots)
            ))
        snapshot = self.event_journal.assistant_snapshot()
        if snapshot is not None:
            return self._with_read_state(
                self._snapshot_feed(snapshot.model_dump(mode="json"))
            )
        value = self._read_json(
            self.data_root
            / "runtime"
            / "real-pdd-assistant"
            / "assistant-feed.json"
        )
        if value:
            return value
        return {
            # Keep the empty runtime feed on the exact same contract as the
            # real PDD observer and the synthetic adapter.  The desktop UI
            # intentionally validates every safety fact before it will render
            # a conversation, so a legacy/partial empty feed must not be used
            # as a harmless fallback.
            "schemaVersion": "channel-agent-workspace-feed.v1",
            "source": "CHANNEL_AGENT_DESKTOP",
            "generatedAt": None,
            "conversations": [],
            "reply": None,
            "safety": {
                "readOnly": True,
                "autoReply": False,
                "realSend": False,
                "browserWriteOperations": 0,
                "executionCount": 0,
                "receiptCount": 0,
                "sendCount": 0,
            },
        }

    def _with_read_state(self, feed: dict[str, Any]) -> dict[str, Any]:
        read_revision = getattr(self.event_journal, "read_revision", None)
        if not callable(read_revision):
            return feed
        for conversation in feed.get("conversations", []):
            if not isinstance(conversation, dict):
                continue
            conversation_id = conversation.get("conversationId")
            revision = conversation.pop("_revision", 1)
            if isinstance(conversation_id, str) and isinstance(revision, int):
                conversation["unreadCount"] = int(
                    revision > read_revision(conversation_id)
                )
                conversation["readRevision"] = read_revision(conversation_id)
                conversation["revision"] = revision
        return feed

    def mark_conversation_read(self, conversation_id: str) -> dict[str, Any]:
        snapshots_reader = getattr(self.event_journal, "assistant_snapshots", None)
        snapshots = snapshots_reader() if callable(snapshots_reader) else ()
        snapshot = next(
            (item for item in snapshots if item.conversation_id == conversation_id),
            None,
        )
        if snapshot is None:
            single = self.event_journal.assistant_snapshot()
            if single is not None and single.conversation_id == conversation_id:
                snapshot = single
        if snapshot is None:
            raise DesktopAssistantError("assistant conversation does not exist")
        marker = getattr(self.event_journal, "mark_conversation_read", None)
        if not callable(marker):
            raise DesktopAssistantError("assistant read cursor is unavailable")
        revision = marker(conversation_id, snapshot.revision)
        return {
            "schema_version": DESKTOP_API_VERSION,
            "conversation_id": conversation_id,
            "read_revision": revision,
        }

    @staticmethod
    def _snapshot_feed(snapshot: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(snapshot["conversation_id"])
        decision_id = str(snapshot["decision_id"])
        customer_reference = str(snapshot["customer_reference"])
        customer_label = f"客户 {customer_reference[-12:]}"
        updated_at = str(snapshot["updated_at"])
        citations = []
        citation_keys: set[tuple[str, str, str, str]] = set()
        for item in snapshot.get("citations", [])[:32]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("reference") or "Knowledge")[:256]
            summary = str(item.get("excerpt") or title)[:512]
            product_id = str(item.get("product_id") or "")
            sku_id = str(item.get("sku_id") or "")
            key = (title, summary, product_id, sku_id)
            if key in citation_keys:
                continue
            citation_keys.add(key)
            citations.append(
                {
                    "file": str(item.get("title") or item.get("reference") or "知识来源"),
                    "page": None,
                    "chunkId": str(item.get("reference") or "")[:512] or None,
                    "summary": summary,
                    "distance": None,
                    "knowledgeVersion": None,
                    "sourceIds": [],
                    "productId": product_id or None,
                    "skuId": sku_id or None,
                }
            )
        raw_product = snapshot.get("product_context")
        product_context = None
        if isinstance(raw_product, dict):
            attributes = raw_product.get("attributes")
            product_context = {
                "productReference": raw_product.get("product_reference"),
                "productName": raw_product.get("product_name"),
                "skuReference": raw_product.get("sku_reference"),
                "skuName": raw_product.get("sku_name"),
                "applicableAge": (
                    attributes.get("applicable_age")
                    if isinstance(attributes, dict)
                    else None
                ),
            }
        reply_content = snapshot.get("reply_content")
        reply = None
        if isinstance(reply_content, str) and reply_content:
            reply = {
                "conversationId": conversation_id,
                "customerReference": customer_reference,
                "messageId": str(snapshot["turn_id"]),
                "decisionId": decision_id,
                "answer": reply_content,
                "requestId": snapshot.get("request_id"),
                "action": "CONTROLLED_ANSWER",
                "riskLevel": snapshot["risk_level"],
                "citations": citations,
                "warnings": ["发送前必须人工核对店铺、会话、客户与回复内容"],
                "requiredFields": list(snapshot.get("required_fields") or []),
                "state": snapshot.get("status"),
                "qualityStatus": snapshot.get("quality_status"),
                "policyMode": snapshot.get("policy_mode"),
                "preparationId": snapshot.get("preparation_id"),
                "traceId": snapshot.get("trace_id"),
                "productContext": product_context,
            }
        return {
            "schemaVersion": "channel-agent-workspace-feed.v2",
            "source": "CHANNEL_AGENT_HOST_SNAPSHOT",
            "generatedAt": updated_at,
            "conversations": [
                {
                    "conversationId": conversation_id,
                    "customerLabel": customer_label,
                    "customerReference": customer_reference,
                    "unreadCount": 1,
                    "_revision": int(snapshot.get("revision") or 1),
                    "source": "CHANNEL_AGENT",
                    "state": snapshot.get("status"),
                    "processingStage": snapshot.get("processing_stage"),
                    "riskLevel": snapshot.get("risk_level"),
                    "qualityStatus": snapshot.get("quality_status"),
                    "policyMode": snapshot.get("policy_mode"),
                    "preparationId": snapshot.get("preparation_id"),
                    "traceId": snapshot.get("trace_id"),
                    "productContext": product_context,
                    "messages": [
                        {
                            "messageId": str(snapshot["turn_id"]),
                            "conversationId": conversation_id,
                            "customerLabel": customer_label,
                            "content": snapshot["current_question"],
                            "receivedAt": updated_at,
                            "source": "CHANNEL_AGENT",
                            "senderRole": "CUSTOMER",
                        }
                    ],
                }
            ],
            "reply": reply,
            "productContext": product_context,
            "safety": {
                "readOnly": True,
                "autoReply": bool(snapshot.get("safety", {}).get("auto_reply")),
                "realSend": False,
                "browserWriteOperations": 0,
                "executionCount": 0,
                "receiptCount": 0,
                "sendCount": 0,
                "executionPrepared": bool(
                    snapshot.get("safety", {}).get("execution_prepared")
                ),
            },
        }

    @classmethod
    def _snapshots_feed(
        cls, snapshots: tuple[dict[str, Any], ...]
    ) -> dict[str, Any]:
        projected = [cls._snapshot_feed(item) for item in snapshots[:100]]
        conversations: list[dict[str, Any]] = []
        replies: dict[str, dict[str, Any]] = {}
        for feed in projected:
            for conversation in feed.get("conversations", []):
                if isinstance(conversation, dict):
                    reply = feed.get("reply")
                    if isinstance(reply, dict):
                        conversation = {**conversation, "reply": reply}
                        replies[str(conversation.get("conversationId"))] = reply
                    conversations.append(conversation)
        latest = projected[0] if projected else {}
        return {
            "schemaVersion": "channel-agent-workspace-feed.v2",
            "source": "CHANNEL_AGENT_HOST_CONVERSATIONS",
            "generatedAt": latest.get("generatedAt"),
            "conversations": conversations,
            "reply": latest.get("reply"),
            "replies": replies,
            "safety": {
                "readOnly": True,
                "autoReply": any(
                    bool(item.get("safety", {}).get("auto_reply"))
                    for item in snapshots
                ),
                "realSend": False,
                "browserWriteOperations": 0,
                "executionCount": 0,
                "receiptCount": 0,
                "sendCount": 0,
                "executionPrepared": any(
                    bool(item.get("safety", {}).get("execution_prepared"))
                    for item in snapshots
                ),
            },
        }

    def request_safe_stop(self) -> None:
        path = self.data_root / "runtime" / "stop.request"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stop\n", encoding="ascii")

    def doctor(self, *, deep: bool = False) -> dict[str, Any]:
        return self.operations.doctor(deep=deep)

    def configuration(self) -> dict[str, Any]:
        return self.operations.config_view()

    def validate_configuration(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.operations.validate_changes(payload, probe=True)

    def save_configuration(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.operations.save_changes(payload)
        if result.get("saved"):
            try:
                from channel_agent.config import load_agent_config

                config = load_agent_config(self.config_path)
                with self._lock:
                    self.platform_origin = self._validate_platform_origin(
                        config.ai_cs_platform_url
                    )
            except Exception:
                # The saved candidate was already validated. A reload marker is
                # present for changes that need a new Runtime instance.
                pass
        return result

    def approve_reply(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.approved_reply_handler is None:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": {
                    "code": "CONTROLLED_SEND_NOT_AVAILABLE",
                    "message": "受控发送尚未启用，请勿绕过人工确认链。",
                }
            }
        return self.approved_reply_handler(payload)

    def select_active_store(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        target = payload.get("store_reference")
        reason = payload.get("reason", "客服在桌面助手中人工切换工作店铺")
        if not isinstance(target, str) or not target.strip() or len(target) > 160:
            return HTTPStatus.BAD_REQUEST, {
                "error": {"code": "ACTIVE_STORE_REQUEST_INVALID"}
            }
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 512:
            return HTTPStatus.BAD_REQUEST, {
                "error": {"code": "ACTIVE_STORE_REQUEST_INVALID"}
            }
        blockers = self._active_store_switch_blockers()
        if blockers:
            return HTTPStatus.CONFLICT, {
                "error": {
                    "code": "ACTIVE_STORE_SWITCH_BLOCKED",
                    "blockers": blockers,
                }
            }
        if self.active_store_handler is None:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": {"code": "ACTIVE_STORE_SELECTION_NOT_AVAILABLE"}
            }
        try:
            return HTTPStatus.OK, self.active_store_handler(target.strip(), reason.strip())
        except Exception:
            return HTTPStatus.CONFLICT, {
                "error": {"code": "ACTIVE_STORE_SELECTION_REJECTED"}
            }

    def enroll_identity(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        raw_code = payload.get("binding_code")
        normalized = raw_code.strip().upper() if isinstance(raw_code, str) else ""
        if not _BINDING_CODE.fullmatch(normalized):
            return HTTPStatus.UNPROCESSABLE_ENTITY, {
                "error": {
                    "code": "BINDING_CODE_INVALID",
                    "message": "绑定许可格式无效，请重新申请。",
                }
            }
        try:
            config = load_agent_config(self.config_path)
        except AgentConfigError:
            return HTTPStatus.CONFLICT, {
                "error": {
                    "code": "AGENT_CONFIGURATION_INVALID",
                    "message": "客户端配置无效，请先修复运行配置。",
                }
            }
        client = ChannelEngineClient(config)
        try:
            client.register(
                hostname=socket.gethostname().strip() or "unknown-host",
                status=AgentRuntimeStatus.STARTING,
                timestamp=datetime.now(UTC),
            )
            response = client.enroll(normalized)
            self._persist_binding(response.binding)
            return HTTPStatus.OK, self._public_binding(response.binding)
        except AgentPairingRequiredError:
            return HTTPStatus.PRECONDITION_REQUIRED, {
                "error": {
                    "code": "DEVICE_PAIRING_REQUIRED",
                    "message": (
                        "这台电脑尚未与 V2 主机建立安全连接。请先使用主机显示的"
                        "12 位一次性连接码完成人工配对。"
                    ),
                }
            }
        except AgentConnectionError:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": {
                    "code": "CHANNEL_ENGINE_UNAVAILABLE",
                    "message": "暂时无法连接设备服务，请检查服务器后重试。",
                }
            }
        except AgentRejectedError as exc:
            return HTTPStatus.CONFLICT, {
                "error": {
                    "code": exc.error_code or "BINDING_CODE_REJECTED",
                    "message": "绑定许可已失效、已使用或与本机不匹配，请重新申请。",
                }
            }
        except (AgentProtocolError, AgentClientError, ValueError):
            return HTTPStatus.BAD_GATEWAY, {
                "error": {
                    "code": "BINDING_RESPONSE_INVALID",
                    "message": "设备服务返回异常，请重新检测后再试。",
                }
            }
        finally:
            client.close()

    def sync_identity(self) -> tuple[int, dict[str, Any]]:
        try:
            config = load_agent_config(self.config_path)
        except AgentConfigError:
            return HTTPStatus.CONFLICT, {
                "error": {"code": "AGENT_CONFIGURATION_INVALID", "message": "客户端配置无效。"}
            }
        client = ChannelEngineClient(config)
        try:
            client.register(
                hostname=socket.gethostname().strip() or "unknown-host",
                status=AgentRuntimeStatus.STARTING,
                timestamp=datetime.now(UTC),
            )
            identity = client.identity
            if identity is None:
                return HTTPStatus.CONFLICT, {
                    "error": {"code": "IDENTITY_NOT_AVAILABLE", "message": "设备身份尚未建立。"}
                }
            binding = AgentRuntimeBinding.from_identity(identity)
            self._persist_binding(binding)
            return HTTPStatus.OK, self._public_binding(binding)
        except AgentPairingRequiredError:
            return HTTPStatus.PRECONDITION_REQUIRED, {
                "error": {
                    "code": "DEVICE_PAIRING_REQUIRED",
                    "message": (
                        "这台电脑尚未与 V2 主机建立安全连接。请先使用主机显示的"
                        "12 位一次性连接码完成人工配对。"
                    ),
                }
            }
        except AgentConnectionError:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": {"code": "CHANNEL_ENGINE_UNAVAILABLE", "message": "暂时无法同步设备状态。"}
            }
        except AgentRejectedError as exc:
            return HTTPStatus.CONFLICT, {
                "error": {"code": exc.error_code or "IDENTITY_SYNC_REJECTED", "message": "设备身份同步被拒绝。"}
            }
        except (AgentProtocolError, AgentClientError, ValueError):
            return HTTPStatus.BAD_GATEWAY, {
                "error": {"code": "IDENTITY_SYNC_INVALID", "message": "设备身份状态异常。"}
            }
        finally:
            client.close()

    def _persist_binding(self, binding: AgentRuntimeBinding) -> None:
        AgentBindingStore(self.data_root / "runtime" / "agent-binding.json").save(binding)
        state_path = self.data_root / "runtime" / "channel-agent-state.json"
        state = self._read_json(state_path)
        state.update({
            "identity_status": binding.identity_status.value,
            "production_eligible": binding.production_eligible,
            "agent_id": binding.agent_id,
            "device_id": binding.device_id,
            "user_id": binding.user_id,
            "store_id": binding.store_ids[0] if binding.store_ids else None,
            "store_ids": list(binding.store_ids),
            "authorized_store_ids": list(binding.authorized_store_ids),
            "active_store_id": binding.active_store_id,
            "binding_revision": binding.binding_revision,
            "updated_at": datetime.now(UTC).isoformat(),
        })
        state_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            atomic_write_bytes(
                state_path,
                (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode(
                    "utf-8"
                ),
            )
        except OSError:
            # The binding file above is the authoritative local identity.  A
            # concurrently-read status snapshot must not turn a successful
            # remote enrollment into a failed enrollment response.  Startup
            # and the next heartbeat rebuild channel-agent-state.json from the
            # newest primary/pending binding revision.
            pass

    @staticmethod
    def _public_binding(binding: AgentRuntimeBinding) -> dict[str, Any]:
        return {
            "schema_version": "channel-agent-local-enrollment.v1",
            "agent_id": binding.agent_id,
            "device_id": binding.device_id,
            "identity_status": binding.identity_status.value,
            "authorized_store_ids": list(binding.authorized_store_ids),
            "active_store_id": binding.active_store_id,
            "binding_revision": binding.binding_revision,
            "production_eligible": binding.production_eligible,
        }

    def _active_store_switch_blockers(self) -> list[str]:
        feed = self.assistant_feed()
        blockers: list[str] = []
        reply = feed.get("reply")
        if isinstance(reply, dict) and reply.get("state") in {
            "WAITING_APPROVAL",
            "APPROVED",
            "EXECUTING",
            "UNKNOWN",
        }:
            blockers.append("ACTIVE_REPLY_WORKFLOW")
        for conversation in feed.get("conversations", []):
            if not isinstance(conversation, dict):
                continue
            state = conversation.get("state") or conversation.get("status")
            if state in {"PROCESSING", "WAITING_APPROVAL", "APPROVED", "EXECUTING", "UNKNOWN"}:
                blockers.append("ACTIVE_CONVERSATION_WORKFLOW")
                break
        return sorted(set(blockers))

    def proxy_platform(
        self,
        *,
        method: str,
        request_path: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes, str]:
        if self.platform_origin is None:
            payload = json.dumps(
                {"detail": "AI-CS platform endpoint is not configured"},
                ensure_ascii=False,
            ).encode("utf-8")
            return HTTPStatus.SERVICE_UNAVAILABLE, payload, "application/json; charset=utf-8"
        parsed = urlsplit(request_path)
        upstream_path = (
            parsed.path
            if self.platform_proxy_mode == "SAME_ORIGIN_GATEWAY"
            else (parsed.path.removeprefix("/platform-api") or "/")
        )
        target = f"{self.platform_origin}{upstream_path}"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        forwarded = {
            key: value
            for key, value in headers.items()
            if key.casefold()
            in {
                "accept",
                "authorization",
                "content-type",
                "idempotency-key",
                "x-request-id",
            }
        }
        request = Request(target, data=body, headers=forwarded, method=method)
        try:
            with self._platform_opener.open(request, timeout=15) as response:  # noqa: S310 - validated origin
                payload = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(payload) > _MAX_RESPONSE_BYTES:
                    raise DesktopAssistantError("platform response exceeds limit")
                return (
                    response.status,
                    payload,
                    response.headers.get("Content-Type", "application/json; charset=utf-8"),
                )
        except HTTPError as exc:
            payload = exc.read(_MAX_RESPONSE_BYTES + 1)[:_MAX_RESPONSE_BYTES]
            return (
                exc.code,
                payload,
                exc.headers.get("Content-Type", "application/json; charset=utf-8"),
            )
        except (URLError, TimeoutError, OSError):
            payload = json.dumps(
                {"detail": "AI-CS platform is unavailable"}, ensure_ascii=False
            ).encode("utf-8")
            return HTTPStatus.BAD_GATEWAY, payload, "application/json; charset=utf-8"

    def static_file(self, request_path: str) -> tuple[bytes, str] | None:
        decoded = unquote(urlsplit(request_path).path)
        if decoded == "/channel-agent-assistant-events.js":
            return self._assistant_event_script(), "application/javascript; charset=utf-8"
        if decoded == "/channel-agent-avatar.png":
            candidates: list[Path] = []
            if self.static_root is not None:
                candidates.append(self.static_root / "channel-agent-avatar.png")
            agent_home = os.environ.get("AI_CS_CHANNEL_AGENT_HOME")
            if agent_home:
                candidates.append(
                    Path(agent_home)
                    / "assets"
                    / "branding"
                    / "channel-agent-avatar.png"
                )
            for candidate in candidates:
                try:
                    if candidate.is_file():
                        return candidate.read_bytes(), "image/png"
                except OSError:
                    continue
            return None
        if self.static_root is None or not self.static_root.is_dir():
            return self._inject_assistant_event_client(self._fallback_html()), "text/html; charset=utf-8"
        relative = decoded.lstrip("/") or "index.html"
        candidate = (self.static_root / relative).resolve()
        try:
            candidate.relative_to(self.static_root)
        except ValueError:
            return None
        if not candidate.is_file():
            candidate = self.static_root / "index.html"
        if not candidate.is_file():
            return self._inject_assistant_event_client(self._fallback_html()), "text/html; charset=utf-8"
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
        }:
            content_type += "; charset=utf-8"
        body = candidate.read_bytes()
        if content_type.startswith("text/html"):
            body = self._inject_assistant_event_client(body)
        return body, content_type

    @staticmethod
    def _assistant_event_script() -> bytes:
        """Tiny transport adapter; the workspace remains the rendering owner."""

        return b"""(() => {
  if (window.__channelAgentAssistantEventsStarted) return;
  window.__channelAgentAssistantEventsStarted = true;
  const recoveryKey = 'channel-agent-local-session-recovery-v1';
  const checkLocalSession = async () => {
    let bootstrapPayload = null;
    try {
      const response = await fetch('/local-api/v1/bootstrap', { cache: 'no-store' });
      if (response.ok) {
        bootstrapPayload = await response.json();
        sessionStorage.removeItem(recoveryKey);
      } else if (response.status === 401) {
        const bootstrap = new URLSearchParams(window.location.search).get('bootstrap');
        const attempted = sessionStorage.getItem(recoveryKey);
        if (bootstrap && attempted !== bootstrap) {
          sessionStorage.setItem(recoveryKey, bootstrap);
          window.location.reload();
          return;
        }
      }
    } catch (_) {
      // The loopback Runtime may still be restarting. Retry without navigating.
    }
    window.setTimeout(checkLocalSession, 2000);
    return bootstrapPayload;
  };
  const connect = async () => {
    const bootstrapPayload = await checkLocalSession();
    const cursor = Number(bootstrapPayload?.assistant_event_cursor ?? 0);
    const after = Number.isSafeInteger(cursor) && cursor >= 0 ? cursor : 0;
    const source = new EventSource(`/local-api/v1/events?after=${after}`);
    source.addEventListener('assistant', (message) => {
      let detail;
      try { detail = JSON.parse(message.data); } catch (_) { return; }
      window.dispatchEvent(new CustomEvent('channel-agent:assistant-event', { detail }));
    });
    source.addEventListener('error', () => {
      // EventSource applies bounded browser reconnect. Existing workspace
      // polling remains the independent degraded fallback.
    });
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', connect, { once: true });
  } else {
    connect();
  }
})();
"""

    @staticmethod
    def _inject_assistant_event_client(body: bytes) -> bytes:
        marker = b'<script src="/channel-agent-assistant-events.js" defer></script>'
        if marker in body:
            return body
        lower = body.lower()
        index = lower.rfind(b"</body>")
        if index < 0:
            return body + marker
        return body[:index] + marker + body[index:]

    def _write_runtime_state(self) -> None:
        path = self._runtime_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": DESKTOP_API_VERSION,
            "status": "RUNNING",
            "origin": self.origin,
            "workspace_url": self.workspace_url,
            "launcher_url": f"{self.origin}/launcher-api/v1/open",
            "launcher_capability": self._launcher_capability,
            "pid": os.getpid(),
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _runtime_path(self) -> Path:
        return self.data_root / "runtime" / "desktop-assistant.json"

    def _bootstrap_handoff_path(self) -> Path:
        return self.data_root / "runtime" / "desktop-bootstrap-handoff.json"

    def _bootstrap_handoff_consumed_path(self) -> Path:
        return self.data_root / "runtime" / "desktop-bootstrap-handoff-consumed.json"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            raw = path.read_bytes()
            if len(raw) > 2 * 1024 * 1024:
                return {}
            value = json.loads(raw.decode("utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _validate_platform_origin(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or (parsed.scheme != "https" and not loopback)
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise DesktopAssistantError("unsafe AI-CS platform origin")
        return normalized

    @staticmethod
    def _fallback_html() -> bytes:
        return """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<link rel="icon" type="image/png" href="/channel-agent-avatar.png">
<title>AI-CS 客服助手</title><style>body{font-family:Segoe UI,Microsoft YaHei,sans-serif;
margin:0;background:#eef7ef;color:#183c2b}main{max-width:760px;margin:10vh auto;padding:32px;
background:white;border:1px solid #b8d8c2;border-radius:18px;box-shadow:0 18px 50px #235b3a22}
h1{margin-top:0;display:flex;align-items:center;gap:14px}h1 img{width:56px;height:56px}
.safe{color:#2f7d57;font-weight:700}</style><main><h1><img src="/channel-agent-avatar.png" alt="AI">AI-CS 客服助手</h1>
<p>桌面助手已启动，正式客服界面资源尚未安装。</p><p class="safe">人工确认保持开启，系统不会自动发送消息。</p></main></html>""".encode("utf-8")


class _DesktopHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    runtime: DesktopAssistantServer


class _DesktopHandler(BaseHTTPRequestHandler):
    server: _DesktopHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        if not self._valid_host():
            self._json(HTTPStatus.FORBIDDEN, {"error": {"code": "INVALID_HOST"}})
            return
        path = urlsplit(self.path).path
        if self._requires_local_session(path) and not self._valid_local_session():
            self._json(
                HTTPStatus.UNAUTHORIZED,
                {"error": {"code": "LOCAL_SESSION_REQUIRED"}},
            )
            return
        if path == "/platform-api" or path.startswith("/platform-api/"):
            self._proxy("GET")
            return
        if path == "/local-api/v1/bootstrap":
            self._json(HTTPStatus.OK, self.server.runtime.bootstrap())
            return
        if path == "/local-api/v1/doctor":
            deep = urlsplit(self.path).query in {"deep=1", "mode=deep"}
            self._json(HTTPStatus.OK, self.server.runtime.doctor(deep=deep))
            return
        if path == "/local-api/v1/config":
            self._json(HTTPStatus.OK, self.server.runtime.configuration())
            return
        if path.startswith("/local-api/v1/repair/"):
            repair_id = path.rsplit("/", 1)[-1]
            try:
                self._json(
                    HTTPStatus.OK,
                    self.server.runtime.operations.repair_status(repair_id),
                )
            except OperationsCenterError as exc:
                self._operations_error(exc)
            return
        if path == "/local-api/v1/events":
            self._stream_assistant_events()
            return
        if path in {
            "/channel-agent-api/assistant-feed.json",
            "/local-api/v1/conversations",
        }:
            feed = self.server.runtime.assistant_feed()
            value = (
                feed
                if path.startswith("/channel-agent-api/")
                else {
                    "schema_version": DESKTOP_API_VERSION,
                    "items": feed.get("conversations", []),
                }
            )
            self._json(HTTPStatus.OK, value)
            return
        static = self.server.runtime.static_file(self.path)
        if static is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body, content_type = static
        query = parse_qs(urlsplit(self.path).query)
        set_local_session = self.server.runtime.consume_bootstrap(
            (query.get("bootstrap") or [None])[0]
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header(
            "Cache-Control",
            "no-store"
            if content_type.startswith("text/html")
            else "public, max-age=31536000, immutable",
        )
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        if set_local_session:
            self.send_header(
                "Set-Cookie",
                self.server.runtime.local_session_cookie,
            )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream_assistant_events(self) -> None:
        raw_cursor = self.headers.get("Last-Event-ID", "0").strip()
        query = parse_qs(urlsplit(self.path).query)
        if raw_cursor == "0":
            raw_cursor = (query.get("after") or ["0"])[0]
        try:
            cursor = max(0, int(raw_cursor))
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": {"code": "ASSISTANT_EVENT_CURSOR_INVALID"}})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        deadline = time.monotonic() + 55.0
        try:
            if cursor == 0:
                snapshot = json.dumps(
                    self.server.runtime.assistant_feed(), ensure_ascii=False, separators=(",", ":")
                )
                self.wfile.write(f"event: snapshot\ndata: {snapshot}\n\n".encode("utf-8"))
                self.wfile.flush()
            while time.monotonic() < deadline:
                events = self.server.runtime.event_journal.read_after(cursor)
                if events:
                    for event in events:
                        sequence_id = int(event["sequence_id"])
                        body = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                        self.wfile.write(
                            f"id: {sequence_id}\nevent: assistant\ndata: {body}\n\n".encode("utf-8")
                        )
                        cursor = sequence_id
                    self.wfile.flush()
                    continue
                self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
                self.server.runtime.event_journal.wait_for_change(5.0)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/launcher-api/v1/open":
            self._discard_request_body()
            if not self._valid_host():
                self._json(HTTPStatus.FORBIDDEN, {"error": {"code": "INVALID_HOST"}})
                return
            try:
                workspace_url = self.server.runtime.issue_workspace_url(
                    self.headers.get("X-Channel-Agent-Launcher")
                )
            except DesktopAssistantError:
                self._json(
                    HTTPStatus.FORBIDDEN,
                    {"error": {"code": "LAUNCHER_CAPABILITY_INVALID"}},
                )
                return
            self._json(HTTPStatus.OK, {"workspace_url": workspace_url})
            return
        if not self._valid_host() or not self._valid_origin():
            # On Windows, closing a request socket while its body is unread can
            # turn this deliberate 403 into a TCP reset. Drain only a bounded
            # body so callers receive the fail-closed response deterministically.
            self._discard_request_body()
            self._json(HTTPStatus.FORBIDDEN, {"error": {"code": "INVALID_ORIGIN"}})
            return
        if self._requires_local_session(path) and (
            not self._valid_local_session() or not self._valid_csrf()
        ):
            self._discard_request_body()
            self._json(
                HTTPStatus.FORBIDDEN,
                {"error": {"code": "LOCAL_SESSION_OR_CSRF_INVALID"}},
            )
            return
        if path == "/platform-api" or path.startswith("/platform-api/"):
            self._proxy("POST")
            return
        if path == "/local-api/v1/runtime/safe-stop":
            self._discard_request_body()
            self.server.runtime.request_safe_stop()
            self._json(HTTPStatus.ACCEPTED, {"status": "STOPPING"})
            return
        if path == "/local-api/v1/browser/pdd/open":
            self._discard_request_body()
            if (
                self.headers.get("X-Channel-Agent-Intent")
                != "HUMAN_REQUESTED_PDD_WINDOW"
            ):
                self._json(
                    HTTPStatus.FORBIDDEN,
                    {"error": {"code": "HUMAN_CONFIRMATION_REQUIRED"}},
                )
                return
            status, response = self.server.runtime.launch_pdd_workspace()
            self._json(status, response)
            return
        if path == "/local-api/v1/browser/pdd/refresh":
            self._discard_request_body()
            if (
                self.headers.get("X-Channel-Agent-Intent")
                != "HUMAN_CONFIRMED_PDD_WORKSPACE_READY"
            ):
                self._json(
                    HTTPStatus.FORBIDDEN,
                    {"error": {"code": "HUMAN_CONFIRMATION_REQUIRED"}},
                )
                return
            status, response = self.server.runtime.refresh_pdd_workspace()
            self._json(status, response)
            return
        if path == "/local-api/v1/observer/pdd/restart":
            self._discard_request_body()
            if (
                self.headers.get("X-Channel-Agent-Intent")
                != "HUMAN_CONFIRMED_PDD_OBSERVER_RESTART"
            ):
                self._json(
                    HTTPStatus.FORBIDDEN,
                    {"error": {"code": "HUMAN_CONFIRMATION_REQUIRED"}},
                )
                return
            status, response = self.server.runtime.request_pdd_observer_restart()
            self._json(status, response)
            return
        read_match = re.fullmatch(
            r"/local-api/v1/conversations/([^/]+)/read", path
        )
        if read_match is not None:
            self._discard_request_body()
            try:
                conversation_id = unquote(read_match.group(1))
                self._json(
                    HTTPStatus.OK,
                    self.server.runtime.mark_conversation_read(conversation_id),
                )
            except DesktopAssistantError:
                self._json(
                    HTTPStatus.NOT_FOUND,
                    {"error": {"code": "ASSISTANT_CONVERSATION_NOT_FOUND"}},
                )
            return
        if path == "/local-api/v1/enrollment":
            if self.headers.get("X-Channel-Agent-Intent") != "HUMAN_CONFIRMED_DEVICE_BINDING":
                self._discard_request_body()
                self._json(HTTPStatus.FORBIDDEN, {"error": {"code": "HUMAN_CONFIRMATION_REQUIRED"}})
                return
            try:
                payload = self._request_json()
            except DesktopAssistantError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": {"code": "INVALID_REQUEST"}})
                return
            status, response = self.server.runtime.enroll_identity(payload)
            self._json(status, response)
            return
        if path == "/local-api/v1/identity/sync":
            if self.headers.get("X-Channel-Agent-Intent") != "HUMAN_CONFIRMED_DEVICE_BINDING":
                self._discard_request_body()
                self._json(HTTPStatus.FORBIDDEN, {"error": {"code": "HUMAN_CONFIRMATION_REQUIRED"}})
                return
            self._discard_request_body()
            status, response = self.server.runtime.sync_identity()
            self._json(status, response)
            return
        if path == "/local-api/v1/config/validate":
            try:
                payload = self._request_json()
                result = self.server.runtime.validate_configuration(payload)
                self._json(
                    HTTPStatus.OK if result.get("valid") else HTTPStatus.UNPROCESSABLE_ENTITY,
                    result,
                )
            except DesktopAssistantError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": {"code": "INVALID_REQUEST"}})
            except OperationsCenterError as exc:
                self._operations_error(exc)
            return
        if path == "/local-api/v1/repair":
            self._discard_request_body()
            if self.headers.get("X-Channel-Agent-Intent") != "HUMAN_CONFIRMED_REPAIR":
                self._json(HTTPStatus.FORBIDDEN, {"error": {"code": "HUMAN_CONFIRMATION_REQUIRED"}})
                return
            try:
                self._json(
                    HTTPStatus.ACCEPTED,
                    self.server.runtime.operations.start_repair(),
                )
            except OperationsCenterError as exc:
                self._operations_error(exc)
            return
        if path == "/local-api/v1/onboarding/discover":
            self._discard_request_body()
            try:
                self._json(HTTPStatus.OK, self.server.runtime.operations.discover_hosts())
            except OperationsCenterError as exc:
                self._operations_error(exc)
            return
        if path == "/local-api/v1/onboarding/pair":
            if self.headers.get("X-Channel-Agent-Intent") != "HUMAN_CONFIRMED_CONFIGURATION":
                self._discard_request_body()
                self._json(HTTPStatus.FORBIDDEN, {"error": {"code": "HUMAN_CONFIRMATION_REQUIRED"}})
                return
            try:
                payload = self._request_json()
                self._json(HTTPStatus.OK, self.server.runtime.operations.pair_host(payload))
            except DesktopAssistantError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": {"code": "INVALID_REQUEST"}})
            except OperationsCenterError as exc:
                self._operations_error(exc)
            return
        if path == "/channel-agent-api/v1/approved-replies":
            try:
                payload = self._request_json()
            except DesktopAssistantError:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": {"code": "INVALID_REQUEST"}},
                )
                return
            if self.headers.get("X-Channel-Agent-Intent") != "HUMAN_CONFIRMED_SEND":
                self._json(
                    HTTPStatus.FORBIDDEN,
                    {"error": {"code": "HUMAN_CONFIRMATION_REQUIRED"}},
                )
                return
            status, response = self.server.runtime.approve_reply(payload)
            self._json(status, response)
            return
        if path == "/local-api/v1/active-store":
            if self.headers.get("X-Channel-Agent-Intent") != "HUMAN_CONFIRMED_STORE_SELECTION":
                self._json(
                    HTTPStatus.FORBIDDEN,
                    {"error": {"code": "HUMAN_CONFIRMATION_REQUIRED"}},
                )
                return
            try:
                payload = self._request_json()
            except DesktopAssistantError:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": {"code": "INVALID_REQUEST"}},
                )
                return
            status, response = self.server.runtime.select_active_store(payload)
            self._json(status, response)
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND"}})

    def do_PUT(self) -> None:  # noqa: N802
        if not self._valid_host() or not self._valid_origin():
            self._discard_request_body()
            self._json(HTTPStatus.FORBIDDEN, {"error": {"code": "INVALID_ORIGIN"}})
            return
        path = urlsplit(self.path).path
        if self._requires_local_session(path) and (
            not self._valid_local_session() or not self._valid_csrf()
        ):
            self._discard_request_body()
            self._json(
                HTTPStatus.FORBIDDEN,
                {"error": {"code": "LOCAL_SESSION_OR_CSRF_INVALID"}},
            )
            return
        if path == "/local-api/v1/config":
            if self.headers.get("X-Channel-Agent-Intent") != "HUMAN_CONFIRMED_CONFIGURATION":
                self._discard_request_body()
                self._json(HTTPStatus.FORBIDDEN, {"error": {"code": "HUMAN_CONFIRMATION_REQUIRED"}})
                return
            try:
                payload = self._request_json()
                result = self.server.runtime.save_configuration(payload)
                self._json(
                    HTTPStatus.ACCEPTED if result.get("saved") else HTTPStatus.UNPROCESSABLE_ENTITY,
                    result,
                )
            except DesktopAssistantError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": {"code": "INVALID_REQUEST"}})
            except OperationsCenterError as exc:
                self._operations_error(exc)
            return
        self._proxy_mutation("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self._proxy_mutation("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy_mutation("DELETE")

    def _proxy_mutation(self, method: str) -> None:
        if not self._valid_host() or not self._valid_origin():
            self._json(HTTPStatus.FORBIDDEN, {"error": {"code": "INVALID_ORIGIN"}})
            return
        path = urlsplit(self.path).path
        if self._requires_local_session(path) and (
            not self._valid_local_session() or not self._valid_csrf()
        ):
            self._discard_request_body()
            self._json(
                HTTPStatus.FORBIDDEN,
                {"error": {"code": "LOCAL_SESSION_OR_CSRF_INVALID"}},
            )
            return
        if path != "/platform-api" and not path.startswith("/platform-api/"):
            self._json(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND"}})
            return
        self._proxy(method)

    def _proxy(self, method: str) -> None:
        body: bytes | None = None
        if method != "GET":
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": {"code": "INVALID_REQUEST"}},
                )
                return
            if length < 0 or length > _MAX_REQUEST_BYTES:
                self._json(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"error": {"code": "REQUEST_TOO_LARGE"}},
                )
                return
            body = self.rfile.read(length)
        status, payload, content_type = self.server.runtime.proxy_platform(
            method=method,
            request_path=self.path,
            headers={key: value for key, value in self.headers.items()},
            body=body,
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _request_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise DesktopAssistantError("invalid content length") from exc
        if length <= 0 or length > _MAX_REQUEST_BYTES:
            raise DesktopAssistantError("invalid request size")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise DesktopAssistantError("invalid json") from exc
        if not isinstance(value, dict):
            raise DesktopAssistantError("request must be object")
        return value

    def _discard_request_body(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.close_connection = True
            return
        if 0 < length <= _MAX_REQUEST_BYTES:
            self.rfile.read(length)
        elif length > _MAX_REQUEST_BYTES:
            self.close_connection = True

    def _valid_host(self) -> bool:
        host = self.headers.get("Host", "").partition(":")[0].casefold()
        return host in {"127.0.0.1", "localhost"}

    def _valid_origin(self) -> bool:
        return self.headers.get("Origin") == self.server.runtime.origin

    @staticmethod
    def _requires_local_session(path: str) -> bool:
        return (
            path.startswith("/local-api/")
            or path.startswith("/channel-agent-api/")
            or path == "/platform-api"
            or path.startswith("/platform-api/")
        )

    def _valid_local_session(self) -> bool:
        return self.server.runtime.valid_local_session(self.headers.get("Cookie"))

    def _valid_csrf(self) -> bool:
        return self.server.runtime.valid_csrf(self.headers.get("X-Channel-Agent-CSRF"))

    def _json(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _operations_error(self, exc: OperationsCenterError) -> None:
        self._json(
            exc.status,
            {"error": {"code": exc.code, "message": str(exc)}},
        )

    def log_message(self, _format: str, *_args: object) -> None:
        return


__all__ = [
    "DESKTOP_API_VERSION",
    "DesktopAssistantError",
    "DesktopAssistantServer",
]
