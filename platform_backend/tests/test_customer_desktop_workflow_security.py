from dataclasses import replace
import hashlib
import hmac
import json

import httpx
import pytest

from app.config import get_settings
from app.desktop_agent.upstream import (
    ChannelAgentNotConfigured,
    HttpChannelAgentUpstream,
    _canonical_service_request,
)


def test_remote_plain_http_and_missing_service_identity_fail_closed() -> None:
    settings = replace(
        get_settings(),
        channel_agent_integration_enabled=True,
        channel_agent_server_url="http://10.10.10.8:18021",
        channel_agent_service_id="ai-cs",
        channel_agent_service_key_id="service-key-001",
        channel_agent_service_credential_reference="wincred://AI-CS/test",
    )
    with pytest.raises(ChannelAgentNotConfigured, match="requires HTTPS"):
        HttpChannelAgentUpstream(settings).list_agents()

    settings = replace(
        settings,
        channel_agent_server_url="http://127.0.0.1:18021",
        channel_agent_service_credential_reference=None,
    )
    with pytest.raises(ChannelAgentNotConfigured, match="incomplete"):
        HttpChannelAgentUpstream(settings).list_agents()


def test_service_request_uses_v21_hmac_and_never_keeps_secret_on_adapter(monkeypatch) -> None:
    secret_value = b"opaque-channel-agent-service-secret-value"
    settings = replace(
        get_settings(),
        channel_agent_integration_enabled=True,
        channel_agent_server_url="http://127.0.0.1:18021",
        channel_agent_service_id="ai-cs",
        channel_agent_service_key_id="service-key-001",
        channel_agent_service_credential_reference="wincred://AI-CS/test",
    )
    captured: dict[str, object] = {}

    def fake_request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return httpx.Response(200, json={
            "protocol_version": "1.0", "items": [], "count": 0,
            "server_time": "2026-08-06T08:00:00Z",
            "authoritative_source": "CHANNEL_ENGINE_HOST_CONTROL",
        })

    monkeypatch.setattr(httpx, "request", fake_request)
    upstream = HttpChannelAgentUpstream(
        settings,
        credential_resolver=lambda _reference: secret_value,
        clock=lambda: 1_786_089_600,
    )
    assert upstream.list_agents().count == 0
    assert captured["url"] == "http://127.0.0.1:18021/channel-agent/v2/service/agents"
    headers = captured["headers"]
    assert headers["X-Channel-Agent-Control"] == "2.1"
    assert "X-Operator-Session-Reference" not in headers
    canonical = _canonical_service_request(
        "ai-cs",
        "service-key-001",
        "GET",
        "/channel-agent/v2/service/agents",
        1_786_089_600,
        headers["X-Channel-Nonce"],
        hashlib.sha256(b"").hexdigest(),
    )
    assert hmac.compare_digest(
        headers["X-Channel-Signature"],
        hmac.new(secret_value, canonical, hashlib.sha256).hexdigest(),
    )
    assert secret_value.decode() not in repr(upstream.__dict__)


def test_https_service_request_uses_the_pinned_channel_engine_ca(
    monkeypatch, tmp_path
) -> None:
    certificate = tmp_path / "channel-engine-ca.pem"
    certificate.write_text("test-ca", encoding="ascii")
    settings = replace(
        get_settings(),
        channel_agent_integration_enabled=True,
        channel_agent_server_url="https://10.10.10.8:18443",
        channel_agent_service_id="ai-cs",
        channel_agent_service_key_id="service-key-001",
        channel_agent_service_credential_reference="wincred://AI-CS/test",
        channel_agent_ca_certificate_file=str(certificate),
    )
    captured: dict[str, object] = {}

    def fake_request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return httpx.Response(
            200,
            json={
                "protocol_version": "1.0",
                "items": [],
                    "count": 0,
                    "server_time": "2026-08-06T08:00:00Z",
                    "authoritative_source": "CHANNEL_ENGINE_HOST_CONTROL",
                },
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    HttpChannelAgentUpstream(
        settings,
        credential_resolver=lambda _reference: b"x" * 32,
    ).list_agents()
    assert captured["verify"] == str(certificate)


def test_https_service_request_without_ca_fails_closed() -> None:
    settings = replace(
        get_settings(),
        channel_agent_integration_enabled=True,
        channel_agent_server_url="https://10.10.10.8:18443",
        channel_agent_service_id="ai-cs",
        channel_agent_service_key_id="service-key-001",
        channel_agent_service_credential_reference="wincred://AI-CS/test",
        channel_agent_ca_certificate_file=None,
    )
    with pytest.raises(ChannelAgentNotConfigured, match="CA certificate"):
        HttpChannelAgentUpstream(
            settings,
            credential_resolver=lambda _reference: b"x" * 32,
        ).list_agents()


def test_host_pairing_rotation_is_signed_human_intent_and_no_store(
    monkeypatch,
) -> None:
    settings = replace(
        get_settings(),
        channel_agent_integration_enabled=True,
        channel_agent_server_url="http://127.0.0.1:18443",
        channel_agent_service_id="ai-cs",
        channel_agent_service_key_id="service-key-001",
        channel_agent_service_credential_reference="wincred://AI-CS/test",
    )
    captured: dict[str, object] = {}

    def fake_request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return httpx.Response(
            201,
            json={
                "control_protocol_version": "2.1",
                "host_id": "host-001",
                "pairing_code": "7K3M9Q2X4T8R",
                "expires_at": "2026-08-06T08:05:00Z",
                "display_once": True,
            },
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    result = HttpChannelAgentUpstream(
        settings,
        credential_resolver=lambda _reference: b"x" * 32,
        clock=lambda: 1_786_089_600,
    ).rotate_host_pairing_code(reason="新客服电脑首次安装连接可信主机")

    assert result.pairing_code == "7K3M9Q2X4T8R"
    assert "7K3M9Q2X4T8R" not in repr(result)
    assert captured["method"] == "POST"
    assert str(captured["url"]).endswith(
        "/channel-agent/v2/service/pairing-codes/rotate"
    )
    assert json.loads(captured["content"].decode("utf-8")) == {
        "control_protocol_version": "2.1",
        "reason": "新客服电脑首次安装连接可信主机",
        "confirmation_phrase": "确认重新生成主机连接码",
    }
    headers = captured["headers"]
    assert headers["X-Operator-Intent"] == (
        "HUMAN_CONFIRMED_HOST_PAIRING_CODE_ROTATION"
    )
    assert headers["X-Channel-Agent-Control"] == "2.1"
