import pytest
from fastapi.testclient import TestClient

from channel_engine.config import Settings
from channel_engine.production_app import create_host_control_app


def test_production_host_exposes_health_without_legacy_or_fake_routes(tmp_path) -> None:
    application = create_host_control_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'host.sqlite3'}")
    )
    with TestClient(application) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["agent_control_protocol"] == "2.1"

        assert client.get("/channel-agent/v1/admin/agents").status_code == 404
        assert client.post("/v1/fake-channel/messages", json={}).status_code == 404
        assert client.get("/pilot/status").status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    (
        ("POST", "/channel-agent/v1/agents/register"),
        ("POST", "/channel-agent/v1/agents/agent-001/heartbeat"),
        ("GET", "/channel-agent/v1/agents/agent-001/config"),
        ("POST", "/channel-agent/v1/agents/agent-001/enroll"),
        ("GET", "/channel-agent/v1/admin/agents"),
        ("POST", "/channel-agent/v1/admin/enrollment-grants"),
    ),
)
def test_production_host_never_mounts_legacy_agent_v1(
    tmp_path, method: str, path: str
) -> None:
    application = create_host_control_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'host.sqlite3'}")
    )
    with TestClient(application) as client:
        response = client.request(method, path, json={} if method == "POST" else None)
    assert response.status_code == 404
