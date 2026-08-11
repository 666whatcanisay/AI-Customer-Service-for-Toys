from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.desktop_agent.models import DesktopWorkflowAuditEvent
from app.desktop_agent.schemas import (
    UpstreamAgentIdentity,
    UpstreamAgentList,
    UpstreamAgentView,
    UpstreamEnrollmentGrant,
    UpstreamHostPairingCode,
)
from app.desktop_agent.upstream import (
    ChannelAgentNotConfigured,
    ChannelAgentPermissionInvalid,
    ChannelAgentResponseInvalid,
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
from app.store_platform_bindings.models import StorePlatformBinding


PASSWORD = "Correct-Horse-42!"
NOW = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)
USER_ID = "11111111-1111-4111-8111-111111111111"


class FakeUpstream:
    def __init__(self, items: list[UpstreamAgentView]) -> None:
        self.items = items
        self.grant_calls: list[dict[str, object]] = []
        self.activation_calls: list[dict[str, object]] = []
        self.store_selection_calls: list[dict[str, object]] = []
        self.pairing_rotation_calls: list[dict[str, object]] = []

    def list_agents(self) -> UpstreamAgentList:
        return UpstreamAgentList(
            items=tuple(self.items),
            count=len(self.items),
            server_time=NOW,
            authoritative_source="CHANNEL_ENGINE_HOST_CONTROL",
        )

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

    def rotate_host_pairing_code(self, **kwargs: object) -> UpstreamHostPairingCode:
        self.pairing_rotation_calls.append(kwargs)
        return UpstreamHostPairingCode(
            host_id="host-001",
            pairing_code="7K3M9Q2X4T8R",
            expires_at=datetime(2026, 8, 6, 8, 5, tzinfo=timezone.utc),
            display_once=True,
        )

    def activate_agent(self, **kwargs: object) -> None:
        self.activation_calls.append(kwargs)
        for index, item in enumerate(self.items):
            if item.identity.agent_id != kwargs["agent_id"]:
                continue
            identity = UpstreamAgentIdentity(
                agent_id=item.identity.agent_id,
                device_id=item.identity.device_id,
                user_id=item.identity.user_id,
                store_id=item.identity.store_id,
                store_ids=item.identity.store_ids,
                authorized_store_ids=item.identity.authorized_store_ids,
                active_store_id=item.identity.active_store_id,
                status="ACTIVE",
                binding_revision=item.identity.binding_revision + 1,
                created_at=item.identity.created_at,
                updated_at=NOW,
            )
            updated = item.model_dump(mode="python")
            updated["identity"] = identity.model_dump(mode="python")
            updated["identity_status"] = "ACTIVE"
            self.items[index] = UpstreamAgentView.model_validate(updated)
            return

    def select_active_store(self, **kwargs: object) -> UpstreamAgentIdentity:
        self.store_selection_calls.append(kwargs)
        for index, item in enumerate(self.items):
            if item.identity.agent_id != kwargs["agent_id"]:
                continue
            identity = item.identity.model_copy(update={
                "active_store_id": str(kwargs["store_reference"]),
                "binding_revision": item.identity.binding_revision + 1,
                "updated_at": NOW,
            })
            updated = item.model_dump(mode="python")
            updated["identity"] = identity.model_dump(mode="python")
            self.items[index] = UpstreamAgentView.model_validate(updated)
            return identity
        raise AssertionError("agent fixture not found")

    def disable_agent(self, **kwargs: object) -> UpstreamAgentIdentity:
        return self._replace_identity(str(kwargs["agent_id"]), "DISABLED")

    def restore_agent_to_registered(self, **kwargs: object) -> UpstreamAgentIdentity:
        return self._replace_identity(str(kwargs["agent_id"]), "REGISTERED")

    def _replace_identity(
        self, agent_id: str, status: str
    ) -> UpstreamAgentIdentity:
        for index, item in enumerate(self.items):
            if item.identity.agent_id != agent_id:
                continue
            identity = UpstreamAgentIdentity(
                agent_id=item.identity.agent_id,
                device_id=item.identity.device_id,
                user_id=None,
                store_id=None,
                store_ids=(),
                authorized_store_ids=(),
                active_store_id=None,
                status=status,
                binding_revision=item.identity.binding_revision + 1,
                created_at=item.identity.created_at,
                updated_at=NOW,
            )
            updated = item.model_dump(mode="python")
            updated["identity"] = identity.model_dump(mode="python")
            updated["identity_status"] = status
            self.items[index] = UpstreamAgentView.model_validate(updated)
            return identity
        raise AssertionError("agent fixture not found")


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
            store_ids=store_codes, authorized_store_ids=store_codes,
            active_store_id=store_codes[0] if store_codes else None,
            status=identity_status, binding_revision=revision,
            created_at=NOW, updated_at=NOW,
        ),
        identity_status=identity_status,
        connectivity_status=("OFFLINE" if online_status == "OFFLINE" else "ONLINE"),
        agent_version="1.1.0", hostname="CS-PC-01",
        runtime_status=runtime_status, last_heartbeat=NOW,
        authoritative_source="CHANNEL_ENGINE_HOST_CONTROL",
    )


