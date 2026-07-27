import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_CORS_ALLOWED_ORIGINS, get_settings, parse_cors_allowed_origins
from app.main import create_app


def test_parse_cors_allowed_origins_uses_explicit_local_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    get_settings.cache_clear()

    try:
        assert get_settings().cors_allowed_origins == (DEFAULT_CORS_ALLOWED_ORIGINS,)
    finally:
        get_settings.cache_clear()


def test_parse_cors_allowed_origins_normalizes_and_deduplicates() -> None:
    assert parse_cors_allowed_origins(
        " http://127.0.0.1:5173/, http://localhost:5173, http://127.0.0.1:5173 "
    ) == ("http://127.0.0.1:5173", "http://localhost:5173")


@pytest.mark.parametrize(
    "raw_value",
    [
        "",
        " , ",
        "*",
        "http://127.0.0.1:5173,*",
        "ftp://127.0.0.1:5173",
        "http://user:password@127.0.0.1:5173",
        "http://127.0.0.1:5173/api",
        "http://127.0.0.1:5173?debug=true",
        "http://127.0.0.1:invalid",
    ],
)
def test_parse_cors_allowed_origins_rejects_unsafe_or_invalid_values(raw_value: str) -> None:
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        parse_cors_allowed_origins(raw_value)


def test_allowed_origin_receives_preflight_and_actual_cors_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5173")
    get_settings.cache_clear()

    try:
        with TestClient(create_app()) as client:
            preflight = client.options(
                "/health",
                headers={
                    "Origin": "http://127.0.0.1:5173",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "X-Request-ID",
                },
            )
            actual = client.get(
                "/health",
                headers={
                    "Origin": "http://127.0.0.1:5173",
                    "X-Request-ID": "cors-allowed",
                },
            )
    finally:
        get_settings.cache_clear()

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "GET" in preflight.headers["access-control-allow-methods"]
    assert "PATCH" in preflight.headers["access-control-allow-methods"]
    assert actual.status_code == 200
    assert actual.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert actual.headers["access-control-expose-headers"] == "X-Request-ID"
    assert actual.headers["X-Request-ID"] == "cors-allowed"


def test_allowed_origin_can_preflight_feedback_idempotency_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browser feedback submissions require this non-simple request header."""
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5173")
    get_settings.cache_clear()

    try:
        with TestClient(create_app()) as client:
            preflight = client.options(
                "/api/v1/ai-response-feedback",
                headers={
                    "Origin": "http://127.0.0.1:5173",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Content-Type, Idempotency-Key",
                },
            )
    finally:
        get_settings.cache_clear()

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "POST" in preflight.headers["access-control-allow-methods"]
    assert "idempotency-key" in preflight.headers["access-control-allow-headers"].lower()


def test_denied_origin_receives_no_actual_cors_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5173")
    get_settings.cache_clear()

    try:
        with TestClient(create_app()) as client:
            preflight = client.options(
                "/health",
                headers={
                    "Origin": "http://untrusted.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
            actual = client.get("/health", headers={"Origin": "http://untrusted.example"})
    finally:
        get_settings.cache_clear()

    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers
    assert actual.status_code == 200
    assert "access-control-allow-origin" not in actual.headers
