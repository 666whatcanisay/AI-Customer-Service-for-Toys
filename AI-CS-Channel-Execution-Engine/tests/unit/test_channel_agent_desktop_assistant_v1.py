from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import pytest

from channel_agent.config import ChannelAgentConfig
from channel_agent.control_v2 import AgentAssistantSnapshot
from channel_agent.desktop import DesktopAssistantServer
from channel_agent.observation_stages import ObservationStage


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


def test_native_launcher_opens_pdd_through_existing_manual_handler_only(
    tmp_path: Path,
) -> None:
    launches: list[str] = []

    def launch() -> dict[str, object]:
        launches.append("PDD")
        return {
            "status": "WAITING_LOGIN",
            "browser_status": "RUNNING",
            "pdd_login_state": "WAITING_QR_SCAN",
        }

    server = DesktopAssistantServer(
        data_root=tmp_path,
        pdd_workspace_launch_handler=launch,
    )
    try:
        server.start()
        runtime = json.loads(
            (tmp_path / "runtime" / "desktop-assistant.json").read_text(
                encoding="utf-8"
            )
        )
        endpoint = runtime["origin"] + "/launcher-api/v1/pdd/open"
        request = Request(
            endpoint,
            data=b"",
            method="POST",
            headers={
                "X-Channel-Agent-Launcher": runtime["launcher_capability"],
                "X-Channel-Agent-Intent": "HUMAN_REQUESTED_PDD_WINDOW",
            },
        )
        with urlopen(request, timeout=2) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
        assert response.status == 202
        assert launches == ["PDD"]
        assert result["observer_started"] is False
        assert result["real_send_enabled"] is False

        for headers in (
            {
                "X-Channel-Agent-Launcher": "wrong-capability",
                "X-Channel-Agent-Intent": "HUMAN_REQUESTED_PDD_WINDOW",
            },
            {"X-Channel-Agent-Launcher": runtime["launcher_capability"]},
        ):
            rejected = Request(endpoint, data=b"", method="POST", headers=headers)
            with pytest.raises(HTTPError) as invalid:
                urlopen(rejected, timeout=2)  # noqa: S310
            assert invalid.value.code == 403
        assert launches == ["PDD"]
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


def test_browser_preserving_reload_hands_old_workspace_to_new_runtime_once(
    tmp_path: Path,
) -> None:
    browser = build_opener(HTTPCookieProcessor(CookieJar()))
    first = DesktopAssistantServer(data_root=tmp_path)
    first_url = first.start()
    first_port = urlsplit(first_url).port
    assert first_port is not None
    try:
        with browser.open(first_url, timeout=2) as response:  # noqa: S310
            response.read()
        first_origin = first.origin
        assert first_origin is not None
        with browser.open(f"{first_origin}/local-api/v1/bootstrap", timeout=2) as response:  # noqa: S310
            first_csrf = json.loads(response.read().decode("utf-8"))["csrf_token"]
        first.prepare_reload_handoff()
    finally:
        first.stop()

    restarted = DesktopAssistantServer(data_root=tmp_path, port=first_port)
    try:
        restarted.start()
        assert not (tmp_path / "runtime" / "desktop-bootstrap-handoff.json").exists()
        with browser.open(first_url, timeout=2) as response:  # noqa: S310
            response.read()
        consumed = json.loads(
            (
                tmp_path
                / "runtime"
                / "desktop-bootstrap-handoff-consumed.json"
            ).read_text(encoding="utf-8")
        )
        assert consumed["schema_version"] == (
            "channel-agent-desktop-bootstrap-consumed.v1"
        )
        assert consumed["pid"] > 0
        restarted_origin = restarted.origin
        assert restarted_origin == first_origin
        with browser.open(f"{restarted_origin}/local-api/v1/bootstrap", timeout=2) as response:  # noqa: S310
            restarted_csrf = json.loads(response.read().decode("utf-8"))["csrf_token"]
        assert restarted_csrf != first_csrf
    finally:
        restarted.stop()


def test_assistant_event_client_has_bounded_local_session_reload_recovery() -> None:
    script = DesktopAssistantServer._assistant_event_script().decode("utf-8")

    assert "response.status === 401" in script
    assert "sessionStorage.getItem(recoveryKey)" in script
    assert "attempted !== bootstrap" in script
    assert "window.location.reload()" in script
    assert "window.setTimeout(checkLocalSession, 2000)" in script
    assert "bootstrapPayload?.assistant_event_cursor" in script
    assert "new EventSource(`/local-api/v1/events?after=${after}`)" in script


