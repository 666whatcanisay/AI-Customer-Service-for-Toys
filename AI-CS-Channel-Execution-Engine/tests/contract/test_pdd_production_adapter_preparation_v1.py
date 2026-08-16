from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from channel_engine.channel import (
    AdapterHealthStatus,
    ChannelCredentialReference,
    ChannelSessionUnavailable,
    FakePDDCredentialProvider,
    FakePDDOutboundTransport,
    FakePDDProductionObservationTransport,
    PDDCredentialRotationError,
    PDDOutboundMode,
    PDDProductionAction,
    PDDProductionPolicyConfig,
    PDDProductionPolicyDecision,
    PDDProductionRiskLevel,
    PDDProductionSafetyError,
    PDDProductionSendPolicy,
    PDDProductionSessionState,
    PlatformAdapter,
)

from tests.pdd_production_support import (
    ProductionClock,
    build_production_adapter,
    production_credential,
)


def test_production_adapter_lifecycle_uses_five_explicit_states(foundation) -> None:
    clock = ProductionClock()
    adapter, provider, observation, outbound, _ledger, _authorization = (
        build_production_adapter(foundation, clock)
    )

    assert [state.value for state in PDDProductionSessionState] == [
        "CREATED",
        "CONNECTED",
        "ACTIVE",
        "EXPIRED",
        "DISCONNECTED",
    ]
    assert isinstance(adapter, PlatformAdapter)
    assert adapter.get_session().state is PDDProductionSessionState.CREATED
    assert adapter.health_check().status is AdapterHealthStatus.UNHEALTHY

    connected = adapter.connect()
    assert connected.state is PDDProductionSessionState.CONNECTED
    assert adapter.health_check().status is AdapterHealthStatus.DEGRADED
    with pytest.raises(ChannelSessionUnavailable, match="not ACTIVE"):
        adapter.receive_message()

    heartbeat = adapter.heartbeat()
    assert heartbeat.healthy is True
    assert heartbeat.real_platform_contacted is False
    assert adapter.get_session().state is PDDProductionSessionState.ACTIVE
    assert adapter.health_check().status is AdapterHealthStatus.HEALTHY

    adapter.disconnect()
    assert adapter.get_session().state is PDDProductionSessionState.DISCONNECTED
    assert adapter.session_manager.history == (
        PDDProductionSessionState.CREATED,
        PDDProductionSessionState.CONNECTED,
        PDDProductionSessionState.ACTIVE,
        PDDProductionSessionState.DISCONNECTED,
    )
    assert provider.acquire_count == 1
    assert provider.release_count == 1
    assert observation.open_count == 1
    assert observation.close_count == 1
    assert observation.real_platform_call_count == 0
    assert outbound.real_platform_call_count == 0


def test_credential_reference_rotation_expiration_and_redaction(foundation) -> None:
    clock = ProductionClock()
    first = production_credential("rotation-v1")
    second = production_credential("rotation-v2")
    provider = FakePDDCredentialProvider(
        clock=clock,
        lease_ttl=timedelta(seconds=30),
    )
    provider.register(first, expires_at=clock() + timedelta(hours=1))
    adapter, _provider, _observation, _outbound, _ledger, _authorization = (
        build_production_adapter(
            foundation,
            clock,
            credential=first,
            provider=provider,
        )
    )

    adapter.connect()
    adapter.heartbeat()
    serialized = (
        first.model_dump_json()
        + adapter.get_session().model_dump_json()
        + adapter.health_check().model_dump_json()
    ).lower()
    for prohibited in (
        '"token"',
        '"secret"',
        '"password"',
        '"cookie"',
        "plaintext-pdd-value",
        "credential_lease_id",
    ):
        assert prohibited not in serialized
    assert provider.secret_value_access_count == 0

    with pytest.raises(PDDCredentialRotationError, match="disconnect"):
        adapter.rotate_credentials(second)
    adapter.disconnect()
    provider.rotate(
        first,
        second,
        expires_at=clock() + timedelta(hours=2),
    )
    adapter.rotate_credentials(second)
    rotated = adapter.reconnect()
    assert rotated.state is PDDProductionSessionState.ACTIVE
    assert rotated.credential_version == "rotation-v2"
    assert provider.rotation_count == 1

    clock.advance(timedelta(seconds=31))
    expired = adapter.heartbeat()
    assert expired.state is PDDProductionSessionState.EXPIRED
    assert adapter.get_session().state is PDDProductionSessionState.EXPIRED
    with pytest.raises(ChannelSessionUnavailable, match="not ACTIVE"):
        adapter.receive_message()

    with pytest.raises(ValidationError):
        ChannelCredentialReference.model_validate(
            {
                **first.model_dump(mode="json"),
                "token": "plaintext-pdd-value",
            }
        )


