from __future__ import annotations

import pytest

from channel_engine.channel import (
    ChannelAuthenticationScheme,
    ChannelCredentialReference,
    FakePDDCredentialProvider,
    PDDProductionSafetyError,
    PDDProductionSessionManager,
)
from channel_engine.app import create_app
from channel_engine.config import Settings
from channel_engine.environment import load_environment_profile
from channel_engine.pdd_adapter import (
    PDDProductionReadinessRecheck,
    PDDReceiveTransportDescriptor,
    PDDTransportActivationState,
    PDDTransportOrigin,
)


def test_fake_transport_is_rejected_from_production_composition() -> None:
    with pytest.raises(ValueError, match="fake transport"):
        PDDReceiveTransportDescriptor(
            implementation_id="FakePDDTransport",
            origin=PDDTransportOrigin.PRODUCTION,
            activation_state=PDDTransportActivationState.DISABLED,
            fake_transport=True,
        )


def test_real_transport_slot_is_default_denied_without_activation_evidence() -> None:
    class DormantRealReceiveTransport:
        transport_name = "pdd-authorized-receive-transport-v1"
        real_platform_transport = True
        call_count = 0

        def open(self, session):
            self.call_count += 1
            raise AssertionError("must not connect in readiness tests")

        def close(self, session):
            self.call_count += 1

        def heartbeat(self, session):
            self.call_count += 1
            return False

        def poll(self, session, *, cursor, after_offset, limit):
            self.call_count += 1
            raise AssertionError("must not poll in readiness tests")

    transport = DormantRealReceiveTransport()
    credential = ChannelCredentialReference(
        credential_id="pdd/store-a/session",
        provider="secret-manager",
        version="v1",
        account_ref="store-a",
        auth_scheme=ChannelAuthenticationScheme.MANAGED_SESSION,
    )

    with pytest.raises(PDDProductionSafetyError, match="activation grant"):
        PDDProductionSessionManager(
            credential,
            FakePDDCredentialProvider(),
            transport,
        )

    assert transport.call_count == 0


def test_structural_recheck_unblocks_code_but_keeps_real_activation_disabled() -> None:
    dormant = PDDReceiveTransportDescriptor(
        implementation_id="pdd-receive-boundary-v1",
        origin=PDDTransportOrigin.PRODUCTION,
        activation_state=PDDTransportActivationState.DISABLED,
        fake_transport=False,
    )

    result = PDDProductionReadinessRecheck.evaluate(
        transport=dormant,
        cursor_safe=True,
        credential_reference_only=True,
        rbac_ready=True,
        selector_evidence_gate_ready=True,
        monitoring_ready=True,
    )

    assert result.status == "PDD_PRODUCTION_READINESS_UNBLOCKED"
    assert result.structural_blockers == ()
    assert all(gate.passed for gate in result.gates)
    assert result.real_platform_activation_allowed is False
    assert result.real_send_enabled is False


def test_recheck_fails_if_any_structural_gate_remains() -> None:
    dormant = PDDReceiveTransportDescriptor(
        implementation_id="pdd-receive-boundary-v1",
        origin=PDDTransportOrigin.PRODUCTION,
        activation_state=PDDTransportActivationState.DISABLED,
        fake_transport=False,
    )
    with pytest.raises(RuntimeError, match="RBAC"):
        PDDProductionReadinessRecheck.evaluate(
            transport=dormant,
            cursor_safe=True,
            credential_reference_only=True,
            rbac_ready=False,
            selector_evidence_gate_ready=True,
            monitoring_ready=True,
        )


def test_production_application_never_falls_back_to_fake_pdd(tmp_path) -> None:
    production_profile = load_environment_profile(
        {
            "CHANNEL_ENGINE_PROFILE": "production",
            "CHANNEL_ENGINE_GATEWAY_ENDPOINT": "https://ai-cs.production.invalid",
            "CHANNEL_ENGINE_ADAPTER_MODE": "PRODUCTION_PREPARATION",
            "CHANNEL_ENGINE_CREDENTIAL_PROVIDER": "secret-manager",
            "CHANNEL_ENGINE_CREDENTIAL_ID": "pdd-production-observer",
            "CHANNEL_ENGINE_CREDENTIAL_VERSION": "v1",
            "CHANNEL_ENGINE_ACCOUNT_REF": "authorized-store-a",
            "CHANNEL_ENGINE_POLICY_PROFILE": "pdd-production-observation.v1",
            "CHANNEL_ENGINE_ALLOWED_ACCOUNTS": "authorized-store-a",
            "CHANNEL_ENGINE_ALLOWED_CONVERSATIONS": "authorized-conversation-a",
            "CHANNEL_ENGINE_ALLOWED_ACTIONS": "OBSERVE_MESSAGE,REQUEST_DECISION",
            "CHANNEL_ENGINE_PRODUCTION_ENABLED": "true",
            "CHANNEL_ENGINE_PRODUCTION_CONFIRMATION": "ENABLE_CHANNEL_ENGINE_PRODUCTION",
        }
    )
    settings = Settings(
        database_url=(
            f"sqlite:///{(tmp_path / 'production-composition.sqlite3').as_posix()}"
        ),
        environment_profile=production_profile,
    )
    with pytest.raises(ValueError, match="TRANSPORT_DESCRIPTOR_REQUIRED"):
        create_app(settings=settings)

    dormant = PDDReceiveTransportDescriptor(
        implementation_id="pdd-receive-boundary-v1",
        origin=PDDTransportOrigin.PRODUCTION,
        activation_state=PDDTransportActivationState.DISABLED,
        fake_transport=False,
    )
    application = create_app(
        settings=settings,
        pdd_receive_transport=dormant,
    )

    assert application.state.adapter_registry.discover() == ()