def test_bootstrap_reports_real_pdd_message_source_only_from_live_config(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "verified-selector-evidence.json"
    evidence.write_text("{}", encoding="utf-8")
    config = ChannelAgentConfig(
        server_url="http://127.0.0.1:18443",
        agent_id="agent-real-pdd",
        device_id="device-real-pdd",
        runtime_mode="STAGING",
        development_profile="STANDARD",
        browser_enabled=True,
        pdd_login_observation_enabled=True,
        pdd_login_url="https://mms.pinduoduo.com/login/",
        pdd_customer_service_url="https://mms.pinduoduo.com/chat-merchant/index.html#",
        customer_assistant_enabled=True,
        message_observation_enabled=True,
        observation_stage=ObservationStage.AI_SUGGESTIONS,
        pdd_observation_evidence_path=evidence,
    )
    config_path = tmp_path / "config" / "agent.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")

    server = DesktopAssistantServer(data_root=tmp_path, config_path=config_path)
    bootstrap = server.bootstrap()

    assert bootstrap["browser"]["message_source"] == "REAL_PDD"  # type: ignore[index]
    assert bootstrap["browser"]["real_pdd_message_observation_enabled"] is True  # type: ignore[index]


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
        assert (
            tmp_path / "runtime" / "operator-safe-stop.request"
        ).read_text(encoding="ascii") == "pause\n"
    finally:
        server.stop()


def test_manual_replied_endpoint_requires_intent_and_marks_only_current_revision(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    server = DesktopAssistantServer(data_root=tmp_path)
    server.event_journal.update_snapshots((AgentAssistantSnapshot(
        agent_id="agent-1",
        device_id="device-1",
        store_id="store-1",
        conversation_id="conversation/a",
        revision=7,
        status="WAITING_APPROVAL",
        turn_id="turn-1",
        decision_id="decision-1",
        request_id="request-1",
        customer_reference="customer-1",
        current_question="privacy filtered question",
        action="REPLY",
        reply_content="answer",
        risk_level="LOW",
        updated_at=now,
        expires_at=now + timedelta(minutes=5),
    ),))
    try:
        server.start()
        opener, origin, csrf = _authenticated_client(server)
        url = f"{origin}/local-api/v1/conversations/conversation%2Fa/replied"
        blocked = Request(
            url,
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
            },
        )
        with pytest.raises(HTTPError) as forbidden:
            opener.open(blocked, timeout=2)  # noqa: S310
        assert forbidden.value.code == 403

        request = Request(
            url,
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
                "X-Channel-Agent-Intent": "HUMAN_CONFIRMED_CONVERSATION_REPLIED",
            },
        )
        with opener.open(request, timeout=2) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
        assert result["replied_revision"] == 7
        assert server.assistant_feed()["conversations"][0]["attentionLevel"] == "NONE"
    finally:
        server.stop()


def test_pdd_window_launch_requires_explicit_human_intent_and_starts_no_observer(
    tmp_path: Path,
) -> None:
    launched: list[bool] = []
    server = DesktopAssistantServer(
        data_root=tmp_path,
        pdd_workspace_launch_handler=lambda: (
            launched.append(True)
            or {
                "status": "OPENING",
                "browser_status": "WAITING_LOGIN",
                "pdd_login_state": "PDD_LOGIN_PAGE",
            }
        ),
        pdd_workspace_status_handler=lambda: {
            "status": "READY",
            "browser_status": "READY",
            "pdd_login_state": "CUSTOMER_SERVICE_READY",
        },
    )
    try:
        server.start()
        opener, origin, csrf = _authenticated_client(server)
        blocked = Request(
            f"{origin}/local-api/v1/browser/pdd/open",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
            },
        )
        with pytest.raises(HTTPError) as forbidden:
            opener.open(blocked, timeout=2)  # noqa: S310
        assert forbidden.value.code == 403
        assert launched == []

        request = Request(
            f"{origin}/local-api/v1/browser/pdd/open",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
                "X-Channel-Agent-Intent": "HUMAN_REQUESTED_PDD_WINDOW",
            },
        )
        with opener.open(request, timeout=2) as response:  # noqa: S310
            assert response.status == 202
            result = json.loads(response.read().decode("utf-8"))
        assert launched == [True]
        assert result["human_login_required"] is True
        assert result["observer_started"] is False
        assert result["real_send_enabled"] is False

        with opener.open(f"{origin}/local-api/v1/bootstrap", timeout=2) as response:  # noqa: S310
            bootstrap = json.loads(response.read().decode("utf-8"))
        assert bootstrap["browser"] == {
            "status": "READY",
            "pdd_login_state": "CUSTOMER_SERVICE_READY",
            "pdd_workspace_launch_available": True,
            "pdd_workspace_refresh_available": True,
            "observer_status": "DISABLED",
            "observer_restart_available": False,
            "message_source": "DISABLED",
            "real_pdd_message_observation_enabled": False,
        }
        assert bootstrap["assistant_event_cursor"] == 0
    finally:
        server.stop()


