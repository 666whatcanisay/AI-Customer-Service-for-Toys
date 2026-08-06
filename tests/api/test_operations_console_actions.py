from __future__ import annotations

from fastapi.testclient import TestClient

from channel_engine.app import create_app
from channel_engine.config import Settings


ACKNOWLEDGEMENT = "HUMAN_ACTION_REVIEWED_NO_AUTOMATIC_EXECUTION"


def _create_decision(client: TestClient, suffix: str) -> str:
    response = client.post(
        "/v1/fake-channel/messages",
        json={
            "conversation_external_ref": f"console-conversation-{suffix}",
            "external_message_id": f"console-message-{suffix}",
            "text": f"synthetic console message {suffix}",
        },
    )
    assert response.status_code == 200
    return response.json()["decision_id"]


def _command(action: str, decision_id: str, *, reason: str | None = None) -> dict:
    localized_action = {"APPROVE": "批准", "REJECT": "拒绝"}[action]
    return {
        "operator": "console.operator",
        "confirmation_text": f"{localized_action} {decision_id}",
        "acknowledgement": ACKNOWLEDGEMENT,
        "reason": reason,
    }


def test_console_approval_requires_explicit_phrase_and_only_queues_pending(tmp_path) -> None:
    app = create_app(
        Settings(database_url=f"sqlite:///{(tmp_path / 'approval.sqlite3').as_posix()}")
    )
    with TestClient(app) as client:
        decision_id = _create_decision(client, "approve")
        incorrect = _command("APPROVE", decision_id)
        incorrect["confirmation_text"] = "APPROVE wrong-decision"

        blocked = client.post(
            f"/ops/approvals/{decision_id}/approve", json=incorrect
        )
        assert blocked.status_code == 409
        assert client.get("/ops/executions").json() == []
        assert app.state.fake_executor.call_count == 0

        approved = client.post(
            f"/ops/approvals/{decision_id}/approve",
            json=_command("APPROVE", decision_id),
        )
        replay = client.post(
            f"/ops/approvals/{decision_id}/approve",
            json=_command("APPROVE", decision_id),
        )

        assert approved.status_code == 200
        assert replay.status_code == 200
        result = approved.json()
        assert result["execution_state"] == "PENDING"
        assert result["execution_id"] == replay.json()["execution_id"]
        assert result["automatic_execution_started"] is False
        assert result["real_send_triggered"] is False
        assert app.state.fake_executor.call_count == 0
        ledger = client.get("/ops/executions").json()
        assert len(ledger) == 1
        assert ledger[0]["state"] == "PENDING"
        assert client.get(
            "/ops/approvals", params={"waiting_only": "true"}
        ).json() == []


def test_console_rejection_creates_no_execution_and_kill_switch_blocks_approval(
    tmp_path,
) -> None:
    app = create_app(
        Settings(database_url=f"sqlite:///{(tmp_path / 'reject.sqlite3').as_posix()}")
    )
    with TestClient(app) as client:
        rejected_id = _create_decision(client, "reject")
        rejected = client.post(
            f"/ops/approvals/{rejected_id}/reject",
            json=_command(
                "REJECT",
                rejected_id,
                reason="Decision requires human revision",
            ),
        )
        assert rejected.status_code == 200
        assert rejected.json()["decision_state"] == "REJECTED"
        assert rejected.json()["execution_id"] is None
        assert rejected.json()["real_send_triggered"] is False
        assert client.get("/ops/executions").json() == []

        blocked_id = _create_decision(client, "kill-switch")
        app.state.control_plane.enable_kill_switch(
            operator="console.operator",
            reason="OPERATIONS_UI_SAFETY_TEST",
        )
        blocked = client.post(
            f"/ops/approvals/{blocked_id}/approve",
            json=_command("APPROVE", blocked_id),
        )
        assert blocked.status_code == 409
        assert "kill switch" in blocked.json()["detail"].casefold()
        assert app.state.fake_executor.call_count == 0
