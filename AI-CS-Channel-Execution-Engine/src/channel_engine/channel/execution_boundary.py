from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from channel_engine.models import (
    Approval,
    ApprovalState,
    Decision,
    DecisionAction,
    DecisionState,
    ExecutionState,
)
from channel_engine.models.entities import new_id, utc_now
from channel_engine.storage import RecordNotFound, SqlAlchemyUnitOfWork

from .platform import (
    AuthorizedOutboundMessage,
    ExecutionBoundaryDenied,
    ExecutionSendAuthorization,
)
from .protocol import OutboundMessage


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class LedgerExecutionAuthorizationService:
    """Issues and verifies send capabilities against the live execution ledger."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        *,
        authorization_ttl: timedelta = timedelta(seconds=30),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if authorization_ttl <= timedelta(0):
            raise ValueError("send authorization TTL must be positive")
        if authorization_ttl > timedelta(minutes=5):
            raise ValueError("send authorization TTL cannot exceed five minutes")
        self._uow_factory = uow_factory
        self._authorization_ttl = authorization_ttl
        self._clock = clock

    def issue(
        self,
        *,
        execution_id: str,
        worker_id: str,
        execution_lease_token: str,
    ) -> AuthorizedOutboundMessage:
        now = _as_aware_utc(self._clock())
        try:
            with self._uow_factory() as uow:
                repo = uow.require_repository()
                execution = repo.get_execution(execution_id)
                decision = repo.get_decision(execution.decision_id)
                approval = repo.get_approval_for_decision(decision.decision_id)
                conversation = repo.get_conversation(decision.conversation_id)
        except RecordNotFound as exc:
            raise ExecutionBoundaryDenied(
                "execution authorization source record is missing"
            ) from exc
        if approval is None:
            raise ExecutionBoundaryDenied("human approval record is missing")
        lease_expires_at = execution.lease_expires_at
        if (
            execution.state is not ExecutionState.RUNNING
            or execution.lease_owner != worker_id
            or execution.lease_token != execution_lease_token
            or lease_expires_at is None
            or _as_aware_utc(lease_expires_at) <= now
        ):
            raise ExecutionBoundaryDenied(
                "execution is not RUNNING under the supplied active lease"
            )
        self._assert_approved_send(decision, approval)
        expires_at = min(
            now + self._authorization_ttl,
            _as_aware_utc(lease_expires_at),
        )
        authorization = ExecutionSendAuthorization(
            authorization_id=new_id("channel-send-authorization"),
            decision_id=decision.decision_id,
            approval_id=approval.approval_id,
            execution_id=execution.execution_id,
            approved_by=approval.decided_by,
            worker_id=worker_id,
            execution_lease_token=execution_lease_token,
            issued_at=now,
            expires_at=expires_at,
        )
        return AuthorizedOutboundMessage(
            message=OutboundMessage(
                channel=conversation.channel_name,
                conversation_id=conversation.external_ref,
                execution_id=execution.execution_id,
                approved_by=approval.decided_by,
                content=decision.proposed_content,
                idempotency_key=execution.idempotency_key,
                requested_at=now,
            ),
            authorization=authorization,
        )

    def verify(self, command: AuthorizedOutboundMessage) -> None:
        now = _as_aware_utc(self._clock())
        authorization = command.authorization
        if (
            authorization.operation != "SEND_MESSAGE"
            or authorization.execution_risk != "LOW"
        ):
            raise ExecutionBoundaryDenied(
                "channel authorization is not a low-risk message send"
            )
        if authorization.issued_at > now or authorization.expires_at <= now:
            raise ExecutionBoundaryDenied("channel send authorization is expired")
        try:
            with self._uow_factory() as uow:
                repo = uow.require_repository()
                execution = repo.get_execution(authorization.execution_id)
                decision = repo.get_decision(authorization.decision_id)
                approval = repo.get_approval_for_decision(decision.decision_id)
                conversation = repo.get_conversation(decision.conversation_id)
        except RecordNotFound as exc:
            raise ExecutionBoundaryDenied(
                "execution authorization source record is missing"
            ) from exc
        if approval is None:
            raise ExecutionBoundaryDenied("human approval record is missing")
        lease_expires_at = execution.lease_expires_at
        if (
            execution.decision_id != decision.decision_id
            or execution.approval_id != approval.approval_id
            or approval.approval_id != authorization.approval_id
            or execution.state is not ExecutionState.RUNNING
            or execution.lease_owner != authorization.worker_id
            or execution.lease_token != authorization.execution_lease_token
            or lease_expires_at is None
            or _as_aware_utc(lease_expires_at) <= now
        ):
            raise ExecutionBoundaryDenied(
                "execution ledger no longer authorizes this channel send"
            )
        self._assert_approved_send(decision, approval)
        message = command.message
        if (
            message.channel != conversation.channel_name
            or message.conversation_id != conversation.external_ref
            or message.execution_id != execution.execution_id
            or message.approved_by != approval.decided_by
            or message.content != decision.proposed_content
            or message.idempotency_key != execution.idempotency_key
        ):
            raise ExecutionBoundaryDenied(
                "channel send payload does not match the approved execution"
            )

    @staticmethod
    def _assert_approved_send(decision: Decision, approval: Approval) -> None:
        if (
            decision.state is not DecisionState.APPROVED
            or decision.action is not DecisionAction.SUGGEST_REPLY
            or not decision.proposed_content
            or approval.state is not ApprovalState.APPROVED
            or not approval.decided_by
        ):
            raise ExecutionBoundaryDenied(
                "Decision and explicit human Approval are required before send"
            )


__all__ = ["LedgerExecutionAuthorizationService"]
