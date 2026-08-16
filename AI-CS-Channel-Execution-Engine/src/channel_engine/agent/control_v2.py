from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Callable

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_agent.binding import (
    AgentActiveStoreSelectionRequest,
    AgentEnrollmentGrantRequest,
    AgentEnrollmentRequest,
    AgentEnrollmentResponse,
    AgentVerifiedActiveStoreSelectionRequest,
)
from channel_agent.contract import (
    AgentConfigResponse,
    AgentHeartbeatAck,
    AgentHeartbeatRequest,
    AgentRegistrationRequest,
    AgentRegistrationResponse,
)
from channel_agent.control_v2 import (
    AgentAssistantEventPollResponse,
    AgentAssistantConversationListResponse,
    AgentAssistantSnapshotResponse,
    AgentCommandEnvelope,
    AgentCommandPollResponse,
    AgentObservationAck,
    AgentObservationSubmission,
    AgentReceiptAck,
    AgentReceiptSubmission,
    DeviceAuthenticationError,
    DeviceRequestVerifier,
    HostPairingCodeRotateRequest,
    HostPairingCodeRotateResponse,
    LANHostCandidate,
    PairDeviceRequest,
    PairDeviceResponse,
    PairingError,
    ServiceApprovalAck,
    ServiceApprovalDelivery,
    ServiceRequestVerifier,
    generate_pairing_code,
    normalize_pairing_code,
)
from channel_agent.identity import (
    AgentIdentity,
    AgentIdentityActivationRequest,
    AgentIdentityRestoreRequest,
)
from channel_agent.security import (
    DeviceCredentialMaterial,
    DeviceCredentialStore,
    device_credential_reference,
)

from .node_api import (
    AgentActiveStoreSelectionBlocked,
    AgentDeviceBindingConflict,
    AgentEnrollmentDenied,
    AgentIdentityClaimMismatch,
    AgentIdentityDisabled,
    AgentIdentityTransitionError,
    ChannelAgentNodeRegistry,
)
from .control_store import AgentControlConflict, AgentControlStore
from .execution_commands import (
    command_id_for_approval,
    delivery_matches_command,
)
from channel_engine.security.rbac import OperatorPrincipal, OperatorRole
from channel_engine.customer_assistant import (
    AuthorizationKind,
    OfflineControlError,
    OfflineReplyControlStore,
    ReplyPolicyMode,
)


class DeviceCredentialRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    credential_reference: str = Field(min_length=1, max_length=512)
    paired_at: AwareDatetime
    disabled: bool = False


