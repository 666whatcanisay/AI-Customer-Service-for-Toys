from __future__ import annotations

from fastapi.testclient import TestClient

from channel_engine.app import create_app
from channel_engine.config import Settings


def test_runtime_adapter_read_model_tracks_runtime_lifecycle(tmp_path) -> None:
    application = create_app(
        Settings(
            database_url=f"sqlite:///{(tmp_path / 'adapter-api.sqlite3').as_posix()}"
        )
    )
    with TestClient(application) as client:
        initial = client.get("/runtime/v1/adapters")
        assert initial.status_code == 200
        assert initial.json()["registered_channels"] == ["fake"]
        assert initial.json()["adapters"][0]["lifecycle"] == "DISCONNECTED"

        started = client.post("/runtime/v1/start")
        assert started.status_code == 200
        connected = client.get("/runtime/v1/adapters").json()
        assert connected["overall"] == "HEALTHY"
        assert connected["adapters"][0]["lifecycle"] == "CONNECTED"
        assert connected["adapters"][0]["capabilities"] == {
            "adapter_contract_version": "1.0",
            "message_receive": True,
            "send_message": False,
            "image": False,
            "order_query": False,
        }
        assert connected["adapters"][0]["real_platform_connected"] is False

        stopped = client.post("/runtime/v1/stop")
        assert stopped.status_code == 200
        assert client.get("/runtime/v1/adapters").json()["adapters"][0][
            "lifecycle"
        ] == "DISCONNECTED"
