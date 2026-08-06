from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.desktop_agent.models import DesktopWorkflowAuditEvent
from app.desktop_agent.schemas import (
    UpstreamAgentIdentity,
    UpstreamAgentList,
    UpstreamAgentView,
    UpstreamEnrollmentGrant,
)
from app.desktop_agent.upstream import (
    ChannelAgentNotConfigured,
    ChannelAgentPermissionInvalid,
    ChannelAgentUnavailable,
    get_channel_agent_upstream,
)
from app.iam.schemas import RoleName, UserCreateRequest
from app.iam.service import UserService, ensure_default_roles
from app.main import app
from app.test_catalog.models import (
    TestKnowledgePackage as KnowledgePackageModel,
    TestStore as StoreModel,
)


PASSWORD = "Correct-Horse-42!"
NOW = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)
USER_ID = "11111111-1111-4111-8111-111111111111"


class FakeUpstream:
    def __init__(self, items: list[UpstreamAgentView]) -> None:
        self.items = items
        self.grant_calls: list[dict[str, object]] = []

    def list_agents(self) -> UpstreamAgentList:
        return UpstreamAgentList(items=tuple(self.items), count=len(self.items), server_time=NOW)

    def issue_enrollment_grant(self, **kwargs: object) -> UpstreamEnrollmentGrant:
        self.grant_calls.append(kwargs)
        return UpstreamEnrollmentGrant(
            grant_id="agent-enrollment-grant:pytest",
            agent_id=str(kwargs["agent_id"]),
            device_id=str(kwargs["device_id"]),
            user_reference=str(kwargs["user_reference"]),
            store_references=tuple(kwargs["store_references"]),
            binding_code="ABCDEF0123456789ABCDEF0123456789",
            issued_at=NOW,
            expires_at=datetime(2026, 8, 6, 8, 10, tzinfo=timezone.utc),
        )


@pytest.fixture
def auth_client(session: Session):
    def override_get_db():
        yield session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _seed_store(session: Session, code: str) -> StoreModel:
    package = KnowledgePackageModel(
        package_id=f"PKG-{code}", package_name=f"{code} package", version="1",
        schema_version="0.3.1-test", tenant_id=f"tenant-{code}", platform="pdd",
        store_code=code, response_mode="SUGGESTION_ONLY", test_data_mode=True,
        production_usable=False, allow_auto_send=False, import_status="IMPORTED_TEST_ONLY",
        original_filename="synthetic.zip", zip_sha256="1" * 64, counts_json="{}",
        imported_by="pytest", imported_at=NOW,
    )
    store = StoreModel(
        package_id=package.package_id, tenant_id=package.tenant_id, platform="pdd",
        store_code=code, store_name=f"{code} 玩具店", trial_enabled=True,
        knowledge_scope="STORE_PRODUCT_SKU", response_mode="SUGGESTION_ONLY",
        allow_auto_send=False, test_data_mode=True, production_usable=False,
        data_source="TEST", customer_service_status="ENABLED", raw_data_json="{}",
    )
    session.add_all([package, store]); session.commit(); session.refresh(store)
    return store


def _create_user(session: Session, username: str, role: RoleName, stores: list[dict]):
    ensure_default_roles(session)
    return UserService(session).create_user(UserCreateRequest(
        username=username, password=PASSWORD, display_name=username,
        roles=[role], store_bindings=stores,
    ), must_change_password=False)


