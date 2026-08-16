from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from channel_agent.binding import AgentEnrollmentGrantRequest, AgentEnrollmentRequest
from channel_agent.contract import (
    AgentHeartbeatRequest,
    AgentRegistrationRequest,
    AgentRuntimeStatus,
)
from channel_agent.control_v2 import (
    AgentCommandEnvelope,
    AgentObservationSubmission,
    AgentReceiptSubmission,
    DeviceRequestSigner,
    DeviceRequestVerifier,
    LANHostCandidate,
    PairDeviceRequest,
    PairingError,
    ServiceRequestSigner,
    ServiceRequestVerifier,
)
from channel_agent.edge_execution import EdgeExecutionReceipt
from channel_agent.execution_authorization import (
    ExecutionAuthorizationClaims,
    ExecutionAuthorizationSigner,
    reply_text_sha256,
)
from channel_agent.identity import (
    AgentIdentityActivationRequest,
    AgentIdentityRestoreRequest,
)
from channel_agent.security import DeviceCredentialMaterial, InMemoryDeviceCredentialStore
from channel_engine.agent.binding_repository import (
    SqlAlchemyAgentIdentityRepository,
    SqlAlchemyEnrollmentGrantRepository,
)
from channel_engine.agent.control_store import AgentControlStore, SqlAlchemyReplayNonceStore
from channel_engine.agent.control_v2 import (
    DeviceCredentialIndex,
    HostPairingService,
    create_channel_agent_control_v2_router,
    create_channel_agent_service_v2_router,
)
from channel_engine.agent.node_api import ChannelAgentNodeRegistry
from channel_engine.security.rbac import OperatorPrincipal, OperatorRole
from channel_engine.storage import create_engine_and_session, create_schema


NOW = datetime(2026, 8, 8, 10, 0, tzinfo=UTC)
DEVICE_SECRET = b"device-control-v21-test-secret-32bytes"
SERVICE_SECRET = b"service-control-v21-test-secret-32bytes"
EXECUTION_SECRET = b"execution-control-v21-test-secret!!"


def _admin() -> OperatorPrincipal:
    return OperatorPrincipal(
        principal_id="admin-001",
        roles=frozenset({OperatorRole.ADMIN}),
        identity_provider="test",
        authenticated_at=NOW,
    )


