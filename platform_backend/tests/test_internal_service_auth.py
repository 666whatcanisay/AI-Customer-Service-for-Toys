from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.main import create_app


def test_internal_rag_exports_fail_closed_without_the_service_identity(
    tmp_path: Path, session: Session
) -> None:
    token = "pytest-internal-service-token-at-least-32-bytes"
    secret_path = tmp_path / "internal-service.secret"
    secret_path.write_text(token, encoding="utf-8")
    application = create_app(
        replace(get_settings(), internal_service_secret_file=str(secret_path))
    )

    def override_get_db():
        yield session

    application.dependency_overrides[get_db] = override_get_db
    path = "/api/v1/test-knowledge-packages/not-present/rag-export"
    with TestClient(application) as client:
        missing = client.get(path)
        invalid = client.get(path, headers={"X-AI-CS-Service-Token": "invalid"})
        accepted = client.get(path, headers={"X-AI-CS-Service-Token": token})

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.json()["error"]["code"] == "INTERNAL_SERVICE_AUTHENTICATION_FAILED"
    assert accepted.status_code != 401
    assert token not in missing.text + invalid.text + accepted.text
