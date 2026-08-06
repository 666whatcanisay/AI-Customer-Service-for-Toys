from __future__ import annotations

from fastapi.testclient import TestClient

from channel_engine.app import create_app
from channel_engine.config import Settings


def test_console_page_assets_and_security_headers(tmp_path) -> None:
    app = create_app(
        Settings(database_url=f"sqlite:///{(tmp_path / 'ui.sqlite3').as_posix()}")
    )
    with TestClient(app) as client:
        page = client.get("/ops/console")
        css = client.get("/ops/assets/operations-console.css")
        javascript = client.get("/ops/assets/operations-console.js")

    assert page.status_code == 200
    assert page.headers["content-security-policy"].startswith("default-src 'self'")
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["referrer-policy"] == "no-referrer"
    assert "AI-CS 智能客服运营控制中心" in page.text
    assert 'lang="zh-CN"' in page.text
    assert "人工审核中心" in page.text
    assert "问题诊断与恢复" in page.text
    assert 'id="view-overview"' in page.text
    assert 'id="view-approvals"' in page.text
    assert 'id="view-recovery"' in page.text
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert ".system-banner" in css.text
    assert javascript.status_code == 200
    assert javascript.headers["content-type"].startswith("text/javascript")
    assert "/ops/console/snapshot" in javascript.text
    assert "innerHTML" not in javascript.text


def test_console_sources_expose_runtime_channel_and_recovery_state_changes(
    tmp_path,
) -> None:
    app = create_app(
        Settings(database_url=f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}")
    )
    with TestClient(app) as client:
        initial = client.get("/ops/console/snapshot")
        channels = client.get("/session-runtime/v1/instances")
        assert initial.status_code == 200
        assert channels.status_code == 200
        assert len(channels.json()) == 1
        assert channels.json()[0]["instance"]["store_id"] == "fake-store"
        assert channels.json()[0]["real_platform_connected"] is False

        started = client.post("/runtime/v1/start")
        assert started.status_code == 200
        assert started.json()["runtime"]["state"] == "RUNNING"
        connected = client.get("/session-runtime/v1/instances").json()[0]
        assert connected["instance"]["status"] == "CONNECTED"
        assert connected["session"]["status"] == "CONNECTED"

        app.state.runtime_browser.simulate_failure("CONSOLE_STATUS_TEST")
        pulse = client.post("/runtime/v1/heartbeat")
        assert pulse.json()["overall"] == "UNHEALTHY"
        degraded = client.get("/ops/console/snapshot").json()
        assert degraded["runtime"]["browser"]["status"] == "UNHEALTHY"

        recovered = client.post(
            "/runtime/v1/recover", json={"component": "BROWSER"}
        )
        assert recovered.status_code == 200
        records = client.get("/ops/recoveries").json()
        assert len(records) == 1
        assert records[0]["component"] == "BROWSER"
        assert records[0]["state"] == "RECOVERED"
        assert records[0]["requires_manual_action"] is False
