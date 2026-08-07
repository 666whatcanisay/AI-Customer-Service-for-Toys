from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from channel_agent.binding import (
    AgentBindingStore,
    AgentEnrollmentGrantRequest,
    AgentEnrollmentRequest,
    AgentStoreBindingUpdateRequest,
)
from channel_agent.client import AgentConnectionError
from channel_agent.config import ChannelAgentConfig
from channel_agent.contract import (
    AgentHeartbeatAck,
    AgentHeartbeatRequest,
    AgentRegistrationRequest,
    AgentRegistrationResponse,
    AgentRuntimeStatus,
    ManagedAgentConfig,
)
from channel_agent.identity import (
    AgentIdentity,
    AgentIdentityActivationRequest,
    AgentIdentityAuditAction,
    AgentIdentityStatus,
    AgentOnlineStatus,
)
from channel_agent.logger import SafeAgentLogger
from channel_agent.runtime import ChannelAgentRuntime
from channel_engine.agent.binding_repository import (
    SqlAlchemyAgentIdentityRepository,
)
from channel_engine.agent.node_api import (
    AgentDeviceBindingConflict,
    AgentEnrollmentDenied,
    AgentIdentityClaimMismatch,
    ChannelAgentNodeRegistry,
)
from channel_engine.security.rbac import (
    OperatorAccessDenied,
    OperatorPrincipal,
    OperatorRole,
)
from channel_engine.storage import create_engine_and_session, create_schema


NOW = datetime(2026, 8, 6, 16, 0, tzinfo=UTC)
CODE = "A" * 32


def principal(role: OperatorRole, identifier: str) -> OperatorPrincipal:
    return OperatorPrincipal(
        principal_id=identifier,
        roles=frozenset({role}),
        identity_provider="runtime-binding-test",
        authenticated_at=NOW,
    )


def registration() -> AgentRegistrationRequest:
    return AgentRegistrationRequest(
        agent_id="agent-runtime-binding-001",
        device_id="device-runtime-binding-001",
        agent_version="1.0.0",
        hostname="service-pc-runtime-binding-001",
        status=AgentRuntimeStatus.STARTING,
        timestamp=NOW,
    )


def heartbeat(
    *,
    user_id: str | None = None,
    stores: tuple[str, ...] = (),
    binding_revision: int = 0,
) -> AgentHeartbeatRequest:
    return AgentHeartbeatRequest(
        agent_id="agent-runtime-binding-001",
        device_id="device-runtime-binding-001",
        user_id=user_id,
        store_id=stores[0] if stores else None,
        store_ids=stores,
        binding_revision=binding_revision,
        version="1.0.0",
        hostname="service-pc-runtime-binding-001",
        status=AgentRuntimeStatus.ONLINE,
        timestamp=NOW,
    )


def grant_request() -> AgentEnrollmentGrantRequest:
    return AgentEnrollmentGrantRequest(
        agent_id="agent-runtime-binding-001",
        device_id="device-runtime-binding-001",
        user_reference="user-runtime-binding-001",
        store_references=("store-a", "store-b"),
        expires_in_seconds=600,
        reason="approved customer service workstation",
    )


def enroll(registry: ChannelAgentNodeRegistry) -> None:
    admin = principal(OperatorRole.ADMIN, "admin-runtime-binding")
    registry.register(registration())
    registry.issue_enrollment_grant(grant_request(), admin)
    registry.enroll(
        AgentEnrollmentRequest(
            agent_id="agent-runtime-binding-001",
            device_id="device-runtime-binding-001",
            binding_code=CODE,
        )
    )


def test_one_time_enrollment_is_admin_authorized_and_code_is_not_retained() -> None:
    registry = ChannelAgentNodeRegistry(
        clock=lambda: NOW,
        binding_code_factory=lambda: CODE,
    )
    registry.register(registration())
    operator = principal(OperatorRole.OPERATOR, "operator-runtime-binding")
    admin = principal(OperatorRole.ADMIN, "admin-runtime-binding")

    with pytest.raises(OperatorAccessDenied):
        registry.issue_enrollment_grant(grant_request(), operator)
    grant = registry.issue_enrollment_grant(grant_request(), admin)
    request = AgentEnrollmentRequest(
        agent_id="agent-runtime-binding-001",
        device_id="device-runtime-binding-001",
        binding_code=grant.binding_code,
    )
    response = registry.enroll(request)

    assert response.binding.identity_status is AgentIdentityStatus.BOUND
    assert response.binding.user_id == "user-runtime-binding-001"
    assert response.binding.store_ids == ("store-a", "store-b")
    assert response.binding.binding_revision == 1
    assert grant.binding_code not in repr(request)
    assert grant.binding_code not in repr(grant)
    assert grant.binding_code not in repr(registry.__dict__)
    with pytest.raises(AgentEnrollmentDenied):
        registry.enroll(request)
    audit = registry.list_identity_audit(admin)
    assert [item.action for item in audit.items] == [AgentIdentityAuditAction.ENROLL]
    assert audit.items[0].operator_id == "admin-runtime-binding"