class DeviceCredentialIndex:
    """Atomic reference-only index; key material stays in the credential store."""

    def __init__(self, path: str | Path, store: DeviceCredentialStore) -> None:
        self.path = Path(path)
        self._store = store
        self._lock = RLock()
        self._records: dict[str, DeviceCredentialRecord] = {}
        self._load()

    def register(self, record: DeviceCredentialRecord, secret: bytes) -> None:
        with self._lock:
            previous = self._records.get(record.device_id)
            if previous is not None and previous.agent_id != record.agent_id:
                raise PairingError("device is already paired to another Agent")
            self._store.put(record.credential_reference, secret)
            self._records[record.device_id] = record
            try:
                self._save()
            except Exception:
                if previous is None:
                    self._records.pop(record.device_id, None)
                    self._store.delete(record.credential_reference)
                else:
                    self._records[record.device_id] = previous
                raise

    def resolve(self, agent_id: str, device_id: str) -> DeviceCredentialMaterial:
        with self._lock:
            record = self._records.get(device_id)
            if (
                record is None
                or record.disabled
                or record.agent_id != agent_id
            ):
                raise DeviceAuthenticationError("device is not paired")
            return self._store.acquire(record.credential_reference)

    def snapshot(self, device_id: str) -> DeviceCredentialRecord | None:
        with self._lock:
            return self._records.get(device_id)

    def _load(self) -> None:
        if not self.path.is_file():
            return
        raw = self.path.read_bytes()
        if len(raw) > 1024 * 1024:
            raise ValueError("device credential index exceeds one MiB")
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, list):
            raise ValueError("device credential index is invalid")
        records = tuple(DeviceCredentialRecord.model_validate(item) for item in value)
        self._records = {item.device_id: item for item in records}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(
            [
                self._records[key].model_dump(mode="json")
                for key in sorted(self._records)
            ],
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8") + b"\n"
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, self.path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise


class HostPairingService:
    def __init__(
        self,
        candidate: LANHostCandidate,
        pairing_code: str,
        credential_index: DeviceCredentialIndex,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        expires_in: timedelta = timedelta(minutes=5),
        maximum_attempts: int = 5,
        expires_at: datetime | None = None,
        rotation_sink: Callable[[str, datetime], None] | None = None,
    ) -> None:
        self.candidate = candidate
        self._code_digest = _code_digest(pairing_code)
        self._credential_index = credential_index
        self._clock = clock
        self._expires_in = expires_in
        self._expires_at = expires_at or (clock() + expires_in)
        self._maximum_attempts = maximum_attempts
        self._rotation_sink = rotation_sink
        self._attempts = 0
        self._used = False
        self._lock = RLock()

    @property
    def expires_at(self) -> datetime:
        return self._expires_at

    @property
    def rotation_supported(self) -> bool:
        return self._rotation_sink is not None

    def rotate(self) -> HostPairingCodeRotateResponse:
        with self._lock:
            if self._rotation_sink is None:
                raise RuntimeError("pairing code rotation is not configured")
            code = generate_pairing_code()
            expires_at = self._clock() + self._expires_in
            # Publish the encrypted-at-rest discovery credential before making
            # the digest authoritative. A publication failure leaves the old
            # code untouched and therefore cannot split discovery from pairing.
            self._rotation_sink(code, expires_at)
            self._code_digest = _code_digest(code)
            self._expires_at = expires_at
            self._attempts = 0
            self._used = False
            return HostPairingCodeRotateResponse(
                host_id=self.candidate.host_id,
                pairing_code=code,
                expires_at=expires_at,
            )

    def pair(self, request: PairDeviceRequest) -> PairDeviceResponse:
        with self._lock:
            now = self._clock()
            if self._used:
                raise PairingError("connection code was already used")
            if now >= self._expires_at:
                raise PairingError("connection code expired")
            if self._attempts >= self._maximum_attempts:
                raise PairingError("connection code attempt limit was reached")
            self._attempts += 1
            if request.host_id != self.candidate.host_id:
                raise PairingError("connection code is for another host")
            try:
                candidate_digest = _code_digest(request.pairing_code)
            except ValueError as exc:
                raise PairingError("connection code is invalid") from exc
            if not secrets.compare_digest(candidate_digest, self._code_digest):
                raise PairingError("connection code is invalid")
            if abs((now - request.requested_at.astimezone(UTC)).total_seconds()) > 120:
                raise PairingError("pairing request timestamp is stale")
            secret = secrets.token_bytes(32)
            reference = device_credential_reference(
                self.candidate.host_id,
                request.device_id,
            )
            self._credential_index.register(
                DeviceCredentialRecord(
                    agent_id=request.agent_id,
                    device_id=request.device_id,
                    credential_reference=reference,
                    paired_at=now,
                ),
                secret,
            )
            self._used = True
            return PairDeviceResponse(
                host_id=self.candidate.host_id,
                agent_id=request.agent_id,
                device_id=request.device_id,
                device_credential_reference=reference,
                device_secret_base64=base64.b64encode(secret).decode("ascii"),
                paired_at=now,
            )


def create_channel_agent_control_v2_router(
    registry: ChannelAgentNodeRegistry,
    pairing: HostPairingService,
    verifier: DeviceRequestVerifier,
    control_store: AgentControlStore | None = None,
    receipt_handler: Callable[[AgentReceiptSubmission], object] | None = None,
    observation_handler: Callable[[AgentObservationSubmission], object] | None = None,
    offline_control: OfflineReplyControlStore | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/channel-agent/v2", tags=["channel-agent-control-v2"])

    @router.get("/host", response_model=LANHostCandidate)
    def host_information() -> LANHostCandidate:
        return pairing.candidate

    @router.post("/pair", response_model=PairDeviceResponse)
    async def pair_device(request: Request) -> PairDeviceResponse:
        body = await _bounded_body(request)
        try:
            payload = PairDeviceRequest.model_validate_json(body)
            return pairing.pair(payload)
        except PairingError as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": "AGENT_PAIRING_DENIED"},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "AGENT_PAIRING_REQUEST_INVALID"},
            ) from exc

    @router.post(
        "/agents/register",
        response_model=AgentRegistrationResponse,
        status_code=201,
    )
    async def register_agent(request: Request) -> AgentRegistrationResponse:
        body, agent_id, device_id = await _authenticated(request, verifier)
        try:
            payload = AgentRegistrationRequest.model_validate_json(body)
            _assert_device(payload.agent_id, payload.device_id, agent_id, device_id)
            return registry.register(payload)
        except AgentDeviceBindingConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_DEVICE_BINDING_CONFLICT"}) from exc
        except AgentIdentityClaimMismatch as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_IDENTITY_CLAIM_MISMATCH"}) from exc
        except AgentIdentityDisabled as exc:
            raise HTTPException(status_code=403, detail={"code": "AGENT_IDENTITY_DISABLED"}) from exc

    @router.put("/agents/{agent_id}/status", response_model=AgentHeartbeatAck)
    async def report_status(agent_id: str, request: Request) -> AgentHeartbeatAck:
        body, signed_agent_id, device_id = await _authenticated(request, verifier)
        try:
            payload = AgentHeartbeatRequest.model_validate_json(body)
            _assert_device(payload.agent_id, payload.device_id, signed_agent_id, device_id)
            if agent_id != signed_agent_id:
                raise AgentIdentityClaimMismatch("path Agent does not match signature")
            identity = registry.identity_snapshot(agent_id)
            if identity is not None and identity.status.value in {"BOUND", "ACTIVE"}:
                if payload.authorized_store_ids != identity.authorized_stores:
                    raise AgentIdentityClaimMismatch(
                        "signed heartbeat authorized stores do not match server binding"
                    )
                if payload.active_store_id != identity.effective_active_store_id:
                    raise AgentIdentityClaimMismatch(
                        "signed heartbeat active store does not match server selection"
                    )
            return registry.heartbeat(agent_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "AGENT_NOT_REGISTERED"}) from exc
        except (AgentDeviceBindingConflict, AgentIdentityClaimMismatch) as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_IDENTITY_CLAIM_MISMATCH"}) from exc
        except AgentIdentityDisabled as exc:
            raise HTTPException(status_code=403, detail={"code": "AGENT_IDENTITY_DISABLED"}) from exc

    @router.post("/agents/enroll", response_model=AgentEnrollmentResponse)
    async def enroll_agent(request: Request) -> AgentEnrollmentResponse:
        body, agent_id, device_id = await _authenticated(request, verifier)
        try:
            payload = AgentEnrollmentRequest.model_validate_json(body)
            _assert_device(payload.agent_id, payload.device_id, agent_id, device_id)
            return registry.enroll(payload)
        except AgentEnrollmentDenied as exc:
            raise HTTPException(status_code=403, detail={"code": "AGENT_ENROLLMENT_DENIED"}) from exc
        except AgentDeviceBindingConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_DEVICE_BINDING_CONFLICT"}) from exc
        except AgentIdentityTransitionError as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_IDENTITY_TRANSITION_DENIED"}) from exc

    @router.get("/agents/{agent_id}/config", response_model=AgentConfigResponse)
    async def get_config(agent_id: str, request: Request) -> AgentConfigResponse:
        _body, signed_agent_id, device_id = await _authenticated(request, verifier)
        if agent_id != signed_agent_id:
            raise HTTPException(status_code=403, detail={"code": "AGENT_DEVICE_AUTHENTICATION_FAILED"})
        try:
            return registry.config(agent_id, device_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "AGENT_NOT_REGISTERED"}) from exc
        except AgentDeviceBindingConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_DEVICE_MISMATCH"}) from exc

    @router.put("/agents/{agent_id}/active-store", response_model=AgentIdentity)
    async def select_active_store(agent_id: str, request: Request) -> AgentIdentity:
        body, signed_agent_id, device_id = await _authenticated(request, verifier)
        if agent_id != signed_agent_id:
            raise HTTPException(status_code=403, detail={"code": "AGENT_DEVICE_AUTHENTICATION_FAILED"})
        try:
            payload = AgentActiveStoreSelectionRequest.model_validate_json(body)
            if payload.device_id != device_id:
                raise AgentDeviceBindingConflict("device does not match signature")
            return registry.select_active_store(agent_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "AGENT_NOT_REGISTERED"}) from exc
        except AgentActiveStoreSelectionBlocked as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "ACTIVE_STORE_SELECTION_BLOCKED", "blockers": list(exc.blockers)},
            ) from exc
        except (AgentDeviceBindingConflict, AgentIdentityClaimMismatch) as exc:
            raise HTTPException(status_code=409, detail={"code": "ACTIVE_STORE_SELECTION_DENIED"}) from exc
        except AgentIdentityTransitionError as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_IDENTITY_TRANSITION_DENIED"}) from exc

    @router.post("/observations", response_model=AgentObservationAck)
    async def submit_observation(request: Request) -> AgentObservationAck:
        body, agent_id, device_id = await _authenticated(request, verifier)
        if control_store is None:
            raise HTTPException(status_code=503, detail={"code": "AGENT_CONTROL_STORE_UNAVAILABLE"})
        try:
            payload = AgentObservationSubmission.model_validate_json(body)
            _assert_device(payload.agent_id, payload.device_id, agent_id, device_id)
            identity = registry.identity_snapshot(agent_id)
            if (
                identity is None
                or identity.effective_active_store_id != payload.store_id
                or payload.store_id not in identity.authorized_stores
            ):
                raise AgentIdentityClaimMismatch("observation store is not the active authorized store")
            # Observation acceptance is deliberately limited to durable inbox
            # persistence.  Buffering/AI runs in the background worker so an AI
            # outage can never invalidate an already committed Agent ACK.
            return control_store.persist_observation(payload)
        except AgentControlConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_OBSERVATION_CONFLICT"}) from exc
        except (AgentDeviceBindingConflict, AgentIdentityClaimMismatch) as exc:
            raise HTTPException(status_code=403, detail={"code": "AGENT_OBSERVATION_SCOPE_DENIED"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "AGENT_OBSERVATION_INVALID"}) from exc

    @router.get(
        "/assistant-events/next",
        response_model=AgentAssistantEventPollResponse,
    )
    async def poll_assistant_events(
        request: Request,
        after_sequence_id: int = 0,
        limit: int = 100,
    ) -> AgentAssistantEventPollResponse:
        _body, agent_id, device_id = await _authenticated(request, verifier)
        if control_store is None:
            raise HTTPException(status_code=503, detail={"code": "AGENT_CONTROL_STORE_UNAVAILABLE"})
        if after_sequence_id < 0 or not 1 <= limit <= 100:
            raise HTTPException(status_code=422, detail={"code": "ASSISTANT_EVENT_CURSOR_INVALID"})
        events = control_store.poll_assistant_events(
            agent_id,
            device_id,
            after_sequence_id=after_sequence_id,
            limit=limit,
        )
        return AgentAssistantEventPollResponse(
            events=events,
            next_sequence_id=(events[-1].sequence_id if events else after_sequence_id),
            server_time=datetime.now(UTC),
        )

    @router.get(
        "/assistant-snapshot",
        response_model=AgentAssistantSnapshotResponse,
    )
    async def get_assistant_snapshot(
        request: Request,
        store_id: str | None = None,
        conversation_id: str | None = None,
    ) -> AgentAssistantSnapshotResponse:
        _body, agent_id, device_id = await _authenticated(request, verifier)
        if control_store is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "AGENT_CONTROL_STORE_UNAVAILABLE"},
            )
        if (store_id is None) != (conversation_id is None):
            raise HTTPException(
                status_code=422,
                detail={"code": "ASSISTANT_SNAPSHOT_SCOPE_INVALID"},
            )
        if store_id is not None and not 1 <= len(store_id) <= 160:
            raise HTTPException(
                status_code=422,
                detail={"code": "ASSISTANT_SNAPSHOT_SCOPE_INVALID"},
            )
        if conversation_id is not None and not 1 <= len(conversation_id) <= 255:
            raise HTTPException(
                status_code=422,
                detail={"code": "ASSISTANT_SNAPSHOT_SCOPE_INVALID"},
            )
        return AgentAssistantSnapshotResponse(
            snapshot=control_store.assistant_snapshot(
                agent_id,
                device_id,
                store_id=store_id,
                conversation_id=conversation_id,
            ),
            server_time=datetime.now(UTC),
        )

    @router.get(
        "/assistant-conversations",
        response_model=AgentAssistantConversationListResponse,
    )
    async def get_assistant_conversations(
        request: Request,
        limit: int = 100,
    ) -> AgentAssistantConversationListResponse:
        _body, agent_id, device_id = await _authenticated(request, verifier)
        if control_store is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "AGENT_CONTROL_STORE_UNAVAILABLE"},
            )
        if not 1 <= limit <= 100:
            raise HTTPException(
                status_code=422,
                detail={"code": "ASSISTANT_CONVERSATION_LIMIT_INVALID"},
            )
        return AgentAssistantConversationListResponse(
            conversations=control_store.assistant_snapshots(
                agent_id, device_id, limit=limit
            ),
            server_time=datetime.now(UTC),
        )

    @router.get("/assistant-traces/{trace_id}")
    async def get_assistant_trace(trace_id: str, request: Request):  # type: ignore[no-untyped-def]
        await _authenticated(request, verifier)
        if not _valid_trace_id(trace_id):
            raise HTTPException(
                status_code=422,
                detail={"code": "ASSISTANT_TRACE_ID_INVALID"},
            )
        if offline_control is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "ASSISTANT_TRACE_UNAVAILABLE"},
            )
        steps = offline_control.trace(trace_id)
        return {
            "trace_id": trace_id,
            "steps": [item.model_dump(mode="json") for item in steps],
            "server_time": datetime.now(UTC),
        }

    @router.get("/commands/next", response_model=AgentCommandPollResponse)
    async def poll_command(request: Request) -> AgentCommandPollResponse:
        _body, agent_id, device_id = await _authenticated(request, verifier)
        if control_store is None:
            raise HTTPException(status_code=503, detail={"code": "AGENT_CONTROL_STORE_UNAVAILABLE"})
        return AgentCommandPollResponse(
            command=control_store.poll_command(agent_id, device_id),
            server_time=datetime.now(UTC),
        )

    @router.post("/receipts", response_model=AgentReceiptAck)
    async def submit_receipt(request: Request) -> AgentReceiptAck:
        body, agent_id, device_id = await _authenticated(request, verifier)
        if control_store is None:
            raise HTTPException(status_code=503, detail={"code": "AGENT_CONTROL_STORE_UNAVAILABLE"})
        try:
            payload = AgentReceiptSubmission.model_validate_json(body)
            _assert_device(payload.agent_id, payload.device_id, agent_id, device_id)
            acknowledgement = control_store.persist_receipt(payload)
            if receipt_handler is not None:
                receipt_handler(payload)
            return acknowledgement
        except AgentControlConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_RECEIPT_CONFLICT"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "AGENT_RECEIPT_INVALID"}) from exc

    return router


