from __future__ import annotations

import json
from datetime import UTC, datetime
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from threading import Thread
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import pytest

from channel_agent.config import ChannelAgentConfig, save_agent_config
from channel_agent.binding import AgentRuntimeBinding
from channel_agent.desktop import DesktopAssistantServer
from channel_agent.diagnostics import ChannelAgentOperationsCenter, OperationsCenterError
from channel_agent.identity import AgentIdentityStatus


class _HealthyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        payload = b'{"status":"healthy"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


@pytest.fixture
def healthy_origin():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthyHandler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def _config(path: Path, origin: str, *, ai_origin: str | None = None) -> ChannelAgentConfig:
    config = ChannelAgentConfig(
        server_url=origin,
        ai_cs_platform_url=ai_origin,
        agent_id="agent-doctor-001",
        device_id="device-doctor-001",
        runtime_mode="MOCK",
    )
    save_agent_config(path, config)
    return config


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


def test_doctor_identifies_missing_ai_cs_address_without_password_language(
    tmp_path: Path, healthy_origin: str
) -> None:
    path = tmp_path / "config" / "agent.json"
    _config(path, healthy_origin)
    center = ChannelAgentOperationsCenter(data_root=tmp_path, config_path=path)

    report = center.doctor()
    ai = next(item for item in report["components"] if item["component"] == "AI-CS身份服务")

    assert report["overall"] == "BLOCKED"
    assert ai["error_code"] == "AI_CS_ADDRESS_MISSING"
    assert ai["repairable"] is True
    assert "密码" not in json.dumps(ai, ensure_ascii=False)


def test_onboarding_blockers_allow_login_and_are_sequenced(
    tmp_path: Path, healthy_origin: str
) -> None:
    path = tmp_path / "config" / "agent.json"
    _config(path, healthy_origin, ai_origin=healthy_origin)
    center = ChannelAgentOperationsCenter(data_root=tmp_path, config_path=path)

    report = center.doctor()
    identity = next(item for item in report["components"] if item["component"] == "设备注册与身份绑定")
    store = next(item for item in report["components"] if item["component"] == "当前店铺绑定")

    assert report["overall"] == "BLOCKED"
    assert report["login_allowed"] is True
    assert identity["scope"] == "ONBOARDING"
    assert identity["error_code"] == "CHANNEL_ENGINE_IDENTITY_UNBOUND"
    assert "第一次使用" in identity["reason"]
    assert store["scope"] == "ONBOARDING"
    assert store["technical"]["dependsOn"] == "CHANNEL_ENGINE_IDENTITY_UNBOUND"


def test_config_validation_rejects_sensitive_locked_and_unconfirmed_advanced_fields(
    tmp_path: Path, healthy_origin: str
) -> None:
    path = tmp_path / "config" / "agent.json"
    _config(path, healthy_origin, ai_origin=healthy_origin)
    center = ChannelAgentOperationsCenter(data_root=tmp_path, config_path=path)

    with pytest.raises(OperationsCenterError) as sensitive:
        center.validate_changes({"changes": {"api_token": "forbidden"}})
    assert sensitive.value.code == "SENSITIVE_FIELD_REJECTED"
    with pytest.raises(OperationsCenterError) as locked:
        center.validate_changes({"changes": {"real_send_enabled": True}})
    assert locked.value.code == "SAFETY_LOCKED_FIELD"
    with pytest.raises(OperationsCenterError) as advanced:
        center.validate_changes({"changes": {"runtime_mode": "SIMULATOR"}})
    assert advanced.value.code == "ADVANCED_CONFIRMATION_REQUIRED"


def test_config_save_is_atomic_backed_up_and_requests_browser_preserving_reload(
    tmp_path: Path, healthy_origin: str
) -> None:
    path = tmp_path / "config" / "agent.json"
    _config(path, healthy_origin, ai_origin=healthy_origin)
    center = ChannelAgentOperationsCenter(data_root=tmp_path, config_path=path)

    result = center.save_changes({"changes": {"heartbeat_interval_seconds": 45.0}})

    assert result["saved"] is True
    assert result["reload_requested"] is True
    assert (tmp_path / "runtime" / "config-backups" / "agent.previous.json").is_file()
    reload_request = json.loads((tmp_path / "runtime" / "reload.request").read_text(encoding="utf-8"))
    assert reload_request["preserve_browser"] is True
    assert (
        tmp_path / "runtime" / "restart-agent.request"
    ).read_text(encoding="ascii") == "restart-preserve-assistant\n"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["manual_approval_required"] is True
    assert saved["auto_reply_enabled"] is False
    assert saved["real_send_enabled"] is False
    assert saved["real_platform_activation_allowed"] is False


