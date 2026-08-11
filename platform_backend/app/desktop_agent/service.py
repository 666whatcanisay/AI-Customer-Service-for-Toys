"""User/Store-scoped Agent projection and minimized audit service."""

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.desktop_agent.models import DesktopWorkflowAuditEvent, utc_now
from app.desktop_agent.schemas import (
    AgentIdentityStatus,
    AgentOnlineStatus,
    AdminBindingTarget,
    AdminBindingTargetListResponse,
    AdminBindingTargetStore,
    AdminDeviceDisableRequest,
    AdminDeviceListResponse,
    AdminDeviceProjection,
    AdminDeviceRestoreRequest,
    AdminEnrollmentGrantRequest,
    AdminEnrollmentGrantResponse,
    AdminHostPairingCodeRotateRequest,
    AdminHostPairingCodeRotateResponse,
    DesktopAgentProjection,
    DesktopAgentStatusResponse,
    DesktopAssociationState,
    DesktopBindingGrantRequest,
    DesktopBindingGrantResponse,
    DesktopBindingActivationRequest,
    DesktopActiveStoreSelectionRequest,
    DesktopWorkflowAuditListResponse,
    DesktopWorkflowAuditProjection,
    UpstreamAgentView,
)
from app.desktop_agent.upstream import ChannelAgentUpstream
from app.errors import AppError
from app.iam.dependencies import Principal
from app.iam.schemas import RoleName, UserStatus
from app.iam.service import UserService
from app.workspace.service import StoreContextService
from app.store_platform_bindings.service import active_binding_projections_by_store


class DesktopWorkflowAuditService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self, *, actor_user_id: str, event_type: str, current_state: str,
        agent_id: str | None = None, device_id: str | None = None,
        store_id: int | None = None, previous_state: str | None = None,
        reason: str | None = None,
        commit: bool = True,
    ) -> DesktopWorkflowAuditEvent:
        row = DesktopWorkflowAuditEvent(
            actor_user_id=actor_user_id,
            event_type=event_type,
            agent_id=agent_id,
            device_id=device_id,
            store_id=store_id,
            previous_state=previous_state,
            current_state=current_state,
            reason=reason,
            outcome="SUCCESS",
            occurred_at=utc_now(),
        )
        self.session.add(row)
        if commit:
            self.session.commit()
        return row

    def record_observation(
        self, *, actor_user_id: str, store_id: int, item: UpstreamAgentView
    ) -> None:
        state = "|".join((
            item.identity.status.value,
            item.connectivity_status.value,
            item.runtime_status,
            str(item.identity.binding_revision),
        ))
        previous = self.session.scalar(
            select(DesktopWorkflowAuditEvent)
            .where(
                DesktopWorkflowAuditEvent.actor_user_id == actor_user_id,
                DesktopWorkflowAuditEvent.agent_id == item.identity.agent_id,
                DesktopWorkflowAuditEvent.event_type.in_((
                    "DEVICE_BINDING_OBSERVED", "DEVICE_STATUS_CHANGED"
                )),
            )
            .order_by(desc(DesktopWorkflowAuditEvent.occurred_at))
            .limit(1)
        )
        if previous is not None and previous.current_state == state:
            return
        self.add(
            actor_user_id=actor_user_id,
            event_type=("DEVICE_BINDING_OBSERVED" if previous is None else "DEVICE_STATUS_CHANGED"),
            agent_id=item.identity.agent_id,
            device_id=item.identity.device_id,
            store_id=store_id,
            previous_state=previous.current_state if previous is not None else None,
            current_state=state,
        )

    def list(self, *, user_id: str | None, limit: int) -> DesktopWorkflowAuditListResponse:
        filters = () if user_id is None else (
            DesktopWorkflowAuditEvent.actor_user_id == user_id,
        )
        total = self.session.scalar(
            select(func.count()).select_from(DesktopWorkflowAuditEvent).where(*filters)
        ) or 0
        query = select(DesktopWorkflowAuditEvent).where(*filters).order_by(
            desc(DesktopWorkflowAuditEvent.occurred_at)
        ).limit(limit)
        rows = list(self.session.scalars(query))
        return DesktopWorkflowAuditListResponse(
            items=[DesktopWorkflowAuditProjection(
                audit_event_id=row.id,
                actor_user_id=row.actor_user_id,
                event_type=row.event_type,
                agent_id=row.agent_id,
                device_id=row.device_id,
                store_id=row.store_id,
                previous_state=row.previous_state,
                current_state=row.current_state,
                reason=row.reason,
                outcome=row.outcome,
                occurred_at=row.occurred_at,
            ) for row in rows],
            total=total,
        )


