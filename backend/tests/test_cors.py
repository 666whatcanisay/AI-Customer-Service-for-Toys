from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config.settings import DEFAULT_CORS_ALLOWED_ORIGINS, Settings
from app.main import create_app


class _NoopRAGService:
    model_configured = False

    def warm_up(self) -> None:
        pass

    def close(self) -> None:
        pass


def _create_cors_client(tmp_path) -> TestClient:
    settings = replace(
        Settings.from_env(),
        backend_root=tmp_path,
        project_root=tmp_path,
        log_dir=tmp_path / "logs",
    )
    app = create_app(settings=settings, rag_factory=lambda _: _NoopRAGService())
    return TestClient(app)


def test_default_cors_origins_are_local_only(monkeypatch):
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    assert Settings.from_env().cors_allowed_origins == DEFAULT_CORS_ALLOWED_ORIGINS


def test_cors_parses_single_lan_origin(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://192.168.1.20:5173")

    assert Settings.from_env().cors_allowed_origins == ("http://192.168.1.20:5173",)


def test_cors_parses_multiple_origins_and_removes_duplicates(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        " http://localhost:5173,https://Example.com:443,http://localhost:5173 ",
    )

    assert Settings.from_env().cors_allowed_origins == (
        "http://localhost:5173",
        "https://example.com",
    )


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "",
        "ftp://192.168.1.20:5173",
        "http://192.168.1.20:5173/",
        "http://192.168.1.20:5173/customer",
        "http://192.168.1.20:5173?tenant=toy",
        "http://192.168.1.20:5173#support",
        "http://user@192.168.1.20:5173",
        "http://192.168.1.20:not-a-port",
        "http://192.168.1.20:5173\n",
    ],
)
def test_invalid_cors_origin_fails_settings_startup(monkeypatch, origin):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origin)

    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        Settings.from_env()


def test_lan_origin_receives_cors_for_health_status_and_preflight(
    monkeypatch, tmp_path
):
    origin = "http://192.168.1.20:5173"
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origin)

    with _create_cors_client(tmp_path) as client:
        for path in ("/api/health", "/api/status"):
            response = client.get(path, headers={"Origin": origin})
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
            assert "access-control-allow-credentials" not in response.headers

        preflight = client.options(
            "/api/chat",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in preflight.headers
    assert set(preflight.headers["access-control-allow-methods"].split(", ")) == {
        "GET",
        "POST",
        "PUT",
        "OPTIONS",
    }
    assert "content-type" in preflight.headers["access-control-allow-headers"].lower()


@pytest.mark.parametrize("allowed_origin", DEFAULT_CORS_ALLOWED_ORIGINS)
def test_default_origin_allows_real_chat_and_rejects_other_origins(
    api_client, allowed_origin
):
    client, _ = api_client

    chat_response = client.post(
        "/api/chat",
        headers={"Origin": allowed_origin},
        json={"message": "星云狐狸玩具的指示灯是紫色"},
    )
    assert chat_response.status_code == 200
    assert chat_response.headers["access-control-allow-origin"] == allowed_origin
    assert chat_response.json()["data"]["action"] == "ANSWER"

    unauthorized = client.get(
        "/api/health", headers={"Origin": "http://192.168.1.99:5173"}
    )
    assert unauthorized.status_code == 200
    assert "access-control-allow-origin" not in unauthorized.headers

    server_request = client.get("/api/health")
    assert server_request.status_code == 200
    assert "access-control-allow-origin" not in server_request.headers
