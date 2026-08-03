from __future__ import annotations

from fastapi.testclient import TestClient

from channel_engine.app import create_app
from channel_engine.config import Settings
from channel_engine.execution import FakeExecutor


def test_foundation_api_full_fake_flow(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'api.sqlite3').as_posix()}"
    )
    executor = FakeExecutor()
    application = create_app(settings=settings, executor=executor)

    with TestClient(application) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {
            "status": "ok",
            "service": "ai-cs-channel-execution-engine",
            "environment": "foundation",
            "real_channel_enabled": False,
            "real_gateway_enabled": False,
            "browser_execution_enabled": False,
            "human_approval_required": True,
            "unknown_auto_retry_enabled": False,
        }

        intake = client.post(
            "/v1/fake-channel/messages",
            json={
                "conversation_external_ref": "api-conversation-1",
                "external_message_id": "api-message-1",
                "text": "hello from the fake channel",
            },
        )
        assert intake.status_code == 200
        body = intake.json()
        assert body["decision_state"] == "WAITING_APPROVAL"
        assert executor.call_count == 0

        decision = client.get(f"/v1/decisions/{body['decision_id']}")
        assert decision.status_code == 200
        assert decision.json()["requires_approval"] is True

        execution = client.post(
            f"/v1/decisions/{body['decision_id']}/approve",
            json={"operator": "api-human-operator"},
        )
        assert execution.status_code == 200
        assert execution.json()["execution_state"] == "SUCCESS"
        assert executor.call_count == 1


def test_unknown_decision_returns_404(tmp_path) -> None:
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'api-404.sqlite3').as_posix()}"
        )
    )
    with TestClient(application) as client:
        response = client.get("/v1/decisions/decision-missing")
    assert response.status_code == 404
