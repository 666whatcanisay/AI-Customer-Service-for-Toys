from __future__ import annotations

from fastapi.testclient import TestClient

from channel_engine.app import create_app
from channel_engine.config import Settings


def test_runtime_status_lifecycle_heartbeat_recovery_api(tmp_path) -> None:
    application = create_app(
        Settings(
            database_url=f"sqlite:///{(tmp_path / 'runtime-api.sqlite3').as_posix()}"
        )
    )

    with TestClient(application) as client:
        initial = client.get("/runtime/v1/status")
        assert initial.status_code == 200
        assert initial.json()["runtime"]["state"] == "STOPPED"
        assert initial.json()["browser"]["health"] == "UNHEALTHY"

        started = client.post("/runtime/v1/start")
        assert started.status_code == 200
        assert started.json()["runtime"]["state"] == "RUNNING"
        assert started.json()["health"] == "HEALTHY"
        assert started.json()["browser"]["process_running"] is True
        assert started.json()["browser"]["page_available"] is True
        assert started.json()["execution"]["approval_required"] is True
        assert started.json()["execution"]["receipt_required"] is True
        assert started.json()["execution"]["unknown_auto_retry_allowed"] is False
        assert started.json()["approval"]["execution_without_approval_allowed"] is False
        assert application.state.runtime_browser.health_check().real_browser_connected is False

        intake = client.post(
            "/v1/fake-channel/messages",
            json={
                "conversation_external_ref": "runtime-dashboard-conversation",
                "external_message_id": "runtime-dashboard-message",
                "text": "fake reliability status request",
            },
        )
        assert intake.status_code == 200
        waiting = client.get("/runtime/v1/status").json()
        assert waiting["approval"]["waiting"] == 1

        enqueued = client.post(
            f"/v1/decisions/{intake.json()['decision_id']}/approve",
            json={"operator": "runtime-human-operator"},
        )
        assert enqueued.status_code == 202
        pending = client.get("/runtime/v1/status").json()
        assert pending["execution"]["pending"] == 1
        result = application.state.execution_worker.run_once()
        assert result is not None
        completed = client.get("/runtime/v1/status").json()
        assert completed["execution"]["success"] == 1
        assert completed["execution"]["terminal_without_receipt"] == 0

        application.state.runtime_browser.simulate_failure("FAKE_PAGE_CRASHED")
        heartbeat = client.post("/runtime/v1/heartbeat")
        assert heartbeat.status_code == 200
        assert heartbeat.json()["overall"] == "UNHEALTHY"
        assert client.get("/runtime/v1/status").json()["runtime"]["state"] == (
            "DEGRADED"
        )

        recovered = client.post(
            "/runtime/v1/recover", json={"component": "BROWSER"}
        )
        assert recovered.status_code == 200
        assert recovered.json()["state"] == "RECOVERED"
        assert client.get("/runtime/v1/status").json()["runtime"]["state"] == (
            "RUNNING"
        )

        stopped = client.post("/runtime/v1/stop")
        assert stopped.status_code == 200
        assert stopped.json()["runtime"]["state"] == "STOPPED"


def test_runtime_recovery_requires_degraded_state(tmp_path) -> None:
    application = create_app(
        Settings(
            database_url=f"sqlite:///{(tmp_path / 'runtime-api-conflict.sqlite3').as_posix()}"
        )
    )
    with TestClient(application) as client:
        response = client.post("/runtime/v1/recover", json={})
    assert response.status_code == 409
    assert response.json()["detail"] == "runtime recovery requires DEGRADED state"
