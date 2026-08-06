from dataclasses import replace
import logging
from fastapi import Request
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app


class StubRag:
    model_configured = True

    def warm_up(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_unhandled_error_log_has_context_without_exception_or_request_secrets(
    tmp_path, monkeypatch
) -> None:
    settings = replace(
        Settings.from_env(),
        backend_root=tmp_path,
        project_root=tmp_path,
        knowledge_base_path=tmp_path / "knowledge",
        vector_db_path=tmp_path / "vectors",
        log_dir=tmp_path / "logs",
    )
    application = create_app(settings=settings, rag_factory=lambda _: StubRag())

    @application.get("/synthetic-unhandled-error")
    def fail(request: Request) -> None:
        request.state.authenticated_user_id = "safe-user-id"
        raise RuntimeError("customer-content-secret-marker")

    records: list[str] = []
    monkeypatch.setattr(
        logging.Logger,
        "error",
        lambda _logger, message, *args, **_: records.append(message % args),
    )
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get(
            "/synthetic-unhandled-error",
            headers={
                "X-Request-ID": "safe-request-id",
                "Authorization": "Bearer must-not-be-logged",
            },
        )

    assert response.status_code == 500
    log_text = "\n".join(records)
    assert "safe-request-id" in log_text
    assert "safe-user-id" in log_text
    assert "RuntimeError" in log_text
    assert "customer-content-secret-marker" not in log_text
    assert "must-not-be-logged" not in log_text
