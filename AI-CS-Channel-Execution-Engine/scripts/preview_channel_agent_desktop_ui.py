from __future__ import annotations

import argparse
import json
import signal
import sys
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread

from channel_agent.desktop import DesktopAssistantServer


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _preview_user() -> dict[str, object]:
    now = _now()
    return {
        "id": "81fd7470-5fb7-4e41-bc98-f12a62ec3619",
        "username": "preview",
        "display_name": "客服小木",
        "status": "ACTIVE",
        "roles": ["CUSTOMER_SERVICE"],
        "permissions": ["workspace.access", "ai.reply", "feedback.submit"],
        "stores": [
            {
                "id": 1,
                "store_id": 8,
                "store_code": "PDD-DEMO",
                "store_name": "玩趣乐园积木店",
                "platform": "pinduoduo",
                "is_default": True,
            }
        ],
        "must_change_password": False,
        "all_store_access": False,
        "created_at": now,
        "updated_at": now,
    }


class _PreviewPlatformHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/v1/auth/me"):
            self._json(HTTPStatus.OK, {"user": _preview_user()})
            return
        if self.path.startswith("/api/v1/workspace/context"):
            store = {
                "store_id": 8,
                "tenant_id": "TENANT-PREVIEW",
                "platform": "pinduoduo",
                "store_code": "PDD-DEMO",
                "store_name": "玩趣乐园积木店",
                "is_default": True,
            }
            self._json(
                HTTPStatus.OK,
                {
                    "schema_version": "ai-cs.store-context.v1",
                    "user_id": _preview_user()["id"],
                    "roles": ["CUSTOMER_SERVICE"],
                    "all_store_access": False,
                    "state": "READY",
                    "stores": [store],
                    "effective_store": store,
                },
            )
            return
        if self.path.startswith("/api/v1/workspace/desktop-agent"):
            self._json(
                HTTPStatus.OK,
                {
                    "schema_version": "ai-cs.customer-desktop-workflow.v1",
                    "user_id": _preview_user()["id"],
                    "store_id": 8,
                    "store_code": "PDD-DEMO",
                    "association_state": "READY",
                    "agent": {
                        "agent_id": "preview-agent-001",
                        "device_id": "preview-device-001",
                        "device_name": "客服电脑",
                        "agent_version": "1.4.0",
                        "identity_status": "ACTIVE",
                        "online_status": "ONLINE",
                        "runtime_status": "RUNNING",
                        "production_eligible": False,
                        "binding_revision": 1,
                        "last_heartbeat": _now(),
                    },
                    "checked_at": _now(),
                },
            )
            return
        if self.path.startswith("/api/v1/workspace/ai-health"):
            self._json(HTTPStatus.OK, {"status": "healthy", "ready": True})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND"}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/api/v1/auth/login"):
            self._json(
                HTTPStatus.OK,
                {
                    "schema_version": "ai-cs.iam.v1",
                    "token_type": "Bearer",
                    "access_token": "local-preview-session",
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "user": _preview_user(),
                },
            )
            return
        if self.path.startswith("/api/v1/auth/logout"):
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND"}})

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, value: object) -> None:
        payload = _json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _seed_preview(data_root: Path) -> None:
    runtime_root = data_root / "runtime"
    assistant_root = runtime_root / "real-pdd-assistant"
    assistant_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "channel-agent-state.json").write_bytes(
        _json_bytes(
            {
                "process_status": "RUNNING",
                "runtime_status": "ONLINE",
                "agent_id": "preview-agent-001",
                "browser_status": "OPENED",
                "pdd_login_state": "CUSTOMER_SERVICE_READY",
                "store_id": "PDD-DEMO",
            }
        )
    )
    (assistant_root / "assistant-feed.json").write_bytes(
        _json_bytes(
            {
                "schemaVersion": "channel-agent-workspace-feed.v1",
                "source": "CHANNEL_AGENT_DESKTOP_PREVIEW",
                "generatedAt": _now(),
                "conversations": [
                    {
                        "conversationId": "preview-conversation-age",
                        "customerLabel": "客户 A17",
                        "unreadCount": 1,
                        "source": "CHANNEL_AGENT",
                        "messages": [
                            {
                                "messageId": "preview-message-001",
                                "conversationId": "preview-conversation-age",
                                "customerLabel": "客户 A17",
                                "senderRole": "CUSTOMER",
                                "content": "你好，这款积木适合几岁的小朋友？",
                                "receivedAt": "2026-08-07T16:32:00+08:00",
                                "source": "CHANNEL_AGENT",
                            },
                            {
                                "messageId": "preview-message-002",
                                "conversationId": "preview-conversation-age",
                                "customerLabel": "客服小木",
                                "senderRole": "AGENT",
                                "content": "您好，我帮您核对一下商品信息。",
                                "receivedAt": "2026-08-07T16:33:00+08:00",
                                "source": "CHANNEL_AGENT",
                            },
                            {
                                "messageId": "preview-message-003",
                                "conversationId": "preview-conversation-age",
                                "customerLabel": "客户 A17",
                                "senderRole": "CUSTOMER",
                                "content": "家里孩子刚满8岁，可以玩吗？",
                                "receivedAt": "2026-08-07T16:34:00+08:00",
                                "source": "CHANNEL_AGENT",
                            },
                        ],
                    }
                ],
                "reply": {
                    "conversationId": "preview-conversation-age",
                    "messageId": "preview-message-003",
                    "decisionId": "decision-preview-001",
                    "answer": "亲，这款积木建议8岁以上儿童使用。产品含小颗粒零件，建议在家长陪同下拼搭并妥善收纳，注意不要吞食哦。",
                    "requestId": "request-preview-001",
                    "action": "CONTROLLED_ANSWER",
                    "riskLevel": "LOW",
                    "citations": [
                        {
                            "file": "商品知识",
                            "page": None,
                            "chunkId": "preview-chunk-001",
                            "summary": "适用年龄：8岁以上",
                            "distance": 0.05,
                            "knowledgeVersion": "preview-v1",
                            "sourceIds": ["source-preview"],
                            "productId": "product-preview",
                            "skuId": "sku-preview",
                        }
                    ],
                    "warnings": [],
                    "requiredFields": [],
                },
                "productContext": {
                    "productReference": "product-preview",
                    "productName": "香薰玫瑰积木花艺摆件",
                    "applicableAge": "8岁以上",
                },
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
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview the packaged Channel Agent UI safely.")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--static-root", required=True)
    parser.add_argument("--ready-file", required=True)
    args = parser.parse_args(argv)
    data_root = Path(args.data_root).resolve()
    _seed_preview(data_root)

    platform = ThreadingHTTPServer(("127.0.0.1", 0), _PreviewPlatformHandler)
    platform_thread = Thread(target=platform.serve_forever, daemon=True)
    platform_thread.start()
    platform_port = int(platform.server_address[1])
    desktop = DesktopAssistantServer(
        data_root=data_root,
        static_root=Path(args.static_root),
        platform_origin=f"http://127.0.0.1:{platform_port}",
    )
    workspace_url = desktop.start()
    ready_file = Path(args.ready_file).resolve()
    ready_file.parent.mkdir(parents=True, exist_ok=True)
    ready_file.write_bytes(_json_bytes({"workspace_url": workspace_url}))

    stopped = Event()
    signal.signal(signal.SIGINT, lambda *_args: stopped.set())
    signal.signal(signal.SIGTERM, lambda *_args: stopped.set())
    try:
        stopped.wait()
    finally:
        desktop.stop()
        platform.shutdown()
        platform.server_close()
        platform_thread.join(timeout=3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
