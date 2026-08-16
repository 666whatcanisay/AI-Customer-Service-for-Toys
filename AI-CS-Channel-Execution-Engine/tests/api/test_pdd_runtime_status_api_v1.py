from __future__ import annotations

from fastapi.testclient import TestClient

from channel_engine.app import create_app
from channel_engine.config import Settings


def test_pdd_runtime_status_api_is_safe_and_disabled_by_default(tmp_path) -> None:
    application = create_app(
        settings=Settings(
            database_url=(
                f"sqlite:///{(tmp_path / 'pdd-runtime-status.sqlite3').as_posix()}"
            )
        )
    )

    with TestClient(application) as client:
        response = client.get("/ops/pdd/runtime/status")

    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == "DISABLED"
    assert body["session"]["health"] == "DISABLED"
    assert body["cursor"]["health"] == "DISABLED"
    assert body["browser"]["health"] == "DISABLED"
    assert body["adapter"]["health"] == "DISABLED"
    assert body["recovery"]["health"] == "DISABLED"
    assert body["observe_only"] is True
    assert body["send_enabled"] is False
    assert body["real_platform_connected"] is False
