from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from channel_agent.binding import (
    AgentActiveStoreSelectionRequest,
    AgentEnrollmentGrantRequest,
    AgentEnrollmentRequest,
)
from channel_agent.config import ChannelAgentConfig, load_agent_config, save_agent_config
from channel_agent.contract import AgentRegistrationRequest, AgentRuntimeStatus
from channel_agent.control_v2 import (
    DeviceAuthenticationError,
    DeviceRequestSigner,
    DeviceRequestVerifier,
    LANDiscoveryAnnouncement,
    LANHostCandidate,
    PairDeviceResponse,
    announcement_proof,
    certificate_sha256,
)
from channel_agent.onboarding import (
    ChannelAgentOnboardingService,
    OnboardingError,
    PairingConfirmation,
)
from channel_agent.security import (
    DeviceCredentialMaterial,
    InMemoryDeviceCredentialStore,
    device_credential_reference,
)
from channel_engine.agent.node_api import (
    AgentActiveStoreSelectionBlocked,
    ChannelAgentNodeRegistry,
)
from channel_engine.security.rbac import OperatorPrincipal, OperatorRole


NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def _admin() -> OperatorPrincipal:
    return OperatorPrincipal(
        principal_id="admin-001",
        roles=frozenset({OperatorRole.ADMIN}),
        identity_provider="test",
        authenticated_at=NOW,
    )


def _registered_registry(*, blockers: tuple[str, ...] = ()) -> ChannelAgentNodeRegistry:
    registry = ChannelAgentNodeRegistry(
        clock=lambda: NOW,
        active_store_guard=lambda _agent, _current, _target: blockers,
        binding_code_factory=lambda: "A" * 32,
    )
    registry.register(
        AgentRegistrationRequest(
            agent_id="agent-001",
            device_id="device-001",
            agent_version="1.5.0",
            hostname="desk-001",
            status=AgentRuntimeStatus.STARTING,
            timestamp=NOW,
        )
    )
    grant = registry.issue_enrollment_grant(
        AgentEnrollmentGrantRequest(
            agent_id="agent-001",
            device_id="device-001",
            user_reference="user-001",
            store_references=("store-a", "store-b"),
            reason="客服多店铺授权",
        ),
        _admin(),
    )
    registry.enroll(
        AgentEnrollmentRequest(
            agent_id="agent-001",
            device_id="device-001",
            binding_code=grant.binding_code,
        )
    )
    return registry


def test_multistore_requires_one_explicit_observed_store_selection() -> None:
    registry = _registered_registry()
    before = registry.identity_snapshot("agent-001")

    assert before is not None
    assert before.authorized_stores == ("store-a", "store-b")
    assert before.effective_active_store_id is None

    with pytest.raises(Exception):
        registry.select_active_store(
            "agent-001",
            AgentActiveStoreSelectionRequest(
                device_id="device-001",
                store_reference="store-b",
                observed_store_reference="store-a",
                binding_revision=before.binding_revision,
                reason="页面店铺不匹配",
            ),
        )

    selected = registry.select_active_store(
        "agent-001",
        AgentActiveStoreSelectionRequest(
            device_id="device-001",
            store_reference="store-b",
            observed_store_reference="store-b",
            binding_revision=before.binding_revision,
            reason="客服人工选择当前工作店铺",
        ),
    )
    assert selected.effective_active_store_id == "store-b"
    assert selected.authorized_stores == ("store-a", "store-b")


def test_store_switch_fails_closed_while_workflow_is_active() -> None:
    registry = _registered_registry(blockers=("RUNNING_EXECUTION",))
    identity = registry.identity_snapshot("agent-001")
    assert identity is not None

    with pytest.raises(AgentActiveStoreSelectionBlocked) as failure:
        registry.select_active_store(
            "agent-001",
            AgentActiveStoreSelectionRequest(
                device_id="device-001",
                store_reference="store-a",
                observed_store_reference="store-a",
                binding_revision=identity.binding_revision,
                reason="客服人工选择当前工作店铺",
            ),
        )

    assert failure.value.blockers == ("RUNNING_EXECUTION",)


def test_device_signature_detects_replay_and_body_tampering() -> None:
    secret = b"v" * 32
    signer = DeviceRequestSigner("agent-001", "device-001", secret)
    verifier = DeviceRequestVerifier(
        lambda agent, device: DeviceCredentialMaterial(
            device_credential_reference("host-001", device), secret
        ),
        clock=lambda: 1_786_089_600,
    )
    body = b'{"state":"ONLINE"}'
    headers = {
        key.casefold(): value
        for key, value in signer.headers(
            "PUT",
            "/channel-agent/v2/agents/agent-001/status",
            body,
            timestamp=1_786_089_600,
            nonce="a" * 32,
        ).items()
    }

    assert verifier.verify(
        "PUT", "/channel-agent/v2/agents/agent-001/status", body, headers
    ) == ("agent-001", "device-001")
    with pytest.raises(DeviceAuthenticationError):
        verifier.verify(
            "PUT", "/channel-agent/v2/agents/agent-001/status", body, headers
        )
    fresh = dict(headers)
    fresh["x-channel-nonce"] = "b" * 32
    with pytest.raises(DeviceAuthenticationError):
        verifier.verify(
            "PUT", "/channel-agent/v2/agents/agent-001/status", b"{}", fresh
        )


