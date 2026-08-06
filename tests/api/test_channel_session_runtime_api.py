from __future__ import annotations

import json

from fastapi.testclient import TestClient

from channel_engine.app import create_app
from channel_engine.config import Settings


def test_session_runtime_read_api_and_runtime_lifecycle(tmp_path) -> None:
    application = create_app(
        Settings(
            database_url=f"sqlite:///{(tmp_path / 'session-runtime-api.db').as_posix()}"
        )
    )
    with TestClient(application) as client:
        initial = client.get("/session-runtime/v1/instances")
        assert initial.status_code == 200
        assert len(initial.json()) == 1
        assert initial.json()[0]["instance"]["status"] == "CREATED"
        assert initial.json()[0]["session"]["status"] == "CREATED"
        assert application.state.session_heartbeat_scheduler.running is True

        started = client.post("/runtime/v1/start")
        assert started.status_code == 200
        connected = client.get("/session-runtime/v1/instances").json()[0]
        assert connected["instance"]["status"] == "CONNECTED"
        assert connected["session"]["status"] == "CONNECTED"
        assert connected["real_platform_connected"] is False

        heartbeat = client.post("/session-runtime/v1/heartbeat")
        assert heartbeat.status_code == 200
        assert heartbeat.json()["overall"] == "HEALTHY"

        serialized = json.dumps(connected, ensure_ascii=False).casefold()
        for prohibited in (
            "cookie=",
            "token=",
            "password=",
            "secret=",
            "bearer ",
        ):
            assert prohibited not in serialized

        stopped = client.post("/runtime/v1/stop")
        assert stopped.status_code == 200
        disconnected = client.get("/session-runtime/v1/instances").json()[0]
        assert disconnected["instance"]["status"] == "STOPPED"
        assert disconnected["session"]["status"] == "EXPIRED"

    assert application.state.session_heartbeat_scheduler.running is False
