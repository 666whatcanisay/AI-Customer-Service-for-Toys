from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock
from typing import Callable, Protocol
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Header, HTTPException, Query

from channel_agent.binding import (
    AgentActiveStoreSelectionRequest,
    AgentEnrollmentGrantRequest,
    AgentEnrollmentGrantResponse,
    AgentEnrollmentRequest,
    AgentEnrollmentResponse,
    AgentRuntimeBinding,
    AgentStoreBindingUpdateRequest,
    AgentVerifiedActiveStoreSelectionRequest,
)
from channel_agent.contract import (
    AgentConfigResponse,
    AgentHeartbeatAck,
    AgentHeartbeatRequest,
    AgentRegistrationRequest,
    AgentRegistrationResponse,
    ManagedAgentConfig,
    utc_now,
)
from channel_agent.identity import (
    AgentAdminListResponse,
    AgentAdminView,
    AgentIdentity,
    AgentIdentityActivationRequest,
    AgentIdentityAuditAction,
    AgentIdentityAuditEvent,
    AgentIdentityAuditListResponse,
    AgentIdentityAuditState,
    AgentIdentityBindingRequest,
    AgentConnectivityStatus,
    AgentIdentityRestoreRequest,
    AgentIdentityStatus,
)
from channel_agent.logger import sanitize
from channel_engine.security.rbac import (
    DenyAllOperatorIdentityProvider,
    OperatorAccessDenied,
    OperatorIdentityProvider,
    OperatorPermission,
    OperatorPrincipal,
    RBACAuthorizer,
)

from .grants import (
    EnrollmentGrantRecord,
    EnrollmentGrantRepositoryPort,
    InMemoryEnrollmentGrantRepository,
)


class AgentDeviceBindingConflict(ValueError):
    pass


class AgentIdentityClaimMismatch(ValueError):
    pass


class AgentIdentityTransitionError(ValueError):
    pass


class AgentIdentityDisabled(PermissionError):
    pass


class AgentEnrollmentDenied(PermissionError):
    pass


class AgentActiveStoreSelectionBlocked(PermissionError):
    def __init__(self, blockers: tuple[str, ...]) -> None:
        super().__init__("active store selection is blocked")
        self.blockers = blockers


class AgentIdentityRepositoryPort(Protocol):
    def list_identities(self) -> tuple[AgentIdentity, ...]: ...

    def save_identity(self, identity: AgentIdentity) -> None: ...


@dataclass(frozen=True, slots=True)
class RegisteredChannelAgent:
    registration_id: str
    agent_id: str
    device_id: str
    version: str
    hostname: str
    status: str
    registered_at: datetime
    last_heartbeat: datetime
    connectivity_status: AgentConnectivityStatus = AgentConnectivityStatus.OFFLINE


class AgentRuntimeRepositoryPort(Protocol):
    def list_runtime_agents(self) -> tuple[RegisteredChannelAgent, ...]: ...

    def save_runtime_agent(self, agent: RegisteredChannelAgent) -> None: ...


