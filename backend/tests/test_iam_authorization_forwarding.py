import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.api.routes import router
from app.service import iam_authorization
from app.service.iam_authorization import require_operations_identity
from app.service.experience_evaluation import PlatformExperienceCaseClient
from app.service.feedback_analysis import PlatformFeedbackClient
from app.service.knowledge_quality import PlatformKnowledgeQualityClient


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self) -> bytes:
        return json.dumps({"items": []}).encode("utf-8")


def test_operator_bearer_is_forwarded_across_all_a_to_c_analysis_bridges(monkeypatch) -> None:
    observed: list[str | None] = []

    def urlopen(request, timeout):
        del timeout
        observed.append(request.get_header("Authorization"))
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    authorization = "Bearer synthetic-operator-session"
    clients = [
        PlatformFeedbackClient("http://platform.test", 1, authorization),
        PlatformKnowledgeQualityClient("http://platform.test", 1, authorization),
        PlatformExperienceCaseClient("http://platform.test", 1, authorization),
    ]
    for client in clients:
        assert client._request_json("GET", "/synthetic") == {"items": []}

    assert observed == [authorization, authorization, authorization]


def _request():
    settings = SimpleNamespace(
        platform_api_base_url="http://platform.test",
        platform_api_timeout_seconds=1,
    )
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        state=SimpleNamespace(),
    )


def test_a_admin_endpoint_authentication_is_server_validated_by_c(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def get(url, *, headers, timeout, trust_env):
        observed.update(url=url, headers=headers, timeout=timeout, trust_env=trust_env)
        return httpx.Response(200, json={
            "schema_version": "ai-cs.iam.v1",
            "user": {"id": "operator-1", "permissions": ["knowledge.manage"], "must_change_password": False},
        })

    monkeypatch.setattr(iam_authorization.httpx, "get", get)
    user = require_operations_identity(_request(), "Bearer synthetic-session")
    assert user["id"] == "operator-1"
    assert observed == {
        "url": "http://platform.test/api/v1/auth/me",
        "headers": {"Authorization": "Bearer synthetic-session"},
        "timeout": 1,
        "trust_env": False,
    }


def test_a_admin_endpoint_rejects_missing_invalid_and_customer_service_sessions(monkeypatch) -> None:
    with pytest.raises(HTTPException) as missing:
        require_operations_identity(_request(), None)
    assert missing.value.status_code == 401

    monkeypatch.setattr(
        iam_authorization.httpx, "get", lambda *args, **kwargs: httpx.Response(401)
    )
    with pytest.raises(HTTPException) as invalid:
        require_operations_identity(_request(), "Bearer invalid")
    assert invalid.value.status_code == 401

    monkeypatch.setattr(iam_authorization.httpx, "get", lambda *args, **kwargs: httpx.Response(
        200, json={"user": {"id": "support-1", "permissions": ["workspace.access"], "must_change_password": False}}
    ))
    with pytest.raises(HTTPException) as denied:
        require_operations_identity(_request(), "Bearer support-session")
    assert denied.value.status_code == 403

    monkeypatch.setattr(iam_authorization.httpx, "get", lambda *args, **kwargs: httpx.Response(
        200, json={
            "user": {
                "id": "operator-1", "permissions": ["ai_quality.view"],
                "must_change_password": True,
            }
        }
    ))
    with pytest.raises(HTTPException) as password_change:
        require_operations_identity(_request(), "Bearer temporary-session")
    assert password_change.value.status_code == 403
    assert password_change.value.detail == "PASSWORD_CHANGE_REQUIRED"


def test_all_browser_ai_admin_routes_install_server_side_authorization() -> None:
    protected = {
        route.path
        for route in router.routes
        if any(
            dependency.call is require_operations_identity
            for dependency in route.dependant.dependencies
        )
    }
    assert {
        "/admin/ai/modules",
        "/admin/ai/modules/{module_id}",
        "/admin/ai/modules/{module_id}/prompt",
        "/admin/ai/modules/{module_id}/test",
        "/admin/ai/experience-evaluations/run",
        "/admin/ai/feedback-analysis/run",
        "/admin/ai/knowledge-quality/run",
        "/admin/ai/modules/{module_id}/evaluations/latest",
        "/admin/ai/control-center/overview",
        "/admin/ai/control-center/product-overview",
    } <= protected
    assert "/admin/ai/knowledge-publications/products" not in protected
    assert "/admin/ai/knowledge-publications/visibility" not in protected