def test_session_failure_recovery_requires_new_active_generation(foundation) -> None:
    clock = ProductionClock()
    observation = FakePDDProductionObservationTransport(
        clock=clock,
        healthy=False,
    )
    adapter, provider, _observation, _outbound, _ledger, _authorization = (
        build_production_adapter(
            foundation,
            clock,
            observation=observation,
        )
    )

    first = adapter.connect()
    failed = adapter.heartbeat()
    assert failed.healthy is False
    assert failed.state is PDDProductionSessionState.CONNECTED
    assert adapter.health_check().status is AdapterHealthStatus.DEGRADED
    with pytest.raises(ChannelSessionUnavailable, match="not ACTIVE"):
        adapter.receive_message()

    observation.healthy = True
    recovered = adapter.reconnect()
    assert recovered.state is PDDProductionSessionState.ACTIVE
    assert recovered.session_id != first.session_id
    assert recovered.generation == 2
    assert provider.acquire_count == 2
    assert provider.release_count == 1
    assert observation.open_count == 2
    assert observation.close_count == 1


def test_policy_is_low_risk_allowlisted_send_only() -> None:
    policy = PDDProductionSendPolicy(
        PDDProductionPolicyConfig(
            allowed_account_refs=frozenset({"account-allowlisted"}),
            allowed_conversation_ids=frozenset({"conversation-allowlisted"}),
        )
    )

    allowed = policy.evaluate_action(
        action=PDDProductionAction.SEND_MESSAGE,
        risk_level=PDDProductionRiskLevel.LOW,
        account_ref="account-allowlisted",
        conversation_id="conversation-allowlisted",
    )
    high_risk = policy.evaluate_action(
        action=PDDProductionAction.SEND_MESSAGE,
        risk_level=PDDProductionRiskLevel.HIGH,
        account_ref="account-allowlisted",
        conversation_id="conversation-allowlisted",
    )
    not_allowlisted = policy.evaluate_action(
        action=PDDProductionAction.SEND_MESSAGE,
        risk_level=PDDProductionRiskLevel.LOW,
        account_ref="account-not-allowed",
        conversation_id="conversation-allowlisted",
    )
    refund = policy.evaluate_action(
        action=PDDProductionAction.REFUND,
        risk_level=PDDProductionRiskLevel.HIGH,
        account_ref="account-allowlisted",
        conversation_id="conversation-allowlisted",
    )
    automatic = policy.evaluate_action(
        action=PDDProductionAction.AUTOMATIC_REPLY,
        risk_level=PDDProductionRiskLevel.LOW,
        account_ref="account-allowlisted",
        conversation_id="conversation-allowlisted",
    )

    assert allowed.decision is PDDProductionPolicyDecision.ALLOW_SEND_MESSAGE
    assert high_risk.reason_code == "PDD_RISK_LEVEL_DENIED"
    assert not_allowlisted.reason_code == "PDD_ACCOUNT_NOT_ALLOWLISTED"
    assert refund.blocked_action is True
    assert refund.reason_code == "PDD_ACTION_BLOCKED"
    assert automatic.blocked_action is True
    assert all(
        result.decision is PDDProductionPolicyDecision.DENY
        for result in (high_risk, not_allowlisted, refund, automatic)
    )

    with pytest.raises(ValidationError, match="mandatory high-impact"):
        PDDProductionPolicyConfig(
            allowed_account_refs=frozenset({"account-allowlisted"}),
            allowed_conversation_ids=frozenset({"conversation-allowlisted"}),
            blocked_actions=frozenset({PDDProductionAction.REFUND}),
        )


def test_preparation_v1_rejects_real_transport_capabilities(foundation) -> None:
    class RealObservationStub(FakePDDProductionObservationTransport):
        real_platform_transport = True

    class RealOutboundStub(FakePDDOutboundTransport):
        real_platform_transport = True

    clock = ProductionClock()
    credential = production_credential()
    provider = FakePDDCredentialProvider(clock=clock)
    provider.register(credential, expires_at=clock() + timedelta(hours=1))

    with pytest.raises(PDDProductionSafetyError, match="real PDD transport"):
        build_production_adapter(
            foundation,
            clock,
            credential=credential,
            provider=provider,
            observation=RealObservationStub(clock=clock),
        )

    adapter, _provider, observation, _outbound, ledger, authorization = (
        build_production_adapter(
            foundation,
            clock,
            credential=credential,
            provider=provider,
        )
    )
    with pytest.raises(PDDProductionSafetyError, match="real PDD outbound"):
        type(adapter)(
            credential,
            provider,
            observation,
            RealOutboundStub(PDDOutboundMode.SUCCESS, clock=clock),
            ledger,
            authorization,
            adapter.policy,
            clock=clock,
        )