class ChannelAgentNodeRegistry:
    """Identity-aware node registry with fail-closed operator authorization."""

    def __init__(
        self,
        *,
        managed_config: ManagedAgentConfig | None = None,
        authorizer: RBACAuthorizer | None = None,
        identity_repository: AgentIdentityRepositoryPort | None = None,
        runtime_repository: AgentRuntimeRepositoryPort | None = None,
        enrollment_grant_repository: EnrollmentGrantRepositoryPort | None = None,
        active_store_guard: Callable[[str, str | None, str], tuple[str, ...]]
        | None = None,
        binding_code_factory=lambda: secrets.token_hex(16).upper(),  # type: ignore[no-untyped-def]
        clock=utc_now,  # type: ignore[no-untyped-def]
    ) -> None:
        self._clock = clock
        self._config = managed_config or ManagedAgentConfig(
            revision="channel-agent-foundation-v1",
            heartbeat_interval_seconds=30.0,
        )
        self._authorizer = authorizer or RBACAuthorizer()
        self._identity_repository = identity_repository
        self._runtime_repository = runtime_repository
        self._enrollment_grant_repository = (
            enrollment_grant_repository or InMemoryEnrollmentGrantRepository()
        )
        self._active_store_guard = active_store_guard or (
            lambda _agent_id, _current, _target: ()
        )
        self._binding_code_factory = binding_code_factory
        self._repository_loaded = False
        self._lock = RLock()
        self._agents: dict[str, RegisteredChannelAgent] = {}
        self._identities: dict[str, AgentIdentity] = {}
        self._audit_events: list[AgentIdentityAuditEvent] = []

    def register(self, request: AgentRegistrationRequest) -> AgentRegistrationResponse:
        with self._lock:
            self._ensure_repository_loaded()
            previous = self._agents.get(request.agent_id)
            if previous is not None and previous.device_id != request.device_id:
                raise AgentDeviceBindingConflict(
                    "agent_id is already bound to another device"
                )
            if any(
                item.agent_id != request.agent_id
                and item.device_id == request.device_id
                for item in self._identities.values()
            ):
                raise AgentDeviceBindingConflict(
                    "device_id is already bound to another Agent"
                )
            now = self._clock()
            identity = self._identities.get(request.agent_id)
            if identity is None:
                identity = AgentIdentity(
                    agent_id=request.agent_id,
                    device_id=request.device_id,
                    user_id=None,
                    store_id=None,
                    store_ids=(),
                    authorized_store_ids=(),
                    active_store_id=None,
                    status=AgentIdentityStatus.REGISTERED,
                    binding_revision=0,
                    created_at=now,
                    updated_at=now,
                )
                self._identities[request.agent_id] = identity
                self._save_identity(identity)
            else:
                if identity.device_id != request.device_id:
                    raise AgentDeviceBindingConflict(
                        "agent identity is bound to another device"
                    )
                self._validate_identity_claim(
                    identity,
                    request.user_reference,
                    request.store_reference,
                    request.authorized_store_ids or request.store_references,
                    active_store_id=request.active_store_id,
                )
                if identity.status is AgentIdentityStatus.DISABLED:
                    raise AgentIdentityDisabled("agent identity is disabled")
            registration_id = (
                previous.registration_id
                if previous is not None
                else f"agent-registration:{uuid5(NAMESPACE_URL, f'{request.agent_id}:{request.device_id}')}"
            )
            registered_at = previous.registered_at if previous is not None else now
            registered = RegisteredChannelAgent(
                registration_id=registration_id,
                agent_id=request.agent_id,
                device_id=request.device_id,
                version=request.agent_version,
                hostname=request.hostname,
                status=request.status.value,
                registered_at=registered_at,
                last_heartbeat=request.timestamp,
                connectivity_status=AgentConnectivityStatus.ONLINE,
            )
            self._agents[request.agent_id] = registered
            self._save_runtime_agent(registered)
            return AgentRegistrationResponse(
                registration_id=registration_id,
                identity=identity,
                production_eligible=identity.production_eligible,
                config=self._config,
                server_time=now,
            )

    def heartbeat(
        self,
        agent_id: str,
        request: AgentHeartbeatRequest,
    ) -> AgentHeartbeatAck:
        with self._lock:
            self._ensure_repository_loaded()
            if request.agent_id != agent_id:
                raise AgentIdentityClaimMismatch(
                    "path agent_id does not match heartbeat"
                )
            previous = self._agents.get(agent_id)
            identity = self._identities.get(agent_id)
            if previous is None or identity is None:
                raise KeyError(agent_id)
            if request.device_id != previous.device_id:
                raise AgentDeviceBindingConflict(
                    "heartbeat device_id does not match registered Agent"
                )
            if identity.status is AgentIdentityStatus.DISABLED:
                raise AgentIdentityDisabled("agent identity is disabled")
            self._validate_identity_claim(
                identity,
                request.user_id,
                request.store_id,
                request.store_ids,
                request.binding_revision,
                active_store_id=request.active_store_id,
            )
            updated = RegisteredChannelAgent(
                registration_id=previous.registration_id,
                agent_id=previous.agent_id,
                device_id=previous.device_id,
                version=request.version,
                hostname=request.hostname,
                status=request.status.value,
                registered_at=previous.registered_at,
                last_heartbeat=request.timestamp,
                connectivity_status=(
                    AgentConnectivityStatus.OFFLINE
                    if request.status.value == "STOPPED"
                    else AgentConnectivityStatus.ONLINE
                ),
            )
            self._agents[agent_id] = updated
            self._save_runtime_agent(updated)
            return AgentHeartbeatAck(
                identity_status=identity.status,
                production_eligible=identity.production_eligible,
                config_revision=self._config.revision,
                identity=identity,
                server_time=self._clock(),
            )

    def config(self, agent_id: str, device_id: str) -> AgentConfigResponse:
        with self._lock:
            self._ensure_repository_loaded()
            agent = self._agents.get(agent_id)
            identity = self._identities.get(agent_id)
            if agent is None or identity is None:
                raise KeyError(agent_id)
            if agent.device_id != device_id:
                raise AgentDeviceBindingConflict(
                    "device_id does not match registered Agent"
                )
            if identity.status is AgentIdentityStatus.DISABLED:
                raise AgentIdentityDisabled("agent identity is disabled")
            return AgentConfigResponse(
                agent_id=agent_id,
                device_id=device_id,
                identity_status=identity.status,
                production_eligible=identity.production_eligible,
                identity=identity,
                config=self._config,
                server_time=self._clock(),
            )

    def issue_enrollment_grant(
        self,
        request: AgentEnrollmentGrantRequest,
        principal: OperatorPrincipal,
    ) -> AgentEnrollmentGrantResponse:
        self._authorizer.require(principal, OperatorPermission.AGENT_IDENTITY_MANAGE)
        code = str(self._binding_code_factory()).strip().upper()
        if len(code) != 32 or any(character not in "0123456789ABCDEF" for character in code):
            raise RuntimeError("binding code factory returned an invalid code")
        now = self._clock()
        expires_at = now + timedelta(seconds=request.expires_in_seconds)
        grant_id = f"agent-enrollment-grant:{uuid5(NAMESPACE_URL, f'{request.agent_id}:{request.device_id}:{now.isoformat()}')}"
        digest = self._binding_code_digest(code)
        grant = EnrollmentGrantRecord(
            grant_id=grant_id,
            code_digest=digest,
            agent_id=request.agent_id,
            device_id=request.device_id,
            user_reference=request.user_reference,
            store_references=request.store_references,
            authorized_by=principal.principal_id,
            reason=str(sanitize(request.reason)),
            issued_at=now,
            expires_at=expires_at,
        )
        with self._lock:
            self._ensure_repository_loaded()
            self._enrollment_grant_repository.replace_for_device(grant)
        return AgentEnrollmentGrantResponse(
            grant_id=grant_id,
            agent_id=request.agent_id,
            device_id=request.device_id,
            user_reference=request.user_reference,
            store_references=request.store_references,
            binding_code=code,
            issued_at=now,
            expires_at=expires_at,
        )

    def enroll(self, request: AgentEnrollmentRequest) -> AgentEnrollmentResponse:
        digest = self._binding_code_digest(request.binding_code)
        with self._lock:
            self._ensure_repository_loaded()
            now = self._clock()
            grant = self._enrollment_grant_repository.consume(digest, now)
            if grant is None:
                raise AgentEnrollmentDenied("binding code is invalid or already used")
            if now >= grant.expires_at:
                raise AgentEnrollmentDenied("binding code has expired")
            if (
                request.agent_id != grant.agent_id
                or request.device_id != grant.device_id
            ):
                raise AgentEnrollmentDenied("binding code does not match this device")
            agent = self._agents.get(request.agent_id)
            before = self._identities.get(request.agent_id)
            if agent is None or before is None:
                raise AgentEnrollmentDenied("Agent must register before enrollment")
            if agent.device_id != request.device_id or before.device_id != request.device_id:
                raise AgentDeviceBindingConflict(
                    "enrollment device_id does not match registered Agent"
                )
            if before.status is not AgentIdentityStatus.UNBOUND:
                raise AgentIdentityTransitionError(
                    f"identity cannot enroll from {before.status.value}"
                )
            stores = grant.store_references
            after = before.model_copy(
                update={
                    "user_id": grant.user_reference,
                    "store_id": stores[0],
                    "store_ids": stores,
                    "authorized_store_ids": stores,
                    "active_store_id": None,
                    "status": AgentIdentityStatus.BOUND,
                    "binding_revision": before.binding_revision + 1,
                    "updated_at": now,
                }
            )
            after = AgentIdentity.model_validate(after.model_dump())
            self._identities[request.agent_id] = after
            self._save_identity(after)
            self._append_audit_by_operator(
                grant.authorized_by,
                AgentIdentityAuditAction.ENROLL,
                grant.reason,
                before,
                after,
            )
            return AgentEnrollmentResponse(
                binding=AgentRuntimeBinding.from_identity(after),
                server_time=now,
            )

    def bind_identity(
        self,
        agent_id: str,
        request: AgentIdentityBindingRequest,
        principal: OperatorPrincipal,
    ) -> AgentIdentity:
        self._authorizer.require(principal, OperatorPermission.AGENT_IDENTITY_MANAGE)
        with self._lock:
            self._ensure_repository_loaded()
            before = self._identity_or_raise(agent_id)
            if before.status is not AgentIdentityStatus.UNBOUND:
                raise AgentIdentityTransitionError(
                    f"identity cannot bind from {before.status.value}"
                )
            after = before.model_copy(
                update={
                    "user_id": request.user_reference,
                    "store_id": request.store_reference,
                    "store_ids": (request.store_reference,),
                    "authorized_store_ids": (request.store_reference,),
                    "active_store_id": request.store_reference,
                    "status": AgentIdentityStatus.BOUND,
                    "binding_revision": before.binding_revision + 1,
                    "updated_at": self._clock(),
                }
            )
            after = AgentIdentity.model_validate(after.model_dump())
            self._identities[agent_id] = after
            self._save_identity(after)
            self._append_audit(
                principal,
                AgentIdentityAuditAction.BIND,
                request.reason,
                before,
                after,
            )
            return after

    def activate_identity(
        self,
        agent_id: str,
        request: AgentIdentityActivationRequest,
        principal: OperatorPrincipal,
    ) -> AgentIdentity:
        self._authorizer.require(principal, OperatorPermission.AGENT_IDENTITY_MANAGE)
        with self._lock:
            self._ensure_repository_loaded()
            before = self._identity_or_raise(agent_id)
            if before.status is not AgentIdentityStatus.BOUND:
                raise AgentIdentityTransitionError(
                    f"identity cannot activate from {before.status.value}"
                )
            after = before.model_copy(
                update={
                    "status": AgentIdentityStatus.ACTIVE,
                    "binding_revision": before.binding_revision + 1,
                    "updated_at": self._clock(),
                }
            )
            after = AgentIdentity.model_validate(after.model_dump())
            self._identities[agent_id] = after
            self._save_identity(after)
            self._append_audit(
                principal,
                AgentIdentityAuditAction.ACTIVATE,
                request.reason,
                before,
                after,
            )
            return after

    def update_store_bindings(
        self,
        agent_id: str,
        request: AgentStoreBindingUpdateRequest,
        principal: OperatorPrincipal,
    ) -> AgentIdentity:
        self._authorizer.require(principal, OperatorPermission.AGENT_IDENTITY_MANAGE)
        with self._lock:
            self._ensure_repository_loaded()
            before = self._identity_or_raise(agent_id)
            if before.status not in {
                AgentIdentityStatus.BOUND,
                AgentIdentityStatus.ACTIVE,
            }:
                raise AgentIdentityTransitionError(
                    f"stores cannot update from {before.status.value}"
                )
            stores = request.store_references
            if stores == before.effective_store_ids:
                return before
            after = before.model_copy(
                update={
                    "store_id": stores[0],
                    "store_ids": stores,
                    "authorized_store_ids": stores,
                    "active_store_id": (
                        before.effective_active_store_id
                        if before.effective_active_store_id in stores
                        else None
                    ),
                    "binding_revision": before.binding_revision + 1,
                    "updated_at": self._clock(),
                }
            )
            after = AgentIdentity.model_validate(after.model_dump())
            self._identities[agent_id] = after
            self._save_identity(after)
            self._append_audit(
                principal,
                AgentIdentityAuditAction.STORES_UPDATE,
                request.reason,
                before,
                after,
            )
            return after

    def select_active_store(
        self,
        agent_id: str,
        request: AgentActiveStoreSelectionRequest,
    ) -> AgentIdentity:
        """Select one authorized store for this device and fail closed on drift."""

        with self._lock:
            self._ensure_repository_loaded()
            before = self._identity_or_raise(agent_id)
            if before.device_id != request.device_id:
                raise AgentDeviceBindingConflict(
                    "active store device_id does not match registered Agent"
                )
            if before.status not in {
                AgentIdentityStatus.BOUND,
                AgentIdentityStatus.ACTIVE,
            }:
                raise AgentIdentityTransitionError(
                    f"active store cannot change from {before.status.value}"
                )
            if request.binding_revision != before.binding_revision:
                raise AgentIdentityClaimMismatch(
                    "active store selection uses a stale binding revision"
                )
            target = request.store_reference
            if target not in before.authorized_stores:
                raise AgentIdentityClaimMismatch("active store is not authorized")
            if request.observed_store_reference != target:
                raise AgentIdentityClaimMismatch(
                    "observed PDD store does not match selected store"
                )
            blockers = tuple(
                self._active_store_guard(
                    agent_id,
                    before.effective_active_store_id,
                    target,
                )
            )
            if blockers:
                raise AgentActiveStoreSelectionBlocked(blockers)
            if before.effective_active_store_id == target:
                return before
            after = before.model_copy(
                update={
                    "active_store_id": target,
                    "binding_revision": before.binding_revision + 1,
                    "updated_at": self._clock(),
                }
            )
            after = AgentIdentity.model_validate(after.model_dump())
            self._identities[agent_id] = after
            self._save_identity(after)
            self._append_audit_by_operator(
                f"agent-device:{request.device_id}",
                AgentIdentityAuditAction.ACTIVE_STORE_SELECT,
                request.reason,
                before,
                after,
            )
            return after

    def select_active_store_verified(
        self,
        agent_id: str,
        request: AgentVerifiedActiveStoreSelectionRequest,
        principal: OperatorPrincipal,
    ) -> AgentIdentity:
        """Select an internal Store from an AI-CS verified platform binding.

        AI-CS owns Store permissions and platform identity bindings.  This
        method therefore accepts the external platform identifier only on the
        service-authenticated control surface, while independently enforcing
        device, user, authorization, revision, and runtime guards here.
        """

        with self._lock:
            self._ensure_repository_loaded()
            before = self._identity_or_raise(agent_id)
            if before.device_id != request.device_id:
                raise AgentDeviceBindingConflict(
                    "verified active store device_id does not match registered Agent"
                )
            if before.user_id != request.user_reference:
                raise AgentIdentityClaimMismatch(
                    "verified active store user does not match bound identity"
                )
            if before.status not in {
                AgentIdentityStatus.BOUND,
                AgentIdentityStatus.ACTIVE,
            }:
                raise AgentIdentityTransitionError(
                    f"active store cannot change from {before.status.value}"
                )
            if request.binding_revision != before.binding_revision:
                raise AgentIdentityClaimMismatch(
                    "verified active store selection uses a stale binding revision"
                )
            target = request.store_reference
            if target not in before.authorized_stores:
                raise AgentIdentityClaimMismatch("active store is not authorized")
            blockers = tuple(
                self._active_store_guard(
                    agent_id,
                    before.effective_active_store_id,
                    target,
                )
            )
            if blockers:
                raise AgentActiveStoreSelectionBlocked(blockers)
            if before.effective_active_store_id == target:
                return before
            after = before.model_copy(
                update={
                    "active_store_id": target,
                    "binding_revision": before.binding_revision + 1,
                    "updated_at": self._clock(),
                }
            )
            after = AgentIdentity.model_validate(after.model_dump())
            self._identities[agent_id] = after
            self._save_identity(after)
            evidence = (
                f"{request.reason}; platform={request.platform}; "
                f"platform_binding={request.platform_binding_id}; "
                f"platform_binding_verified_at="
                f"{request.platform_binding_verified_at.isoformat()}"
            )
            self._append_audit(
                principal,
                AgentIdentityAuditAction.ACTIVE_STORE_SELECT,
                evidence,
                before,
                after,
            )
            return after

    def unbind_identity(
        self,
        agent_id: str,
        reason: str,
        principal: OperatorPrincipal,
    ) -> AgentIdentity:
        self._authorizer.require(principal, OperatorPermission.AGENT_IDENTITY_MANAGE)
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 512:
            raise ValueError("unbind reason is required")
        with self._lock:
            self._ensure_repository_loaded()
            before = self._identity_or_raise(agent_id)
            if before.status not in {
                AgentIdentityStatus.BOUND,
                AgentIdentityStatus.ACTIVE,
            }:
                raise AgentIdentityTransitionError(
                    f"identity cannot unbind from {before.status.value}"
                )
            after = before.model_copy(
                update={
                    "user_id": None,
                    "store_id": None,
                    "store_ids": (),
                    "authorized_store_ids": (),
                    "active_store_id": None,
                    "status": AgentIdentityStatus.DISABLED,
                    "binding_revision": before.binding_revision + 1,
                    "updated_at": self._clock(),
                }
            )
            after = AgentIdentity.model_validate(after.model_dump())
            self._identities[agent_id] = after
            self._save_identity(after)
            self._append_audit(
                principal,
                AgentIdentityAuditAction.UNBIND,
                normalized_reason,
                before,
                after,
            )
            return after

    def release_identity(
        self,
        agent_id: str,
        reason: str,
        principal: OperatorPrincipal,
    ) -> AgentIdentity:
        """Remove account/Store references so this device can be enrolled again."""

        self._authorizer.require(principal, OperatorPermission.AGENT_IDENTITY_MANAGE)
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 512:
            raise ValueError("unbind reason is required")
        with self._lock:
            self._ensure_repository_loaded()
            before = self._identity_or_raise(agent_id)
            if before.status is AgentIdentityStatus.REGISTERED:
                return before
            if before.status not in {
                AgentIdentityStatus.BOUND,
                AgentIdentityStatus.ACTIVE,
                AgentIdentityStatus.DISABLED,
            }:
                raise AgentIdentityTransitionError(
                    f"identity cannot release from {before.status.value}"
                )
            after = before.model_copy(
                update={
                    "user_id": None,
                    "store_id": None,
                    "store_ids": (),
                    "authorized_store_ids": (),
                    "active_store_id": None,
                    "status": AgentIdentityStatus.REGISTERED,
                    "binding_revision": before.binding_revision + 1,
                    "updated_at": self._clock(),
                }
            )
            after = AgentIdentity.model_validate(after.model_dump())
            self._identities[agent_id] = after
            self._save_identity(after)
            self._append_audit(
                principal,
                AgentIdentityAuditAction.UNBIND,
                normalized_reason,
                before,
                after,
            )
            return after

    def disable_identity(
        self,
        agent_id: str,
        reason: str,
        principal: OperatorPrincipal,
    ) -> AgentIdentity:
        """Fail closed by disabling a device and clearing all account references."""

        self._authorizer.require(principal, OperatorPermission.AGENT_IDENTITY_MANAGE)
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 512:
            raise ValueError("disable reason is required")
        with self._lock:
            self._ensure_repository_loaded()
            before = self._identity_or_raise(agent_id)
            if before.status is AgentIdentityStatus.DISABLED:
                return before
            after = before.model_copy(
                update={
                    "user_id": None,
                    "store_id": None,
                    "store_ids": (),
                    "authorized_store_ids": (),
                    "active_store_id": None,
                    "status": AgentIdentityStatus.DISABLED,
                    "binding_revision": before.binding_revision + 1,
                    "updated_at": self._clock(),
                }
            )
            after = AgentIdentity.model_validate(after.model_dump())
            self._identities[agent_id] = after
            self._save_identity(after)
            self._append_audit(
                principal,
                AgentIdentityAuditAction.DISABLE,
                normalized_reason,
                before,
                after,
            )
            return after

    def restore_identity_to_registered(
        self,
        agent_id: str,
        request: AgentIdentityRestoreRequest,
        principal: OperatorPrincipal,
    ) -> AgentIdentity:
        """Recover a disabled device without restoring any former authority."""

        self._authorizer.require(principal, OperatorPermission.AGENT_IDENTITY_MANAGE)
        normalized_reason = request.reason.strip()
        if not normalized_reason or len(normalized_reason) > 512:
            raise ValueError("restore reason is required")
        with self._lock:
            self._ensure_repository_loaded()
            before = self._identity_or_raise(agent_id)
            if before.status is AgentIdentityStatus.REGISTERED:
                return before
            if before.status is not AgentIdentityStatus.DISABLED:
                raise AgentIdentityTransitionError(
                    "only a disabled identity can be restored to registered"
                )
            after = before.model_copy(
                update={
                    "user_id": None,
                    "store_id": None,
                    "store_ids": (),
                    "authorized_store_ids": (),
                    "active_store_id": None,
                    "status": AgentIdentityStatus.REGISTERED,
                    "binding_revision": before.binding_revision + 1,
                    "updated_at": self._clock(),
                }
            )
            after = AgentIdentity.model_validate(after.model_dump())
            self._identities[agent_id] = after
            self._save_identity(after)
            self._append_audit(
                principal,
                AgentIdentityAuditAction.RESTORE_TO_REGISTERED,
                normalized_reason,
                before,
                after,
            )
            return after

    def list_agents(self, principal: OperatorPrincipal) -> AgentAdminListResponse:
        self._authorizer.require(principal, OperatorPermission.AGENT_IDENTITY_READ)
        with self._lock:
            self._ensure_repository_loaded()
            items = tuple(
                self._admin_view(
                    self._identities[agent_id],
                    self._agents.get(agent_id),
                )
                for agent_id in sorted(self._identities)
            )
            return AgentAdminListResponse(
                items=items,
                count=len(items),
                server_time=self._clock(),
            )

    def get_agent(
        self,
        agent_id: str,
        principal: OperatorPrincipal,
    ) -> AgentAdminView:
        self._authorizer.require(principal, OperatorPermission.AGENT_IDENTITY_READ)
        with self._lock:
            self._ensure_repository_loaded()
            identity = self._identity_or_raise(agent_id)
            return self._admin_view(identity, self._agents.get(agent_id))

    def list_identity_audit(
        self,
        principal: OperatorPrincipal,
    ) -> AgentIdentityAuditListResponse:
        self._authorizer.require(principal, OperatorPermission.AGENT_IDENTITY_READ)
        with self._lock:
            self._ensure_repository_loaded()
            items = tuple(self._audit_events)
            return AgentIdentityAuditListResponse(
                items=items,
                count=len(items),
                server_time=self._clock(),
            )

    def snapshot(self, agent_id: str) -> RegisteredChannelAgent | None:
        with self._lock:
            self._ensure_repository_loaded()
            return self._agents.get(agent_id)

    def identity_snapshot(self, agent_id: str) -> AgentIdentity | None:
        with self._lock:
            self._ensure_repository_loaded()
            return self._identities.get(agent_id)

    def _identity_or_raise(self, agent_id: str) -> AgentIdentity:
        identity = self._identities.get(agent_id)
        if identity is None:
            raise KeyError(agent_id)
        return identity

    @staticmethod
    def _validate_identity_claim(
        identity: AgentIdentity,
        user_id: str | None,
        store_id: str | None,
        store_ids: tuple[str, ...] = (),
        binding_revision: int = 0,
        active_store_id: str | None = None,
    ) -> None:
        asserted_stores = store_ids or ((store_id,) if store_id is not None else ())
        if store_ids and store_id != store_ids[0]:
            raise AgentIdentityClaimMismatch(
                "primary store reference does not match store references"
            )
        if user_id is None and not asserted_stores:
            return
        if user_id is None or not asserted_stores:
            raise AgentIdentityClaimMismatch(
                "user and store references must be reported together"
            )
        if identity.status is AgentIdentityStatus.UNBOUND:
            return
        if identity.status in {AgentIdentityStatus.BOUND, AgentIdentityStatus.ACTIVE}:
            if (
                binding_revision < identity.binding_revision
                and user_id == identity.user_id
            ):
                return
            if (
                user_id != identity.user_id
                or asserted_stores != identity.effective_store_ids
            ):
                raise AgentIdentityClaimMismatch(
                    "Agent identity references do not match server binding"
                )
            if (
                active_store_id is not None
                and active_store_id != identity.effective_active_store_id
            ):
                raise AgentIdentityClaimMismatch(
                    "Agent active store does not match server selection"
                )

    def _append_audit(
        self,
        principal: OperatorPrincipal,
        action: AgentIdentityAuditAction,
        reason: str,
        before: AgentIdentity,
        after: AgentIdentity,
    ) -> None:
        timestamp = self._clock()
        event_id = f"agent-identity-audit:{uuid5(NAMESPACE_URL, f'{before.agent_id}:{action.value}:{timestamp.isoformat()}')}"
        self._audit_events.append(
            AgentIdentityAuditEvent(
                audit_event_id=event_id,
                agent_id=before.agent_id,
                operator_id=principal.principal_id,
                action=action,
                timestamp=timestamp,
                reason=str(sanitize(reason)),
                before=AgentIdentityAuditState(
                    status=before.status,
                    user_id=before.user_id,
                    store_id=before.store_id,
                    store_ids=before.effective_store_ids,
                    authorized_store_ids=before.authorized_stores,
                    active_store_id=before.effective_active_store_id,
                    binding_revision=before.binding_revision,
                ),
                after=AgentIdentityAuditState(
                    status=after.status,
                    user_id=after.user_id,
                    store_id=after.store_id,
                    store_ids=after.effective_store_ids,
                    authorized_store_ids=after.authorized_stores,
                    active_store_id=after.effective_active_store_id,
                    binding_revision=after.binding_revision,
                ),
            )
        )

    def _append_audit_by_operator(
        self,
        operator_id: str,
        action: AgentIdentityAuditAction,
        reason: str,
        before: AgentIdentity,
        after: AgentIdentity,
    ) -> None:
        timestamp = self._clock()
        event_id = f"agent-identity-audit:{uuid5(NAMESPACE_URL, f'{before.agent_id}:{action.value}:{timestamp.isoformat()}')}"
        self._audit_events.append(
            AgentIdentityAuditEvent(
                audit_event_id=event_id,
                agent_id=before.agent_id,
                operator_id=operator_id,
                action=action,
                timestamp=timestamp,
                reason=str(sanitize(reason)),
                before=AgentIdentityAuditState(
                    status=before.status,
                    user_id=before.user_id,
                    store_id=before.store_id,
                    store_ids=before.effective_store_ids,
                    authorized_store_ids=before.authorized_stores,
                    active_store_id=before.effective_active_store_id,
                    binding_revision=before.binding_revision,
                ),
                after=AgentIdentityAuditState(
                    status=after.status,
                    user_id=after.user_id,
                    store_id=after.store_id,
                    store_ids=after.effective_store_ids,
                    authorized_store_ids=after.authorized_stores,
                    active_store_id=after.effective_active_store_id,
                    binding_revision=after.binding_revision,
                ),
            )
        )

    def _ensure_repository_loaded(self) -> None:
        if self._repository_loaded:
            return
        if self._identity_repository is not None:
            for identity in self._identity_repository.list_identities():
                self._identities.setdefault(identity.agent_id, identity)
        if self._runtime_repository is not None:
            for agent in self._runtime_repository.list_runtime_agents():
                self._agents.setdefault(agent.agent_id, agent)
        self._repository_loaded = True

    def _save_identity(self, identity: AgentIdentity) -> None:
        if self._identity_repository is not None:
            self._identity_repository.save_identity(identity)

    def _save_runtime_agent(self, agent: RegisteredChannelAgent) -> None:
        if self._runtime_repository is not None:
            self._runtime_repository.save_runtime_agent(agent)

    def _admin_view(
        self,
        identity: AgentIdentity,
        agent: RegisteredChannelAgent | None,
    ) -> AgentAdminView:
        if agent is None:
            return AgentAdminView(
                identity=identity,
                identity_status=identity.status,
                connectivity_status=AgentConnectivityStatus.OFFLINE,
                runtime_status="OFFLINE",
            )
        now = self._clock()
        stale_after = max(self._config.heartbeat_interval_seconds * 3, 15.0)
        age_seconds = max((now - agent.last_heartbeat).total_seconds(), 0.0)
        if agent.status == "STOPPED" or age_seconds > stale_after:
            connectivity = AgentConnectivityStatus.OFFLINE
        else:
            connectivity = AgentConnectivityStatus.ONLINE
        if connectivity is not agent.connectivity_status:
            agent = RegisteredChannelAgent(
                registration_id=agent.registration_id,
                agent_id=agent.agent_id,
                device_id=agent.device_id,
                version=agent.version,
                hostname=agent.hostname,
                status=agent.status,
                registered_at=agent.registered_at,
                last_heartbeat=agent.last_heartbeat,
                connectivity_status=connectivity,
            )
            self._agents[agent.agent_id] = agent
            self._save_runtime_agent(agent)
        return AgentAdminView(
            identity=identity,
            identity_status=identity.status,
            connectivity_status=connectivity,
            agent_version=agent.version,
            hostname=agent.hostname,
            runtime_status=agent.status,
            last_heartbeat=agent.last_heartbeat,
        )

    @staticmethod
    def _binding_code_digest(code: str) -> str:
        return hashlib.sha256(code.strip().upper().encode("ascii")).hexdigest()