def test_multi_store_update_and_heartbeat_sync_are_server_authoritative() -> None:
    registry = ChannelAgentNodeRegistry(
        clock=lambda: NOW,
        binding_code_factory=lambda: CODE,
    )
    enroll(registry)
    admin = principal(OperatorRole.ADMIN, "admin-runtime-binding")
    active = registry.activate_identity(
        "agent-runtime-binding-001",
        AgentIdentityActivationRequest(reason="binding references verified"),
        admin,
    )
    first_ack = registry.heartbeat(
        "agent-runtime-binding-001",
        heartbeat(),
    )
    updated = registry.update_store_bindings(
        "agent-runtime-binding-001",
        AgentStoreBindingUpdateRequest(
            store_references=("store-a", "store-c", "store-d"),
            reason="authorized store assignment changed",
        ),
        admin,
    )

    assert active.production_eligible is True
    assert first_ack.identity is not None
    assert first_ack.identity.effective_store_ids == ("store-a", "store-b")
    assert updated.effective_store_ids == ("store-a", "store-c", "store-d")
    assert updated.binding_revision == 3
    with pytest.raises(AgentIdentityClaimMismatch):
        registry.heartbeat(
            "agent-runtime-binding-001",
            heartbeat(
                user_id="user-runtime-binding-001",
                stores=("store-a", "store-b"),
                binding_revision=3,
            ),
        )
    synchronized = registry.heartbeat(
        "agent-runtime-binding-001",
        heartbeat(),
    )
    assert synchronized.identity is not None
    assert synchronized.identity.effective_store_ids == (
        "store-a",
        "store-c",
        "store-d",
    )
    disabled = registry.unbind_identity(
        "agent-runtime-binding-001",
        "workstation assignment revoked",
        admin,
    )
    assert disabled.status is AgentIdentityStatus.DISABLED
    assert disabled.user_id is None
    assert disabled.effective_store_ids == ()
    assert disabled.binding_revision == 4


def test_operator_cannot_change_store_assignments() -> None:
    registry = ChannelAgentNodeRegistry(
        clock=lambda: NOW,
        binding_code_factory=lambda: CODE,
    )
    enroll(registry)
    operator = principal(OperatorRole.OPERATOR, "operator-runtime-binding")

    with pytest.raises(OperatorAccessDenied):
        registry.update_store_bindings(
            "agent-runtime-binding-001",
            AgentStoreBindingUpdateRequest(
                store_references=("store-z",),
                reason="self-selected store",
            ),
            operator,
        )

    identity = registry.identity_snapshot("agent-runtime-binding-001")
    assert identity is not None
    assert identity.effective_store_ids == ("store-a", "store-b")


def test_device_cannot_register_as_a_second_agent() -> None:
    registry = ChannelAgentNodeRegistry(clock=lambda: NOW)
    registry.register(registration())

    with pytest.raises(AgentDeviceBindingConflict):
        registry.register(
            registration().model_copy(update={"agent_id": "agent-runtime-binding-002"})
        )


def test_expired_binding_code_fails_closed() -> None:
    current = [NOW]
    registry = ChannelAgentNodeRegistry(
        clock=lambda: current[0],
        binding_code_factory=lambda: CODE,
    )
    registry.register(registration())
    registry.issue_enrollment_grant(
        grant_request().model_copy(update={"expires_in_seconds": 60}),
        principal(OperatorRole.ADMIN, "admin-runtime-binding"),
    )
    current[0] = NOW + timedelta(seconds=60)

    with pytest.raises(AgentEnrollmentDenied):
        registry.enroll(
            AgentEnrollmentRequest(
                agent_id="agent-runtime-binding-001",
                device_id="device-runtime-binding-001",
                binding_code=CODE,
            )
        )