def _login(client: TestClient, username: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _agent(
    *, user_id: str | None = USER_ID, store_codes: tuple[str, ...] = ("STORE-DESKTOP",),
    identity_status: str = "ACTIVE", online_status: str = "ONLINE",
    runtime_status: str = "ONLINE", revision: int = 2,
) -> UpstreamAgentView:
    return UpstreamAgentView(
        identity=UpstreamAgentIdentity(
            agent_id="agent-desktop-001", device_id="device-desktop-001",
            user_id=user_id, store_id=store_codes[0] if store_codes else None,
            store_ids=store_codes, status=identity_status, binding_revision=revision,
            created_at=NOW, updated_at=NOW,
        ),
        online_status=online_status, agent_version="1.1.0", hostname="CS-PC-01",
        runtime_status=runtime_status, last_heartbeat=NOW,
    )


def test_login_and_agent_status_are_minimally_audited(
    auth_client: TestClient, session: Session
) -> None:
    store = _seed_store(session, "STORE-DESKTOP")
    created = _create_user(session, "support.desktop", RoleName.CUSTOMER_SERVICE, [
        {"store_id": store.id, "is_default": True}
    ])
    headers = _login(auth_client, "support.desktop")
    fake = FakeUpstream([_agent(user_id=created.id)])
    app.dependency_overrides[get_channel_agent_upstream] = lambda: fake

    response = auth_client.get(
        "/api/v1/workspace/desktop-agent", params={"store_id": store.id}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["association_state"] == "READY"
    assert body["agent"] == {
        "agent_id": "agent-desktop-001", "device_id": "device-desktop-001",
        "device_name": "CS-PC-01", "agent_version": "1.1.0",
        "identity_status": "ACTIVE", "online_status": "ONLINE",
        "runtime_status": "ONLINE", "production_eligible": True,
        "binding_revision": 2, "last_heartbeat": "2026-08-06T08:00:00Z",
    }

    auth_client.get(
        "/api/v1/workspace/desktop-agent", params={"store_id": store.id}, headers=headers
    )
    events = list(session.scalars(select(DesktopWorkflowAuditEvent).order_by(
        DesktopWorkflowAuditEvent.occurred_at
    )))
    assert [item.event_type for item in events] == ["LOGIN", "DEVICE_BINDING_OBSERVED"]
    assert all(item.current_state != "ABCDEF0123456789ABCDEF0123456789" for item in events)

    fake.items = [_agent(
        user_id=created.id, online_status="OFFLINE", runtime_status="STOPPED", revision=3
    )]
    auth_client.get(
        "/api/v1/workspace/desktop-agent", params={"store_id": store.id}, headers=headers
    )
    changed = session.scalars(select(DesktopWorkflowAuditEvent).where(
        DesktopWorkflowAuditEvent.event_type == "DEVICE_STATUS_CHANGED"
    )).one()
    assert changed.previous_state == "ACTIVE|ONLINE|ONLINE|2"
    assert changed.current_state == "ACTIVE|OFFLINE|STOPPED|3"


def test_self_binding_grant_uses_authenticated_user_and_authorized_store_codes(
    auth_client: TestClient, session: Session
) -> None:
    first = _seed_store(session, "STORE-DESKTOP-A")
    second = _seed_store(session, "STORE-DESKTOP-B")
    created = _create_user(session, "support.binding", RoleName.CUSTOMER_SERVICE, [
        {"store_id": first.id, "is_default": True},
        {"store_id": second.id, "is_default": False},
    ])
    headers = _login(auth_client, "support.binding")
    fake = FakeUpstream([_agent(user_id=None, store_codes=(), identity_status="UNBOUND", revision=0)])
    app.dependency_overrides[get_channel_agent_upstream] = lambda: fake

    response = auth_client.post(
        "/api/v1/workspace/desktop-agent/binding-grants",
        headers=headers,
        json={
            "agent_id": "agent-desktop-001", "device_id": "device-desktop-001",
            "store_id": second.id,
        },
    )
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["binding_code"] == "ABCDEF0123456789ABCDEF0123456789"
    assert len(fake.grant_calls) == 1
    call = fake.grant_calls[0]
    assert call["user_reference"] == created.id
    assert call["store_references"] == ("STORE-DESKTOP-B", "STORE-DESKTOP-A")
    audit = session.scalars(select(DesktopWorkflowAuditEvent).where(
        DesktopWorkflowAuditEvent.event_type == "DEVICE_BINDING_GRANT_ISSUED"
    )).one()
    assert audit.current_state == "GRANT_ISSUED"
    assert "ABCDEF" not in repr(audit.__dict__)


def test_store_and_role_scope_fail_closed(
    auth_client: TestClient, session: Session
) -> None:
    authorized = _seed_store(session, "STORE-SCOPE-A")
    other = _seed_store(session, "STORE-SCOPE-B")
    _create_user(session, "support.scope", RoleName.CUSTOMER_SERVICE, [
        {"store_id": authorized.id, "is_default": True}
    ])
    operator = _create_user(session, "operator.scope", RoleName.OPERATOR, [])
    fake = FakeUpstream([_agent(user_id=None, store_codes=(), identity_status="UNBOUND", revision=0)])
    app.dependency_overrides[get_channel_agent_upstream] = lambda: fake

    support_headers = _login(auth_client, "support.scope")
    denied_store = auth_client.get(
        "/api/v1/workspace/desktop-agent", params={"store_id": other.id}, headers=support_headers
    )
    assert denied_store.status_code == 403
    assert denied_store.json()["error"]["code"] == "AUTHORIZATION_DENIED"

    operator_headers = _login(auth_client, "operator.scope")
    denied_role = auth_client.post(
        "/api/v1/workspace/desktop-agent/binding-grants", headers=operator_headers,
        json={
            "agent_id": "agent-desktop-001", "device_id": "device-desktop-001",
            "store_id": authorized.id,
        },
    )
    assert operator.id
    assert denied_role.status_code == 403
    assert denied_role.json()["error"]["code"] == "AUTHORIZATION_DENIED"


def test_disabled_agent_observation_does_not_cross_authorized_store_scope(
    auth_client: TestClient, session: Session
) -> None:
    first = _seed_store(session, "STORE-DISABLED-A")
    second = _seed_store(session, "STORE-DISABLED-B")
    created = _create_user(session, "support.disabled", RoleName.CUSTOMER_SERVICE, [
        {"store_id": first.id, "is_default": True},
        {"store_id": second.id, "is_default": False},
    ])
    headers = _login(auth_client, "support.disabled")
    active = FakeUpstream([_agent(user_id=created.id, store_codes=("STORE-DISABLED-A",))])
    app.dependency_overrides[get_channel_agent_upstream] = lambda: active
    observed = auth_client.get(
        "/api/v1/workspace/desktop-agent", params={"store_id": first.id}, headers=headers
    )
    assert observed.status_code == 200
    assert observed.json()["association_state"] == "READY"

    disabled = FakeUpstream([_agent(
        user_id=None, store_codes=(), identity_status="DISABLED",
        online_status="OFFLINE", runtime_status="STOPPED", revision=3,
    )])
    app.dependency_overrides[get_channel_agent_upstream] = lambda: disabled
    unrelated = auth_client.get(
        "/api/v1/workspace/desktop-agent", params={"store_id": second.id}, headers=headers
    )
    assert unrelated.status_code == 200
    assert unrelated.json()["association_state"] == "BINDING_REQUIRED"
    assert unrelated.json()["agent"] is None


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (ChannelAgentNotConfigured("missing"), "CHANNEL_AGENT_INTEGRATION_NOT_CONFIGURED"),
        (ChannelAgentUnavailable("offline"), "CHANNEL_AGENT_SERVER_UNREACHABLE"),
        (ChannelAgentPermissionInvalid("revoked"), "CHANNEL_AGENT_OPERATOR_PERMISSION_INVALID"),
    ],
)
def test_upstream_exceptions_have_distinct_non_200_envelopes(
    auth_client: TestClient, session: Session, exception: Exception, code: str
) -> None:
    store = _seed_store(session, f"STORE-{code[-6:]}")
    _create_user(session, f"support.{code[-6:].lower()}", RoleName.CUSTOMER_SERVICE, [
        {"store_id": store.id, "is_default": True}
    ])
    headers = _login(auth_client, f"support.{code[-6:].lower()}")

    class FailingUpstream:
        def list_agents(self):
            raise exception

    app.dependency_overrides[get_channel_agent_upstream] = lambda: FailingUpstream()
    response = auth_client.get(
        "/api/v1/workspace/desktop-agent", params={"store_id": store.id}, headers=headers
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == code
    assert response.json()["request_id"]