def test_pdd_refresh_and_observer_restart_require_local_human_intent(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "runtime" / "channel-agent-state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps({
            "message_observation_enabled": True,
            "pdd_login_state": "CUSTOMER_SERVICE_READY",
            "identity_status": "ACTIVE",
            "observer_status": "SESSION_LIMIT_REACHED",
        }),
        encoding="utf-8",
    )
    refreshes: list[bool] = []
    server = DesktopAssistantServer(
        data_root=tmp_path,
        pdd_workspace_status_handler=lambda: (
            refreshes.append(True)
            or {
                "status": "READY",
                "browser_status": "READY",
                "pdd_login_state": "CUSTOMER_SERVICE_READY",
            }
        ),
    )
    try:
        server.start()
        opener, origin, csrf = _authenticated_client(server)

        for path in ("browser/pdd/refresh", "observer/pdd/restart"):
            blocked = Request(
                f"{origin}/local-api/v1/{path}", data=b"{}", method="POST",
                headers={"Origin": origin, "X-Channel-Agent-CSRF": csrf},
            )
            with pytest.raises(HTTPError) as forbidden:
                opener.open(blocked, timeout=2)  # noqa: S310
            assert forbidden.value.code == 403

        refresh = Request(
            f"{origin}/local-api/v1/browser/pdd/refresh", data=b"{}", method="POST",
            headers={
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
                "X-Channel-Agent-Intent": "HUMAN_CONFIRMED_PDD_WORKSPACE_READY",
            },
        )
        with opener.open(refresh, timeout=2) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["pdd_login_state"] == "CUSTOMER_SERVICE_READY"
        assert payload["observer_started"] is False
        assert payload["real_send_enabled"] is False
        assert refreshes == [True]

        restart = Request(
            f"{origin}/local-api/v1/observer/pdd/restart", data=b"{}", method="POST",
            headers={
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
                "X-Channel-Agent-Intent": "HUMAN_CONFIRMED_PDD_OBSERVER_RESTART",
            },
        )
        with opener.open(restart, timeout=2) as response:  # noqa: S310
            first = json.loads(response.read().decode("utf-8"))
        with opener.open(restart, timeout=2) as response:  # noqa: S310
            second = json.loads(response.read().decode("utf-8"))
        assert first["status"] == "RESTART_REQUESTED"
        assert second["status"] == "ALREADY_REQUESTED"
        assert first["real_send_enabled"] is False
        assert (tmp_path / "runtime" / "pdd-observer-restart.request").is_file()
    finally:
        server.stop()


def test_desktop_projects_and_toggles_authoritative_controlled_auto(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "channel-agent-state.json").write_text(
        json.dumps({
            "identity_status": "ACTIVE",
            "pdd_login_state": "CUSTOMER_SERVICE_READY",
            "observer_status": "OBSERVING",
            "active_store_id": "c-store-1",
            "pdd_store_id": "328616090",
        }),
        encoding="utf-8",
    )
    (runtime / "controlled-auto-public-status.json").write_text(
        json.dumps({
            "schema_version": "controlled-auto-public-status.v1",
            "runtime_mode": "PRODUCTION_AUTO",
            "production_real_send_enabled": True,
            "controlled_store_auto_enabled": True,
            "policy_mode": "AUTO_ALL_MESSAGES_V1",
            "kill_switch_enabled": False,
            "ai_cs_store_id": "c-store-1",
            "platform_store_id": "328616090",
            "state_revision": 9,
            "state_reason": "USER_ENABLED",
            "runner_active": True,
            "control_error_code": None,
            "updated_at": datetime.now(UTC).isoformat(),
        }),
        encoding="utf-8",
    )
    server = DesktopAssistantServer(data_root=tmp_path)
    try:
        server.start()
        opener, origin, csrf = _authenticated_client(server)
        with opener.open(f"{origin}/local-api/v1/bootstrap", timeout=2) as response:  # noqa: S310
            bootstrap = json.loads(response.read().decode("utf-8"))
        assert bootstrap["safety"]["auto_reply"] is True
        assert bootstrap["safety"]["real_send_enabled"] is True
        assert bootstrap["safety"]["controlled_auto"]["control_available"] is True

        blocked = Request(
            f"{origin}/local-api/v1/runtime/controlled-auto-toggle",
            data=b'{"target_enabled":false}',
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
            },
        )
        with pytest.raises(HTTPError) as forbidden:
            opener.open(blocked, timeout=2)  # noqa: S310
        assert forbidden.value.code == 403

        request = Request(
            f"{origin}/local-api/v1/runtime/controlled-auto-toggle",
            data=b'{"target_enabled":false}',
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
                "X-Channel-Agent-Intent": "HUMAN_CONFIRMED_CONTROLLED_AUTO_TOGGLE",
            },
        )
        with opener.open(request, timeout=2) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
        assert result == {
            "schema_version": "controlled-auto-toggle-response.v1",
            "status": "TOGGLE_REQUESTED",
            "target_enabled": False,
        }
        queued = json.loads(
            (runtime / "controlled-auto-toggle.request").read_text(encoding="utf-8")
        )
        assert queued["target_enabled"] is False
        assert queued["human_intent"] is True
    finally:
        server.stop()


