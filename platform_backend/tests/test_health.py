from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_service_status_and_request_id() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "platform-backend"
    assert body["version"] == "0.1.0"
    assert body["request_id"]
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_health_preserves_caller_request_id() -> None:
    response = client.get("/health", headers={"X-Request-ID": "test-request-id"})

    assert response.status_code == 200
    assert response.json()["request_id"] == "test-request-id"
    assert response.headers["X-Request-ID"] == "test-request-id"


def test_unknown_route_uses_unified_error_response() -> None:
    response = client.get("/missing", headers={"X-Request-ID": "missing-route"})

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "HTTP_404", "message": "Not Found"},
        "request_id": "missing-route",
    }
