from __future__ import annotations

from fastapi.testclient import TestClient

from channel_engine.app import create_app
from channel_engine.config import Settings


def test_observability_api_and_read_only_console(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{(tmp_path / 'observability.sqlite3').as_posix()}"
        )
    )
    with TestClient(app) as client:
        intake = client.post(
            "/v1/fake-channel/messages",
            json={
                "conversation_external_ref": "ops-api-conversation",
                "external_message_id": "ops-api-message",
                "text": "confidential customer phrase must not appear",
                "sender": "private-customer-id",
            },
        )
        assert intake.status_code == 200
        message_id = intake.json()["message_id"]

        runtime = client.get("/ops/runtime/status")
        events = client.get("/ops/events", params={"trace_id": message_id})
        trace = client.get(f"/ops/traces/{message_id}")
        approvals = client.get(
            "/ops/approvals", params={"waiting_only": "true"}
        )
        review = client.get(
            f"/ops/approvals/{intake.json()['decision_id']}/review"
        )
        executions = client.get("/ops/executions")
        snapshot = client.get("/ops/console/snapshot")
        console = client.get("/ops/console")

        assert runtime.status_code == 200
        assert runtime.json()["event_count"] >= 6
        assert events.status_code == 200
        assert events.json()["count"] >= 5
        assert trace.status_code == 200
        assert trace.json()["why_stopped"] == "WAITING_APPROVAL"
        assert trace.json()["next_step"] == "等待人工批准或拒绝"
        assert approvals.status_code == 200
        assert len(approvals.json()) == 1
        assert review.status_code == 200
        assert review.json()["customer_question"] == (
            "confidential customer phrase must not appear"
        )
        assert review.json()["knowledge_sources"] == []
        assert review.json()["knowledge_source_status"] == "NOT_PROVIDED"
        assert review.json()["risk_level"] == "UNSPECIFIED"
        assert executions.json() == []
        assert snapshot.status_code == 200
        assert console.status_code == 200
        assert "AI-CS 智能客服运营控制中心" in console.text
        assert "必须人工审核" in console.text
        assert "自动执行已关闭" in console.text
        assert "click send" not in console.text.casefold()

        serialized = events.text.casefold()
        assert "confidential customer phrase" not in serialized
        assert "private-customer-id" not in serialized
        assert "cookie" not in serialized
        assert "password" not in serialized
        assert "bearer " not in serialized


def test_trace_lookup_returns_404_for_unknown_identifier(tmp_path) -> None:
    app = create_app(
        Settings(database_url=f"sqlite:///{(tmp_path / 'empty.sqlite3').as_posix()}")
    )
    with TestClient(app) as client:
        response = client.get("/ops/traces/not-a-real-id")
    assert response.status_code == 404


def test_channel_connection_and_bounded_runtime_recovery_are_logged(tmp_path) -> None:
    app = create_app(
        Settings(database_url=f"sqlite:///{(tmp_path / 'recovery.sqlite3').as_posix()}")
    )
    with TestClient(app) as client:
        assert client.post("/runtime/v1/start").status_code == 200
        app.state.runtime_browser.simulate_failure("SYNTHETIC_PAGE_CRASH")
        pulse = client.post("/runtime/v1/heartbeat")
        assert pulse.json()["overall"] == "UNHEALTHY"
        recovered = client.post(
            "/runtime/v1/recover", json={"component": "BROWSER"}
        )
        assert recovered.status_code == 200
        assert recovered.json()["state"] == "RECOVERED"

        assert client.get(
            "/ops/events", params={"event_type": "CHANNEL_CONNECTED"}
        ).json()["count"] == 1
        assert client.get(
            "/ops/events", params={"event_type": "RECOVERY_STARTED"}
        ).json()["count"] == 1
        assert client.get(
            "/ops/events", params={"event_type": "RECOVERY_COMPLETED"}
        ).json()["count"] == 1