class DesktopAgentService:
    def __init__(self, session: Session, upstream: ChannelAgentUpstream) -> None:
        self.session = session
        self.upstream = upstream
        self.audit = DesktopWorkflowAuditService(session)

    def _store_context(self, principal: Principal, store_id: int):
        context = StoreContextService(self.session).workspace_context(principal)
        store = next((item for item in context.stores if item.store_id == store_id), None)
        if store is None:
            raise AppError(
                "AUTHORIZATION_DENIED",
                "The requested Store is outside the authenticated Workspace scope.",
                status_code=403,
            )
        return context, store

    @staticmethod
    def _project(item: UpstreamAgentView) -> DesktopAgentProjection:
        return DesktopAgentProjection(
            agent_id=item.identity.agent_id,
            device_id=item.identity.device_id,
            device_name=item.hostname,
            agent_version=item.agent_version,
            identity_status=item.identity.status,
            online_status=AgentOnlineStatus(item.connectivity_status.value),
            runtime_status=item.runtime_status,
            production_eligible=item.identity.status is AgentIdentityStatus.ACTIVE,
            binding_revision=item.identity.binding_revision,
            last_heartbeat=item.last_heartbeat,
        )

    def status(self, principal: Principal, store_id: int) -> DesktopAgentStatusResponse:
        _, store = self._store_context(principal, store_id)
        listing = self.upstream.list_agents()
        user_items = [item for item in listing.items if item.identity.user_id == principal.user_id]
        matches = [
            item for item in user_items
            if store.store_code in item.identity.effective_store_ids
        ]
        if not matches:
            last_observation = self.session.scalar(
                select(DesktopWorkflowAuditEvent)
                .where(
                    DesktopWorkflowAuditEvent.actor_user_id == principal.user_id,
                    DesktopWorkflowAuditEvent.store_id == store.store_id,
                    DesktopWorkflowAuditEvent.event_type.in_((
                        "DEVICE_BINDING_OBSERVED", "DEVICE_STATUS_CHANGED"
                    )),
                )
                .order_by(desc(DesktopWorkflowAuditEvent.occurred_at))
                .limit(1)
            )
            if last_observation is not None:
                disabled = next((
                    item for item in listing.items
                    if item.identity.agent_id == last_observation.agent_id
                    and item.identity.status is AgentIdentityStatus.DISABLED
                ), None)
                if disabled is not None:
                    matches = [disabled]
        state = DesktopAssociationState.BINDING_REQUIRED
        selected: UpstreamAgentView | None = None
        if not matches and user_items:
            state = DesktopAssociationState.STORE_MISMATCH
        elif len(matches) > 1:
            state = DesktopAssociationState.MULTIPLE_MATCHES
        elif len(matches) == 1:
            selected = matches[0]
            if selected.identity.status is AgentIdentityStatus.DISABLED:
                state = DesktopAssociationState.DISABLED
            elif selected.identity.status is AgentIdentityStatus.BOUND:
                state = DesktopAssociationState.ACTIVATION_REQUIRED
            elif selected.identity.status is AgentIdentityStatus.ACTIVE:
                state = DesktopAssociationState.READY
            else:
                state = DesktopAssociationState.BINDING_REQUIRED
            self.audit.record_observation(
                actor_user_id=principal.user_id, store_id=store.store_id, item=selected
            )
        return DesktopAgentStatusResponse(
            user_id=principal.user_id,
            store_id=store.store_id,
            store_code=store.store_code,
            association_state=state,
            agent=self._project(selected) if selected is not None else None,
            checked_at=listing.server_time,
        )

    def issue_grant(
        self, principal: Principal, request: DesktopBindingGrantRequest
    ) -> DesktopBindingGrantResponse:
        if RoleName.CUSTOMER_SERVICE not in principal.roles:
            raise AppError(
                "AUTHORIZATION_DENIED",
                "Only a CUSTOMER_SERVICE account can bind its Workspace device.",
                status_code=403,
            )
        context, store = self._store_context(principal, request.store_id)
        listing = self.upstream.list_agents()
        candidate = next((
            item for item in listing.items
            if item.identity.agent_id == request.agent_id
            and item.identity.device_id == request.device_id
        ), None)
        if candidate is None:
            raise AppError(
                "CHANNEL_AGENT_NOT_REGISTERED",
                "The specified Agent and device are not registered.",
                status_code=404,
            )
        if (
            candidate.identity.status is not AgentIdentityStatus.REGISTERED
            or candidate.identity.user_id is not None
            or candidate.identity.effective_store_ids
        ):
            raise AppError(
                "CHANNEL_AGENT_BINDING_INVALID",
                "The specified Agent is not available for enrollment.",
                status_code=409,
            )
        store_codes = (store.store_code,) + tuple(
            item.store_code for item in context.stores if item.store_id != store.store_id
        )
        result = self.upstream.issue_enrollment_grant(
            agent_id=request.agent_id,
            device_id=request.device_id,
            user_reference=principal.user_id,
            store_references=store_codes,
            reason="AI-CS authenticated self-device enrollment",
        )
        self.audit.add(
            actor_user_id=principal.user_id,
            event_type="DEVICE_BINDING_GRANT_ISSUED",
            agent_id=request.agent_id,
            device_id=request.device_id,
            store_id=store.store_id,
            previous_state="REGISTERED",
            current_state="GRANT_ISSUED",
        )
        return DesktopBindingGrantResponse(
            grant_id=result.grant_id,
            agent_id=result.agent_id,
            device_id=result.device_id,
            binding_code=result.binding_code,
            expires_at=result.expires_at,
        )

    def activate(
        self,
        principal: Principal,
        request: DesktopBindingActivationRequest,
    ) -> DesktopAgentStatusResponse:
        _, store = self._store_context(principal, request.store_id)
        listing = self.upstream.list_agents()
        candidate = next((
            item for item in listing.items
            if item.identity.agent_id == request.agent_id
            and item.identity.device_id == request.device_id
        ), None)
        if candidate is None:
            raise AppError(
                "CHANNEL_AGENT_NOT_REGISTERED",
                "The specified Agent and device are not registered.",
                status_code=404,
            )
        if (
            candidate.identity.user_id != principal.user_id
            or store.store_code not in candidate.identity.effective_store_ids
        ):
            raise AppError(
                "AUTHORIZATION_DENIED",
                "The bound device is outside the authenticated user and Store scope.",
                status_code=403,
            )
        if candidate.identity.status is AgentIdentityStatus.ACTIVE:
            return self.status(principal, request.store_id)
        if candidate.identity.status is not AgentIdentityStatus.BOUND:
            raise AppError(
                "CHANNEL_AGENT_BINDING_INVALID",
                "Only a bound device can be activated.",
                status_code=409,
            )
        self.upstream.activate_agent(
            agent_id=request.agent_id,
            reason="AI-CS authenticated self-device enrollment completed",
        )
        self.audit.add(
            actor_user_id=principal.user_id,
            event_type="DEVICE_BINDING_ACTIVATED",
            agent_id=request.agent_id,
            device_id=request.device_id,
            store_id=request.store_id,
            previous_state="BOUND",
            current_state="ACTIVE",
        )
        return self.status(principal, request.store_id)

    def select_active_store(
        self,
        principal: Principal,
        request: DesktopActiveStoreSelectionRequest,
    ) -> DesktopAgentStatusResponse:
        """Resolve an observed platform identity to one authorized AI-CS Store."""

        _, store = self._store_context(principal, request.store_id)
        bindings = active_binding_projections_by_store(
            self.session,
            {store.store_id},
        ).get(store.store_id, [])
        platform = request.platform.strip().casefold()
        observed = request.observed_platform_store_id.strip()
        binding = next(
            (
                item
                for item in bindings
                if item.platform.casefold() == platform
                and item.platform_store_id == observed
            ),
            None,
        )
        if binding is None:
            raise AppError(
                "PLATFORM_STORE_BINDING_NOT_VERIFIED",
                "The observed platform Store is not an active verified binding.",
                status_code=409,
            )

        listing = self.upstream.list_agents()
        candidate = next(
            (
                item
                for item in listing.items
                if item.identity.agent_id == request.agent_id
                and item.identity.device_id == request.device_id
            ),
            None,
        )
        if candidate is None:
            raise AppError(
                "CHANNEL_AGENT_NOT_REGISTERED",
                "The specified Agent and device are not registered.",
                status_code=404,
            )
        if (
            candidate.identity.user_id != principal.user_id
            or store.store_code not in candidate.identity.effective_store_ids
        ):
            raise AppError(
                "AUTHORIZATION_DENIED",
                "The device or Store is outside the authenticated user scope.",
                status_code=403,
            )
        if candidate.identity.status not in {
            AgentIdentityStatus.BOUND,
            AgentIdentityStatus.ACTIVE,
        }:
            raise AppError(
                "CHANNEL_AGENT_BINDING_INVALID",
                "Only a bound or active device can select its working Store.",
                status_code=409,
            )

        self.upstream.select_active_store(
            agent_id=request.agent_id,
            device_id=request.device_id,
            user_reference=principal.user_id,
            store_reference=store.store_code,
            platform=platform,
            observed_platform_store_id=observed,
            platform_binding_id=binding.binding_id,
            platform_binding_verified_at=binding.verified_at.isoformat(),
            binding_revision=candidate.identity.binding_revision,
            reason="Customer service operator confirmed the observed platform Store",
        )
        self.audit.add(
            actor_user_id=principal.user_id,
            event_type="ACTIVE_STORE_SELECTED",
            agent_id=request.agent_id,
            device_id=request.device_id,
            store_id=store.store_id,
            previous_state=candidate.identity.effective_active_store_id,
            current_state=store.store_code,
            reason=f"verified platform binding {binding.binding_id}",
        )
        return self.status(principal, request.store_id)