def _real_agent_160_list_payload() -> dict[str, object]:
    return {
        "protocol_version": "1.0",
        "items": [{
            "protocol_version": "1.0",
            "identity": {
                "protocol_version": "1.0",
                "agent_id": "agent-real-shape-001",
                "device_id": "device-real-shape-001",
                "user_id": USER_ID,
                "store_id": "STORE-A",
                "store_ids": ["STORE-A", "STORE-B"],
                "authorized_store_ids": ["STORE-A", "STORE-B"],
                "active_store_id": "STORE-B",
                "status": "ACTIVE",
                "binding_revision": 3,
                "created_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
            },
            "identity_status": "ACTIVE",
            "connectivity_status": "ONLINE",
            "agent_version": "1.6.0",
            "hostname": "CS-PC-REAL-SHAPE",
            "runtime_status": "ONLINE",
            "last_heartbeat": NOW.isoformat(),
            "authoritative_source": "CHANNEL_ENGINE_HOST_CONTROL",
        }],
        "count": 1,
        "server_time": NOW.isoformat(),
        "authoritative_source": "CHANNEL_ENGINE_HOST_CONTROL",
    }


def test_agent_160_real_response_shape_is_strictly_compatible() -> None:
    listing = UpstreamAgentList.model_validate(_real_agent_160_list_payload())
    identity = listing.items[0].identity
    assert identity.effective_store_ids == ("STORE-A", "STORE-B")
    assert identity.effective_active_store_id == "STORE-B"


def test_agent_identity_contract_rejects_unknown_or_inconsistent_permission_fields() -> None:
    unknown = _real_agent_160_list_payload()
    unknown["items"][0]["identity"]["unexpected_permission_scope"] = "ALL"  # type: ignore[index]
    with pytest.raises(ValidationError, match="unexpected_permission_scope"):
        UpstreamAgentList.model_validate(unknown)

    inconsistent = _real_agent_160_list_payload()
    inconsistent["items"][0]["identity"]["active_store_id"] = "STORE-C"  # type: ignore[index]
    with pytest.raises(ValidationError, match="active Store reference is not authorized"):
        UpstreamAgentList.model_validate(inconsistent)

    missing = _real_agent_160_list_payload()
    del missing["items"][0]["identity"]["device_id"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="device_id"):
        UpstreamAgentList.model_validate(missing)