def create_channel_agent_service_v2_router(
    registry: ChannelAgentNodeRegistry,
    verifier: ServiceRequestVerifier,
    control_store: AgentControlStore,
    *,
    pairing: HostPairingService | None = None,
    approval_command_factory: Callable[[ServiceApprovalDelivery], AgentCommandEnvelope]
    | None = None,
    offline_control: OfflineReplyControlStore | None = None,
) -> APIRouter:
    """Signed AI-CS service surface. Browser clients can never call this directly."""

    router = APIRouter(
        prefix="/channel-agent/v2/service",
        tags=["channel-agent-service-control-v2"],
    )

    def principal(service_id: str) -> OperatorPrincipal:
        return OperatorPrincipal(
            principal_id=f"service:{service_id}",
            roles=frozenset({OperatorRole.ADMIN}),
            identity_provider="channel-agent-control.v2.1",
            authenticated_at=datetime.now(UTC),
        )

    @router.get("/agents")
    async def list_agents(request: Request):  # type: ignore[no-untyped-def]
        _body, service_id = await _service_authenticated(request, verifier)
        return registry.list_agents(principal(service_id))

    @router.post(
        "/pairing-codes/rotate",
        response_model=HostPairingCodeRotateResponse,
        status_code=201,
    )
    async def rotate_pairing_code(
        request: Request,
        response: Response,
    ) -> HostPairingCodeRotateResponse:
        body, _service_id = await _service_authenticated(request, verifier)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        if (
            request.headers.get("X-Operator-Intent")
            != "HUMAN_CONFIRMED_HOST_PAIRING_CODE_ROTATION"
        ):
            raise HTTPException(
                status_code=403,
                detail={"code": "HOST_PAIRING_ROTATION_HUMAN_INTENT_REQUIRED"},
            )
        if pairing is None or not pairing.rotation_supported:
            raise HTTPException(
                status_code=503,
                detail={"code": "HOST_PAIRING_ROTATION_UNAVAILABLE"},
            )
        try:
            HostPairingCodeRotateRequest.model_validate_json(body)
            return pairing.rotate()
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "HOST_PAIRING_ROTATION_UNAVAILABLE"},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "HOST_PAIRING_ROTATION_INVALID"},
            ) from exc

    @router.post("/enrollment-grants", status_code=201)
    async def issue_grant(request: Request):  # type: ignore[no-untyped-def]
        body, service_id = await _service_authenticated(request, verifier)
        try:
            payload = AgentEnrollmentGrantRequest.model_validate_json(body)
            return registry.issue_enrollment_grant(payload, principal(service_id))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "AGENT_ENROLLMENT_GRANT_INVALID"}) from exc

    @router.post("/agents/{agent_id}/activate", response_model=AgentIdentity)
    async def activate_agent(agent_id: str, request: Request) -> AgentIdentity:
        body, service_id = await _service_authenticated(request, verifier)
        try:
            payload = AgentIdentityActivationRequest.model_validate_json(body)
            identity = registry.identity_snapshot(agent_id)
            if identity is not None and identity.status.value == "ACTIVE":
                return identity
            return registry.activate_identity(agent_id, payload, principal(service_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "AGENT_NOT_REGISTERED"}) from exc
        except AgentIdentityTransitionError as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_IDENTITY_TRANSITION_DENIED"}) from exc

    @router.post("/agents/{agent_id}/active-store", response_model=AgentIdentity)
    async def select_verified_active_store(
        agent_id: str,
        request: Request,
    ) -> AgentIdentity:
        body, service_id = await _service_authenticated(request, verifier)
        if request.headers.get("X-Operator-Intent") != "HUMAN_CONFIRMED_STORE_SELECTION":
            raise HTTPException(
                status_code=403,
                detail={"code": "ACTIVE_STORE_SELECTION_HUMAN_INTENT_REQUIRED"},
            )
        try:
            payload = AgentVerifiedActiveStoreSelectionRequest.model_validate_json(body)
            return registry.select_active_store_verified(
                agent_id,
                payload,
                principal(service_id),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "AGENT_NOT_REGISTERED"}) from exc
        except AgentActiveStoreSelectionBlocked as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "ACTIVE_STORE_SELECTION_BLOCKED", "blockers": list(exc.blockers)},
            ) from exc
        except (AgentDeviceBindingConflict, AgentIdentityClaimMismatch) as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "ACTIVE_STORE_SELECTION_DENIED"},
            ) from exc
        except AgentIdentityTransitionError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_IDENTITY_TRANSITION_DENIED"},
            ) from exc

    @router.post("/agents/{agent_id}/unbind", response_model=AgentIdentity)
    async def unbind_agent(agent_id: str, request: Request) -> AgentIdentity:
        body, service_id = await _service_authenticated(request, verifier)
        try:
            payload = AgentIdentityActivationRequest.model_validate_json(body)
            return registry.release_identity(
                agent_id,
                payload.reason,
                principal(service_id),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "AGENT_NOT_REGISTERED"}) from exc
        except (AgentIdentityTransitionError, ValueError) as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_IDENTITY_UNBIND_DENIED"}) from exc

    @router.post("/agents/{agent_id}/disable", response_model=AgentIdentity)
    async def disable_agent(agent_id: str, request: Request) -> AgentIdentity:
        body, service_id = await _service_authenticated(request, verifier)
        try:
            payload = AgentIdentityActivationRequest.model_validate_json(body)
            return registry.disable_identity(
                agent_id,
                payload.reason,
                principal(service_id),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "AGENT_NOT_REGISTERED"}) from exc
        except (AgentIdentityTransitionError, ValueError) as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_IDENTITY_DISABLE_DENIED"}) from exc

    @router.post(
        "/agents/{agent_id}/restore-to-registered",
        response_model=AgentIdentity,
    )
    async def restore_agent_to_registered(
        agent_id: str,
        request: Request,
    ) -> AgentIdentity:
        body, service_id = await _service_authenticated(request, verifier)
        if request.headers.get("X-Operator-Intent") != "HUMAN_CONFIRMED_AGENT_RESTORE":
            raise HTTPException(
                status_code=403,
                detail={"code": "AGENT_RESTORE_HUMAN_INTENT_REQUIRED"},
            )
        try:
            payload = AgentIdentityRestoreRequest.model_validate_json(body)
            return registry.restore_identity_to_registered(
                agent_id,
                payload,
                principal(service_id),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "AGENT_NOT_REGISTERED"}) from exc
        except (AgentIdentityTransitionError, ValueError) as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_IDENTITY_RESTORE_DENIED"},
            ) from exc

    @router.post("/approvals", response_model=ServiceApprovalAck)
    async def deliver_approval(request: Request) -> ServiceApprovalAck:
        body, _service_id = await _service_authenticated(request, verifier)
        if approval_command_factory is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "EXECUTION_AUTHORIZATION_ISSUER_UNAVAILABLE"},
            )
        try:
            delivery = ServiceApprovalDelivery.model_validate_json(body)
            existing = control_store.command(
                command_id_for_approval(delivery.approval_delivery_id)
            )
            if existing is not None:
                if not delivery_matches_command(delivery, existing):
                    raise AgentControlConflict(
                        "approval delivery identity is bound to different content"
                    )
                return ServiceApprovalAck(
                    approval_delivery_id=delivery.approval_delivery_id,
                    command_id=existing.command_id,
                    execution_id=existing.execution_authorization.execution_id,
                    status="DUPLICATE",
                    queued_at=datetime.now(UTC),
                )
            command = approval_command_factory(delivery)
            status = control_store.enqueue_command(command)
            return ServiceApprovalAck(
                approval_delivery_id=delivery.approval_delivery_id,
                command_id=command.command_id,
                execution_id=command.execution_authorization.execution_id,
                status=status,
                queued_at=datetime.now(UTC),
            )
        except AgentControlConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "AGENT_COMMAND_CONFLICT"}) from exc
        except (PermissionError, ValueError) as exc:
            raise HTTPException(status_code=403, detail={"code": "EXECUTION_AUTHORIZATION_DENIED"}) from exc

    @router.get("/receipts/{receipt_id}")
    async def get_receipt(receipt_id: str, request: Request):  # type: ignore[no-untyped-def]
        await _service_authenticated(request, verifier)
        value = control_store.receipt(receipt_id)
        if value is None:
            raise HTTPException(status_code=404, detail={"code": "AGENT_RECEIPT_NOT_FOUND"})
        return value

    @router.get("/reply-policies/{store_id}")
    async def get_reply_policy(store_id: str, request: Request):  # type: ignore[no-untyped-def]
        await _service_authenticated(request, verifier)
        if offline_control is None:
            raise HTTPException(status_code=503, detail={"code": "REPLY_POLICY_UNAVAILABLE"})
        return offline_control.policy(store_id).model_dump(mode="json")

    @router.put("/reply-policies/{store_id}")
    async def put_reply_policy(store_id: str, request: Request):  # type: ignore[no-untyped-def]
        body, service_id = await _service_authenticated(request, verifier)
        if offline_control is None:
            raise HTTPException(status_code=503, detail={"code": "REPLY_POLICY_UNAVAILABLE"})
        if request.headers.get("X-Operator-Intent") != "AUTHORIZED_REPLY_POLICY_CHANGE":
            raise HTTPException(
                status_code=403,
                detail={"code": "REPLY_POLICY_CHANGE_INTENT_REQUIRED"},
            )
        try:
            raw = json.loads(body or b"{}")
            mode = ReplyPolicyMode(raw["mode"])
            expected_revision = raw.get("expected_revision")
            if expected_revision is not None and not isinstance(expected_revision, int):
                raise ValueError("expected_revision must be an integer")
            return offline_control.set_policy(
                store_id,
                mode,
                authorized_by=_service_actor(service_id, raw.get("actor_reference")),
                expected_revision=expected_revision,
            ).model_dump(mode="json")
        except OfflineControlError as exc:
            raise HTTPException(status_code=409, detail={"code": exc.error_code}) from exc
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail={"code": "REPLY_POLICY_CHANGE_INVALID"}) from exc

    @router.post("/decisions/{decision_id}/execution-preparations", status_code=201)
    async def prepare_execution(decision_id: str, request: Request):  # type: ignore[no-untyped-def]
        body, service_id = await _service_authenticated(request, verifier)
        if offline_control is None:
            raise HTTPException(status_code=503, detail={"code": "EXECUTION_PREPARATION_UNAVAILABLE"})
        if request.headers.get("X-Operator-Intent") != "HUMAN_CONFIRMED_EXECUTION_PREPARATION":
            raise HTTPException(
                status_code=403,
                detail={"code": "EXECUTION_PREPARATION_HUMAN_INTENT_REQUIRED"},
            )
        try:
            raw = json.loads(body or b"{}")
            prepared = offline_control.prepare(
                decision_id,
                authorization_kind=AuthorizationKind.HUMAN,
                authorized_by=_service_actor(service_id, raw.get("actor_reference")),
                expected_store_id=raw.get("store_id"),
                expected_conversation_id=raw.get("conversation_id"),
                expected_customer_reference=raw.get("customer_reference"),
            )
            snapshot = control_store.mark_snapshot_execution_prepared(prepared)
            if snapshot is not None:
                event_digest = hashlib.sha256(
                    f"EXECUTION_PREPARED_MANUAL:{prepared.preparation_id}".encode(
                        "utf-8"
                    )
                ).hexdigest()
                control_store.append_assistant_event(
                    event_id=f"assistant-event:{event_digest}",
                    event_type="EXECUTION_PREPARED",
                    agent_id=snapshot.agent_id,
                    device_id=snapshot.device_id,
                    store_id=snapshot.store_id,
                    conversation_id=snapshot.conversation_id,
                    turn_id=snapshot.turn_id,
                    decision_id=snapshot.decision_id,
                    status="EXECUTION_PREPARED",
                    metadata={
                        "trace_id": prepared.trace_id,
                        "preparation_id": prepared.preparation_id,
                        "authorization_kind": "HUMAN",
                        "real_send_enabled": False,
                        "contains_customer_content": False,
                    },
                )
            return prepared.model_dump(mode="json")
        except OfflineControlError as exc:
            raise HTTPException(status_code=409, detail={"code": exc.error_code}) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail={"code": "EXECUTION_PREPARATION_INVALID"}) from exc

    return router