def test_desktop_separates_desired_auto_from_effective_runtime_after_reboot(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    stale = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    (runtime / "controlled-auto-public-status.json").write_text(
        json.dumps(
            {
                "schema_version": "controlled-auto-public-status.v1",
                "runtime_mode": "PRODUCTION_AUTO",
                "production_real_send_enabled": True,
                "controlled_store_auto_enabled": True,
                "policy_mode": "AUTO_ALL_MESSAGES_V1",
                "kill_switch_enabled": False,
                "ai_cs_store_id": "c-store-1",
                "platform_store_id": "328616090",
                "runner_active": True,
                "control_error_code": "PROCESS_OLD_FAILURE",
                "updated_at": stale,
            }
        ),
        encoding="utf-8",
    )
    (runtime / "current-page-production-supervisor.json").write_text(
        json.dumps(
            {
                "schema_version": "current-page-auto-production-status.v1",
                "supervisor_active": True,
                "supervisor_state": "WAITING_FOR_CURRENT_PDD_CONVERSATION",
                "desired_auto_reply_enabled": True,
                "observation_scope": "CURRENT_ACTIVE_CONVERSATION_ONLY",
                "automatic_navigation_enabled": False,
                "components": {
                    "agent": True,
                    "ai_gateway": True,
                    "ai_platform": True,
                    "host": True,
                    "bridge": False,
                    "runner": False,
                },
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    status = DesktopAssistantServer(data_root=tmp_path)._controlled_auto_status()

    assert status["desired_auto_reply_enabled"] is True
    assert status["auto_reply_running"] is False
    assert status["control_available"] is False
    assert status["supervisor_active"] is True
    assert status["supervisor_state"] == "WAITING_FOR_CURRENT_PDD_CONVERSATION"
    assert status["observation_scope"] == "CURRENT_ACTIVE_CONVERSATION_ONLY"
    assert status["automatic_navigation_enabled"] is False
    assert status["control_error_code"] is None


def test_desktop_queues_human_controlled_auto_repair_for_live_store(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "channel-agent-state.json").write_text(
        json.dumps({
            "identity_status": "ACTIVE",
            "pdd_login_state": "CUSTOMER_SERVICE_READY",
            "observer_status": "OBSERVING",
            "active_store_id": "c-store-1",
            "pdd_store_id": "328616090",
        }),
        encoding="utf-8",
    )
    server = DesktopAssistantServer(data_root=tmp_path)
    try:
        server.start()
        opener, origin, csrf = _authenticated_client(server)
        blocked = Request(
            f"{origin}/local-api/v1/runtime/controlled-auto-repair",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
            },
        )
        with pytest.raises(HTTPError) as forbidden:
            opener.open(blocked, timeout=2)  # noqa: S310
        assert forbidden.value.code == 403

        request = Request(
            f"{origin}/local-api/v1/runtime/controlled-auto-repair",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
                "X-Channel-Agent-Intent": "HUMAN_REQUESTED_CONTROLLED_AUTO_REPAIR",
            },
        )
        with opener.open(request, timeout=2) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
        assert result == {
            "schema_version": "controlled-auto-repair-response.v1",
            "status": "REPAIR_REQUESTED",
        }
        queued = json.loads(
            (runtime / "controlled-auto-repair.request").read_text(
                encoding="utf-8"
            )
        )
        assert queued["ai_cs_store_id"] == "c-store-1"
        assert queued["platform_store_id"] == "328616090"
        assert queued["human_intent"] is True
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