def test_admin_device_management_uses_authoritative_host_state(
    auth_client: TestClient,
    session: Session,
) -> None:
    _seed_store(session, "STORE-ADMIN-DEVICE")
    _create_user(session, "admin.device", RoleName.ADMIN, [])
    headers = _login(auth_client, "admin.device")
    fake = FakeUpstream([_agent()])
    app.dependency_overrides[get_channel_agent_upstream] = lambda: fake

    listing = auth_client.get(
        "/api/v1/admin/desktop-workflow/devices", headers=headers
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["authoritative_source"] == "CHANNEL_ENGINE_HOST_CONTROL"
    assert listing.json()["items"][0]["identity_status"] == "ACTIVE"
    assert listing.json()["items"][0]["connectivity_status"] == "ONLINE"

    disabled = auth_client.post(
        "/api/v1/admin/desktop-workflow/devices/agent-desktop-001/disable",
        headers=headers,
        json={
            "reason": "管理员确认停用测试设备",
            "confirmation_phrase": "确认禁用设备",
        },
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["items"][0]["identity_status"] == "DISABLED"

    restored = auth_client.post(
        "/api/v1/admin/desktop-workflow/devices/agent-desktop-001/restore-to-registered",
        headers=headers,
        json={
            "reason": "管理员确认恢复并要求重新人工绑定",
            "confirmation_phrase": "确认恢复为待绑定",
        },
    )
    assert restored.status_code == 200, restored.text
    item = restored.json()["items"][0]
    assert item["identity_status"] == "REGISTERED"
    assert item["user_reference"] is None
    assert item["authorized_store_ids"] == []


def test_admin_rotates_display_once_host_pairing_code_without_auditing_plaintext(
    auth_client: TestClient,
    session: Session,
) -> None:
    _create_user(session, "admin.host.pairing", RoleName.ADMIN, [])
    headers = _login(auth_client, "admin.host.pairing")
    fake = FakeUpstream([])
    app.dependency_overrides[get_channel_agent_upstream] = lambda: fake

    rotated = auth_client.post(
        "/api/v1/admin/desktop-workflow/host/pairing-codes/rotate",
        headers=headers,
        json={
            "reason": "新客服电脑首次安装连接可信主机",
            "confirmation_phrase": "确认重新生成主机连接码",
        },
    )
    assert rotated.status_code == 201, rotated.text
    assert rotated.headers["cache-control"] == "no-store"
    assert rotated.headers["pragma"] == "no-cache"
    assert rotated.json()["pairing_code"] == "7K3M9Q2X4T8R"
    assert rotated.json()["display_once"] is True
    assert fake.pairing_rotation_calls == [
        {"reason": "新客服电脑首次安装连接可信主机"}
    ]

    audit = session.scalars(
        select(DesktopWorkflowAuditEvent).where(
            DesktopWorkflowAuditEvent.event_type == "HOST_PAIRING_CODE_ROTATED"
        )
    ).one()
    assert audit.reason == "新客服电脑首次安装连接可信主机"
    assert "7K3M9Q2X4T8R" not in repr(audit.__dict__)


def test_host_pairing_rotation_rejects_unauthenticated_and_non_admin_users(
    auth_client: TestClient,
    session: Session,
) -> None:
    _create_user(session, "support.host.pairing", RoleName.CUSTOMER_SERVICE, [])
    payload = {
        "reason": "新客服电脑首次安装连接可信主机",
        "confirmation_phrase": "确认重新生成主机连接码",
    }
    fake = FakeUpstream([])
    app.dependency_overrides[get_channel_agent_upstream] = lambda: fake

    unauthenticated = auth_client.post(
        "/api/v1/admin/desktop-workflow/host/pairing-codes/rotate",
        json=payload,
    )
    assert unauthenticated.status_code == 401

    support_headers = _login(auth_client, "support.host.pairing")
    unauthorized = auth_client.post(
        "/api/v1/admin/desktop-workflow/host/pairing-codes/rotate",
        headers=support_headers,
        json=payload,
    )
    assert unauthorized.status_code == 403
    assert fake.pairing_rotation_calls == []


def test_admin_can_issue_one_time_grant_only_with_existing_user_store_scope(
    auth_client: TestClient,
    session: Session,
) -> None:
    first = _seed_store(session, "STORE-ADMIN-GRANT-A")
    second = _seed_store(session, "STORE-ADMIN-GRANT-B")
    unauthorized = _seed_store(session, "STORE-ADMIN-GRANT-X")
    _create_user(session, "admin.grant", RoleName.ADMIN, [])
    support = _create_user(session, "support.admin.grant", RoleName.CUSTOMER_SERVICE, [
        {"store_id": first.id, "is_default": True},
        {"store_id": second.id, "is_default": False},
    ])
    headers = _login(auth_client, "admin.grant")
    fake = FakeUpstream([
        _agent(user_id=None, store_codes=(), identity_status="UNBOUND", revision=0)
    ])
    app.dependency_overrides[get_channel_agent_upstream] = lambda: fake

    targets = auth_client.get(
        "/api/v1/admin/desktop-workflow/binding-targets", headers=headers
    )
    assert targets.status_code == 200, targets.text
    assert targets.headers["cache-control"] == "no-store"
    assert targets.json()["items"] == [{
        "user_id": support.id,
        "username": "support.admin.grant",
        "display_name": support.display_name,
        "stores": [
            {
                "store_id": first.id,
                "store_code": "STORE-ADMIN-GRANT-A",
                "store_name": first.store_name,
                "platform": first.platform,
                "is_default": True,
            },
            {
                "store_id": second.id,
                "store_code": "STORE-ADMIN-GRANT-B",
                "store_name": second.store_name,
                "platform": second.platform,
                "is_default": False,
            },
        ],
    }]

    denied = auth_client.post(
        "/api/v1/admin/desktop-workflow/devices/agent-desktop-001/enrollment-grants",
        headers=headers,
        json={
            "user_id": support.id,
            "store_ids": [unauthorized.id],
            "reason": "管理员尝试绑定未授权店铺应被拒绝",
            "confirmation_phrase": "确认生成设备绑定许可",
        },
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "BINDING_TARGET_STORE_UNAUTHORIZED"
    assert fake.grant_calls == []

    granted = auth_client.post(
        "/api/v1/admin/desktop-workflow/devices/agent-desktop-001/enrollment-grants",
        headers=headers,
        json={
            "user_id": support.id,
            "store_ids": [second.id, first.id],
            "reason": "管理员确认新客服电脑首次人工绑定",
            "confirmation_phrase": "确认生成设备绑定许可",
        },
    )
    assert granted.status_code == 201, granted.text
    assert granted.headers["cache-control"] == "no-store"
    assert granted.json()["binding_code"] == "ABCDEF0123456789ABCDEF0123456789"
    assert fake.grant_calls[0]["user_reference"] == support.id
    assert fake.grant_calls[0]["store_references"] == (
        "STORE-ADMIN-GRANT-A", "STORE-ADMIN-GRANT-B"
    )
    audit = session.scalars(select(DesktopWorkflowAuditEvent).where(
        DesktopWorkflowAuditEvent.event_type
        == "DEVICE_BINDING_GRANT_ISSUED_BY_ADMIN"
    )).one()
    assert audit.actor_user_id != support.id
    assert "ABCDEF" not in repr(audit.__dict__)


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


def test_authenticated_user_can_activate_own_bound_device_idempotently(
    auth_client: TestClient, session: Session
) -> None:
    store = _seed_store(session, "STORE-ACTIVATE")
    created = _create_user(session, "support.activate", RoleName.CUSTOMER_SERVICE, [
        {"store_id": store.id, "is_default": True}
    ])
    headers = _login(auth_client, "support.activate")
    fake = FakeUpstream([_agent(
        user_id=created.id,
        store_codes=("STORE-ACTIVATE",),
        identity_status="BOUND",
        revision=1,
    )])
    app.dependency_overrides[get_channel_agent_upstream] = lambda: fake
    request = {
        "agent_id": "agent-desktop-001",
        "device_id": "device-desktop-001",
        "store_id": store.id,
    }

    activated = auth_client.post(
        "/api/v1/workspace/desktop-agent/activate", headers=headers, json=request
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["association_state"] == "READY"
    assert activated.json()["agent"]["identity_status"] == "ACTIVE"
    assert len(fake.activation_calls) == 1

    repeated = auth_client.post(
        "/api/v1/workspace/desktop-agent/activate", headers=headers, json=request
    )
    assert repeated.status_code == 200, repeated.text
    assert len(fake.activation_calls) == 1
    audit = session.scalars(select(DesktopWorkflowAuditEvent).where(
        DesktopWorkflowAuditEvent.event_type == "DEVICE_BINDING_ACTIVATED"
    )).all()
    assert len(audit) == 1


def test_authenticated_user_selects_internal_store_through_verified_platform_binding(
    auth_client: TestClient, session: Session
) -> None:
    store = _seed_store(session, "STORE-PDD-VERIFIED")
    created = _create_user(session, "support.store.select", RoleName.CUSTOMER_SERVICE, [
        {"store_id": store.id, "is_default": True}
    ])
    session.add(StorePlatformBinding(
        binding_id=str(uuid4()),
        store_id=store.id,
        platform="pinduoduo",
        platform_store_id="328616090",
        status="ACTIVE",
        verified_at=NOW,
        verified_by="admin-test",
        created_at=NOW,
        change_reason="pytest verified PDD mapping",
    ))
    session.commit()
    headers = _login(auth_client, "support.store.select")
    fake = FakeUpstream([_agent(
        user_id=created.id,
        store_codes=("STORE-PDD-VERIFIED",),
        identity_status="ACTIVE",
        revision=4,
    )])
    fake.items[0] = fake.items[0].model_copy(update={
        "identity": fake.items[0].identity.model_copy(update={"active_store_id": None})
    })
    app.dependency_overrides[get_channel_agent_upstream] = lambda: fake

    response = auth_client.post(
        "/api/v1/workspace/desktop-agent/active-store",
        headers=headers,
        json={
            "agent_id": "agent-desktop-001",
            "device_id": "device-desktop-001",
            "store_id": store.id,
            "platform": "pinduoduo",
            "observed_platform_store_id": "328616090",
            "human_confirmed": True,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["association_state"] == "READY"
    call = fake.store_selection_calls[0]
    assert call["store_reference"] == "STORE-PDD-VERIFIED"
    assert call["observed_platform_store_id"] == "328616090"
    assert call["user_reference"] == created.id
    assert call["binding_revision"] == 4


def test_activation_rejects_device_bound_to_another_user(
    auth_client: TestClient, session: Session
) -> None:
    store = _seed_store(session, "STORE-ACTIVATE-DENIED")
    _create_user(session, "support.activate.denied", RoleName.CUSTOMER_SERVICE, [
        {"store_id": store.id, "is_default": True}
    ])
    headers = _login(auth_client, "support.activate.denied")
    fake = FakeUpstream([_agent(
        user_id="22222222-2222-4222-8222-222222222222",
        store_codes=("STORE-ACTIVATE-DENIED",), identity_status="BOUND",
    )])
    app.dependency_overrides[get_channel_agent_upstream] = lambda: fake

    denied = auth_client.post(
        "/api/v1/workspace/desktop-agent/activate",
        headers=headers,
        json={
            "agent_id": "agent-desktop-001",
            "device_id": "device-desktop-001",
            "store_id": store.id,
        },
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "AUTHORIZATION_DENIED"
    assert fake.activation_calls == []


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
    ("exception", "code", "status_code"),
    [
        (ChannelAgentNotConfigured("missing"), "CHANNEL_AGENT_INTEGRATION_NOT_CONFIGURED", 503),
        (ChannelAgentUnavailable("offline"), "CHANNEL_AGENT_SERVER_UNREACHABLE", 503),
        (ChannelAgentPermissionInvalid("revoked"), "CHANNEL_AGENT_OPERATOR_PERMISSION_INVALID", 503),
        (ChannelAgentResponseInvalid("drift"), "CHANNEL_AGENT_RESPONSE_INVALID", 502),
    ],
)
def test_upstream_exceptions_have_distinct_non_200_envelopes(
    auth_client: TestClient, session: Session, exception: Exception, code: str,
    status_code: int,
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
    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert response.json()["request_id"]