async def _authenticated(
    request: Request,
    verifier: DeviceRequestVerifier,
) -> tuple[bytes, str, str]:
    body = await _bounded_body(request)
    try:
        identity = verifier.verify(
            request.method,
            request.url.path,
            body,
            {key.casefold(): value for key, value in request.headers.items()},
        )
    except DeviceAuthenticationError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "AGENT_DEVICE_AUTHENTICATION_FAILED"},
        ) from exc
    return body, identity[0], identity[1]


async def _service_authenticated(
    request: Request,
    verifier: ServiceRequestVerifier,
) -> tuple[bytes, str]:
    body = await _bounded_body(request)
    try:
        service_id = verifier.verify(
            request.method,
            request.url.path,
            body,
            {key.casefold(): value for key, value in request.headers.items()},
        )
    except DeviceAuthenticationError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "AGENT_SERVICE_AUTHENTICATION_FAILED"},
        ) from exc
    return body, service_id


async def _bounded_body(request: Request) -> bytes:
    body = await request.body()
    if len(body) > 1024 * 1024:
        raise HTTPException(status_code=413, detail={"code": "AGENT_REQUEST_TOO_LARGE"})
    return body


def _assert_device(
    payload_agent_id: str,
    payload_device_id: str,
    signed_agent_id: str,
    signed_device_id: str,
) -> None:
    if payload_agent_id != signed_agent_id or payload_device_id != signed_device_id:
        raise AgentDeviceBindingConflict("signed device does not match request body")


def _code_digest(code: str) -> bytes:
    return hashlib.sha256(normalize_pairing_code(code).encode("ascii")).digest()


def _service_actor(service_id: str, actor_reference: object) -> str:
    if actor_reference is None:
        return f"service:{service_id}"[:160]
    if (
        not isinstance(actor_reference, str)
        or not actor_reference.strip()
        or len(actor_reference) > 128
        or "\r" in actor_reference
        or "\n" in actor_reference
    ):
        raise ValueError("service actor reference is invalid")
    digest = hashlib.sha256(actor_reference.strip().encode("utf-8")).hexdigest()
    return f"service:{service_id[:64]}:actor-sha256:{digest}"[:160]


def _valid_trace_id(value: str) -> bool:
    if not value.startswith("trace:") or len(value) != 70:
        return False
    return all(character in "0123456789abcdef" for character in value[6:])


__all__ = [
    "DeviceCredentialIndex",
    "DeviceCredentialRecord",
    "HostPairingService",
    "create_channel_agent_control_v2_router",
    "create_channel_agent_service_v2_router",
]
