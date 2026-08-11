from __future__ import annotations

import json
from http.cookiejar import CookieJar
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import pytest

from channel_agent.desktop import DesktopAssistantServer


class _ProxyCaptureHandler(BaseHTTPRequestHandler):
    seen: dict[str, str | None] = {}

    def do_GET(self) -> None:  # noqa: N802
        type(self).seen = {
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "cookie": self.headers.get("Cookie"),
        }
        payload = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _get_json(url: str) -> dict[str, object]:
    with urlopen(url, timeout=2) as response:  # noqa: S310 - loopback test URL
        return json.loads(response.read().decode("utf-8"))


def _authenticated_client(server: DesktopAssistantServer):  # type: ignore[no-untyped-def]
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    workspace_url = server.workspace_url
    assert workspace_url is not None
    with opener.open(workspace_url, timeout=2) as response:  # noqa: S310
        response.read()
    origin = server.origin
    assert origin is not None
    with opener.open(f"{origin}/local-api/v1/bootstrap", timeout=2) as response:  # noqa: S310
        bootstrap = json.loads(response.read().decode("utf-8"))
    return opener, origin, bootstrap["csrf_token"]


def test_desktop_server_serves_spa_status_and_safe_empty_feed(tmp_path: Path) -> None:
    static = tmp_path / "ui"
    static.mkdir()
    (static / "index.html").write_text("<main>desktop assistant</main>", encoding="utf-8")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "channel-agent-state.json").write_text(
        json.dumps({"process_status": "RUNNING", "pdd_login_state": "CUSTOMER_SERVICE_READY"}),
        encoding="utf-8",
    )
    server = DesktopAssistantServer(data_root=tmp_path, static_root=static)
    try:
        workspace_url = server.start()
        assert "/workspace?channel-agent-desktop=1&bootstrap=" in workspace_url
        origin = server.origin
        assert origin is not None and origin.startswith("http://127.0.0.1:")
        opener, _, _csrf = _authenticated_client(server)
        with opener.open(f"{origin}/local-api/v1/bootstrap", timeout=2) as response:  # noqa: S310
            bootstrap = json.loads(response.read().decode("utf-8"))
        assert bootstrap["agent"]["process_status"] == "RUNNING"  # type: ignore[index]
        with opener.open(f"{origin}/channel-agent-api/assistant-feed.json", timeout=2) as response:  # noqa: S310
            feed = json.loads(response.read().decode("utf-8"))
        assert feed["conversations"] == []
        assert feed["schemaVersion"] == "channel-agent-workspace-feed.v1"
        assert feed["safety"]["autoReply"] is False  # type: ignore[index]
        assert feed["safety"] == {
            "readOnly": True,
            "autoReply": False,
            "realSend": False,
            "browserWriteOperations": 0,
            "executionCount": 0,
            "receiptCount": 0,
            "sendCount": 0,
        }
    finally:
        server.stop()
    assert not (runtime / "desktop-assistant.json").exists()


def test_desktop_assistant_serves_packaged_brand_avatar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_home = tmp_path / "program"
    avatar = agent_home / "assets" / "branding" / "channel-agent-avatar.png"
    avatar.parent.mkdir(parents=True)
    avatar.write_bytes(b"\x89PNG\r\n\x1a\nbrand")
    monkeypatch.setenv("AI_CS_CHANNEL_AGENT_HOME", str(agent_home))
    server = DesktopAssistantServer(data_root=tmp_path / "data")

    assert server.static_file("/channel-agent-avatar.png") == (
        avatar.read_bytes(),
        "image/png",
    )
    fallback, content_type = server.static_file("/") or (b"", "")
    assert content_type == "text/html; charset=utf-8"
    assert b"/channel-agent-avatar.png" in fallback


def test_launcher_gets_a_fresh_one_time_session_each_time_the_window_reopens(
    tmp_path: Path,
) -> None:
    server = DesktopAssistantServer(data_root=tmp_path)
    try:
        initial_url = server.start()
        first = build_opener(HTTPCookieProcessor(CookieJar()))
        with first.open(initial_url, timeout=2) as response:  # noqa: S310
            response.read()
        origin = server.origin
        assert origin is not None
        with first.open(f"{origin}/local-api/v1/bootstrap", timeout=2) as response:  # noqa: S310
            assert response.status == 200

        runtime = json.loads(
            (tmp_path / "runtime" / "desktop-assistant.json").read_text(
                encoding="utf-8"
            )
        )
        assert runtime["launcher_capability"] not in runtime["workspace_url"]
        request = Request(
            runtime["launcher_url"],
            data=b"",
            method="POST",
            headers={"X-Channel-Agent-Launcher": runtime["launcher_capability"]},
        )
        with urlopen(request, timeout=2) as response:  # noqa: S310
            fresh_url = json.loads(response.read().decode("utf-8"))["workspace_url"]
        assert fresh_url != initial_url

        reopened = build_opener(HTTPCookieProcessor(CookieJar()))
        with reopened.open(fresh_url, timeout=2) as response:  # noqa: S310
            response.read()
        with reopened.open(f"{origin}/local-api/v1/doctor", timeout=2) as response:  # noqa: S310
            assert response.status == 200

        rejected = Request(
            runtime["launcher_url"],
            data=b"",
            method="POST",
            headers={"X-Channel-Agent-Launcher": "wrong-capability"},
        )
        with pytest.raises(HTTPError) as invalid:
            urlopen(rejected, timeout=2)  # noqa: S310
        assert invalid.value.code == 403
    finally:
        server.stop()


