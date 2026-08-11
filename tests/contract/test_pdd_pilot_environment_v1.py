from __future__ import annotations

import json
from datetime import timedelta

import pytest

from channel_engine.agent import (
    AgentBrowserConfig,
    AgentChannelConfig,
    AgentEnvironment,
    AgentSafetyConfig,
    AgentServerConfig,
    ChannelAgentConfig,
)
from channel_engine.browser import (
    BrowserLoginState,
    BrowserPageContext,
    BrowserProfileReference,
    BrowserSession,
    BrowserSessionState,
    ChromeLaunchStrategy,
    LocatorEngine,
    SelectorBinding,
    SelectorCapability,
    SelectorContractState,
    SelectorDiscoveryError,
    SelectorDiscoveryWorkflow,
    SelectorEvidenceEnvironment,
    SelectorKey,
    SelectorProbeResult,
    SelectorRegistry,
    draft_pdd_merchant_chat_v1,
)
from channel_engine.models.entities import utc_now
from channel_engine.pilot import (
    PDDStoreBindingDiscoveryError,
    PDDStoreBindingDiscoveryService,
    PilotBrowserDiscoveryLaunchConfig,
    PilotEnvironmentConfig,
    PilotEnvironmentFinalStatus,
    PilotEnvironmentService,
    PilotGatewayVerification,
    VerifiedSelectorStoreIdentitySource,
    build_selector_discovery_browser_session,
    load_pilot_environment_config,
)


def _environment_config(tmp_path) -> PilotEnvironmentConfig:
    chrome = tmp_path / "chrome.exe"
    chrome.write_bytes(b"test chrome placeholder")
    return PilotEnvironmentConfig(
        agent=ChannelAgentConfig(
            node_id="pdd-pilot-test-node",
            node_name="PDD Pilot Test Node",
            server=AgentServerConfig(
                server_url="http://127.0.0.1:18021",
                agent_token_reference="secret-ref://ai-cs/pilot/gateway-hmac",
            ),
            browser=AgentBrowserConfig(
                chrome_path=chrome.resolve(),
                profile_root=(tmp_path / "profiles").resolve(),
            ),
            channel=AgentChannelConfig(
                credential_reference=(
                    "credential-ref://pdd/pilot/manual-browser-session"
                )
            ),
            safety=AgentSafetyConfig(
                runtime_mode=AgentEnvironment.PILOT,
                dry_run=True,
                kill_switch=True,
            ),
        ),
        browser_profile_id="pdd-pilot-test-profile",
        merchant_chat_url="https://mms.pinduoduo.com/chat-merchant/index.html",
    )


def _gateway_verification() -> PilotGatewayVerification:
    return PilotGatewayVerification(
        endpoint="http://127.0.0.1:18021",
        client_id="channel-engine",
        key_id="pilot-env-v1",
        decision_route=True,
        health_route=True,
        signed_health_verified=True,
        health_status="UNHEALTHY",
        contract_version="1.0",
        gateway_version="ai-cs-gateway.v1",
        capability_version="decision.ai-cs-scope.v1",
        real_ai_cs_connected=True,
        verified_at=utc_now(),
    )


def _identity_selector_candidate():
    draft = draft_pdd_merchant_chat_v1()
    discovery = SelectorDiscoveryWorkflow.begin(
        draft,
        evidence_reference="discovery-ref://pdd/pilot/session-1",
    )
    return SelectorDiscoveryWorkflow.record_candidates(
        discovery,
        capabilities=frozenset({SelectorCapability.STORE_IDENTITY}),
        bindings=(
            SelectorBinding(
                key=SelectorKey.STORE_ID,
                engine=LocatorEngine.ATTRIBUTE,
                locator="data-store-id",
            ),
            SelectorBinding(
                key=SelectorKey.STORE_NAME,
                engine=LocatorEngine.ATTRIBUTE,
                locator="data-store-name",
            ),
        ),
        evidence_reference="evidence-ref://pdd/pilot/store-identity-probe-1",
    )


def _verified_identity_selector():
    candidate = _identity_selector_candidate()
    probe = SelectorProbeResult(
        contract_id=candidate.contract_id,
        contract_fingerprint=candidate.fingerprint(),
        page_context_id="page-pilot-1",
        passed=True,
        checked_at=utc_now(),
        page_fingerprint="sha256:" + "7" * 64,
    )
    verified_at = utc_now()
    return SelectorDiscoveryWorkflow.verify(
        candidate,
        probe,
        verified_at=verified_at,
        verified_by="test-ref://channel-engine/pilot-environment-suite",
        expires_at=verified_at + timedelta(days=365),
        applicable_page_version="synthetic-pilot-v1",
        environment=SelectorEvidenceEnvironment.SYNTHETIC,
    )


def _active_browser_session(selector_version: str) -> BrowserSession:
    now = utc_now()
    profile = BrowserProfileReference(
        profile_id="pdd-pilot-profile-1",
        account_ref="pdd-pilot-node-1",
        storage_reference="profile-ref://pdd/pilot/node-1",
    )
    page = BrowserPageContext(
        page_context_id="page-pilot-1",
        session_id="session-pilot-1",
        generation=1,
        selector_contract_version=selector_version,
        page_revision="page-revision-1",
        created_at=now,
    )
    return BrowserSession(
        session_id="session-pilot-1",
        account_ref=profile.account_ref,
        profile=profile,
        launch_strategy=ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT,
        state=BrowserSessionState.ACTIVE,
        login_state=BrowserLoginState.AUTHENTICATED,
        generation=1,
        page_context=page,
        started_at=now,
        last_heartbeat_at=now,
    )