class DesktopAgentAdminService:
    """RBAC-gated facade; Host Control remains the only device authority."""

    def __init__(self, session: Session, upstream: ChannelAgentUpstream) -> None:
        self.session = session
        self.upstream = upstream
        self.audit = DesktopWorkflowAuditService(session)

    def list_devices(self) -> AdminDeviceListResponse:
        listing = self.upstream.list_agents()
        return AdminDeviceListResponse(
            items=tuple(
                AdminDeviceProjection(
                    agent_id=item.identity.agent_id,
                    device_id=item.identity.device_id,
                    agent_version=item.agent_version,
                    hostname=item.hostname,
                    identity_status=item.identity_status,
                    connectivity_status=item.connectivity_status,
                    runtime_status=item.runtime_status,
                    user_reference=item.identity.user_id,
                    authorized_store_ids=item.identity.effective_store_ids,
                    active_store_id=item.identity.effective_active_store_id,
                    binding_revision=item.identity.binding_revision,
                    last_heartbeat=item.last_heartbeat,
                    authoritative_source=item.authoritative_source,
                )
                for item in listing.items
            ),
            count=listing.count,
            checked_at=listing.server_time,
            authoritative_source=listing.authoritative_source,
        )

    def rotate_host_pairing_code(
        self,
        principal: Principal,
        request: AdminHostPairingCodeRotateRequest,
    ) -> AdminHostPairingCodeRotateResponse:
        result = self.upstream.rotate_host_pairing_code(reason=request.reason)
        self.audit.add(
            actor_user_id=principal.user_id,
            event_type="HOST_PAIRING_CODE_ROTATED",
            agent_id=result.host_id,
            current_state="PAIRING_CODE_ROTATED",
            reason=request.reason,
        )
        return AdminHostPairingCodeRotateResponse(
            host_id=result.host_id,
            pairing_code=result.pairing_code,
            expires_at=result.expires_at,
            display_once=result.display_once,
        )

    def list_binding_targets(self) -> AdminBindingTargetListResponse:
        targets: list[AdminBindingTarget] = []
        for user in UserService(self.session).list_users():
            if (
                user.status is not UserStatus.ACTIVE
                or RoleName.CUSTOMER_SERVICE not in user.roles
                or not user.stores
            ):
                continue
            targets.append(
                AdminBindingTarget(
                    user_id=user.id,
                    username=user.username,
                    display_name=user.display_name,
                    stores=tuple(
                        AdminBindingTargetStore(
                            store_id=store.store_id,
                            store_code=store.store_code,
                            store_name=store.store_name,
                            platform=store.platform,
                            is_default=store.is_default,
                        )
                        for store in user.stores
                    ),
                )
            )
        return AdminBindingTargetListResponse(
            items=tuple(targets),
            count=len(targets),
            checked_at=utc_now(),
        )

    def issue_enrollment_grant(
        self,
        principal: Principal,
        agent_id: str,
        request: AdminEnrollmentGrantRequest,
    ) -> AdminEnrollmentGrantResponse:
        listing = self.upstream.list_agents()
        device = next(
            (item for item in listing.items if item.identity.agent_id == agent_id),
            None,
        )
        if device is None:
            raise AppError(
                "CHANNEL_AGENT_NOT_REGISTERED",
                "The specified Agent is not registered.",
                status_code=404,
            )
        if (
            device.identity.status is not AgentIdentityStatus.REGISTERED
            or device.identity.user_id is not None
            or device.identity.effective_store_ids
        ):
            raise AppError(
                "CHANNEL_AGENT_BINDING_INVALID",
                "Only a REGISTERED and unbound device can receive an enrollment grant.",
                status_code=409,
            )

        target = next(
            (
                user
                for user in UserService(self.session).list_users()
                if user.id == request.user_id
            ),
            None,
        )
        if target is None or target.status is not UserStatus.ACTIVE:
            raise AppError(
                "BINDING_TARGET_USER_UNAVAILABLE",
                "The selected user is not available for device binding.",
                status_code=409,
            )
        if RoleName.CUSTOMER_SERVICE not in target.roles:
            raise AppError(
                "BINDING_TARGET_ROLE_INVALID",
                "Only a CUSTOMER_SERVICE user can be bound to a customer desktop.",
                status_code=409,
            )
        stores_by_id = {store.store_id: store for store in target.stores}
        requested_ids = tuple(request.store_ids)
        if any(store_id not in stores_by_id for store_id in requested_ids):
            raise AppError(
                "BINDING_TARGET_STORE_UNAUTHORIZED",
                "One or more selected Stores are outside the user's existing authorization.",
                status_code=403,
            )
        ordered = sorted(
            (stores_by_id[store_id] for store_id in requested_ids),
            key=lambda store: (not store.is_default, requested_ids.index(store.store_id)),
        )
        store_codes = tuple(store.store_code for store in ordered)
        result = self.upstream.issue_enrollment_grant(
            agent_id=device.identity.agent_id,
            device_id=device.identity.device_id,
            user_reference=target.id,
            store_references=store_codes,
            reason=request.reason,
        )
        self.audit.add(
            actor_user_id=principal.user_id,
            event_type="DEVICE_BINDING_GRANT_ISSUED_BY_ADMIN",
            agent_id=device.identity.agent_id,
            device_id=device.identity.device_id,
            store_id=ordered[0].store_id,
            previous_state=AgentIdentityStatus.REGISTERED.value,
            current_state="GRANT_ISSUED",
        )
        return AdminEnrollmentGrantResponse(
            grant_id=result.grant_id,
            agent_id=result.agent_id,
            device_id=result.device_id,
            user_reference=target.id,
            store_references=store_codes,
            binding_code=result.binding_code,
            issued_at=result.issued_at,
            expires_at=result.expires_at,
        )

    def disable(
        self,
        principal: Principal,
        agent_id: str,
        request: AdminDeviceDisableRequest,
    ) -> AdminDeviceListResponse:
        before = self._identity_status(agent_id)
        self.upstream.disable_agent(agent_id=agent_id, reason=request.reason)
        self.audit.add(
            actor_user_id=principal.user_id,
            event_type="DEVICE_DISABLED_BY_ADMIN",
            agent_id=agent_id,
            previous_state=before.value,
            current_state=AgentIdentityStatus.DISABLED.value,
        )
        return self.list_devices()

    def restore_to_registered(
        self,
        principal: Principal,
        agent_id: str,
        request: AdminDeviceRestoreRequest,
    ) -> AdminDeviceListResponse:
        before = self._identity_status(agent_id)
        self.upstream.restore_agent_to_registered(
            agent_id=agent_id,
            reason=request.reason,
        )
        self.audit.add(
            actor_user_id=principal.user_id,
            event_type="DEVICE_RESTORED_TO_REGISTERED",
            agent_id=agent_id,
            previous_state=before.value,
            current_state=AgentIdentityStatus.REGISTERED.value,
        )
        return self.list_devices()

    def _identity_status(self, agent_id: str) -> AgentIdentityStatus:
        listing = self.upstream.list_agents()
        item = next(
            (item for item in listing.items if item.identity.agent_id == agent_id),
            None,
        )
        if item is None:
            raise AppError(
                "CHANNEL_AGENT_NOT_REGISTERED",
                "The requested Agent is not registered by Host Control.",
                status_code=404,
            )
        return item.identity_status