def test_exe_restart_reestablishes_cookie_and_csrf_without_reusing_old_runtime(
    tmp_path: Path,
) -> None:
    browser = build_opener(HTTPCookieProcessor(CookieJar()))
    first = DesktopAssistantServer(data_root=tmp_path)
    try:
        first_url = first.start()
        with browser.open(first_url, timeout=2) as response:  # noqa: S310
            response.read()
        first_origin = first.origin
        assert first_origin is not None
        with browser.open(f"{first_origin}/local-api/v1/bootstrap", timeout=2) as response:  # noqa: S310
            first_csrf = json.loads(response.read().decode("utf-8"))["csrf_token"]
    finally:
        first.stop()

    restarted = DesktopAssistantServer(data_root=tmp_path)
    try:
        restarted_url = restarted.start()
        with browser.open(restarted_url, timeout=2) as response:  # noqa: S310
            response.read()
        restarted_origin = restarted.origin
        assert restarted_origin is not None
        with browser.open(f"{restarted_origin}/local-api/v1/bootstrap", timeout=2) as response:  # noqa: S310
            restarted_csrf = json.loads(response.read().decode("utf-8"))["csrf_token"]
        assert restarted_csrf != first_csrf
    finally:
        restarted.stop()


def test_desktop_server_rejects_send_without_origin_intent_or_handler(tmp_path: Path) -> None:
    server = DesktopAssistantServer(data_root=tmp_path)
    try:
        server.start()
        opener, origin, csrf = _authenticated_client(server)
        request = Request(
            f"{origin}/channel-agent-api/v1/approved-replies",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urlopen(request, timeout=2)  # noqa: S310
            raise AssertionError("request should fail closed")
        except HTTPError as exc:
            assert exc.code == 403

        request = Request(
            f"{origin}/channel-agent-api/v1/approved-replies",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
                "X-Channel-Agent-Intent": "HUMAN_CONFIRMED_SEND",
            },
        )
        try:
            opener.open(request, timeout=2)  # noqa: S310
            raise AssertionError("request should fail closed")
        except HTTPError as exc:
            assert exc.code == 503
            payload = json.loads(exc.read().decode("utf-8"))
            assert payload["error"]["code"] == "CONTROLLED_SEND_NOT_AVAILABLE"
    finally:
        server.stop()


def test_safe_stop_endpoint_only_writes_stop_marker_after_same_origin_post(
    tmp_path: Path,
) -> None:
    server = DesktopAssistantServer(data_root=tmp_path)
    try:
        server.start()
        opener, origin, csrf = _authenticated_client(server)
        request = Request(
            f"{origin}/local-api/v1/runtime/safe-stop",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
            },
        )
        with opener.open(request, timeout=2) as response:  # noqa: S310
            assert response.status == 202
        assert (tmp_path / "runtime" / "stop.request").read_text(encoding="ascii") == "stop\n"
    finally:
        server.stop()


def test_active_store_selection_requires_intent_and_no_active_workflow(
    tmp_path: Path,
) -> None:
    selected: list[tuple[str, str]] = []
    feed = tmp_path / "runtime" / "real-pdd-assistant" / "assistant-feed.json"
    feed.parent.mkdir(parents=True)
    feed.write_text(
        json.dumps(
            {
                "conversations": [],
                "reply": {"state": "WAITING_APPROVAL"},
            }
        ),
        encoding="utf-8",
    )
    server = DesktopAssistantServer(
        data_root=tmp_path,
        active_store_handler=lambda store, reason: (
            selected.append((store, reason))
            or {"active_store_id": store}
        ),
    )
    try:
        server.start()
        opener, origin, csrf = _authenticated_client(server)
        request = Request(
            f"{origin}/local-api/v1/active-store",
            data=json.dumps(
                {"store_reference": "store-b", "reason": "客服人工选择"}
            ).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
                "X-Channel-Agent-Intent": "HUMAN_CONFIRMED_STORE_SELECTION",
            },
        )
        with pytest.raises(HTTPError) as blocked:
            opener.open(request, timeout=2)  # noqa: S310
        assert blocked.value.code == 409
        assert selected == []

        feed.write_text(
            json.dumps({"conversations": [], "reply": None}), encoding="utf-8"
        )
        with opener.open(request, timeout=2) as response:  # noqa: S310
            assert response.status == 200
        assert selected == [("store-b", "客服人工选择")]
    finally:
        server.stop()


def test_platform_proxy_uses_fixed_origin_and_never_forwards_cookie(
    tmp_path: Path,
) -> None:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _ProxyCaptureHandler)
    worker = Thread(target=upstream.serve_forever, daemon=True)
    worker.start()
    port = upstream.server_address[1]
    server = DesktopAssistantServer(
        data_root=tmp_path,
        platform_origin=f"http://127.0.0.1:{port}",
    )
    try:
        server.start()
        opener, origin, _csrf = _authenticated_client(server)
        request = Request(
            f"{origin}/platform-api/v1/status?scope=agent",
            headers={"Authorization": "Bearer test-reference"},
        )
        with opener.open(request, timeout=2) as response:  # noqa: S310 - loopback test URL
            assert json.loads(response.read()) == {"ok": True}
        assert _ProxyCaptureHandler.seen == {
            "path": "/v1/status?scope=agent",
            "authorization": "Bearer test-reference",
            "cookie": None,
        }
    finally:
        server.stop()
        upstream.shutdown()
        upstream.server_close()
        worker.join(timeout=2)