def test_local_api_requires_same_origin_and_explicit_human_intent(
    tmp_path: Path, healthy_origin: str
) -> None:
    path = tmp_path / "config" / "agent.json"
    _config(path, healthy_origin, ai_origin=healthy_origin)
    server = DesktopAssistantServer(data_root=tmp_path, config_path=path)
    try:
        server.start()
        opener, origin, csrf = _authenticated_client(server)
        doctor = json.loads(opener.open(f"{origin}/local-api/v1/doctor", timeout=2).read())  # noqa: S310
        assert doctor["schema_version"] == "channel-agent-doctor.v1"

        request = Request(
            f"{origin}/local-api/v1/config",
            data=json.dumps({"changes": {"heartbeat_interval_seconds": 45}}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        with pytest.raises(HTTPError) as missing_intent:
            opener.open(request, timeout=2)  # noqa: S310
        assert missing_intent.value.code == 403

        request.add_header("X-Channel-Agent-Intent", "HUMAN_CONFIRMED_CONFIGURATION")
        request.add_header("X-Channel-Agent-CSRF", csrf)
        with opener.open(request, timeout=2) as response:  # noqa: S310
            assert response.status == 202

        enrollment = Request(
            f"{origin}/local-api/v1/enrollment",
            data=json.dumps({"binding_code": "A" * 32}).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        with pytest.raises(HTTPError) as missing_binding_intent:
            opener.open(enrollment, timeout=2)  # noqa: S310
        assert missing_binding_intent.value.code == 403
    finally:
        server.stop()


def test_repair_is_bounded_and_never_changes_safety_locks(
    tmp_path: Path, healthy_origin: str
) -> None:
    path = tmp_path / "config" / "agent.json"
    _config(path, healthy_origin, ai_origin=healthy_origin)
    center = ChannelAgentOperationsCenter(data_root=tmp_path, config_path=path)

    first = center.start_repair()
    with pytest.raises(OperationsCenterError) as active:
        center.start_repair()
    assert active.value.code == "REPAIR_ALREADY_RUNNING"
    for _ in range(100):
        status = center.repair_status(first["repair_id"])
        if status["status"] != "RUNNING":
            break
        import time
        time.sleep(0.01)
    assert status["status"] == "RELOAD_REQUESTED"
    config = json.loads(path.read_text(encoding="utf-8"))
    assert config["manual_approval_required"] is True
    assert config["auto_reply_enabled"] is False
    assert config["real_send_enabled"] is False


def test_enrollment_persists_only_public_binding_and_never_the_one_time_code(
    tmp_path: Path, healthy_origin: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config" / "agent.json"
    _config(path, healthy_origin, ai_origin=healthy_origin)
    now = datetime.now(UTC)
    binding = AgentRuntimeBinding(
        binding_id="agent-binding:agent-doctor-001:device-doctor-001",
        binding_revision=1,
        agent_id="agent-doctor-001",
        device_id="device-doctor-001",
        user_id="user-001",
        store_ids=("STORE-A",),
        authorized_store_ids=("STORE-A",),
        active_store_id=None,
        identity_status=AgentIdentityStatus.BOUND,
        production_eligible=False,
        created_at=now,
        updated_at=now,
    )

    class FakeChannelEngineClient:
        def __init__(self, _config: ChannelAgentConfig) -> None:
            pass

        def register(self, **_kwargs: object) -> None:
            return None

        def enroll(self, _binding_code: str) -> SimpleNamespace:
            return SimpleNamespace(binding=binding)

        def close(self) -> None:
            return None

    monkeypatch.setattr("channel_agent.desktop.ChannelEngineClient", FakeChannelEngineClient)
    server = DesktopAssistantServer(data_root=tmp_path, config_path=path)
    binding_code = "A" * 32
    try:
        server.start()
        opener, origin, csrf = _authenticated_client(server)
        request = Request(
            f"{origin}/local-api/v1/enrollment",
            data=json.dumps({"binding_code": binding_code}).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Channel-Agent-CSRF": csrf,
                "X-Channel-Agent-Intent": "HUMAN_CONFIRMED_DEVICE_BINDING",
            },
        )
        with opener.open(request, timeout=2) as response:  # noqa: S310
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert binding_code not in body
            assert json.loads(body)["identity_status"] == "BOUND"
    finally:
        server.stop()

    persisted = "\n".join(
        item.read_text(encoding="utf-8")
        for item in (tmp_path / "runtime").glob("*.json")
    )
    assert binding_code not in persisted
    assert '"authorized_store_ids"' in persisted