def create_channel_agent_node_router(
    registry: ChannelAgentNodeRegistry,
    *,
    identity_provider: OperatorIdentityProvider | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/channel-agent/v1", tags=["channel-agent-node-v1"])
    provider = identity_provider or DenyAllOperatorIdentityProvider()

    def authenticated_operator(session_reference: str | None) -> OperatorPrincipal:
        if session_reference is None:
            raise HTTPException(
                status_code=401,
                detail={"code": "OPERATOR_AUTHENTICATION_REQUIRED"},
            )
        try:
            return provider.authenticate(session_reference)
        except OperatorAccessDenied as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.error_code},
            ) from exc

    @router.post(
        "/agents/register",
        response_model=AgentRegistrationResponse,
        status_code=201,
    )
    def register_agent(request: AgentRegistrationRequest) -> AgentRegistrationResponse:
        try:
            return registry.register(request)
        except AgentDeviceBindingConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_DEVICE_BINDING_CONFLICT"},
            ) from exc
        except AgentIdentityClaimMismatch as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_IDENTITY_CLAIM_MISMATCH"},
            ) from exc
        except AgentIdentityDisabled as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": "AGENT_IDENTITY_DISABLED"},
            ) from exc

    @router.put(
        "/agents/{agent_id}/status",
        response_model=AgentHeartbeatAck,
    )
    def report_agent_status(
        agent_id: str,
        request: AgentHeartbeatRequest,
    ) -> AgentHeartbeatAck:
        try:
            return registry.heartbeat(agent_id, request)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "AGENT_NOT_REGISTERED"},
            ) from exc
        except AgentDeviceBindingConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_DEVICE_MISMATCH"},
            ) from exc
        except AgentIdentityClaimMismatch as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_IDENTITY_CLAIM_MISMATCH"},
            ) from exc
        except AgentIdentityDisabled as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": "AGENT_IDENTITY_DISABLED"},
            ) from exc

    @router.get(
        "/agents/{agent_id}/config",
        response_model=AgentConfigResponse,
    )
    def get_agent_config(
        agent_id: str,
        device_id: str = Query(min_length=1, max_length=128),
    ) -> AgentConfigResponse:
        try:
            return registry.config(agent_id, device_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "AGENT_NOT_REGISTERED"},
            ) from exc
        except AgentDeviceBindingConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_DEVICE_MISMATCH"},
            ) from exc
        except AgentIdentityDisabled as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": "AGENT_IDENTITY_DISABLED"},
            ) from exc

    @router.post(
        "/agents/enroll",
        response_model=AgentEnrollmentResponse,
    )
    def enroll_agent(request: AgentEnrollmentRequest) -> AgentEnrollmentResponse:
        try:
            return registry.enroll(request)
        except AgentEnrollmentDenied as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": "AGENT_ENROLLMENT_DENIED"},
            ) from exc
        except AgentDeviceBindingConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_DEVICE_BINDING_CONFLICT"},
            ) from exc
        except AgentIdentityTransitionError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_IDENTITY_TRANSITION_DENIED"},
            ) from exc

    @router.post(
        "/admin/enrollment-grants",
        response_model=AgentEnrollmentGrantResponse,
        status_code=201,
    )
    def issue_enrollment_grant(
        request: AgentEnrollmentGrantRequest,
        x_operator_session_reference: str | None = Header(
            default=None,
            alias="X-Operator-Session-Reference",
        ),
    ) -> AgentEnrollmentGrantResponse:
        principal = authenticated_operator(x_operator_session_reference)
        try:
            return registry.issue_enrollment_grant(request, principal)
        except OperatorAccessDenied as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.error_code},
            ) from exc

    @router.get("/admin/agents", response_model=AgentAdminListResponse)
    def list_agents(
        x_operator_session_reference: str | None = Header(
            default=None,
            alias="X-Operator-Session-Reference",
        ),
    ) -> AgentAdminListResponse:
        principal = authenticated_operator(x_operator_session_reference)
        try:
            return registry.list_agents(principal)
        except OperatorAccessDenied as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.error_code},
            ) from exc

    @router.get("/admin/agents/{agent_id}", response_model=AgentAdminView)
    def get_agent(
        agent_id: str,
        x_operator_session_reference: str | None = Header(
            default=None,
            alias="X-Operator-Session-Reference",
        ),
    ) -> AgentAdminView:
        principal = authenticated_operator(x_operator_session_reference)
        try:
            return registry.get_agent(agent_id, principal)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "AGENT_NOT_REGISTERED"},
            ) from exc
        except OperatorAccessDenied as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.error_code},
            ) from exc

    @router.put(
        "/admin/agents/{agent_id}/binding",
        response_model=AgentIdentity,
    )
    def bind_agent_identity(
        agent_id: str,
        request: AgentIdentityBindingRequest,
        x_operator_session_reference: str | None = Header(
            default=None,
            alias="X-Operator-Session-Reference",
        ),
    ) -> AgentIdentity:
        principal = authenticated_operator(x_operator_session_reference)
        try:
            return registry.bind_identity(agent_id, request, principal)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "AGENT_NOT_REGISTERED"},
            ) from exc
        except OperatorAccessDenied as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.error_code},
            ) from exc
        except AgentIdentityTransitionError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_IDENTITY_TRANSITION_DENIED"},
            ) from exc

    @router.put(
        "/admin/agents/{agent_id}/stores",
        response_model=AgentIdentity,
    )
    def update_agent_stores(
        agent_id: str,
        request: AgentStoreBindingUpdateRequest,
        x_operator_session_reference: str | None = Header(
            default=None,
            alias="X-Operator-Session-Reference",
        ),
    ) -> AgentIdentity:
        principal = authenticated_operator(x_operator_session_reference)
        try:
            return registry.update_store_bindings(agent_id, request, principal)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "AGENT_NOT_REGISTERED"},
            ) from exc
        except OperatorAccessDenied as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.error_code},
            ) from exc
        except AgentIdentityTransitionError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_IDENTITY_TRANSITION_DENIED"},
            ) from exc

    @router.post(
        "/admin/agents/{agent_id}/activate",
        response_model=AgentIdentity,
    )
    def activate_agent_identity(
        agent_id: str,
        request: AgentIdentityActivationRequest,
        x_operator_session_reference: str | None = Header(
            default=None,
            alias="X-Operator-Session-Reference",
        ),
    ) -> AgentIdentity:
        principal = authenticated_operator(x_operator_session_reference)
        try:
            return registry.activate_identity(agent_id, request, principal)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "AGENT_NOT_REGISTERED"},
            ) from exc
        except OperatorAccessDenied as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.error_code},
            ) from exc
        except AgentIdentityTransitionError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_IDENTITY_TRANSITION_DENIED"},
            ) from exc

    @router.delete(
        "/admin/agents/{agent_id}/binding",
        response_model=AgentIdentity,
    )
    def unbind_agent_identity(
        agent_id: str,
        reason: str = Query(min_length=1, max_length=512),
        x_operator_session_reference: str | None = Header(
            default=None,
            alias="X-Operator-Session-Reference",
        ),
    ) -> AgentIdentity:
        principal = authenticated_operator(x_operator_session_reference)
        try:
            return registry.unbind_identity(agent_id, reason, principal)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "AGENT_NOT_REGISTERED"},
            ) from exc
        except OperatorAccessDenied as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.error_code},
            ) from exc
        except (AgentIdentityTransitionError, ValueError) as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "AGENT_IDENTITY_TRANSITION_DENIED"},
            ) from exc

    @router.get(
        "/admin/identity-audit",
        response_model=AgentIdentityAuditListResponse,
    )
    def list_identity_audit(
        x_operator_session_reference: str | None = Header(
            default=None,
            alias="X-Operator-Session-Reference",
        ),
    ) -> AgentIdentityAuditListResponse:
        principal = authenticated_operator(x_operator_session_reference)
        try:
            return registry.list_identity_audit(principal)
        except OperatorAccessDenied as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.error_code},
            ) from exc

    return router


__all__ = [
    "AgentDeviceBindingConflict",
    "AgentEnrollmentDenied",
    "AgentActiveStoreSelectionBlocked",
    "AgentIdentityClaimMismatch",
    "AgentIdentityDisabled",
    "AgentIdentityRepositoryPort",
    "AgentIdentityTransitionError",
    "ChannelAgentNodeRegistry",
    "RegisteredChannelAgent",
    "create_channel_agent_node_router",
]
