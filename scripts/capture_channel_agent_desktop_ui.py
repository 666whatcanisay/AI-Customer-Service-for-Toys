from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import sys
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import unquote, urlsplit

from preview_channel_agent_desktop_ui import _preview_user, _seed_preview


def _payload(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class _PreviewServer(ThreadingHTTPServer):
    static_root: Path
    data_root: Path
    feed_file: Path


class _PreviewHandler(BaseHTTPRequestHandler):
    server: _PreviewServer

    def _store(self) -> dict[str, object]:
        feed_path = self.server.feed_file
        try:
            feed = json.loads(feed_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            feed = {}
        context = feed.get("storeContext") if isinstance(feed, dict) else None
        store_code = (
            str(context.get("storeId"))
            if isinstance(context, dict) and context.get("storeId")
            else "PDD-DEMO"
        )
        store_name = (
            str(context.get("storeName"))
            if isinstance(context, dict) and context.get("storeName")
            else "玩趣乐园积木店"
        )
        return {
            "store_id": 8,
            "tenant_id": "TENANT-PREVIEW",
            "platform": "pinduoduo",
            "store_code": store_code,
            "store_name": store_name,
            "is_default": True,
        }

    def _user(self) -> dict[str, object]:
        user = _preview_user()
        store = self._store()
        user["stores"] = [
            {
                "id": 1,
                "store_id": store["store_id"],
                "store_code": store["store_code"],
                "store_name": store["store_name"],
                "platform": store["platform"],
                "is_default": True,
            }
        ]
        return user

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/preview-login":
            body = b"""<!doctype html><meta charset=utf-8><title>Channel Agent Preview</title>
<script>
sessionStorage.setItem('ai-cs-customer-session-v1','local-preview-session');
location.replace('/workspace?channel-agent-desktop=1');
</script>"""
            self._write(HTTPStatus.OK, body, "text/html; charset=utf-8")
            return
        if path == "/local-api/v1/bootstrap":
            self._json(
                HTTPStatus.OK,
                {
                    "schema_version": "1.0",
                    "agent": {
                        "process_status": "RUNNING",
                        "runtime_status": "ONLINE",
                        "version": "1.4.0",
                        "node_id": "preview-agent-001",
                    },
                    "browser": {
                        "status": "OPENED",
                        "pdd_login_state": "CUSTOMER_SERVICE_READY",
                    },
                    "binding": {"store_reference": self._store()["store_code"]},
                    "assistant": {"status": "READY"},
                    "safety": {
                        "manual_approval": True,
                        "auto_reply": False,
                        "real_send_enabled": False,
                    },
                },
            )
            return
        if path == "/platform-api/api/v1/auth/me":
            self._json(HTTPStatus.OK, {"user": self._user()})
            return
        if path == "/platform-api/api/v1/workspace/context":
            store = self._store()
            self._json(
                HTTPStatus.OK,
                {
                    "schema_version": "ai-cs.store-context.v1",
                    "user_id": self._user()["id"],
                    "roles": ["CUSTOMER_SERVICE"],
                    "all_store_access": False,
                    "state": "READY",
                    "stores": [store],
                    "effective_store": store,
                },
            )
            return
        if path == "/platform-api/api/v1/workspace/desktop-agent":
            self._json(
                HTTPStatus.OK,
                {
                    "schema_version": "ai-cs.customer-desktop-workflow.v1",
                    "user_id": self._user()["id"],
                    "store_id": 8,
                    "store_code": self._store()["store_code"],
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
        if path == "/platform-api/api/v1/workspace/ai-health":
            self._json(HTTPStatus.OK, {"status": "healthy", "ready": True})
            return
        if path == "/channel-agent-api/assistant-feed.json":
            feed = self.server.feed_file.read_bytes()
            self._write(HTTPStatus.OK, feed, "application/json; charset=utf-8")
            return
        self._static(path)

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _static(self, path: str) -> None:
        relative = unquote(path).lstrip("/")
        candidate = (self.server.static_root / relative).resolve()
        root = self.server.static_root.resolve()
        if candidate != root and root not in candidate.parents:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not candidate.is_file():
            candidate = root / "index.html"
        if not candidate.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self._write(HTTPStatus.OK, candidate.read_bytes(), mime)

    def _json(self, status: int, value: object) -> None:
        self._write(status, _payload(value), "application/json; charset=utf-8")

    def _write(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture the packaged Channel Agent UI.")
    parser.add_argument("--static-root", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--no-seed", action="store_true")
    parser.add_argument("--expected-text")
    parser.add_argument("--feed-file")
    parser.add_argument(
        "--edge",
        default=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    )
    args = parser.parse_args(argv)
    static_root = Path(args.static_root).resolve()
    data_root = Path(args.data_root).resolve()
    feed_file = (
        Path(args.feed_file).resolve()
        if args.feed_file
        else data_root / "runtime" / "real-pdd-assistant" / "assistant-feed.json"
    )
    output = Path(args.output).resolve()
    edge = Path(args.edge).resolve()
    if not static_root.is_dir() or not edge.is_file():
        print("Packaged UI or Microsoft Edge was not found.", file=sys.stderr)
        return 5
    output.parent.mkdir(parents=True, exist_ok=True)
    if not args.no_seed:
        _seed_preview(data_root)
    server = _PreviewServer(("127.0.0.1", 0), _PreviewHandler)
    server.static_root = static_root
    server.data_root = data_root
    server.feed_file = feed_file
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    browser_profile = data_root / "capture-edge-profile"
    browser_profile.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                str(edge),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1800,1080",
                "--force-device-scale-factor=1",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=10000",
                "--dump-dom",
                f"--user-data-dir={browser_profile}",
                f"--screenshot={output}",
                f"http://127.0.0.1:{port}/preview-login",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    if result.returncode != 0 or not output.is_file():
        print(result.stderr[-2000:], file=sys.stderr)
        return 4
    if args.expected_text and args.expected_text not in result.stdout:
        print("Expected AI reply was not rendered by the Desktop Assistant UI.", file=sys.stderr)
        return 4
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
