from dataclasses import replace
from fastapi import Request
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app import errors as errors_module


def test_unhandled_error_log_has_context_without_exception_or_request_secrets(
    tmp_path, monkeypatch
) -> None:
    application = create_app(replace(
        get_settings(), database_url=f"sqlite:///{(tmp_path / 'errors.sqlite3').as_posix()}"
    ))

    @application.get("/synthetic-unhandled-error")
    def fail(request: Request) -> None:
        request.state.authenticated_user_id = "safe-user-id"
        raise RuntimeError("customer-content-secret-marker")

    records: list[str] = []
    monkeypatch.setattr(
        errors_module.logger,
        "error",
        lambda message, *args, **_: records.append(message % args),
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