def _database(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine, sessions = create_engine_and_session(
        f"sqlite:///{(tmp_path / 'control-v21.db').as_posix()}"
    )
    create_schema(engine)
    return engine, sessions


def _registered_active_registry(sessions) -> ChannelAgentNodeRegistry:  # type: ignore[no-untyped-def]
    registry = ChannelAgentNodeRegistry(
        identity_repository=SqlAlchemyAgentIdentityRepository(sessions),
        enrollment_grant_repository=SqlAlchemyEnrollmentGrantRepository(sessions),
        binding_code_factory=lambda: "A" * 32,
        clock=lambda: NOW,
    )
    registry.register(
        AgentRegistrationRequest(
            agent_id="agent-001",
            device_id="device-001",
            agent_version="2.0.0rc1",
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
            store_references=("store-001",),
            reason="approved test enrollment",
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
    registry.activate_identity(
        "agent-001",
        AgentIdentityActivationRequest(reason="verified binding"),
        _admin(),
    )
    identity = registry.identity_snapshot("agent-001")
    assert identity is not None
    registry.select_active_store(
        "agent-001",
        __import__("channel_agent.binding", fromlist=["AgentActiveStoreSelectionRequest"])
        .AgentActiveStoreSelectionRequest(
            device_id="device-001",
            store_reference="store-001",
            observed_store_reference="store-001",
            binding_revision=identity.binding_revision,
            reason="human confirmed observed store",
        ),
    )
    return registry


def _execution_authorization():  # type: ignore[no-untyped-def]
    reply = "synthetic approved reply"
    claims = ExecutionAuthorizationClaims(
        agent_id="agent-001",
        device_id="device-001",
        store_id="store-001",
        conversation_id="conversation-001",
        customer_reference="customer-001",
        message_id="message-001",
        decision_id="decision-001",
        approval_id="approval-001",
        execution_id="execution-001",
        lease_id="lease-001",
        lease_expires_at=NOW + timedelta(minutes=2),
        reply_sha256=reply_text_sha256(reply),
        send_key="send-key-001",
        policy_version="policy.v2",
        selector_evidence_hash="sha256:" + "1" * 64,
        activation_grant_id="activation-001",
        human_approval_verified=True,
        lease_valid=True,
        kill_switch_disabled=True,
        store_allowlisted=True,
        risk_policy_allowed=True,
        rate_limit_allowed=True,
    )
    authorization = ExecutionAuthorizationSigner(
        key_id="execution-key-001",
        secret=EXECUTION_SECRET,
        clock=lambda: NOW,
    ).issue(claims)
    return reply, authorization


def _signed(
    client: TestClient,
    signer,
    method: str,
    path: str,
    payload=None,
    nonce="a" * 32,
    extra_headers=None,
):  # type: ignore[no-untyped-def]
    body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = signer.headers(
        method,
        path,
        body,
        timestamp=int(NOW.timestamp()),
        nonce=nonce,
    )
    headers.update(extra_headers or {})
    return client.request(method, path, content=body or None, headers=headers)


def test_v21_observation_command_receipt_and_service_authentication(tmp_path: Path) -> None:
    engine, sessions = _database(tmp_path)
    registry = _registered_active_registry(sessions)
    nonce_store = SqlAlchemyReplayNonceStore(sessions)
    device_signer = DeviceRequestSigner("agent-001", "device-001", DEVICE_SECRET)
    device_verifier = DeviceRequestVerifier(
        lambda _agent, _device: DeviceCredentialMaterial("wincred://test/device", DEVICE_SECRET),
        clock=lambda: NOW.timestamp(),
        nonce_store=nonce_store,
    )
    service_signer = ServiceRequestSigner("ai-cs", "service-key-001", SERVICE_SECRET)
    service_verifier = ServiceRequestVerifier(
        lambda service, key: SERVICE_SECRET
        if (service, key) == ("ai-cs", "service-key-001")
        else b"",
        clock=lambda: NOW.timestamp(),
        nonce_store=nonce_store,
    )
    store = AgentControlStore(sessions, clock=lambda: NOW)
    credential_index = DeviceCredentialIndex(
        tmp_path / "device-index.json", InMemoryDeviceCredentialStore()
    )
    pairing = HostPairingService(
        LANHostCandidate(
            host_id="host-001",
            host_name="host",
            environment="STAGING",
            server_url="https://host.example",
            server_version="0.2.0rc1",
            certificate_sha256="1" * 64,
            ca_certificate_pem="-----BEGIN CERTIFICATE-----\n" + "A" * 80 + "\n-----END CERTIFICATE-----",
        ),
        "7K3M9Q2X4T8R",
        credential_index,
        clock=lambda: NOW,
    )
    app = FastAPI()
    app.include_router(create_channel_agent_control_v2_router(registry, pairing, device_verifier, store))
    app.include_router(create_channel_agent_service_v2_router(registry, service_verifier, store))
    client = TestClient(app, base_url="https://testserver")

    payload = AgentObservationSubmission(
        observation_id="observation-001",
        agent_id="agent-001",
        device_id="device-001",
        store_id="store-001",
        conversation_id="conversation-001",
        external_message_id="message-001",
        source_cursor="cursor-1",
        source_sequence=1,
        payload_digest="sha256:" + hashlib.sha256(b"payload").hexdigest(),
        payload={"content": "privacy-filtered synthetic message"},
        captured_at=NOW,
    ).model_dump(mode="json")
    observed = _signed(client, device_signer, "POST", "/channel-agent/v2/observations", payload)
    duplicate = _signed(
        client,
        device_signer,
        "POST",
        "/channel-agent/v2/observations",
        payload,
        nonce="b" * 32,
    )
    assert observed.status_code == 200
    assert observed.json()["status"] == "PERSISTED"
    assert duplicate.json()["status"] == "DUPLICATE"

    reply, authorization = _execution_authorization()
    command = AgentCommandEnvelope(
        command_id="command-001",
        command_type="SEND_MESSAGE",
        agent_id="agent-001",
        device_id="device-001",
        store_id="store-001",
        execution_authorization=authorization,
        reply_text=reply,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=1),
    )
    assert store.enqueue_command(command) == "QUEUED"
    polled = _signed(client, device_signer, "GET", "/channel-agent/v2/commands/next", nonce="c" * 32)
    assert polled.status_code == 200
    assert polled.json()["command"]["command_id"] == "command-001"

    receipt = EdgeExecutionReceipt(
        receipt_id="receipt-001",
        authorization_id=authorization.authorization_id,
        execution_id=authorization.execution_id,
        decision_id=authorization.decision_id,
        approval_id=authorization.approval_id,
        lease_id=authorization.lease_id,
        send_key=authorization.send_key,
        reply_sha256=authorization.reply_sha256,
        outcome="UNKNOWN",
        transport_triggered=None,
        customer_message_sent=None,
        confirmation_state="UNCONFIRMED",
        reconciliation_required=True,
        created_at=NOW,
    )
    receipt_payload = AgentReceiptSubmission(
        agent_id="agent-001",
        device_id="device-001",
        receipt=receipt,
        submitted_at=NOW,
    ).model_dump(mode="json")
    accepted = _signed(
        client,
        device_signer,
        "POST",
        "/channel-agent/v2/receipts",
        receipt_payload,
        nonce="d" * 32,
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "PERSISTED"

    service_status = _signed(
        client,
        service_signer,
        "GET",
        "/channel-agent/v2/service/receipts/receipt-001",
        nonce="e" * 32,
    )
    replay = _signed(
        client,
        service_signer,
        "GET",
        "/channel-agent/v2/service/receipts/receipt-001",
        nonce="e" * 32,
    )
    assert service_status.status_code == 200
    assert service_status.json()["outcome"] == "UNKNOWN"
    assert replay.status_code == 401

    disable_payload = AgentIdentityActivationRequest(
        reason="service administrator disabled device"
    ).model_dump(mode="json")
    disabled = _signed(
        client,
        service_signer,
        "POST",
        "/channel-agent/v2/service/agents/agent-001/disable",
        disable_payload,
        nonce="f" * 32,
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "DISABLED"
    assert disabled.json()["user_id"] is None

    restore_payload = AgentIdentityRestoreRequest(
        reason="service administrator restored disabled device",
        confirmation_phrase="确认恢复为待绑定",
    ).model_dump(mode="json")
    restored = _signed(
        client,
        service_signer,
        "POST",
        "/channel-agent/v2/service/agents/agent-001/restore-to-registered",
        restore_payload,
        nonce="0" * 32,
        extra_headers={"X-Operator-Intent": "HUMAN_CONFIRMED_AGENT_RESTORE"},
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "REGISTERED"
    assert restored.json()["user_id"] is None
    assert restored.json()["store_ids"] == []

    unsigned = client.get("/channel-agent/v2/commands/next")
    assert unsigned.status_code == 401
    engine.dispose()


def test_enrollment_grant_hash_survives_restart_and_plaintext_never_persists(
    tmp_path: Path,
) -> None:
    engine, sessions = _database(tmp_path)
    first = ChannelAgentNodeRegistry(
        identity_repository=SqlAlchemyAgentIdentityRepository(sessions),
        enrollment_grant_repository=SqlAlchemyEnrollmentGrantRepository(sessions),
        binding_code_factory=lambda: "B" * 32,
        clock=lambda: NOW,
    )
    registration = AgentRegistrationRequest(
        agent_id="agent-restart",
        device_id="device-restart",
        agent_version="2.0.0rc1",
        hostname="desk-restart",
        status=AgentRuntimeStatus.STARTING,
        timestamp=NOW,
    )
    first.register(registration)
    grant = first.issue_enrollment_grant(
        AgentEnrollmentGrantRequest(
            agent_id="agent-restart",
            device_id="device-restart",
            user_reference="user-restart",
            store_references=("store-restart",),
            reason="restart-safe grant",
        ),
        _admin(),
    )

    restarted = ChannelAgentNodeRegistry(
        identity_repository=SqlAlchemyAgentIdentityRepository(sessions),
        enrollment_grant_repository=SqlAlchemyEnrollmentGrantRepository(sessions),
        clock=lambda: NOW,
    )
    restarted.register(registration)
    enrolled = restarted.enroll(
        AgentEnrollmentRequest(
            agent_id="agent-restart",
            device_id="device-restart",
            binding_code=grant.binding_code,
        )
    )
    assert enrolled.binding.identity_status.value == "BOUND"
    database_bytes = (tmp_path / "control-v21.db").read_bytes()
    assert grant.binding_code.encode("ascii") not in database_bytes
    engine.dispose()


def test_identity_and_connectivity_are_independent_and_restart_safe(
    tmp_path: Path,
) -> None:
    engine, sessions = _database(tmp_path)
    repo = SqlAlchemyAgentIdentityRepository(sessions)
    registry = ChannelAgentNodeRegistry(
        identity_repository=repo,
        runtime_repository=repo,
        enrollment_grant_repository=SqlAlchemyEnrollmentGrantRepository(sessions),
        binding_code_factory=lambda: "C" * 32,
        clock=lambda: NOW,
    )
    registration = AgentRegistrationRequest(
        agent_id="agent-state",
        device_id="device-state",
        agent_version="2.0.0rc1",
        hostname="desk-state",
        status=AgentRuntimeStatus.STARTING,
        timestamp=NOW,
    )
    registry.register(registration)
    grant = registry.issue_enrollment_grant(
        AgentEnrollmentGrantRequest(
            agent_id="agent-state",
            device_id="device-state",
            user_reference="user-state",
            store_references=("store-state",),
            reason="state persistence test",
        ),
        _admin(),
    )
    registry.enroll(
        AgentEnrollmentRequest(
            agent_id="agent-state",
            device_id="device-state",
            binding_code=grant.binding_code,
        )
    )
    registry.activate_identity(
        "agent-state",
        AgentIdentityActivationRequest(reason="activate persisted identity"),
        _admin(),
    )

    later = NOW + timedelta(minutes=10)
    restarted = ChannelAgentNodeRegistry(
        identity_repository=repo,
        runtime_repository=repo,
        enrollment_grant_repository=SqlAlchemyEnrollmentGrantRepository(sessions),
        clock=lambda: later,
    )
    offline = restarted.list_agents(_admin()).items[0]
    assert offline.identity_status.value == "ACTIVE"
    assert offline.connectivity_status.value == "OFFLINE"

    restarted.heartbeat(
        "agent-state",
        AgentHeartbeatRequest(
            agent_id="agent-state",
            device_id="device-state",
            user_id="user-state",
            store_id="store-state",
            store_ids=("store-state",),
            authorized_store_ids=("store-state",),
            binding_revision=offline.identity.binding_revision,
            version="2.0.0rc1",
            hostname="desk-state",
            status=AgentRuntimeStatus.ONLINE,
            timestamp=later,
        ),
    )
    online = restarted.list_agents(_admin()).items[0]
    assert online.identity_status.value == "ACTIVE"
    assert online.connectivity_status.value == "ONLINE"
    engine.dispose()


def test_signed_service_rotation_invalidates_old_host_pairing_code(
    tmp_path: Path,
) -> None:
    engine, sessions = _database(tmp_path)
    registry = ChannelAgentNodeRegistry(
        identity_repository=SqlAlchemyAgentIdentityRepository(sessions),
        enrollment_grant_repository=SqlAlchemyEnrollmentGrantRepository(sessions),
        clock=lambda: NOW,
    )
    nonce_store = SqlAlchemyReplayNonceStore(sessions)
    service_signer = ServiceRequestSigner("ai-cs", "service-key-001", SERVICE_SECRET)
    service_verifier = ServiceRequestVerifier(
        lambda service, key: SERVICE_SECRET
        if (service, key) == ("ai-cs", "service-key-001")
        else b"",
        clock=lambda: NOW.timestamp(),
        nonce_store=nonce_store,
    )
    published: list[tuple[str, datetime]] = []
    pairing = HostPairingService(
        LANHostCandidate(
            host_id="host-rotation",
            host_name="host",
            environment="STAGING",
            server_url="https://host.example",
            server_version="0.2.0rc1",
            certificate_sha256="1" * 64,
            ca_certificate_pem="-----BEGIN CERTIFICATE-----\n" + "A" * 80 + "\n-----END CERTIFICATE-----",
        ),
        "7K3M9Q2X4T8R",
        DeviceCredentialIndex(
            tmp_path / "rotation-device-index.json",
            InMemoryDeviceCredentialStore(),
        ),
        clock=lambda: NOW,
        rotation_sink=lambda code, expires_at: published.append((code, expires_at)),
    )
    app = FastAPI()
    app.include_router(
        create_channel_agent_service_v2_router(
            registry,
            service_verifier,
            AgentControlStore(sessions, clock=lambda: NOW),
            pairing=pairing,
        )
    )
    client = TestClient(app, base_url="https://testserver")
    payload = {
        "control_protocol_version": "2.1",
        "reason": "新客服电脑首次安装连接可信主机",
        "confirmation_phrase": "确认重新生成主机连接码",
    }
    rotated = _signed(
        client,
        service_signer,
        "POST",
        "/channel-agent/v2/service/pairing-codes/rotate",
        payload,
        nonce="9" * 32,
        extra_headers={
            "X-Operator-Intent": "HUMAN_CONFIRMED_HOST_PAIRING_CODE_ROTATION"
        },
    )
    assert rotated.status_code == 201
    assert rotated.headers["cache-control"] == "no-store"
    rotated_payload = rotated.json()
    new_code = rotated_payload["pairing_code"]
    assert len(new_code) == 12
    assert new_code != "7K3M9Q2X4T8R"
    assert rotated_payload["display_once"] is True
    assert published == [(new_code, NOW + timedelta(minutes=5))]

    with pytest.raises(PairingError, match="invalid"):
        pairing.pair(
            PairDeviceRequest(
                host_id="host-rotation",
                agent_id="agent-old",
                device_id="device-old",
                pairing_code="7K3M9Q2X4T8R",
                human_confirmed=True,
                requested_at=NOW,
            )
        )
    accepted = pairing.pair(
        PairDeviceRequest(
            host_id="host-rotation",
            agent_id="agent-new",
            device_id="device-new",
            pairing_code=new_code,
            human_confirmed=True,
            requested_at=NOW,
        )
    )
    assert accepted.accepted is True
    with pytest.raises(PairingError, match="already used"):
        pairing.pair(
            PairDeviceRequest(
                host_id="host-rotation",
                agent_id="agent-new",
                device_id="device-new",
                pairing_code=new_code,
                human_confirmed=True,
                requested_at=NOW,
            )
        )
    engine.dispose()