def test_identity_binding_persists_and_admin_view_reports_offline_after_restart(
    tmp_path,
) -> None:
    engine, session_factory = create_engine_and_session(
        f"sqlite:///{(tmp_path / 'runtime-binding.sqlite3').as_posix()}"
    )
    create_schema(engine)
    repository = SqlAlchemyAgentIdentityRepository(session_factory)
    first = ChannelAgentNodeRegistry(
        clock=lambda: NOW,
        identity_repository=repository,
        binding_code_factory=lambda: CODE,
    )
    enroll(first)
    admin = principal(OperatorRole.ADMIN, "admin-runtime-binding")
    first.activate_identity(
        "agent-runtime-binding-001",
        AgentIdentityActivationRequest(reason="binding references verified"),
        admin,
    )

    restarted = ChannelAgentNodeRegistry(
        clock=lambda: NOW + timedelta(minutes=10),
        identity_repository=SqlAlchemyAgentIdentityRepository(session_factory),
    )
    view = restarted.list_agents(admin)

    assert view.count == 1
    assert view.items[0].identity.status is AgentIdentityStatus.ACTIVE
    assert view.items[0].identity.effective_store_ids == ("store-a", "store-b")
    assert view.items[0].online_status is AgentOnlineStatus.OFFLINE
    assert view.items[0].runtime_status == "OFFLINE"
    engine.dispose()


def test_local_binding_store_contains_references_but_no_binding_code(tmp_path) -> None:
    registry = ChannelAgentNodeRegistry(
        clock=lambda: NOW,
        binding_code_factory=lambda: CODE,
    )
    enroll(registry)
    identity = registry.identity_snapshot("agent-runtime-binding-001")
    assert identity is not None
    store = AgentBindingStore(tmp_path / "runtime" / "agent-binding.json")

    saved = store.save_identity(identity)
    serialized = store.path.read_text(encoding="utf-8")

    assert store.load() == saved
    assert saved.store_ids == ("store-a", "store-b")
    assert "binding_code" not in serialized.casefold()
    assert CODE not in serialized


class RecoveringBoundClient:
    def __init__(self) -> None:
        self.heartbeat_count = 0
        self.config = ManagedAgentConfig(
            revision="runtime-binding-recovery-v1",
            heartbeat_interval_seconds=30,
        )

    def register(self, **_kwargs) -> AgentRegistrationResponse:
        return AgentRegistrationResponse(
            registration_id="registration:runtime-binding-recovery",
            identity=AgentIdentity(
                agent_id="agent-runtime-binding-001",
                device_id="device-runtime-binding-001",
                user_id="user-runtime-binding-001",
                store_id="store-a",
                store_ids=("store-a", "store-b"),
                status=AgentIdentityStatus.ACTIVE,
                binding_revision=2,
                created_at=NOW,
                updated_at=NOW,
            ),
            production_eligible=True,
            config=self.config,
            server_time=NOW,
        )

    def report_status(self, **_kwargs) -> AgentHeartbeatAck:
        self.heartbeat_count += 1
        if self.heartbeat_count == 1:
            raise AgentConnectionError("synthetic disconnect")
        identity = AgentIdentity(
            agent_id="agent-runtime-binding-001",
            device_id="device-runtime-binding-001",
            user_id="user-runtime-binding-001",
            store_id="store-a",
            store_ids=("store-a", "store-c"),
            status=AgentIdentityStatus.ACTIVE,
            binding_revision=3,
            created_at=NOW,
            updated_at=NOW,
        )
        return AgentHeartbeatAck(
            identity_status=identity.status,
            production_eligible=True,
            config_revision=self.config.revision,
            identity=identity,
            server_time=NOW,
        )

    def fetch_config(self) -> ManagedAgentConfig:
        return self.config

    def close(self) -> None:
        return None


def test_disconnect_recovery_synchronizes_authoritative_binding(tmp_path) -> None:
    client = RecoveringBoundClient()
    runtime = ChannelAgentRuntime(
        ChannelAgentConfig(
            server_url="https://channel-engine.example",
            agent_id="agent-runtime-binding-001",
            device_id="device-runtime-binding-001",
        ),
        client,
        SafeAgentLogger(tmp_path / "binding-recovery.jsonl"),
        hostname="service-pc-runtime-binding-001",
        clock=lambda: NOW,
    )

    started = runtime.start(background_heartbeat=False)
    degraded = runtime.heartbeat_once()
    recovered = runtime.heartbeat_once()
    runtime.close()

    assert started.status is AgentRuntimeStatus.ONLINE
    assert started.store_ids == ("store-a", "store-b")
    assert degraded.status is AgentRuntimeStatus.DEGRADED
    assert recovered.status is AgentRuntimeStatus.ONLINE
    assert recovered.store_ids == ("store-a", "store-c")
    assert recovered.binding_revision == 3
    assert recovered.consecutive_failures == 0
