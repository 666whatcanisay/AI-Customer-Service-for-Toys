"""User/Store-scoped Agent projection and minimized audit service."""

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.desktop_agent.models import DesktopWorkflowAuditEvent, utc_now
from app.desktop_agent.schemas import (
    AgentIdentityStatus,
    DesktopAgentProjection,
    DesktopAgentStatusResponse,
    DesktopAssociationState,
    DesktopBindingGrantRequest,
    DesktopBindingGrantResponse,
    DesktopWorkflowAuditListResponse,
    DesktopWorkflowAuditProjection,
    UpstreamAgentView,
)
from app.desktop_agent.upstream import ChannelAgentUpstream
from app.errors import AppError
from app.iam.dependencies import Principal
from app.iam.schemas import RoleName
from app.workspace.service import StoreContextService


class DesktopWorkflowAuditService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self, *, actor_user_id: str, event_type: str, current_state: str,
        agent_id: str | None = None, device_id: str | None = None,
        store_id: int | None = None, previous_state: str | None = None,
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
            item.online_status.value,
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
            online_status=item.online_status,
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
            candidate.identity.status is not AgentIdentityStatus.UNBOUND
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
            previous_state="UNBOUND",
            current_state="GRANT_ISSUED",
        )
        return DesktopBindingGrantResponse(
            grant_id=result.grant_id,
            agent_id=result.agent_id,
            device_id=result.device_id,
            binding_code=result.binding_code,
            expires_at=result.expires_at,
        )
