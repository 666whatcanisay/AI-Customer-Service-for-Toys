from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from channel_agent.contract import (
    AgentHeartbeatRequest,
    AgentRegistrationRequest,
    AgentRuntimeStatus,
)
from channel_agent.identity import (
    AgentIdentity,
    AgentIdentityActivationRequest,
    AgentIdentityAuditAction,
    AgentIdentityBindingRequest,
    AgentIdentityStatus,
)
from channel_engine.agent.node_api import (
    AgentIdentityDisabled,
    AgentIdentityTransitionError,
    ChannelAgentNodeRegistry,
)
from channel_engine.security.rbac import (
    OperatorAccessDenied,
    OperatorPermission,
    OperatorPrincipal,
    OperatorRole,
)


NOW = datetime(2026, 8, 6, 11, 0, tzinfo=UTC)


def principal(role: OperatorRole, identity: str) -> OperatorPrincipal:
    return OperatorPrincipal(
        principal_id=identity,
        roles=frozenset({role}),
        identity_provider="identity-test",
        authenticated_at=NOW,
    )


def registration(
    *,
    user_reference: str | None = None,
    store_reference: str | None = None,
) -> AgentRegistrationRequest:
    return AgentRegistrationRequest(
        agent_id="agent-identity-001",
        device_id="device-identity-001",
        agent_version="1.0.0",
        user_reference=user_reference,
        store_reference=store_reference,
        hostname="service-pc-identity-001",
        status=AgentRuntimeStatus.STARTING,
        timestamp=NOW,
    )


def heartbeat(
    *,
    user_id: str | None = None,
    store_id: str | None = None,
) -> AgentHeartbeatRequest:
    return AgentHeartbeatRequest(
        agent_id="agent-identity-001",
        device_id="device-identity-001",
        user_id=user_id,
        store_id=store_id,
        version="1.0.0",
        hostname="service-pc-identity-001",
        status=AgentRuntimeStatus.ONLINE,
        timestamp=NOW,
    )


def test_identity_model_requires_references_for_bound_states() -> None:
    with pytest.raises(ValidationError, match="bound identity requires"):
        AgentIdentity(
            agent_id="agent-identity-001",
            device_id="device-identity-001",
            status=AgentIdentityStatus.BOUND,
            created_at=NOW,
            updated_at=NOW,
        )


def test_registration_claims_cannot_self_bind_or_enable_production() -> None:
    registry = ChannelAgentNodeRegistry(clock=lambda: NOW)

    response = registry.register(
        registration(
            user_reference="user-ref-001",
            store_reference="store-ref-001",
        )
    )

    assert response.identity.status is AgentIdentityStatus.UNBOUND
    assert response.identity.user_id is None
    assert response.identity.store_id is None
    assert response.production_eligible is False


def test_admin_binding_activation_and_heartbeat_form_active_identity() -> None:
    registry = ChannelAgentNodeRegistry(clock=lambda: NOW)
    registry.register(registration())
    admin = principal(OperatorRole.ADMIN, "admin-identity-001")

    bound = registry.bind_identity(
        "agent-identity-001",
        AgentIdentityBindingRequest(
            user_reference="user-ref-001",
            store_reference="store-ref-001",
            reason="approved workstation assignment",
        ),
        admin,
    )
    active = registry.activate_identity(
        "agent-identity-001",
        AgentIdentityActivationRequest(reason="identity references verified"),
        admin,
    )
    ack = registry.heartbeat(
        "agent-identity-001",
        heartbeat(user_id="user-ref-001", store_id="store-ref-001"),
    )
    audit = registry.list_identity_audit(admin)

    assert bound.status is AgentIdentityStatus.BOUND
    assert bound.production_eligible is False
    assert active.status is AgentIdentityStatus.ACTIVE
    assert active.production_eligible is True
    assert ack.identity_status is AgentIdentityStatus.ACTIVE
    assert ack.production_eligible is True
    assert [event.action for event in audit.items] == [
        AgentIdentityAuditAction.BIND,
        AgentIdentityAuditAction.ACTIVATE,
    ]
    assert all(event.operator_id == "admin-identity-001" for event in audit.items)


def test_unbind_disables_identity_clears_references_and_blocks_heartbeat() -> None:
    registry = ChannelAgentNodeRegistry(clock=lambda: NOW)
    registry.register(registration())
    admin = principal(OperatorRole.ADMIN, "admin-identity-001")
    registry.bind_identity(
        "agent-identity-001",
        AgentIdentityBindingRequest(
            user_reference="user-ref-001",
            store_reference="store-ref-001",
            reason="approved assignment",
        ),
        admin,
    )
    registry.activate_identity(
        "agent-identity-001",
        AgentIdentityActivationRequest(reason="references verified"),
        admin,
    )

    disabled = registry.unbind_identity(
        "agent-identity-001",
        "workstation removed from service",
        admin,
    )

    assert disabled.status is AgentIdentityStatus.DISABLED
    assert disabled.user_id is None
    assert disabled.store_id is None
    assert disabled.production_eligible is False
    with pytest.raises(AgentIdentityDisabled):
        registry.heartbeat(
            "agent-identity-001",
            heartbeat(user_id="user-ref-001", store_id="store-ref-001"),
        )
    with pytest.raises(AgentIdentityTransitionError):
        registry.bind_identity(
            "agent-identity-001",
            AgentIdentityBindingRequest(
                user_reference="user-ref-002",
                store_reference="store-ref-002",
                reason="attempted rebind",
            ),
            admin,
        )


def test_operator_cannot_read_or_change_identity_binding() -> None:
    registry = ChannelAgentNodeRegistry(clock=lambda: NOW)
    registry.register(registration())
    operator = principal(OperatorRole.OPERATOR, "operator-identity-001")

    with pytest.raises(OperatorAccessDenied) as read_denied:
        registry.list_agents(operator)
    with pytest.raises(OperatorAccessDenied) as write_denied:
        registry.bind_identity(
            "agent-identity-001",
            AgentIdentityBindingRequest(
                user_reference="user-ref-001",
                store_reference="store-ref-001",
                reason="unauthorized attempt",
            ),
            operator,
        )

    assert read_denied.value.permission is OperatorPermission.AGENT_IDENTITY_READ
    assert write_denied.value.permission is OperatorPermission.AGENT_IDENTITY_MANAGE
    assert registry.identity_snapshot("agent-identity-001").status is AgentIdentityStatus.UNBOUND


def test_invalid_transition_and_sensitive_audit_reason_fail_safely() -> None:
    registry = ChannelAgentNodeRegistry(clock=lambda: NOW)
    registry.register(registration())
    admin = principal(OperatorRole.ADMIN, "admin-identity-001")

    with pytest.raises(AgentIdentityTransitionError):
        registry.activate_identity(
            "agent-identity-001",
            AgentIdentityActivationRequest(reason="skip binding"),
            admin,
        )
    registry.bind_identity(
        "agent-identity-001",
        AgentIdentityBindingRequest(
            user_reference="user-ref-001",
            store_reference="store-ref-001",
            reason="token=must-not-be-recorded",
        ),
        admin,
    )
    serialized = registry.list_identity_audit(admin).model_dump_json()
    assert "must-not-be-recorded" not in serialized
    assert "[REDACTED]" in serialized
