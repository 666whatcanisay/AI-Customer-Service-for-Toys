from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from channel_agent.control_v2 import AgentAssistantSnapshot
from channel_engine.customer_assistant import (
    AIReplyPackage,
    CustomerAssistantRuntime,
    CustomerContext,
    OfflineReplyControlStore,
    PreparationState,
    ReplyControlOutcome,
)

from .control_store import AgentControlStore


@dataclass(frozen=True, slots=True)
class AssistantProjectionReconciliation:
    durable_replies: int = 0
    decisions_repaired: int = 0
    snapshots_rebuilt: int = 0
    unchanged: int = 0
    unroutable: int = 0


def build_assistant_snapshot(
    package: AIReplyPackage,
    outcome: ReplyControlOutcome | None,
    *,
    agent_id: str,
    device_id: str,
    trace_id: str,
    now: datetime,
) -> AgentAssistantSnapshot:
    """Build the UI projection exclusively from durable upstream facts."""

    prepared = bool(
        outcome is not None
        and outcome.preparation is not None
        and outcome.preparation.state is PreparationState.READY
    )
    status = package.state
    if prepared:
        status = "EXECUTION_PREPARED"
    elif outcome is not None and outcome.quality.status.value == "BLOCKED":
        status = "MANUAL_INTERVENTION"
    preparation = outcome.preparation if prepared and outcome is not None else None
    return AgentAssistantSnapshot(
        agent_id=agent_id,
        device_id=device_id,
        store_id=package.store_id,
        conversation_id=package.conversation_id,
        revision=1,
        status=status,
        turn_id=package.turn_id,
        decision_id=package.decision_id,
        request_id=package.request_id,
        customer_reference=package.customer_reference,
        current_question=package.customer_question,
        action=package.action,
        reply_content=package.reply_content,
        risk_level=package.risk_level.value,
        ai_cs_action=getattr(package, "ai_cs_action", "UNKNOWN"),
        warnings=getattr(package, "warnings", ()),
        required_fields=getattr(package, "required_fields", ()),
        policy_mode=outcome.policy.mode.value if outcome is not None else "MANUAL_CONFIRM",
        quality_status=outcome.quality.status.value if outcome is not None else "PASS",
        preparation_id=preparation.preparation_id if preparation is not None else None,
        trace_id=trace_id,
        processing_stage=(
            "EXECUTION_PREPARED" if prepared else "WAITING_CONFIRMATION"
        ),
        safety={
            "manual_approval_required": not prepared,
            "auto_reply": bool(
                preparation is not None
                and preparation.authorization_kind.value == "AUTO_POLICY"
            ),
            "execution_prepared": prepared,
            "preparation_count": 1 if prepared else 0,
        },
        citations=tuple(citation.model_dump(mode="json") for citation in package.citations),
        updated_at=now.astimezone(UTC),
        expires_at=now.astimezone(UTC) + timedelta(minutes=30),
    )


class AssistantProjectionReconciler:
    """Repair Buffer -> Decision -> Assistant Snapshot projections idempotently."""

    def __init__(
        self,
        store: AgentControlStore,
        assistant: CustomerAssistantRuntime,
        offline_control: OfflineReplyControlStore,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._assistant = assistant
        self._offline_control = offline_control
        self._clock = clock

    def reconcile(self) -> AssistantProjectionReconciliation:
        durable = repaired = rebuilt = unchanged = unroutable = 0
        for context, package in self._assistant.stored_replies():
            durable += 1
            scope = self._store.assistant_scope_for_conversation(
                package.store_id, package.conversation_id
            )
            if scope is None:
                unroutable += 1
                continue
            trace_id = self._trace_id(context, package)
            outcome = self._offline_control.reply_outcome(package.decision_id)
            if outcome is None:
                outcome = self._offline_control.register_reply(
                    context, package, trace_id=trace_id
                )
                repaired += 1
            expected = build_assistant_snapshot(
                package,
                outcome,
                agent_id=scope[0],
                device_id=scope[1],
                trace_id=trace_id,
                now=self._clock(),
            )
            current = self._store.stored_assistant_snapshot(
                scope[0],
                scope[1],
                store_id=package.store_id,
                conversation_id=package.conversation_id,
            )
            if current is not None and _projection_facts(current) == _projection_facts(expected):
                unchanged += 1
                continue
            self._store.persist_assistant_snapshot(expected)
            rebuilt += 1
        return AssistantProjectionReconciliation(
            durable_replies=durable,
            decisions_repaired=repaired,
            snapshots_rebuilt=rebuilt,
            unchanged=unchanged,
            unroutable=unroutable,
        )

    def _trace_id(self, context: CustomerContext, package: AIReplyPackage) -> str:
        raw = self._store.latest_observation_payload(
            package.store_id, package.conversation_id
        ) or {}
        value = raw.get("trace_id")
        if isinstance(value, str) and value.startswith("trace:"):
            return value
        source = f"{package.store_id}\0{package.conversation_id}\0{context.context_id}"
        digest = hashlib.sha256(source.encode()).hexdigest()
        return f"trace:{digest}"


def _projection_facts(value: AgentAssistantSnapshot) -> dict[str, object]:
    payload = value.model_dump(mode="json")
    for key in ("revision", "updated_at", "expires_at"):
        payload.pop(key, None)
    return payload


__all__ = [
    "AssistantProjectionReconciler",
    "AssistantProjectionReconciliation",
    "build_assistant_snapshot",
]