class _Response:
    status_code = 200

    def __init__(self, value: dict[str, object]) -> None:
        self._value = value

    def json(self) -> dict[str, object]:
        return self._value


class _PairingClient:
    def __init__(self, response: PairDeviceResponse, **_kwargs: object) -> None:
        self.response = response

    def __enter__(self) -> "_PairingClient":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def post(self, _path: str, **_kwargs: object) -> _Response:
        return _Response(self.response.model_dump(mode="json"))


class _RegisterClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def register(self, **_kwargs: object) -> None:
        return None

    def close(self) -> None:
        return None


def test_first_connection_requires_code_and_keeps_secret_out_of_config(
    tmp_path: Path,
) -> None:
    code = "7K3M9Q2X4T8R"
    pem = "-----BEGIN CERTIFICATE-----\n" + ("A" * 80) + "\n-----END CERTIFICATE-----\n"
    candidate = LANHostCandidate(
        host_id="host-001",
        host_name="AI-CS 主机",
        environment="STAGING",
        server_url="https://192.168.1.10:18443",
        server_version="1.5.0",
        certificate_sha256=certificate_sha256(pem),
        ca_certificate_pem=pem,
    )
    announcement = LANDiscoveryAnnouncement(
        request_nonce="c" * 32,
        candidate=candidate,
        pairing_proof=announcement_proof(candidate, "c" * 32, code),
    )
    store = InMemoryDeviceCredentialStore()
    response = PairDeviceResponse(
        host_id="host-001",
        agent_id="agent-fixed",
        device_id="device-fixed",
        device_credential_reference=device_credential_reference(
            "host-001", "device-fixed"
        ),
        device_secret_base64=base64.b64encode(b"s" * 32).decode("ascii"),
        paired_at=NOW,
    )
    identity_path = tmp_path / "runtime" / "bootstrap-device.json"
    identity_path.parent.mkdir(parents=True)
    identity_path.write_text(
        json.dumps({"agent_id": "agent-fixed", "device_id": "device-fixed"}),
        encoding="utf-8",
    )
    save_agent_config(
        tmp_path / "config" / "agent.json",
        ChannelAgentConfig(
            server_url="http://127.0.0.1:18020",
            agent_id="agent-fixed",
            device_id="device-fixed",
            ai_cs_platform_url="http://127.0.0.1:8422",
        ),
    )
    service = ChannelAgentOnboardingService(
        data_root=tmp_path,
        config_path=tmp_path / "config" / "agent.json",
        credential_store=store,
        discover=lambda **_kwargs: (announcement,),
        http_client_factory=lambda **kwargs: _PairingClient(response, **kwargs),
        channel_client_factory=_RegisterClient,
        clock=lambda: NOW,
    )
    service.discover_hosts()

    with pytest.raises(OnboardingError) as not_confirmed:
        service.pair(
            PairingConfirmation(
                host_id="host-001", pairing_code=code, human_confirmed=False
            )
        )
    assert not_confirmed.value.error_code == "HUMAN_CONFIRMATION_REQUIRED"

    result = service.pair(
        PairingConfirmation(
            host_id="host-001", pairing_code="7K3M-9Q2X-4T8R", human_confirmed=True
        )
    )
    config = load_agent_config(tmp_path / "config" / "agent.json")
    serialized = (tmp_path / "config" / "agent.json").read_text(encoding="utf-8")

    assert result["state"] in {"CONNECTED", "PAIRED_RETRY_REQUIRED"}
    assert config.device_credential_reference == response.device_credential_reference
    assert config.ai_cs_platform_url == "http://127.0.0.1:8422"
    assert base64.b64encode(b"s" * 32).decode("ascii") not in serialized
    assert "password" not in serialized.casefold()
    assert store.acquire(response.device_credential_reference).for_signing() == b"s" * 32


def test_config_v2_is_reference_only_and_keeps_safety_defaults(tmp_path: Path) -> None:
    config = ChannelAgentConfig(
        config_version="2.0",
        server_url="https://192.168.1.10:18443",
        host_id="host-001",
        agent_id="agent-001",
        device_id="device-001",
        device_credential_reference=device_credential_reference("host-001", "device-001"),
        runtime_mode="STAGING",
    )
    value = config.public_view()
    assert value["contains_credentials"] is False
    assert value["manual_approval_required"] is True
    assert value["auto_reply_enabled"] is False
    assert value["real_send_enabled"] is False