class _StoreIdentityReader:
    read_only = True
    real_platform_source = True

    def read_values(self, page, bindings):  # type: ignore[no-untyped-def]
        assert page.page_context_id == "page-pilot-1"
        assert {binding.key for binding in bindings} == {
            SelectorKey.STORE_ID,
            SelectorKey.STORE_NAME,
        }
        return (
            {
                SelectorKey.STORE_ID: "pdd-store-observed-001",
                SelectorKey.STORE_NAME: "玩趣乐园积木店",
            },
            "evidence-ref://pdd/pilot/store-page-read-1",
            utc_now(),
        )


def test_deployment_environment_config_is_reference_only_and_unbound() -> None:
    config = load_pilot_environment_config("deploy/pdd-pilot-environment.json")

    assert config.agent.safety.runtime_mode is AgentEnvironment.PILOT
    assert config.agent.channel.store_binding is None
    assert config.agent.channel.credential_reference is not None
    assert config.inbound_transport_mode.value == "DISABLED"
    assert config.outbound_transport_enabled is False
    serialized = json.dumps(config.model_dump(mode="json"), ensure_ascii=False)
    assert "cookie=" not in serialized.casefold()
    assert "bearer " not in serialized.casefold()
    assert "pdd-store-id-must-be-verified" not in serialized


def test_environment_ready_provisions_profile_without_activating_transport(
    tmp_path,
) -> None:
    config = _environment_config(tmp_path)
    service = PilotEnvironmentService(config)

    profile = service.provision_profile_directory()
    status = service.readiness(
        _gateway_verification(),
        draft_pdd_merchant_chat_v1(),
        generated_at=utc_now(),
    )

    assert profile.is_dir()
    assert status.final_status is PilotEnvironmentFinalStatus.READY
    assert status.store_binding == "PENDING_PAGE_DISCOVERY"
    assert status.selector_state is SelectorContractState.DRAFT
    assert status.transports_active is False
    assert status.customer_message_read_enabled is False
    assert status.outbound_transport_enabled is False


def test_browser_discovery_session_is_prepared_but_not_started(tmp_path) -> None:
    launch = PilotBrowserDiscoveryLaunchConfig(
        merchant_chat_url="https://mms.pinduoduo.com/chat-merchant/index.html",
        node_id="pdd-pilot-test-node",
        profile_id="pdd-pilot-test-profile",
    )

    manager = build_selector_discovery_browser_session(
        launch,
        chrome_path=(tmp_path / "chrome.exe").resolve(),
        profile_root=(tmp_path / "profiles").resolve(),
    )
    session = manager.snapshot()

    assert session.state is BrowserSessionState.CREATED
    assert session.login_state is BrowserLoginState.UNKNOWN
    assert session.generation == 0
    assert session.profile.profile_id == "pdd-pilot-test-profile"
    assert not (tmp_path / "profiles").exists()


def test_selector_requires_discovery_and_passing_probe_before_activation() -> None:
    draft = draft_pdd_merchant_chat_v1()
    registry = SelectorRegistry()
    registry.register(draft)
    with pytest.raises(ValueError, match="verified"):
        registry.register(draft, activate=True)

    discovery = SelectorDiscoveryWorkflow.begin(
        draft,
        evidence_reference="discovery-ref://pdd/pilot/session-1",
    )
    discovery_registry = SelectorRegistry()
    with pytest.raises(ValueError, match="verified"):
        discovery_registry.register(discovery, activate=True)
    registry.promote(discovery)
    with pytest.raises(SelectorDiscoveryError, match="forbidden"):
        registry.promote(draft)

    candidate = _identity_selector_candidate()
    registry.promote(candidate)
    verified = _verified_identity_selector()
    registry.promote(verified, activate=True)
    assert registry.active("pdd", "merchant_chat").state is (
        SelectorContractState.VERIFIED
    )


def test_store_binding_is_derived_from_authenticated_real_page_source() -> None:
    selector = _verified_identity_selector()
    source = VerifiedSelectorStoreIdentitySource(_StoreIdentityReader())
    service = PDDStoreBindingDiscoveryService(
        "credential-ref://pdd/pilot/manual-browser-session"
    )

    binding = service.discover(
        _active_browser_session(selector.version),
        selector,
        source,
    )

    assert binding.store_id == "pdd-store-observed-001"
    assert binding.store_name == "玩趣乐园积木店"
    assert binding.credential_reference.startswith("credential-ref://")


def test_store_binding_rejects_non_real_identity_source() -> None:
    selector = _verified_identity_selector()
    reader = _StoreIdentityReader()
    reader.real_platform_source = False
    source = VerifiedSelectorStoreIdentitySource(reader)
    service = PDDStoreBindingDiscoveryService(
        "credential-ref://pdd/pilot/manual-browser-session"
    )

    with pytest.raises(PDDStoreBindingDiscoveryError, match="real read-only"):
        service.discover(
            _active_browser_session(selector.version),
            selector,
            source,
        )
