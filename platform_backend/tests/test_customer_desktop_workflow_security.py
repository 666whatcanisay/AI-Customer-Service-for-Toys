from dataclasses import replace

import httpx
import pytest

from app.config import get_settings
from app.desktop_agent.upstream import ChannelAgentNotConfigured, HttpChannelAgentUpstream


def test_remote_plain_http_and_multiline_session_reference_fail_closed(tmp_path) -> None:
    secret = tmp_path / "operator-session.txt"
    secret.write_text("opaque-session\nsecond-line", encoding="utf-8")
    settings = replace(
        get_settings(),
        channel_agent_integration_enabled=True,
        channel_agent_server_url="http://10.10.10.8:18021",
        channel_agent_operator_session_file=str(secret),
    )
    with pytest.raises(ChannelAgentNotConfigured, match="requires HTTPS"):
        HttpChannelAgentUpstream(settings).list_agents()

    settings = replace(settings, channel_agent_server_url="http://127.0.0.1:18021")
    with pytest.raises(ChannelAgentNotConfigured, match="session reference is invalid"):
        HttpChannelAgentUpstream(settings).list_agents()


def test_operator_session_is_read_from_file_and_never_kept_on_adapter(monkeypatch, tmp_path) -> None:
    secret_value = "opaque-channel-agent-session"
    secret = tmp_path / "operator-session.txt"
    secret.write_text(secret_value, encoding="utf-8")
    settings = replace(
        get_settings(),
        channel_agent_integration_enabled=True,
        channel_agent_server_url="http://127.0.0.1:18021",
        channel_agent_operator_session_file=str(secret),
    )
    captured: dict[str, object] = {}

    def fake_request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return httpx.Response(200, json={
            "protocol_version": "1.0", "items": [], "count": 0,
            "server_time": "2026-08-06T08:00:00Z",
        })

    monkeypatch.setattr(httpx, "request", fake_request)
    upstream = HttpChannelAgentUpstream(settings)
    assert upstream.list_agents().count == 0
    assert captured["headers"] == {"X-Operator-Session-Reference": secret_value}
    assert secret_value not in repr(upstream.__dict__)
